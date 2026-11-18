from unittest.mock import patch
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest


class EmptyProductsResponse:
    """Minimal successful response for the dashboard's initial product load."""

    def raise_for_status(self):
        pass

    def json(self):
        return []


def test_demo_comparison_is_hidden_until_demo_mode_is_enabled():
    with patch.object(
        requests,
        "get",
        return_value=EmptyProductsResponse(),
    ):
        app_path = Path(__file__).resolve().parents[1] / "frontend" / "app.py"
        app = AppTest.from_file(app_path, default_timeout=10).run()

        assert not app.exception
        assert [(item.label, item.value) for item in app.checkbox] == [
            ("Show simulated demo comparison", False)
        ]
        assert not any("Demo Price Comparison" in item.value for item in app.subheader)
        assert not app.warning
        assert len(app.dataframe) == 0

        app.checkbox[0].check().run()

        assert not app.exception
        assert any("Demo Price Comparison" in item.value for item in app.subheader)
        assert "SIMULATED DEMO DATA — NOT LIVE RETAILER PRICES" in [
            item.value for item in app.warning
        ]
        assert {item.label for item in app.metric} >= {
            "Lowest price", "Highest price", "Savings"
        }
        assert len(app.dataframe) == 1

        app.checkbox[0].uncheck().run()

        assert not any("Demo Price Comparison" in item.value for item in app.subheader)
        assert not app.warning
        assert len(app.dataframe) == 0
