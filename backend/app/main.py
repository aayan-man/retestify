from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.ai_engine.providers.errors import ProviderNotConfiguredError
from app.api import (
    routes_changes,
    routes_companies,
    routes_jobs,
    routes_projects,
    routes_recommendations,
    routes_reports,
    routes_risks,
    routes_runs,
    routes_webhooks,
)
from app.git_integration.repo import NotAGitRepoError
from app.jobs.queue import JobConflictError

app = FastAPI(title="Retestify")

# Permissive CORS for the local dashboard dev server; tighten before any
# real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pipeline functions raise plain Python exceptions rather than HTTPException
# (so the same functions work identically from the CLI); translate the
# expected ones here into actionable 4xx responses instead of a bare 500.
@app.exception_handler(ProviderNotConfiguredError)
async def provider_not_configured_handler(request: Request, exc: ProviderNotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(NotAGitRepoError)
async def not_a_git_repo_handler(request: Request, exc: NotAGitRepoError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(JobConflictError)
async def job_conflict_handler(request: Request, exc: JobConflictError) -> JSONResponse:
    # Only one job per project, since concurrent runs would interleave
    # writes into the same knowledge-base files.
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(FileNotFoundError)
async def workspace_not_found_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def bad_request_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})

app.include_router(routes_projects.router)
app.include_router(routes_recommendations.router)
app.include_router(routes_jobs.router)
app.include_router(routes_runs.router)
app.include_router(routes_changes.router)
app.include_router(routes_reports.router)
app.include_router(routes_risks.router)
app.include_router(routes_companies.router)
app.include_router(routes_webhooks.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
