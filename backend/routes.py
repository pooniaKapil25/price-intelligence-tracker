
"""API routes for product management and price tracking."""

import requests

from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Product, PriceHistory
from backend.schemas import (
    ProductCreate,
    ProductRead,
    PriceHistoryRead,
    PriceCheckRequest,
    DemoPriceRead,
)

from backend.services.demo_fetcher import DemoPriceFetcher
from backend.services.product_relevance import assess_product_category
from backend.services.rewalto_client import RewaltoError, search_products

router = APIRouter(prefix="/products", tags=["products"])

DatabaseSession = Annotated[Session, Depends(get_db)]
SUPPORTED_RETAILERS = {"blinkit", "zepto", "instamart", "bigbasket"}


# ==========================================
# External product search using Rewalto
# ==========================================

@router.get("/external-search")
def external_product_search(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    refined_query: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    retailer: Annotated[str, Query(pattern=r"^[a-z0-9_]{2,40}$")] = "blinkit",
    pincode: Annotated[str | None, Query(pattern=r"^[1-9][0-9]{5}$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 5,
    brand: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    mode: Annotated[str, Query(pattern=r"^(words|semantic)$")] = "words",
):
    """Search external product listings through Rewalto."""

    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Search query cannot be blank.")
    search_query = refined_query.strip() if refined_query is not None else query
    if not search_query:
        raise HTTPException(status_code=422, detail="Refined query cannot be blank.")
    brand_filter = brand.strip() if brand is not None else None
    if brand is not None and not brand_filter:
        raise HTTPException(status_code=422, detail="Exact brand cannot be blank.")
    if retailer not in SUPPORTED_RETAILERS:
        supported = ", ".join(sorted(SUPPORTED_RETAILERS))
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported retailer. Choose one of: {supported}.",
        )

    try:
        result = search_products(
            query=search_query,
            retailer=retailer,
            pincode=pincode,
            limit=limit,
            brand=brand_filter,
            mode=mode,
        )
        products = []

        for item in result.get("data", []):
            latest = item.get("latest")
            if not isinstance(latest, dict):
                latest = {}
            price_minor = latest.get("priceMinor")
            valid_price = (
                latest.get("state") == "priced"
                and latest.get("currency") == "INR"
                and isinstance(price_minor, int)
                and not isinstance(price_minor, bool)
                and price_minor > 0
            )

            category_status, category_reason = assess_product_category(
                search_query,
                item.get("title"),
                brand_filter=brand_filter,
                category_tag=item.get("categoryTag"),
            )
            match = item.get("match")
            match_kind = match.get("kind") if isinstance(match, dict) else None
            identity_fields_present = all((item.get("productId"), item.get("brand"), item.get("packSizeRaw")))
            match_supports_verification = (
                match_kind in {"exact_id", "phrase", "words"}
            ) if isinstance(match, dict) else False
            if category_status == "irrelevant":
                relevance_status = "irrelevant"
                relevance_reason = category_reason
            elif category_status != "verified":
                relevance_status = "unverified"
                relevance_reason = category_reason
            elif identity_fields_present and match_supports_verification:
                relevance_status = "verified"
                relevance_reason = None
            else:
                relevance_status = "unverified"
                relevance_reason = "Rewalto match metadata or canonical product identity is incomplete."

            products.append({
                "listing_id": item.get("id"),
                "product_id": item.get("productId"),
                "retailer_sku": item.get("retailerSku"),
                "title": item.get("title"),
                "brand": item.get("brand"),
                # Rewalto's current listing contract does not define a variant
                # field. Preserve one only when a response actually includes it.
                "variant": item.get("variant"),
                "match": match,
                "similarity": item.get("similarity"),
                "category_tag": item.get("categoryTag"),
                "relevance_status": relevance_status,
                "relevance_reason": relevance_reason,
                "retailer": item.get("retailer"),
                "pack_size": item.get("packSizeRaw"),
                "image_url": item.get("imageUrl"),
                "price": price_minor / 100 if valid_price else None,
                "currency": latest.get("currency"),
                "price_status": latest.get("state"),
                "pincode": latest.get("pincode"),
                "observed_at": latest.get("observedAt"),
                "in_stock": latest.get("inStock"),
            })

        return {
            "data": products,
            "original_query": query,
            "searched_query": search_query,
            "brand_filter": brand_filter,
            "mode": mode,
            "page": result.get("page"),
            "meta": result.get("meta"),
        }

    except RewaltoError as error:
        messages = {
            "missing_configuration": (
                503,
                "Rewalto configuration is missing. Set REWALTO_API_KEY for the backend and restart it.",
            ),
            "authentication": (
                503,
                "Rewalto authentication failed. Check that the configured API key is current.",
            ),
            "credits_exhausted": (
                503,
                "Rewalto credits are exhausted. Check the Rewalto account before retrying.",
            ),
            "permission_denied": (
                503,
                "The Rewalto API key lacks permission for product search.",
            ),
            "rate_limited": (
                429,
                "Rewalto rate limit reached. Wait before retrying.",
            ),
        }
        if error.code == "unavailable":
            detail = (
                "Rewalto semantic search is unavailable on this deployment. Select word search or try again later."
                if mode == "semantic"
                else "Rewalto product search is temporarily unavailable. Try again later."
            )
            messages["unavailable"] = (503, detail)
        code, detail = messages.get(
            error.code,
            (502, "Rewalto could not complete the product search. Try again later."),
        )
        headers = {"Retry-After": error.retry_after} if error.retry_after else None
        raise HTTPException(status_code=code, detail=detail, headers=headers) from error

    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="Rewalto product search failed.",
        ) from error


# ==========================================
# Create product
# ==========================================

@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(product_data: ProductCreate, db: DatabaseSession) -> Product:
    """Create product and save initial price history."""

    product = Product(
        name=product_data.name,
        product_url=str(product_data.product_url),
        current_price=product_data.current_price,
    )

    try:
        db.add(product)
        db.flush()

        history = PriceHistory(
            product_id=product.id,
            price=product.current_price,
        )

        db.add(history)
        db.commit()
        db.refresh(product)

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create product.",
        ) from exc

    return product


# ==========================================
# Get all products
# ==========================================

@router.get("", response_model=list[ProductRead])
def get_products(db: DatabaseSession) -> list[Product]:
    """Get all products."""

    return db.query(Product).all()


# ==========================================
# Get one product
# ==========================================

@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: Annotated[int, Path(gt=0)],
    db: DatabaseSession,
) -> Product:
    """Get one product."""

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    return product


# ==========================================
# Manual price check
# ==========================================

@router.post("/{product_id}/check", response_model=PriceHistoryRead)
def check_product_price(
    product_id: Annotated[int, Path(gt=0)],
    price_data: PriceCheckRequest,
    db: DatabaseSession,
) -> PriceHistory:
    """Update current price and save a historical price record."""

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    try:
        product.current_price = price_data.current_price

        history = PriceHistory(
            product_id=product.id,
            price=price_data.current_price,
            checked_at=datetime.now(timezone.utc),
        )

        db.add(history)
        db.commit()
        db.refresh(history)

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Price check failed.",
        ) from exc

    return history


# ==========================================
# Automatic demo price check
# ==========================================

@router.post("/{product_id}/auto-check", response_model=DemoPriceRead)
def automatic_price_check(
    product_id: Annotated[int, Path(gt=0)],
    db: DatabaseSession,
) -> DemoPriceRead:
    """Return a simulated sample without changing the product or its history."""

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    fetcher = DemoPriceFetcher()
    result = fetcher.fetch_price(product.product_url)

    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error or "Could not fetch product price.",
        )

    return DemoPriceRead(
        source=result.source,
        simulated=True,
        price=result.price,
        message="Simulated sample only; the tracked product and real price history were not changed.",
    )


# ==========================================
# Get price history
# ==========================================

@router.get("/{product_id}/history", response_model=list[PriceHistoryRead])
def get_price_history(
    product_id: Annotated[int, Path(gt=0)],
    db: DatabaseSession,
) -> list[PriceHistory]:
    """Get historical prices for a product."""

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    return (
        db.query(PriceHistory)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.checked_at.asc())
        .all()
    )


# ==========================================
# Delete product
# ==========================================

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: Annotated[int, Path(gt=0)],
    db: DatabaseSession,
) -> Response:
    """Delete product and its price history."""

    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    try:
        db.delete(product)
        db.commit()

    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not delete product.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
