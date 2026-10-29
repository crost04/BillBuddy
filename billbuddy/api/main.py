"""FastAPI application – the interface between the backend and the frontend.

Start:      uvicorn billbuddy.api.main:app --reload
API docs:   http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from billbuddy import __version__
from billbuddy.api.routes import router
from billbuddy.db import init_db, make_engine, make_session_factory
from billbuddy.expenses.service import NotFoundError, ValidationError


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the app; tests pass their own (in-memory) database engine."""
    engine = engine or make_engine()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        yield

    app = FastAPI(title="BillBuddy API", version=__version__, lifespan=lifespan)
    app.state.session_factory = make_session_factory(engine)
    app.include_router(router)

    # Turn errors from the service layer into proper HTTP status codes
    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def invalid(request: Request, exc: ValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "This change conflicts with existing data"})

    return app


app = create_app()
