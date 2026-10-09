from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import CORS_ORIGINS
from app.courses import router as courses_router
from app.dashboard import router as dashboard_router
from app.db import UNAVAILABLE_ERRORS, check_database, close_pool
from app.degree_progress import router as degree_progress_router
from app.eligibility import router as eligibility_router
from app.graduation_plan import router as graduation_plan_router
from app.requirements import router as requirements_router
from app.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="Finish Line API",
    description="Degree planning for UMD Information Science. A planning tool, not an "
    "official UMD degree audit.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Total-Count"],  # search result totals
)


@app.exception_handler(UNAVAILABLE_ERRORS[0])
@app.exception_handler(UNAVAILABLE_ERRORS[1])
async def database_unavailable(request: Request, exc: Exception):
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


app.include_router(courses_router)
app.include_router(requirements_router)
app.include_router(sessions_router)
app.include_router(degree_progress_router)
app.include_router(eligibility_router)
app.include_router(graduation_plan_router)
app.include_router(dashboard_router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "database": "ok" if check_database() else "unavailable",
    }
