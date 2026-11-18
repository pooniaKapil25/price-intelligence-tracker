"""Pure helpers for validating Rewalto prices and grouping safe comparisons."""

import math
from datetime import datetime, timedelta, timezone
from typing import Any


PRICE_MAX_AGE_DAYS = 7


def normalize_text(value: Any) -> str:
    """Normalize a product identity component without fuzzy matching."""
    if not value:
        return ""
    normalized = "".join(
        character.lower() if character.isalnum() else " "
        for character in str(value).strip()
    )
    return " ".join(normalized.split())


def normalize_pin(value: Any) -> str | None:
    """Return a valid Indian six-digit PIN as text, preserving leading digits."""
    pin = str(value).strip() if value is not None else ""
    if len(pin) == 6 and pin.isdigit() and pin[0] != "0":
        return pin
    return None


def parse_observation_time(value: Any) -> datetime | None:
    """Parse an ISO timestamp and return it in UTC, or None when unknown."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def get_display_price(
    item: dict[str, Any],
    requested_pincode: str | None = None,
    *,
    now: datetime | None = None,
) -> tuple[float | None, str | None]:
    """Return a usable INR price only when status, time, and location are verified."""
    price = item.get("price")
    if price is None:
        return None, "No price was reported."
    if item.get("currency") != "INR":
        return None, "Price currency is not confirmed as INR."
    if item.get("price_status") != "priced":
        return None, "Price is unavailable from the retailer."
    try:
        price = float(price)
    except (ValueError, TypeError, OverflowError):
        return None, "Price value is invalid."
    if not math.isfinite(price) or price <= 0:
        return None, "Price must be greater than zero."

    pin = normalize_pin(item.get("pincode"))
    if pin is None:
        return None, "Price PIN code is missing or invalid."
    requested_pin = normalize_pin(requested_pincode) if requested_pincode else None
    if requested_pincode and requested_pin is None:
        return None, "Requested PIN code is invalid."
    if requested_pin and pin != requested_pin:
        return None, f"Price is for PIN {pin}, not requested PIN {requested_pin}."

    observed_at = parse_observation_time(item.get("observed_at"))
    if observed_at is None:
        return None, "Price observation time is missing or invalid."
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    if observed_at > current_time:
        return None, "Price observation is in the future."
    if observed_at < current_time - timedelta(days=PRICE_MAX_AGE_DAYS):
        return None, "Price observation is stale (older than 7 days)."

    return price, None


def get_comparison_key(item: dict[str, Any]) -> tuple[str, ...] | None:
    """Require canonical Rewalto identity, brand, and pack size.

    A variant is compared when Rewalto supplies one. Titles are deliberately
    not used as a substitute for product identity or variant data.
    """
    product_id = normalize_text(item.get("product_id"))
    brand = normalize_text(item.get("brand"))
    variant = normalize_text(item.get("variant"))
    pack_size = normalize_text(item.get("pack_size"))
    if not all((product_id, brand, pack_size)):
        return None
    return product_id, brand, variant, pack_size


def prepare_comparison_groups(
    items: list[dict[str, Any]],
    requested_pincode: str | None = None,
    *,
    now: datetime | None = None,
) -> list[list[dict[str, Any]]]:
    """Group the same canonical product at one PIN, using fresh INR in-stock prices."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}

    for item in items:
        if not isinstance(item, dict) or item.get("in_stock") is not True:
            # Unknown availability is not evidence that a listing can be purchased.
            continue
        if item.get("relevance_status") != "verified":
            continue

        price, _reason = get_display_price(item, requested_pincode, now=now)
        if price is None:
            continue

        identity = get_comparison_key(item)
        if identity is None:
            continue

        pin = normalize_pin(item.get("pincode"))
        retailer = normalize_text(item.get("retailer"))
        observed_at = parse_observation_time(item.get("observed_at"))
        if pin is None or not retailer or observed_at is None:
            continue

        key = (*identity, pin)
        candidate = {
            **item,
            "retailer": item["retailer"],
            "comparison_price": price,
            "parsed_observed_at": observed_at,
            "comparison_identity": "rewalto_product_id",
        }
        group = groups.setdefault(key, [])
        existing = next(
            (entry for entry in group if normalize_text(entry.get("retailer")) == retailer),
            None,
        )
        if existing is None:
            group.append(candidate)
        elif observed_at > existing["parsed_observed_at"]:
            group.remove(existing)
            group.append(candidate)

    return [
        group
        for group in groups.values()
        if len({normalize_text(item.get("retailer")) for item in group}) >= 2
    ]
