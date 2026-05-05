"""CORS registration for the FastAPI app."""

from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings


def register_cors(app) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
