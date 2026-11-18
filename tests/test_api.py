from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import routes
from backend.services.rewalto_client import RewaltoError


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_product_creation_requires_positive_initial_price(client):
    created = client.post("/products", json={
        "name": "Unknown price test item",
        "product_url": "https://example.com/unknown-price-test",
    })
    assert created.status_code == 422
    assert "positive initial price is required" in created.text.lower()

    whitespace_name = client.post("/products", json={
        "name": "   ",
        "product_url": "https://example.com/blank-name-test",
        "current_price": 10,
    })
    assert whitespace_name.status_code == 422

    created = client.post("/products", json={
        "name": "Null price test item",
        "product_url": "https://example.com/null-price-test",
        "current_price": None,
    })
    assert created.status_code == 422


def test_positive_price_product_crud_saves_only_positive_initial_history(client):
    created = client.post("/products", json={
        "name": "  CRUD test item  ",
        "product_url": "https://example.com/crud-test",
        "current_price": 120.0,
    })
    assert created.status_code == 201
    product = created.json()
    assert product["name"] == "CRUD test item"
    assert product["current_price"] == 120.0
    product_id = product["id"]
    listed_products = client.get("/products")
    assert listed_products.status_code == 200
    assert any(item["id"] == product_id for item in listed_products.json())

    history = client.get(f"/products/{product_id}/history")
    assert history.status_code == 200
    assert [item["price"] for item in history.json()] == [120.0]

    assert client.get(f"/products/{product_id}").json()["current_price"] == 120.0
    assert client.delete(f"/products/{product_id}").status_code == 204
    assert client.get(f"/products/{product_id}").status_code == 404


def test_zero_is_rejected_for_product_and_price_observations(client):
    created = client.post("/products", json={
        "name": "Zero price validation item",
        "product_url": "https://example.com/zero-price-test",
        "current_price": 0,
    })
    assert created.status_code == 422

    created = client.post("/products", json={
        "name": "Manual price validation item",
        "product_url": "https://example.com/manual-price-test",
        "current_price": 12.0,
    })
    product_id = created.json()["id"]
    try:
        check = client.post(f"/products/{product_id}/check", json={"current_price": 0})
        assert check.status_code == 422
    finally:
        client.delete(f"/products/{product_id}")


def test_demo_price_is_labeled_and_does_not_change_product_or_history(client):
    created = client.post("/products", json={
        "name": "Demo separation test item",
        "product_url": "https://example.com/demo-test",
        "current_price": 100.0,
    })
    product_id = created.json()["id"]
    try:
        before_history = client.get(f"/products/{product_id}/history").json()
        demo = client.post(f"/products/{product_id}/auto-check")
        assert demo.status_code == 200
        assert demo.json()["simulated"] is True
        assert demo.json()["source"] == "demo"
        assert "not changed" in demo.json()["message"]
        assert client.get(f"/products/{product_id}").json()["current_price"] == 100.0
        assert client.get(f"/products/{product_id}/history").json() == before_history
    finally:
        client.delete(f"/products/{product_id}")


def test_positive_manual_price_check_updates_history(client):
    created = client.post("/products", json={
        "name": "Manual price history test item",
        "product_url": "https://example.com/manual-history-test",
        "current_price": 100.0,
    })
    product_id = created.json()["id"]
    try:
        checked = client.post(
            f"/products/{product_id}/check",
            json={"current_price": 125.5},
        )
        assert checked.status_code == 200
        assert checked.json()["price"] == 125.5
        assert client.get(f"/products/{product_id}").json()["current_price"] == 125.5
        assert [row["price"] for row in client.get(
            f"/products/{product_id}/history"
        ).json()] == [100.0, 125.5]
    finally:
        client.delete(f"/products/{product_id}")


@pytest.mark.parametrize("params", [
    {"q": " "},
    {"q": "x" * 201},
    {"q": "amul", "pincode": "000000"},
    {"q": "amul", "pincode": "12345"},
    {"q": "amul", "retailer": "Bad Retailer"},
    {"q": "amul", "retailer": "unknown"},
    {"q": "amul", "limit": 0},
    {"q": "amul", "limit": 101},
    {"q": "amul", "mode": "guess"},
    {"q": "amul", "brand": " "},
    {"q": "amul", "refined_query": " "},
])
def test_invalid_external_search_arguments_return_422_without_search(params, client, monkeypatch):
    called = False

    def fail_if_called(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("Invalid input must be rejected before Rewalto is called")

    monkeypatch.setattr(routes, "search_products", fail_if_called)
    response = client.get("/products/external-search", params=params)
    assert response.status_code == 422
    assert called is False


def test_external_search_maps_price_and_preserves_canonical_product_id(client, monkeypatch):
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: {
        "data": [{
            "id": "listing-a",
            "productId": "rewalto-product-a",
            "retailerSku": "retailer-sku-a",
            "title": "Amul Butter 500g",
            "brand": "Amul",
            "variant": "Salted",
            "packSizeRaw": "500 g",
            "match": {"kind": "words", "wholeWords": 2, "allWords": True},
            "similarity": 0.92,
            "categoryTag": {"family": "dairy products"},
            "retailer": "blinkit",
            "latest": {
                "priceMinor": 27500,
                "currency": "INR",
                "state": "priced",
                "pincode": "121006",
                "observedAt": datetime.now(timezone.utc).isoformat(),
                "inStock": True,
            },
        }, {
            "id": "listing-b",
            "latest": {
                "priceMinor": 0,
                "currency": "INR",
                "state": "unavailable",
            },
        }],
        "page": {"nextCursor": None},
        "meta": {},
    })
    response = client.get(
        "/products/external-search",
        params={"q": "amul butter", "pincode": "121006"},
    )
    assert response.status_code == 200
    item = response.json()["data"][0]
    assert item["product_id"] == "rewalto-product-a"
    assert item["retailer_sku"] == "retailer-sku-a"
    assert item["variant"] == "Salted"
    assert item["match"] == {"kind": "words", "wholeWords": 2, "allWords": True}
    assert item["similarity"] == 0.92
    assert item["category_tag"] == {"family": "dairy products"}
    assert item["relevance_status"] == "verified"
    assert item["price"] == 275.0
    assert item["currency"] == "INR"
    assert item["price_status"] == "priced"
    assert item["pincode"] == "121006"
    assert item["observed_at"] is not None
    assert item["in_stock"] is True
    assert response.json()["data"][1]["price"] is None


@pytest.mark.parametrize("latest", [
    {"priceMinor": None, "currency": "INR", "state": "priced"},
    {"priceMinor": 0, "currency": "INR", "state": "priced"},
    {"priceMinor": -100, "currency": "INR", "state": "priced"},
    {"priceMinor": 100.5, "currency": "INR", "state": "priced"},
    {"priceMinor": True, "currency": "INR", "state": "priced"},
    {"priceMinor": 100, "currency": "USD", "state": "priced"},
    {"priceMinor": 100, "currency": "INR", "state": "unavailable"},
    {"priceMinor": "100", "currency": "INR", "state": "priced"},
])
def test_invalid_or_unknown_minor_prices_remain_unknown(client, monkeypatch, latest):
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: {
        "data": [{"id": "listing-x", "title": "Sample product", "latest": latest}],
    })
    response = client.get("/products/external-search", params={"q": "sample"})
    assert response.status_code == 200
    assert response.json()["data"][0]["price"] is None


def test_malformed_latest_price_shape_remains_an_unknown_price(client, monkeypatch):
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: {
        "data": [{"id": "listing-x", "title": "Sample product", "latest": []}],
    })
    response = client.get("/products/external-search", params={"q": "sample"})
    assert response.status_code == 200
    assert response.json()["data"][0]["price"] is None


def test_search_forwards_parameters_and_mapped_identity_can_compare(client, monkeypatch):
    observed = datetime.now(timezone.utc).isoformat()
    calls = []

    def fake_search(**kwargs):
        calls.append(kwargs)
        retailer = kwargs["retailer"]
        return {"data": [{
            "id": f"listing-{retailer}",
            "productId": "canonical-coffee-1",
            "retailerSku": f"sku-{retailer}",
            "title": f"Example Coffee 250 g at {retailer}",
            "brand": "Example",
            "variant": "Medium Roast",
            "packSizeRaw": "250 g",
            "match": {"kind": "phrase"},
            "retailer": retailer,
            "latest": {
                "priceMinor": 12999,
                "currency": "INR",
                "state": "priced",
                "pincode": "121006",
                "observedAt": observed,
                "inStock": True,
            },
        }]}

    monkeypatch.setattr(routes, "search_products", fake_search)
    first = client.get("/products/external-search", params={
        "q": "example coffee", "retailer": "blinkit", "pincode": "121006", "limit": 10,
    }).json()["data"][0]
    second = client.get("/products/external-search", params={
        "q": "example coffee", "retailer": "zepto", "pincode": "121006", "limit": 10,
    }).json()["data"][0]

    from frontend.comparison import prepare_comparison_groups

    groups = prepare_comparison_groups([first, second], "121006")
    assert calls[0] == {
        "query": "example coffee", "retailer": "blinkit", "pincode": "121006", "limit": 10,
        "brand": None, "mode": "words",
    }
    assert first["price"] == 129.99
    assert first["product_id"] == second["product_id"] == "canonical-coffee-1"
    assert first["variant"] == second["variant"] == "Medium Roast"
    assert first["relevance_status"] == second["relevance_status"] == "verified"
    assert len(groups) == 1


def test_milk_cake_is_not_presented_as_ordinary_milk(client, monkeypatch):
    observed = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: {
        "data": [{
            "id": "listing-milk-cake",
            "productId": "canonical-milk-cake",
            "title": "Milk Cake Amul 500 g",
            "brand": "Amul",
            "packSizeRaw": "500 g",
            "match": {"kind": "words", "wholeWords": 2},
            "latest": {
                "priceMinor": 13300,
                "currency": "INR",
                "state": "priced",
                "pincode": "121006",
                "observedAt": observed,
                "inStock": True,
            },
        }],
    })
    milk_cake = client.get("/products/external-search", params={"q": "Amul milk"}).json()["data"][0]
    assert milk_cake["relevance_status"] == "irrelevant"
    assert "milk cake" in milk_cake["relevance_reason"].lower()
    ordinary_milk = dict(milk_cake, title="Amul Toned Milk 1 L", product_id="canonical-milk")
    from frontend.comparison import prepare_comparison_groups
    assert prepare_comparison_groups([ordinary_milk, dict(ordinary_milk, retailer="zepto")]) == []
    assert prepare_comparison_groups([milk_cake, dict(milk_cake, retailer="zepto")]) == []


def test_search_preserves_original_query_and_supports_explicit_refinement_and_brand(client, monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: calls.append(kwargs) or {"data": []})
    response = client.get("/products/external-search", params={
        "q": "Amul milk", "refined_query": "Amul toned milk 1 L", "brand": "Amul", "mode": "semantic",
    })
    assert response.status_code == 200
    assert response.json()["original_query"] == "Amul milk"
    assert response.json()["searched_query"] == "Amul toned milk 1 L"
    assert response.json()["brand_filter"] == "Amul"
    assert response.json()["mode"] == "semantic"
    assert calls == [{
        "query": "Amul toned milk 1 L", "retailer": "blinkit", "pincode": None,
        "limit": 5, "brand": "Amul", "mode": "semantic",
    }]


def test_missing_canonical_identity_and_rewalto_match_are_unverified(client, monkeypatch):
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: {"data": [{
        "id": "listing-no-product-id", "title": "Amul Milk 1 L", "brand": "Amul",
        "packSizeRaw": "1 L", "match": {"kind": "words"}, "latest": {},
    }]})
    response = client.get("/products/external-search", params={"q": "Amul milk"})
    item = response.json()["data"][0]
    assert item["relevance_status"] == "unverified"
    assert item["product_id"] is None

    monkeypatch.setattr(routes, "search_products", lambda **kwargs: {"data": [{
        "productId": "canonical-uncertain", "title": "Possibly related item", "brand": "Amul",
        "packSizeRaw": "1 L", "latest": {},
    }]})
    item = client.get("/products/external-search", params={"q": "Amul milk"}).json()["data"][0]
    assert item["relevance_status"] == "unverified"


@pytest.mark.parametrize("error, expected_status, message", [
    (RewaltoError("missing_configuration"), 503, "configuration is missing"),
    (RewaltoError("authentication", 401), 503, "authentication failed"),
    (RewaltoError("credits_exhausted", 402), 503, "credits are exhausted"),
    (RewaltoError("permission_denied", 403), 503, "lacks permission"),
    (RewaltoError("rate_limited", 429, "30"), 429, "rate limit reached"),
    (RewaltoError("upstream_error", 503), 502, "could not complete"),
])
def test_rewalto_failures_are_distinct_and_do_not_leak_configuration(
    client, monkeypatch, error, expected_status, message
):
    sentinel = "do-not-return-test-credential"
    monkeypatch.setattr(routes, "search_products", lambda **kwargs: (_ for _ in ()).throw(error))
    response = client.get("/products/external-search", params={"q": "test"})
    assert response.status_code == expected_status
    assert message in response.json()["detail"].lower()
    assert sentinel not in response.text
    if error.retry_after:
        assert response.headers["retry-after"] == error.retry_after


def test_semantic_unavailable_is_reported_without_silent_word_search_fallback(client, monkeypatch):
    monkeypatch.setattr(
        routes,
        "search_products",
        lambda **kwargs: (_ for _ in ()).throw(RewaltoError("unavailable", 503)),
    )
    response = client.get("/products/external-search", params={"q": "Amul milk", "mode": "semantic"})
    assert response.status_code == 503
    assert "semantic search is unavailable" in response.json()["detail"].lower()


def test_api_search_missing_key_is_handled_without_network(client, monkeypatch):
    from backend.services import rewalto_client

    monkeypatch.setattr(rewalto_client.settings, "rewalto_api_key", None)
    response = client.get("/products/external-search", params={"q": "test"})
    assert response.status_code == 503
    assert "configuration is missing" in response.json()["detail"].lower()


def test_existing_database_schema_and_records_are_not_touched(test_database_path):
    import sqlite3
    from pathlib import Path

    from tests.conftest import (
        ORIGINAL_DATABASE_COLUMNS,
        ORIGINAL_DATABASE_COUNTS,
        PROJECT_ROOT,
    )

    original = Path(PROJECT_ROOT / "price_tracker.db")
    if not original.exists():
        assert ORIGINAL_DATABASE_COUNTS == {}
        assert ORIGINAL_DATABASE_COLUMNS == {}
        return
    connection = sqlite3.connect(f"file:{original}?mode=ro", uri=True)
    try:
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("products", "price_history")
        }
        columns = {
            table: [tuple(row) for row in connection.execute(f'PRAGMA table_info("{table}")')]
            for table in ("products", "price_history")
        }
    finally:
        connection.close()
    assert counts == ORIGINAL_DATABASE_COUNTS
    assert columns == ORIGINAL_DATABASE_COLUMNS
