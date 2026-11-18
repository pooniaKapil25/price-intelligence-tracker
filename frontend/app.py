
"""Price Intelligence Tracker — Streamlit dashboard."""

import math
import sys
from pathlib import Path

# Streamlit may put the script directory (frontend/) on sys.path without the
# project root. Add the root derived from this file so shared project packages
# such as backend and frontend are importable when launched from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
import streamlit as st

from backend.config import settings
from frontend.comparison import get_display_price, normalize_pin, prepare_comparison_groups
from frontend.demo_comparison import calculate_demo_summary, get_demo_listings

st.set_page_config(
    page_title="Price Intelligence Tracker",
    page_icon="📈",
    layout="wide",
)

API_URL = settings.backend_api_url.rstrip("/")


def api_error_message(error: requests.RequestException, fallback: str) -> str:
    """Show a safe API detail when available; never echo arbitrary response bodies."""
    response = getattr(error, "response", None)
    if response is not None:
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if isinstance(detail, str) and detail:
            return detail
    return fallback

st.title("📈 Price Intelligence Tracker")
st.caption("Track products, compare retailer prices and monitor price history.")


# ==========================================
# LOAD TRACKED PRODUCTS
# ==========================================

try:
    response = requests.get(
        f"{API_URL}/products",
        timeout=10,
    )
    response.raise_for_status()
    products = response.json()

except requests.RequestException as error:
    st.error(
        api_error_message(
            error,
            "Cannot connect to the backend. Make sure FastAPI is running.",
        )
    )
    st.stop()


# ==========================================
# DASHBOARD SUMMARY
# ==========================================

col1, col2 = st.columns(2)

col1.metric("Tracked products", len(products))

known_prices = [
    product["current_price"]
    for product in products
    if product.get("current_price") is not None
]
col2.metric(
    "Known tracked value",
    f"₹{sum(known_prices):,.2f}" if known_prices else "Not available",
)

st.divider()


# ==========================================
# MULTI-RETAILER PRODUCT SEARCH
# ==========================================

st.header("🔎 Search Products Across Retailers")

st.caption(
    "Search product listings and compare fresh prices only when Rewalto "
    "confirms the same product, PIN and in-stock availability."
)

with st.form("rewalto_search_form"):

    search_query = st.text_input(
        "Product name",
        placeholder="Example: Amul butter",
    )

    refined_query = st.text_input(
        "More specific query (optional)",
        placeholder="Example: Amul toned milk 1 L",
        help="Leave blank to search the product name above. If supplied, both queries are shown in the results.",
    )

    exact_brand = st.text_input(
        "Exact brand filter (optional)",
        placeholder="Example: Amul",
        help="Rewalto applies an exact, case-sensitive brand match.",
    )

    search_mode = st.selectbox(
        "Search mode",
        ["words", "semantic"],
        help="Word search is the default. Semantic search may be unavailable on this Rewalto deployment.",
    )

    retailers = st.multiselect(
        "Select retailers to compare",
        ["blinkit", "zepto", "instamart", "bigbasket"],
        default=["blinkit"],
    )

    pincode = st.text_input(
        "Delivery PIN code",
        value="121006",
        max_chars=6,
    )

    search_limit = st.selectbox(
        "Maximum results per retailer",
        [5, 10, 20],
        index=0,
    )

    search_submitted = st.form_submit_button(
        "🔍 Compare Prices"
    )


# ==========================================
# EXECUTE SEARCH
# ==========================================

if search_submitted:

    if not search_query.strip():

        st.warning("Enter a product name first.")

    elif pincode and normalize_pin(pincode) is None:

        st.warning("Enter a valid PIN code with six digits, starting from 1–9.")

    elif not retailers:

        st.warning("Select at least one retailer.")

    else:

        try:
            all_products = []
            total_credits = 0
            successful_retailers = []
            failed_retailers = []
            retailer_errors = []

            with st.spinner("Searching selected retailers..."):

                for selected_retailer in retailers:

                    search_params = {
                        "q": search_query.strip(),
                        "retailer": selected_retailer,
                        "limit": search_limit,
                    }

                    if refined_query.strip():
                        search_params["refined_query"] = refined_query.strip()
                    if exact_brand.strip():
                        search_params["brand"] = exact_brand.strip()
                    if search_mode != "words":
                        search_params["mode"] = search_mode

                    if pincode:
                        search_params["pincode"] = pincode

                    try:
                        search_response = requests.get(
                            f"{API_URL}/products/external-search",
                            params=search_params,
                            timeout=40,
                        )

                        search_response.raise_for_status()

                        retailer_result = search_response.json()

                        all_products.extend(
                            retailer_result.get("data", [])
                        )

                        credits = (
                        (retailer_result.get("meta") or {})
                            .get("credits", {})
                        )

                        total_credits += credits.get("charged", 0)

                        successful_retailers.append(
                            selected_retailer
                        )

                    except requests.RequestException as error:
                        failed_retailers.append(
                            selected_retailer
                        )
                        retailer_errors.append(
                            f"{selected_retailer.title()}: "
                            + api_error_message(error, "request failed")
                        )

            st.session_state["rewalto_results"] = {
                "data": all_products,
                "meta": {
                    "credits": {
                        "charged": total_credits
                    }
                },
                "successful_retailers": successful_retailers,
                "failed_retailers": failed_retailers,
                "retailer_errors": retailer_errors,
                "requested_pincode": pincode or None,
                "searched_query": refined_query.strip() or search_query.strip(),
                "brand_filter": exact_brand.strip() or None,
                "mode": search_mode,
            }

            st.session_state["rewalto_query"] = (
                search_query.strip()
            )

        except Exception:
            st.error("Search failed unexpectedly. Please try again.")


# ==========================================
# DISPLAY SEARCH RESULTS
# ==========================================

if "rewalto_results" in st.session_state:

    search_result = st.session_state["rewalto_results"]

    external_products = search_result.get("data", [])

    requested_pincode = search_result.get(
        "requested_pincode"
    )

    st.subheader(
        f"Search results: {st.session_state['rewalto_query']}"
    )
    searched_query = search_result.get("searched_query", st.session_state["rewalto_query"])
    if searched_query != st.session_state["rewalto_query"]:
        st.caption(f"More specific query sent to Rewalto: {searched_query}")
    if search_result.get("brand_filter"):
        st.caption(f"Exact brand filter: {search_result['brand_filter']}")
    st.caption(f"Search mode: {search_result.get('mode', 'words')}")

    successful = search_result.get(
        "successful_retailers", []
    )

    failed = search_result.get(
        "failed_retailers", []
    )

    if successful:
        st.caption(
            "Successfully searched: "
            + ", ".join(name.title() for name in successful)
        )

    if failed:
        st.warning(
            "Search failed for: "
            + ", ".join(name.title() for name in failed)
        )
        for message in search_result.get("retailer_errors", []):
            st.caption(message)

    st.write(f"Found {len(external_products)} listings.")

    # ======================================
    # VERIFIED PRICE COMPARISON
    # ======================================

    st.subheader("💰 Verified Price Comparison")

    comparison_groups = prepare_comparison_groups(
        external_products,
        requested_pincode=requested_pincode,
    )

    if comparison_groups:

        for group in comparison_groups:

            lowest = min(
                group,
                key=lambda item: item["comparison_price"],
            )

            highest = max(
                group,
                key=lambda item: item["comparison_price"],
            )

            savings = (
                highest["comparison_price"]
                - lowest["comparison_price"]
            )

            st.success(
                f"Lowest price: ₹{lowest['comparison_price']:.2f} "
                f"at {lowest['retailer'].title()}"
            )

            st.caption(
                f"{lowest['title']} | "
                f"{lowest['pack_size']} | "
                f"PIN: {lowest['pincode']}"
            )

            if savings > 0:
                st.caption(
                    f"Difference between highest and lowest: "
                    f"₹{savings:.2f}"
                )

            comparison_rows = []

            for item in sorted(
                group,
                key=lambda x: x["comparison_price"],
            ):

                comparison_rows.append({
                    "Retailer": item["retailer"].title(),
                    "Product": item["title"],
                    "Pack size": item["pack_size"],
                    "Price (₹)": item["comparison_price"],
                    "PIN": item["pincode"],
                    "Observed at": item["observed_at"],
                })

            comparison_df = pd.DataFrame(comparison_rows)

            st.dataframe(
                comparison_df,
                width="stretch",
                hide_index=True,
            )

    else:

        st.info(
            "No verified cross-retailer comparison is available yet. "
            "Listings need the same canonical product ID, brand, variant, "
            "pack size and PIN, a fresh INR price, and confirmed in-stock status."
        )

    # ======================================
    # ALL EXTERNAL PRODUCT LISTINGS
    # ======================================

    st.subheader("📦 External Product Listings")

    if not external_products:

        st.info(
            "Rewalto returned no listings for this query and its selected filters. "
            "Data coverage varies; an empty result does not confirm that the "
            "product is unavailable. No price comparison can be calculated."
        )

    else:

        for item in external_products:

            with st.container(border=True):

                image_col, details_col = st.columns([1, 3])

                with image_col:

                    image_url = item.get("image_url")

                    if (
                        isinstance(image_url, str)
                        and image_url.startswith(
                            ("http://", "https://")
                        )
                    ):

                        try:
                            st.image(
                                image_url,
                                width=150,
                            )

                        except Exception:
                            st.caption("Image unavailable")

                    else:
                        st.caption("Image unavailable")

                with details_col:

                    relevance_status = item.get("relevance_status", "unverified")
                    if relevance_status == "irrelevant":
                        st.warning(item.get("relevance_reason") or "This listing does not match the requested product category.")
                    elif relevance_status == "unverified":
                        st.caption(item.get("relevance_reason") or "Unverified search result; excluded from price comparisons.")
                    else:
                        st.caption("Rewalto match metadata and identity fields are available for comparison checks.")

                    st.write(
                        f"**{item.get('title') or 'Unknown product'}**"
                    )

                    st.caption(
                        f"Brand: {item.get('brand') or 'Unknown'}"
                        f" | Pack: {item.get('pack_size') or 'Unknown'}"
                    )

                    retailer_name = (
                        item.get("retailer") or "Unknown"
                    )

                    st.caption(
                        f"Retailer: {retailer_name.title()}"
                    )

                    display_price, price_problem = get_display_price(
                        item,
                        requested_pincode=requested_pincode,
                    )

                    if display_price is not None:

                        stock = item.get("in_stock")
                        if stock is True:
                            price_label = "Fresh price (in stock)"
                        elif stock is False:
                            price_label = "Reported price (out of stock)"
                        else:
                            price_label = "Fresh price (stock unknown)"

                        st.metric(
                            price_label,
                            f"₹{display_price:,.2f}",
                        )

                    else:
                        st.info(price_problem or "No usable price is available.")

                    metadata = []

                    if item.get("pincode"):
                        metadata.append(
                            f"PIN: {item['pincode']}"
                        )

                    if item.get("observed_at"):
                        metadata.append(
                            f"Observed: {item['observed_at']}"
                        )

                    if item.get("in_stock") is True:
                        metadata.append("In stock")

                    elif item.get("in_stock") is False:
                        metadata.append("Out of stock")

                    if metadata:
                        st.caption(" | ".join(metadata))

    # Credit usage.
    credits = (
        (search_result.get("meta") or {})
        .get("credits", {})
    )

    st.caption(
        f"Rewalto credits charged: "
        f"{credits.get('charged', 0)}"
    )

st.divider()

# ==========================================
# SIMULATED DEMO COMPARISON
# ==========================================

st.subheader("Demo Price Comparison")
st.warning("SIMULATED DEMO DATA — NOT LIVE RETAILER PRICES")
demo_listings = get_demo_listings()
demo_summary = calculate_demo_summary(demo_listings)

lowest_col, highest_col, savings_col = st.columns(3)
lowest_col.metric(
    "Lowest price",
    f"₹{demo_summary['lowest_price']:.2f}",
    demo_summary["lowest_retailer"],
)
highest_col.metric("Highest price", f"₹{demo_summary['highest_price']:.2f}")
savings_col.metric("Savings", f"₹{demo_summary['savings']:.2f}")

demo_df = pd.DataFrame([
    {
        "Retailer": item["retailer"],
        "Product": item["product"],
        "Price (₹)": item["price"],
        "Currency": item["currency"],
        "PIN": item["pincode"],
        "Availability": item["availability"],
        "Observed at": item["observed_at"],
        "Data type": item["source"],
    }
    for item in demo_listings
])
lowest_price = demo_summary["lowest_price"]
st.dataframe(
    demo_df.style.apply(
        lambda row: [
            "background-color: #d9f2dd; font-weight: bold"
            if row["Price (₹)"] == lowest_price else ""
            for _ in row
        ],
        axis=1,
    ),
    width="stretch",
    hide_index=True,
)
st.caption(
    "This fixed sample is displayed locally only. It is separate from live "
    "Rewalto results and is never saved to tracked products or price history."
)

st.divider()


# ==========================================
# ADD A PRODUCT
# ==========================================

st.subheader("➕ Add a product")

with st.form("add_product_form"):

    name = st.text_input("Product name")

    product_url = st.text_input("Product URL")

    initial_price_text = st.text_input(
        "Initial price (₹; required)",
        placeholder="For example, 299.00",
    )

    submitted = st.form_submit_button("Add product")

    if submitted:

        if not name.strip() or not product_url.strip():

            st.warning("Enter both product name and URL.")

        else:

            try:
                if not initial_price_text.strip():
                    raise ValueError("Enter a positive initial price to track this product.")
                initial_price = float(initial_price_text)
                if not math.isfinite(initial_price) or initial_price <= 0:
                    raise ValueError("Initial price must be a finite amount greater than zero.")

                result = requests.post(
                    f"{API_URL}/products",
                    json={
                        "name": name,
                        "product_url": product_url,
                        "current_price": initial_price,
                    },
                    timeout=10,
                )

                result.raise_for_status()

                st.success("Product added successfully!")
                st.rerun()

            except ValueError as error:
                st.warning(str(error))

            except requests.RequestException as error:
                st.error(api_error_message(error, "Could not add product."))

st.divider()


# ==========================================
# TRACKED PRODUCTS
# ==========================================

st.subheader("📦 Your products")

if not products:

    st.info(
        "No products tracked yet. Add your first product above."
    )

else:

    for product in products:

        with st.container(border=True):

            st.write(f"**{product['name']}**")

            current_price = product.get("current_price")
            if current_price is None:
                st.write("Current price: Unknown — add a confirmed price to start tracking.")
            else:
                st.write(f"Current price: ₹{current_price:,.2f}")

            # Price analytics.
            try:
                history_response = requests.get(
                    f"{API_URL}/products/{product['id']}/history",
                    timeout=10,
                )

                history_response.raise_for_status()

                history = history_response.json()

                if history:

                    prices = [
                        item["price"]
                        for item in history
                        if item.get("price") is not None and item["price"] > 0
                    ]

                    if not prices:
                        st.info("No confirmed price observations yet.")
                        prices = []

                    if prices:
                        lowest_price = min(prices)
                        first_price = prices[0]
                        latest_recorded_price = prices[-1]

                        price_change = latest_recorded_price - first_price

                        percentage_change = (price_change / first_price) * 100

                        col1, col2, col3 = st.columns(3)

                        col1.metric(
                            "Lowest price",
                            f"₹{lowest_price:,.2f}",
                        )

                        col2.metric(
                            "Recorded price change",
                            f"₹{price_change:,.2f}",
                            f"{percentage_change:.2f}%",
                            delta_color="inverse",
                        )

                        col3.metric(
                            "Price records",
                            len(prices),
                        )

            except requests.RequestException as error:
                st.warning(api_error_message(error, "Price analytics unavailable."))

            st.caption(product["product_url"])

            # Delete product.
            if st.button(
                "🗑️ Delete product",
                key=f"delete_{product['id']}",
            ):

                try:
                    result = requests.delete(
                        f"{API_URL}/products/{product['id']}",
                        timeout=10,
                    )

                    result.raise_for_status()

                    st.success("Product deleted successfully!")
                    st.rerun()

                except requests.RequestException as error:
                    st.error(api_error_message(error, "Could not delete product."))

            # Automatic demo price check.
            if st.button(
                "🎭 Simulate demo price (not saved)",
                key=f"auto_check_{product['id']}",
            ):

                try:
                    result = requests.post(
                        f"{API_URL}/products/{product['id']}/auto-check",
                        timeout=10,
                    )

                    result.raise_for_status()

                    demo_result = result.json()
                    st.info(
                        f"SIMULATED DEMO ONLY: ₹{demo_result['price']:,.2f}. "
                        f"{demo_result['message']}"
                    )

                except requests.RequestException as error:
                    st.error(
                        api_error_message(error, "Automatic price check failed.")
                    )

            # Manual price check.
            with st.expander("Check latest price"):

                with st.form(f"check_{product['id']}"):

                    new_price = st.number_input(
                        "Enter latest price (₹)",
                        min_value=0.01,
                        value=max(float(current_price or 0.01), 0.01),
                        step=1.0,
                        key=f"price_{product['id']}",
                    )

                    check_submitted = st.form_submit_button(
                        "Save price check"
                    )

                    if check_submitted:

                        try:
                            result = requests.post(
                                f"{API_URL}/products/{product['id']}/check",
                                json={
                                    "current_price": new_price
                                },
                                timeout=10,
                            )

                            result.raise_for_status()

                            st.success("Price history updated!")
                            st.rerun()

                        except requests.RequestException as error:
                            st.error(
                                api_error_message(error, "Price check failed.")
                            )

            # View price history.
            with st.expander("View price history"):

                try:
                    history_response = requests.get(
                        f"{API_URL}/products/{product['id']}/history",
                        timeout=10,
                    )

                    history_response.raise_for_status()

                    history = history_response.json()

                    if history:

                        history_df = pd.DataFrame(history)

                        history_df["checked_at"] = pd.to_datetime(
                            history_df["checked_at"]
                        )

                        history_df = history_df.sort_values(
                            "checked_at"
                        )

                        st.line_chart(
                            history_df.set_index("checked_at")["price"]
                        )

                        st.dataframe(
                            history_df[["checked_at", "price"]],
                            width="stretch",
                        )

                    else:

                        st.info("No price history available.")

                except requests.RequestException as error:
                    st.error(api_error_message(error, "Could not load history."))
