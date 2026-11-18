
"""Demo price source for testing the price-fetching architecture."""

from backend.services.price_fetcher import PriceFetcher, PriceResult


class DemoPriceFetcher(PriceFetcher):
    """Returns a sample price without accessing an external website."""

    def fetch_price(self, product_url: str) -> PriceResult:
        if not product_url.startswith(("http://", "https://")):
            return PriceResult(
                price=0,
                source="demo",
                success=False,
                error="Invalid product URL.",
            )

        # Fixed sample price for architecture testing.
        return PriceResult(
            price=45999.0,
            source="demo",
            success=True,
        )
