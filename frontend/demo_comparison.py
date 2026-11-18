"""Fixed simulated comparison data kept separate from live and saved prices."""

from typing import Any


DEMO_PRODUCT = "Amul Taaza Toned Milk, 1 L"
DEMO_PIN = "121006"
DEMO_OBSERVED_AT = "2026-11-18 09:00 IST"
_DEMO_ROWS = (
    ("Blinkit", 65.0),
    ("Zepto", 62.0),
    ("Instamart", 68.0),
)


def get_demo_listings() -> list[dict[str, Any]]:
    """Return fresh copies of the fixed, clearly simulated sample listings."""
    return [
        {
            "retailer": retailer,
            "product": DEMO_PRODUCT,
            "price": price,
            "currency": "INR",
            "pincode": DEMO_PIN,
            "availability": "In stock",
            "observed_at": DEMO_OBSERVED_AT,
            "source": "SIMULATED",
        }
        for retailer, price in _DEMO_ROWS
    ]


def calculate_demo_summary(
    listings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate min, max, and savings without calling persistence code."""
    rows = listings if listings is not None else get_demo_listings()
    if not rows:
        raise ValueError("At least one demo listing is required.")
    lowest = min(rows, key=lambda item: item["price"])
    highest = max(rows, key=lambda item: item["price"])
    return {
        "lowest_price": lowest["price"],
        "lowest_retailer": lowest["retailer"],
        "highest_price": highest["price"],
        "savings": highest["price"] - lowest["price"],
    }
