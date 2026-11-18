"""Conservative category checks for external product-search results."""

import re
from typing import Any


MILK_BEVERAGE_CUES = {
    "taaza",
    "toned",
    "skimmed",
    "full cream",
    "double toned",
    "uht",
    "pasteurised",
    "pasteurized",
    "homogenised",
    "homogenized",
    "fresh milk",
    "cow milk",
    "buffalo milk",
}
MILK_CONFLICT_CUES = {
    "milk cake",
    "peda",
    "honey",
    "gift",
    "mithai",
    "confectionery",
}
PACK_OR_GENERIC_TERMS = {
    "a", "an", "the", "and", "of", "for", "with", "pack", "of",
    "ml", "l", "ltr", "litre", "liter", "g", "gm", "gram", "kg",
}


def _words(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _category_text(value: Any) -> str:
    """Flatten only supplied category-tag values; never infer a tag."""
    if isinstance(value, dict):
        return " ".join(_category_text(part) for part in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_category_text(part) for part in value)
    if isinstance(value, str):
        return value.lower()
    return ""


def assess_product_category(
    query: str,
    title: str | None,
    *,
    brand_filter: str | None = None,
    category_tag: Any = None,
) -> tuple[str, str | None]:
    """Return verified, irrelevant, or unverified based on category evidence.

    Brand filters, Rewalto match kinds, and semantic similarity are deliberately
    not used as category evidence. A milk listing must name milk as a drink and
    include a beverage cue; clear sweets, honey, and gift listings are rejected.
    """
    title_text = (title or "").lower()
    tag_text = _category_text(category_tag)
    combined_text = f"{title_text} {tag_text}"
    query_words = _words(query)
    brand_words = _words(brand_filter)
    product_words = {
        word for word in query_words - brand_words - PACK_OR_GENERIC_TERMS
        if not any(character.isdigit() for character in word)
    }
    if not product_words:
        return "unverified", "The search does not identify a product category to verify."

    if "milk" in product_words:
        # These are explicit, distinct product classes in the title or supplied
        # category tag, rather than evidence inferred from brand or similarity.
        for cue in MILK_CONFLICT_CUES:
            cue_words = _words(cue)
            if cue in combined_text or cue_words.issubset(_words(combined_text)):
                return "irrelevant", f"The listing is categorized as {cue}, not drinking milk."

        if "milk" not in _words(title_text):
            return "unverified", "The listing title does not establish that this is a milk product."

        beverage_cue_present = any(
            cue in combined_text
            or _words(cue).issubset(_words(combined_text))
            for cue in MILK_BEVERAGE_CUES
        )
        if beverage_cue_present:
            return "verified", None
        return "unverified", "The listing identifies milk but does not establish that it is drinking milk."

    # For other explicitly searched product types, require the product words
    # themselves to appear in the title. Match metadata alone is insufficient.
    if product_words.issubset(_words(title_text)):
        return "verified", None
    if product_words.isdisjoint(_words(title_text)):
        return "unverified", "The listing title does not establish the searched product category."
    return "unverified", "The listing only partially matches the searched product category."
