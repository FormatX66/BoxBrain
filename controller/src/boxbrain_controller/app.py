import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
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

    application.state.authentication_required = settings.api_token is not None

    @application.middleware("http")
    async def require_local_api_token(request: Request, call_next):
        expected = settings.api_token
        requires_token = (
            expected is not None
            and request.method != "OPTIONS"
            and request.url.path not in _PUBLIC_PATHS
            and request.url.path.startswith("/api/")
        )
        presented = request.headers.get("X-BoxBrain-Token")
        if requires_token and (
            presented is None
            or not secrets.compare_digest(presented, expected)
        ):
            response = JSONResponse(
                status_code=401,
                content={"detail": "A valid BoxBrain API token is required."},
                headers={"WWW-Authenticate": "BoxBrain-Token"},
            )
        else:
            response = await call_next(request)

        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'",
            )
            response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response

    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(settings.allowed_hosts),
    )
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