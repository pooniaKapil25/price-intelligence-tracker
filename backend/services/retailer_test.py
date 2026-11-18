"""Explicit, operator-run Rewalto retailer check; safe to import during pytest collection."""

from backend.services.rewalto_client import get_retailers


def main() -> None:
    try:
        result = get_retailers()
        retailers = result.get("data", []) if isinstance(result, dict) else []
        print(f"Rewalto retailer lookup succeeded ({len(retailers)} records).")
    except Exception as error:
        print(f"Rewalto retailer lookup failed ({type(error).__name__}).")


if __name__ == "__main__":
    main()
