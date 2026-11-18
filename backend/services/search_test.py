"""Explicit, operator-run Rewalto search; safe to import during pytest collection."""

from backend.services.rewalto_client import search_products


def main() -> None:
    try:
        result = search_products(
            query="amul butter",
            retailer="blinkit",
            pincode=None,
            limit=5,
        )
        listings = result.get("data", []) if isinstance(result, dict) else []
        print(f"Rewalto search succeeded ({len(listings)} listings).")
    except Exception as error:
        print(f"Rewalto search failed ({type(error).__name__}).")


if __name__ == "__main__":
    main()
