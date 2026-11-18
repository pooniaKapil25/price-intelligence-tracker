
"""Common interface for fetching product prices from different sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceResult:
    """Standard result returned by every price source."""

    price: float
    source: str
    success: bool = True
    error: Optional[str] = None


class PriceFetcher(ABC):
    """Base class that all website price fetchers must implement."""

    @abstractmethod
    def fetch_price(self, product_url: str) -> PriceResult:
        """Fetch the current price for a product URL."""
        raise NotImplementedError
