from __future__ import annotations

import time

from app.jobs import pipeline


def poll_once(project_ids: list[str]) -> dict[str, int]:
    """Run detect_changes for every project once. Returns the number of
    changes found per project, or -1 if that project's check failed —
    one project's error never stops the others from being checked."""
    results: dict[str, int] = {}
    for project_id in project_ids:
        try:
            results[project_id] = len(pipeline.detect_changes(project_id))
        except Exception:
            results[project_id] = -1
    return results


def run_polling_loop(project_ids: list[str], interval_s: int = 300, iterations: int | None = None) -> None:
    """Fallback continuous-monitoring loop for target repos that don't have
    a webhook registered against this framework. `iterations` bounds the
    loop (useful for tests); leave it None to run indefinitely."""
    ran = 0
    while iterations is None or ran < iterations:
        poll_once(project_ids)
        ran += 1
        if iterations is None or ran < iterations:
            time.sleep(interval_s)
