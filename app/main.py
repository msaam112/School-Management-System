"""FastAPI application entry point: app factory, cookie/session handling,
and shared response helpers used by every router."""
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, SESSION_TTL_SECONDS
from app.db import init_db
from app.security import verify_session

COOKIE_NAME = "sms_session"


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
        path="/",
    )


def clear_session_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")


def json_err(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"error": message})


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="School Management System")

    #/////Routes for the API endpoints are defined in separate routers, which are included here.
    from app.routers import (auth, dashboard, parents, students, subjects, teachers,
                              assignments, classes, student_attendance, teacher_attendance,
                              attendance_unlock, examinations, promotions, fee_structures, fees, reports,
                              audit, backup, settings)
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
    #/////////////////////////////////////////////////

    # Serve the frontend once static/ exists (Module 2 focuses on the API first)
   # Serve the frontend once static/ exists
    import os
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def serve_index():
            from fastapi.responses import FileResponse
            return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    return app


app = create_app()