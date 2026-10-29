"""FastAPI application – the interface between the backend and the frontend.

Start:      uvicorn billbuddy.api.main:app --reload
Web app:    http://127.0.0.1:8000
API docs:   http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from billbuddy import __version__
from billbuddy.api import auth_routes, expense_routes, settlement_routes
from billbuddy.auth.limiter import LoginLimiter, TooManyAttemptsError
from billbuddy.auth.service import AuthError
from billbuddy.db import PROJECT_ROOT, init_db, make_engine, make_session_factory
from billbuddy.expenses.service import NotFoundError, ValidationError

FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the app; tests pass their own (in-memory) database engine."""
    engine = engine or make_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        yield

    app = FastAPI(title="BillBuddy API", version=__version__, lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    app.state.login_limiter = LoginLimiter()

    @app.middleware("http")
    async def mark_responses(request: Request, call_next):
        # Lets the service worker tell real answers of this app apart from
        # waiting or error pages of the hosting provider
        response = await call_next(request)
        response.headers["X-BillBuddy"] = __version__
        return response

    @app.get("/api/health")
    def health():
        """For the hosting provider: answers without touching the database."""
        return {"status": "ok"}

    app.include_router(auth_routes.router)
    app.include_router(expense_routes.router)
    app.include_router(settlement_routes.router)
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
