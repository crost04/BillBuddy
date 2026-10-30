"""FastAPI application – the interface between the backend and the frontend.

Start:      uvicorn billbuddy.api.main:app --reload
Web app:    http://127.0.0.1:8000
API docs:   http://127.0.0.1:8000/docs
"""

import datetime as dt
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from billbuddy import __version__
from billbuddy.api import (
    anomaly_routes,
    auth_routes,
    categorizer_routes,
    expense_routes,
    forecast_routes,
    keep_awake,
    receipt_routes,
    recurring_routes,
    settlement_routes,
)
from billbuddy.auth.limiter import LoginLimiter, TooManyAttemptsError
from billbuddy.auth.service import AuthError
from billbuddy.db import PROJECT_ROOT, init_db, make_engine, make_session_factory
from billbuddy.expenses.service import NotFoundError, ValidationError
from billbuddy.ml.categorizer import service as categorizer

FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the app; tests pass their own (in-memory) database engine."""
    engine = engine or make_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        # Train the categorizer's base model now, so the first suggestion does not wait for it
        threading.Thread(target=categorizer.warm_up, daemon=True).start()
        stop_keep_awake = threading.Event()
        keep_awake.start(stop_keep_awake)
        yield
        stop_keep_awake.set()

    app = FastAPI(title="BillBuddy API", version=__version__, lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    app.state.login_limiter = LoginLimiter()

    @app.middleware("http")
    async def mark_responses(request: Request, call_next):
        # Lets the service worker tell real answers of this app apart from
        # waiting or error pages of the hosting provider
        response = await call_next(request)
        response.headers["X-BillBuddy"] = __version__
        # App files: the browser has to ask whether its copy is still current (a tiny
        # request answered with "304 Not Modified"), so updates arrive right away
        if not request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-cache")
        return response

    started = dt.datetime.now(dt.UTC)

    @app.get("/api/health")
    def health():
        """For the hosting provider: answers without touching the database.
        running_since shows whether the free server slept in between (it restarts when woken)."""
        return {"status": "ok", "running_since": started.isoformat(timespec="seconds")}

    app.include_router(auth_routes.router)
    app.include_router(expense_routes.router)
    app.include_router(settlement_routes.router)
    app.include_router(categorizer_routes.router)
    app.include_router(forecast_routes.router)
    app.include_router(recurring_routes.router)
    app.include_router(anomaly_routes.router)
    app.include_router(receipt_routes.router)
    # The web app itself; mounted last so the /api routes above take priority
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    # Turn errors from the service layer into proper HTTP status codes
    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def invalid(request: Request, exc: ValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(AuthError)
    async def unauthorized(request: Request, exc: AuthError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(TooManyAttemptsError)
    async def too_many(request: Request, exc: TooManyAttemptsError):
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "This change conflicts with existing data"})

    return app


app = create_app()
