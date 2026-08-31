from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    routes_changes,
    routes_projects,
    routes_recommendations,
    routes_reports,
    routes_runs,
    routes_webhooks,
)

app = FastAPI(title="AI-Driven Test Case Management Framework")

# Permissive CORS for the local dashboard dev server; tighten before any
# real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_projects.router)
app.include_router(routes_recommendations.router)
app.include_router(routes_runs.router)
app.include_router(routes_changes.router)
app.include_router(routes_reports.router)
app.include_router(routes_webhooks.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
