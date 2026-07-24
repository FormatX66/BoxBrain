from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api import router
from .settings import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title="BoxBrain Controller",
        summary="Control-plane API for the BoxBrain alpha.",
        version=__version__,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(router)
    return application

