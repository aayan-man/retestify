from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings
from app.jobs import pipeline
from app.jobs.queue import JobConflictError, queue

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(payload: bytes, signature_header: str | None) -> None:
    if not settings.github_webhook_secret:
        return  # no secret configured: verification skipped (local/dev use only)
    if not signature_header or not signature_header.startswith("sha256="):
        raise HTTPException(status_code=401, detail="missing or malformed X-Hub-Signature-256 header")
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="signature mismatch")


@router.post("/github/{project_id}")
async def github_webhook(
    project_id: str,
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> dict:
    """Each target project registers its own webhook URL
    (`/webhooks/github/{project_id}`) in its GitHub repo settings, pointing
    at this server. On a push event, pull the new commits, diff against the
    stored knowledge base, and incrementally reclassify only what changed."""
    payload = await request.body()
    _verify_signature(payload, x_hub_signature_256)

    if x_github_event != "push":
        return {"status": "ignored", "reason": f"event {x_github_event!r} is not a push"}

    # Pulling and reclassifying takes far longer than GitHub's delivery
    # timeout, so acknowledge the push immediately and do the work in the
    # background (see app/jobs/queue.py).
    def run(progress):
        changes = pipeline.detect_changes(project_id)
        recommendations = pipeline.classify_changed_components(project_id)
        return {"changes": len(changes), "recommendations": len(recommendations)}

    try:
        job = queue.submit(project_id, "webhook_push", run)
    except JobConflictError as e:
        # A push landing while the previous one is still being processed is
        # normal; report it rather than failing the delivery.
        return {"status": "skipped", "reason": str(e)}
    return {"status": "accepted", "job_id": job.id}
