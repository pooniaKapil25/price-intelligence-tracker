import pytest
from pydantic import SecretStr

from backend.services import rewalto_client
from backend.services.rewalto_client import RewaltoError


class FakeResponse:
    def __init__(self, status_code, *, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self.payload = {"data": []} if payload is None else payload

    def json(self):
        return self.payload


def test_missing_configuration_fails_before_http(monkeypatch):
    monkeypatch.setattr(rewalto_client.settings, "rewalto_api_key", None)
    monkeypatch.setattr(
        rewalto_client.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("No request should be made without configuration"),
    )
    with pytest.raises(RewaltoError) as error:
        rewalto_client.search_products("tea")
    assert error.value.code == "missing_configuration"


@pytest.mark.parametrize("status_code, expected_code", [
    (401, "authentication"),
    (402, "credits_exhausted"),
    (403, "permission_denied"),
    (429, "rate_limited"),
    (503, "upstream_error"),
])
def test_upstream_statuses_are_classified_without_reading_error_body(
    monkeypatch, status_code, expected_code
):
    monkeypatch.setattr(
        rewalto_client.settings,
        "rewalto_api_key",
        SecretStr("unit-test-only-value"),
    )
    monkeypatch.setattr(
        rewalto_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            status_code,
            headers={"Retry-After": "25"},
            payload={"detail": "a response body must not be exposed"},
        ),
    )
    with pytest.raises(RewaltoError) as error:
        rewalto_client.search_products("tea")
    assert error.value.code == expected_code
    if status_code == 429:
        assert error.value.retry_after == "25"


def test_documented_unavailable_code_is_preserved_without_exposing_error_text(monkeypatch):
    monkeypatch.setattr(
        rewalto_client.settings,
        "rewalto_api_key",
        SecretStr("unit-test-only-value"),
    )
    monkeypatch.setattr(
        rewalto_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(
            503,
            payload={"error": {"code": "unavailable", "message": "private upstream details"}},
        ),
    )
    with pytest.raises(RewaltoError) as error:
        rewalto_client.search_products("Amul milk", mode="semantic")
    assert error.value.code == "unavailable"
    assert "private upstream details" not in str(error.value)


def test_search_omits_unrequested_pin_and_uses_bearer_auth(monkeypatch):
    monkeypatch.setattr(
        rewalto_client.settings,
        "rewalto_api_key",
        SecretStr("unit-test-only-value"),
    )
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse(200, payload={"data": []})

    monkeypatch.setattr(rewalto_client.requests, "get", fake_get)
    assert rewalto_client.search_products("tea", pincode=None) == {"data": []}
    assert "pincode" not in captured["params"]
    assert captured["headers"]["Authorization"] == "Bearer unit-test-only-value"


def test_search_sends_only_documented_optional_brand_and_mode(monkeypatch):
    monkeypatch.setattr(
        rewalto_client.settings,
        "rewalto_api_key",
        SecretStr("unit-test-only-value"),
    )
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(200, payload={"data": []})

    monkeypatch.setattr(rewalto_client.requests, "get", fake_get)
    rewalto_client.search_products(
        "Amul milk", retailer="blinkit", pincode="121006", limit=5,
        brand="Amul", mode="semantic",
    )
    assert captured["params"] == {
        "q": "Amul milk", "retailer": "blinkit", "limit": 5,
        "include": "latest", "pincode": "121006", "brand": "Amul",
        "mode": "semantic",
    }


def test_word_search_uses_rewalto_documented_default_without_mode_parameter(monkeypatch):
    monkeypatch.setattr(
        rewalto_client.settings,
        "rewalto_api_key",
        SecretStr("unit-test-only-value"),
    )
    captured = {}
    monkeypatch.setattr(
        rewalto_client.requests,
        "get",
        lambda url, **kwargs: captured.update(kwargs) or FakeResponse(200, payload={"data": []}),
    )
    rewalto_client.search_products("Amul milk", mode="words")
    assert captured["params"]["q"] == "Amul milk"
    assert "mode" not in captured["params"]


@pytest.mark.parametrize("payload", [
    [],
    {"data": None},
    {"data": [{"id": "valid"}, "not-a-listing"]},
])
def test_malformed_success_payload_is_reported_as_safe_upstream_error(monkeypatch, payload):
    monkeypatch.setattr(
        rewalto_client.settings,
        "rewalto_api_key",
        SecretStr("unit-test-only-value"),
    )
    monkeypatch.setattr(
        rewalto_client.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(200, payload=payload),
    )

    with pytest.raises(RewaltoError) as error:
        rewalto_client.search_products("tea")
    assert error.value.code == "invalid_response"
