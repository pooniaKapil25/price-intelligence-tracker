
"""Pydantic schemas for product and price tracking."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class ProductCreate(BaseModel):
    """Fields required to add a product."""

    name: str = Field(min_length=1, max_length=200)
    product_url: HttpUrl
    # The existing database column is NOT NULL, so tracked products need a
    # confirmed positive initial price until the schema supports unknowns.
    current_price: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def require_initial_price(cls, value):
        """Return a direct validation error for a missing or null initial price."""
        if isinstance(value, dict) and value.get("current_price") is None:
            raise ValueError("A positive initial price is required to track a product.")
        return value


class ProductRead(BaseModel):
    """Product response."""

    id: int
    name: str
    product_url: str
    current_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("current_price", mode="before")
    @classmethod
    def zero_is_unknown(cls, value):
        """The unchanged legacy column uses zero as its internal unknown sentinel."""
        if value is None or value <= 0:
            return None
        return value


class PriceHistoryRead(BaseModel):
    """Historical price response."""

    id: int
    product_id: int
    price: float = Field(gt=0, allow_inf_nan=False)
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceCheckRequest(BaseModel):
    """Latest price received from a price check."""

    current_price: float = Field(gt=0, allow_inf_nan=False)


class DemoPriceRead(BaseModel):
    """A simulated price response that is deliberately not a history record."""

    source: str = "demo"
    simulated: bool = True
    price: float = Field(gt=0, allow_inf_nan=False)
    message: str
