import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from . import __version__
from .api import router
from .settings import settings


_PUBLIC_PATHS = {
    "/api/v1/health",
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
}


def create_app() -> FastAPI:
    if settings.api_token is not None and len(settings.api_token) < 32:
        raise ValueError("BOXBRAIN_API_TOKEN must contain at least 32 characters.")

    application = FastAPI(
        title="BoxBrain Controller",
        summary="Control-plane API for the BoxBrain alpha.",
        version=__version__,
    )

    @application.middleware("http")
    async def require_local_api_token(request: Request, call_next):
        expected = settings.api_token
        if (
            expected is None
            or request.method == "OPTIONS"
            or request.url.path in _PUBLIC_PATHS
            or not request.url.path.startswith("/api/")
        ):
            return await call_next(request)

        presented = request.headers.get("X-BoxBrain-Token")
        if presented is None or not secrets.compare_digest(presented, expected):
            return JSONResponse(
                status_code=401,
                content={"detail": "A valid BoxBrain API token is required."},
                headers={"WWW-Authenticate": "BoxBrain-Token"},
            )
        return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-BoxBrain-Token",
        ],
    )
    application.include_router(router)

    def custom_openapi() -> dict:
        if application.openapi_schema is not None:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            summary=application.summary,
            routes=application.routes,
        )
        schema.setdefault("components", {}).setdefault(
            "securitySchemes",
            {},
        )["BoxBrainToken"] = {
            "type": "apiKey",
            "in": "header",
            "name": "X-BoxBrain-Token",
        }
        schema["security"] = [{"BoxBrainToken": []}]
        for method in schema["paths"]["/api/v1/health"].values():
            method["security"] = []
        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi
    return application