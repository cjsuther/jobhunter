"""FastAPI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.config import get_settings
from app.logging_setup import configure_logging, get_logger
from app.routers import (
    account,
    admin,
    auth,
    costs,
    criteria,
    matches,
    profiles,
    queue,
    scrapers,
    tracking,
)

configure_logging()
log = get_logger("app.main")
settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_global_per_min}/minute"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    log.info("app.startup", environment=settings.environment)
    yield
    log.info("app.shutdown")


app = FastAPI(
    title="JobHunter API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Routers
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=f"{API_PREFIX}/auth", tags=["auth"])
app.include_router(account.router, prefix=f"{API_PREFIX}/account", tags=["account"])
app.include_router(profiles.router, prefix=f"{API_PREFIX}/profiles", tags=["profiles"])
app.include_router(
    criteria.profile_criteria_router,
    prefix=f"{API_PREFIX}/profiles",
    tags=["criteria"],
)
app.include_router(criteria.router, prefix=f"{API_PREFIX}/criteria", tags=["criteria"])
app.include_router(matches.router, prefix=f"{API_PREFIX}/matches", tags=["matches"])
app.include_router(tracking.router, prefix=f"{API_PREFIX}/tracking", tags=["tracking"])
app.include_router(queue.router, prefix=f"{API_PREFIX}/queue", tags=["queue"])
app.include_router(scrapers.router, prefix=f"{API_PREFIX}/scrapers", tags=["scrapers"])
app.include_router(costs.router, prefix=f"{API_PREFIX}/costs", tags=["costs"])
app.include_router(admin.router, prefix=f"{API_PREFIX}/admin", tags=["admin"])
