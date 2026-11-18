from datetime import datetime, timedelta, timezone

from frontend.comparison import get_display_price, prepare_comparison_groups


NOW = datetime.now(timezone.utc)


def listing(**overrides):
    item = {
        "listing_id": "listing-1",
        "product_id": "canonical-product-1",
        "title": "Amul Salted Butter 500 g",
        "brand": "Amul",
        "variant": "Salted",
        "pack_size": "500 g",
        "retailer": "blinkit",
        "price": 275.0,
        "currency": "INR",
        "price_status": "priced",
        "pincode": "121006",
        "observed_at": NOW.isoformat(),
        "in_stock": True,
        "relevance_status": "verified",
    }
    item.update(overrides)
    return item


def test_display_price_requires_valid_currency_status_time_and_pin():
    assert get_display_price(listing(), "121006", now=NOW) == (275.0, None)
    assert get_display_price(listing(price=None), "121006", now=NOW)[0] is None
    assert get_display_price(listing(currency="USD"), "121006", now=NOW)[0] is None
    assert get_display_price(listing(price_status="unavailable"), "121006", now=NOW)[0] is None
    assert get_display_price(listing(pincode="110001"), "121006", now=NOW)[0] is None
    assert get_display_price(listing(observed_at=(NOW - timedelta(days=8)).isoformat()), "121006", now=NOW)[0] is None


def test_comparison_requires_same_canonical_identity_pin_and_confirmed_stock():
    same_product_other_retailer = listing(
        listing_id="listing-2",
        retailer="zepto",
        price=260.0,
    )
    assert len(prepare_comparison_groups(
        [listing(), same_product_other_retailer], "121006", now=NOW
    )) == 1

    no_canonical_id = listing(product_id=None, retailer="zepto")
    out_of_stock = listing(retailer="zepto", in_stock=False)
    unknown_stock = listing(retailer="zepto", in_stock=None)
    wrong_pin = listing(retailer="zepto", pincode="110001")
    assert prepare_comparison_groups(
        [listing(), no_canonical_id], "121006", now=NOW
    ) == []
    assert prepare_comparison_groups(
        [listing(), out_of_stock], "121006", now=NOW
    ) == []
    assert prepare_comparison_groups(
        [listing(), unknown_stock], "121006", now=NOW
    ) == []
    assert prepare_comparison_groups(
        [listing(), wrong_pin], "121006", now=NOW
    ) == []


def test_different_canonical_products_do_not_match():
    group = prepare_comparison_groups(
        [listing(), listing(product_id="another-product", retailer="zepto")],
        "121006",
        now=NOW,
    )
    assert group == []


def test_uncertain_or_irrelevant_relevance_is_excluded():
    for status in ("unverified", "irrelevant"):
        assert prepare_comparison_groups(
            [listing(), listing(retailer="zepto", relevance_status=status)],
            "121006",
            now=NOW,
        ) == []


def test_canonical_id_not_title_similarity_proves_product_identity():
    left = listing(variant=None, title="A product sold at Blinkit")
    right = listing(
        variant=None,
        title="A differently named listing at Zepto",
        retailer="zepto",
    )
    assert len(prepare_comparison_groups([left, right], "121006", now=NOW)) == 1

    left["product_id"] = None
    right["product_id"] = None
    assert prepare_comparison_groups([left, right], "121006", now=NOW) == []


def test_brand_variant_and_pack_size_are_required_even_with_canonical_id():
    for changed_identity in (
        {"brand": "Different brand"},
        {"variant": "Unsalted"},
        {"pack_size": "250 g"},
    ):
        group = prepare_comparison_groups(
            [listing(), listing(retailer="zepto", **changed_identity)],
            "121006",
            now=NOW,
        )
        assert group == []
