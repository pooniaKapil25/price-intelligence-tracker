"""FastAPI application entry point."""

from fastapi import FastAPI

from backend import models  # Import models so SQLAlchemy can create their tables.
from backend.config import settings
from backend.database import Base, engine
from backend.routes import router as products_router

app = FastAPI(title=settings.app_name)

# Create any tables that do not exist yet when the API starts.
Base.metadata.create_all(bind=engine)

app.include_router(products_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Return a small response that confirms the API is running."""
    return {"status": "ok"}
