"""FastAPI application entry point: app factory, cookie/session handling,
and shared response helpers used by every router."""
import logging
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import STATIC_DIR, SESSION_TTL_SECONDS, ENVIRONMENT
from app.db import init_db
from app.security import verify_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sms")

COOKIE_NAME = "sms_session"
IS_PRODUCTION = ENVIRONMENT == "production"


def get_session(request: Request):
    """Decode the session cookie into a dict (uid, role, name, ...), or None."""
    token = request.cookies.get(COOKIE_NAME)
    return verify_session(token)


def set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=IS_PRODUCTION,  # only require HTTPS-only cookies once actually deployed
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")


def json_err(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"error": message})


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(
        title="School Management System",
        # Hide the interactive API explorer in production — no reason to
        # publicly advertise the full endpoint surface once this is live.
        docs_url=None if IS_PRODUCTION else "/docs",
        redoc_url=None if IS_PRODUCTION else "/redoc",
        openapi_url=None if IS_PRODUCTION else "/openapi.json",
    )

    # Permissive same-origin-friendly default. Since the frontend is served
    # from this same app (see static mount below), this mainly matters if
    # a separate frontend/mobile client is ever added later.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not IS_PRODUCTION else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return json_err("An unexpected error occurred. Please try again.", 500)

    # Routes for the API endpoints are defined in separate routers, included here.
    from app.routers import (auth, dashboard, parents, students, subjects, teachers,
                              assignments, classes, student_attendance, teacher_attendance,
                              attendance_unlock, examinations, promotions, fee_structures, fees, reports,
                              audit, backup, settings, principals)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(parents.router)
    app.include_router(students.router)
    app.include_router(subjects.router)
    app.include_router(teachers.router)
    app.include_router(assignments.router)
    app.include_router(classes.router)
    app.include_router(student_attendance.router)
    app.include_router(teacher_attendance.router)
    app.include_router(attendance_unlock.router)
    app.include_router(examinations.router)
    app.include_router(promotions.router)
    app.include_router(fee_structures.router)
    app.include_router(fees.router)
    app.include_router(reports.router)
    app.include_router(audit.router)
    app.include_router(backup.router)
    app.include_router(settings.router)
    app.include_router(principals.router)
    # Serve the frontend once static/ exists
    import os
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def serve_index():
            from fastapi.responses import FileResponse
            return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    logger.info("SMS backend started (environment=%s)", ENVIRONMENT)
    return app


app = create_app()