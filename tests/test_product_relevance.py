from backend.services.product_relevance import assess_product_category


def test_milk_query_rejects_clear_non_milk_categories():
    unrelated_titles = [
        "Milk Cake Amul 500 g",
        "Amul Honey 500 g",
        "Amul Malai Peda",
        "Amul Chocolate Gift Pack",
    ]
    for title in unrelated_titles:
        status, reason = assess_product_category(
            "Amul milk toned", title, brand_filter="Amul"
        )
        assert status == "irrelevant", title
        assert reason


def test_milk_query_requires_positive_drinking_milk_evidence():
    assert assess_product_category(
        "Amul milk toned", "Amul Taaza Toned Milk 1 L", brand_filter="Amul"
    ) == ("verified", None)

    status, reason = assess_product_category(
        "Amul milk", "Amul Milk 1 L", brand_filter="Amul"
    )
    assert status == "unverified"
    assert "drinking milk" in reason


def test_category_tag_can_identify_a_clear_conflict_but_generic_tag_cannot_verify():
    assert assess_product_category(
        "Amul milk",
        "Amul Assorted Pack",
        brand_filter="Amul",
        category_tag={"family": "gift sets"},
    )[0] == "irrelevant"

    assert assess_product_category(
        "Amul milk",
        "Amul Milk 1 L",
        brand_filter="Amul",
        category_tag={"family": "dairy products"},
    )[0] == "unverified"


def test_other_product_category_requires_title_evidence_not_brand_or_match():
    assert assess_product_category(
        "Amul butter", "Amul Salted Butter 500 g", brand_filter="Amul"
    ) == ("verified", None)
    assert assess_product_category(
        "Amul butter", "Amul Honey 500 g", brand_filter="Amul"
    )[0] == "unverified"
