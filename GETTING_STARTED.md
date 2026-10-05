# Getting Started

Step-by-step setup for running Retestify locally, start to finish on a fresh
machine. See [README.md](README.md) for an architecture overview.

## Run the whole thing

The short version — each command is explained in the numbered steps below.
Run these from the repo root, in order:

```bash
# 1. backend venv + install
cd backend
python -m venv .venv
./.venv/Scripts/pip install -e ".[dev,ai,eval]"    # Git Bash (Windows)
./.venv/Scripts/python -m pytest                   # sanity check: "N passed"

# 2. optional, only for JS/TS repos — parser bridge deps
cd app/analyzers/javascript/parser_bridge && npm install && cd -

# 3. config — create backend/.env with at least a provider + key
#    APP_AI_PROVIDER=anthropic
#    APP_ANTHROPIC_API_KEY=sk-ant-...

# 4. start the API (terminal 1, from backend/)
./.venv/Scripts/python -m uvicorn app.main:app --reload   # http://localhost:8000

# 5. start the frontend (terminal 2, from repo root)
cd frontend && npm install && npm run dev                 # http://localhost:5173

# 6. open the dashboard
#    http://localhost:5173 — paste a GitHub URL or upload a .zip
```

PowerShell equivalents for the two venv invocations:

```powershell
.venv\Scripts\pip install -e ".[dev,ai,eval]"
.venv\Scripts\python -m uvicorn app.main:app --reload
```

On macOS/Linux use `.venv/bin/pip` and `.venv/bin/python` instead.

Docker is **not** needed for any of the above — only for `run-tests` and
coverage numbers. See [Prerequisites](#prerequisites).

## Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| Python 3.11+ | backend, CLI | `python --version` |
| Node.js 18+ | JS/TS analysis, frontend dashboard | `node --version` |
| git | repo ingestion, change detection | `git --version` |
| Docker | executing target-repo test suites (`run-tests`) | `docker info` |

Java, C++, Go, and C# analysis needs no extra tooling beyond the backend's
own `pip install` (step 1) — their parsers are `tree-sitter` grammar
packages, pure Python-installable wheels, not compilers/SDKs for those
languages.

### Docker

Docker is optional for exploring the analysis/classification pipeline, but
required for `run-tests` / coverage — the test runner refuses to execute
target-repo code on the host if Docker isn't available, by design (see
README's "Known scope limits").

**Check with `docker info`, not `docker --version`.** The `docker` CLI
reports a version whenever Docker Desktop is *installed*, even when its
engine isn't running — and every `docker run` fails in that state. That gap
is exactly what produced a false-green `run-tests` result before commit
`9b510f1`, so `docker_unavailable_reason()` in
`backend/app/test_runner/sandbox_exec.py` now probes the daemon with
`docker info`. `docker info` printing a Server section means the engine is
actually usable.

**On Windows, Docker Desktop requires WSL2.** If WSL isn't installed, Docker
Desktop fails to start with "Docker Desktop is unable to start". To set it
up:

```powershell
wsl --status            # does it report an installed WSL?
wsl --install           # must be run in an Administrator terminal
```

Then **reboot**, launch Docker Desktop once, and wait for the whale icon in
the system tray to stop animating before running anything. Verify:

```bash
docker info
```

**First `run-tests` builds a runner image.** The suite executes with
networking disabled, so its tooling (pytest, pytest-json-report, coverage)
cannot be installed from inside the run — it is baked into a
`retestify-runner:*` image instead. That build happens once, needs network,
and adds roughly 30s to the first run; later runs reuse the cached image.
Changing `APP_TEST_RUNNER_DOCKER_IMAGE_PYTHON` builds a new one rather than
reusing the old.

A target repo whose own tests import third-party packages still needs those
available in the workspace — the runner image carries the test tooling, not
the repo's dependencies.

**What works without Docker:** `analyze` (ingest + static analysis),
`classify`, `apply`, `assess-risks`, `detect-changes`, `classify-changed`,
the dashboard, the whole CLI except one command, and the backend test suite.

**What doesn't:** `run-tests` (CLI and `POST /projects/{id}/run-tests`) —
and therefore the evaluation harness's `coverage_before` / `coverage_after`
numbers, since `research/evaluation/run_framework.py` and
`research/evaluation/baseline_manual.py` both get coverage by calling
`pipeline.run_tests`. The harness's other metrics (execution time, token
usage) don't need Docker.

## 1. Backend setup

```bash
cd backend
python -m venv .venv

# Windows (Git Bash)
./.venv/Scripts/pip install -e ".[dev,ai,eval]"
# Windows (PowerShell)
.venv\Scripts\pip install -e ".[dev,ai,eval]"
# macOS/Linux
.venv/bin/pip install -e ".[dev,ai,eval]"
```

`[dev,ai,eval]` pulls in test tooling (pytest, httpx), the Anthropic/OpenAI
SDKs, and the evaluation harness's dependencies (PyYAML, pandas). Drop
extras you don't need yet — e.g. just `.[dev]` to run the test suite without
AI provider SDKs.

Verify the install:

```bash
./.venv/Scripts/python -m pytest    # should show "N passed"
```

## 2. Configure settings (API keys and tuning)

Settings are read from environment variables prefixed `APP_` (see
`backend/app/config.py`). Create `backend/.env` (gitignored) or export them
in your shell:

```bash
# pick one provider
APP_AI_PROVIDER=anthropic
APP_ANTHROPIC_API_KEY=sk-ant-...
APP_ANTHROPIC_MODEL=claude-sonnet-4-5

# or:
APP_AI_PROVIDER=openai
APP_OPENAI_API_KEY=sk-...
APP_OPENAI_MODEL=gpt-4o-mini
# APP_OPENAI_BASE_URL=http://localhost:11434/v1   # for a local/self-hosted model

# retries the provider SDK makes on a rate-limited/failed call (default 5).
# Applying makes one call per recommendation back to back and saturates
# tokens-per-minute limits on smaller tiers; both SDKs honor Retry-After and
# back off exponentially, so a higher ceiling absorbs rate limiting instead
# of failing individual recommendations.
APP_LLM_MAX_RETRIES=5

# background worker threads for the API's job queue (default 4). Jobs are
# already serialized per project, so this caps how many *different* projects
# can be classified or applied at the same time.
APP_JOB_MAX_WORKERS=4

# where ingested repos and knowledge-base JSON live (default backend/workspace)
# APP_WORKSPACE_ROOT=/some/other/path

# container images used by the sandboxed test runner
# APP_TEST_RUNNER_DOCKER_IMAGE_PYTHON=python:3.11-slim
# APP_TEST_RUNNER_DOCKER_IMAGE_NODE=node:20-slim

# only needed for the GitHub webhook route
APP_GITHUB_WEBHOOK_SECRET=...
```

Without a key configured, ingestion/`analyze`/`assess-risks`/dashboard
browsing all still work — only `classify`, `apply`, `classify-changed`, and
the evaluation harness's `framework`/`standalone_llm` arms need one (the
`manual` baseline doesn't). The API checks provider configuration *before*
queueing a job, so a missing key is an immediate, readable `400` rather than
a job that accepts and then fails.

## 3. JS/TS analyzer setup (optional, one-time)

Only needed if you'll analyze JavaScript/TypeScript repos:

```bash
cd backend/app/analyzers/javascript/parser_bridge
npm install
cd -
```

## 4. Try it via the CLI

**The CLI is fully synchronous.** It calls the pipeline functions in
`backend/app/jobs/pipeline.py` directly and does not go through the API, so
there are no jobs, no polling, and no 202s here — `classify` and `apply`
block until they finish and then print their results. `apply` on a
real-world repo routinely runs for minutes. This is now a meaningful
difference from the API, where the same two operations are background jobs
(see step 6).

```bash
cd backend
./.venv/Scripts/python -m app.cli analyze --path tests/fixtures/sample_python_repo
# -> prints a project_id, e.g. "project_id: a1b2c3d4e5f6"

./.venv/Scripts/python -m app.cli classify --project <project_id>   # needs an API key
./.venv/Scripts/python -m app.cli apply --project <project_id>
./.venv/Scripts/python -m app.cli run-tests --project <project_id>   # needs Docker

# deployment-readiness / performance-risk / recurring-issue prediction (static, no key/Docker needed)
./.venv/Scripts/python -m app.cli assess-risks --project <project_id>
./.venv/Scripts/python -m app.cli assess-risks --project <project_id> --company example-corp
```

Other flags worth knowing: `analyze --github <url> [--ref <branch|tag|sha>]`,
`classify/apply/classify-changed --provider anthropic|openai` to override
`APP_AI_PROVIDER`, `apply --company <id>`, and `run-tests --language python`
(the default; `javascript` and `typescript` are the only other registered
runners).

`run-tests` reports `status: error` — not a false `passed` — when Docker is
unavailable or the suite never ran. A run that produced zero test results is
always an error, since "no failures" is only good news if something actually
executed. The daemon-connection reason shows up in the printed `stderr`.

For a repo you want change-tracking on, ingest via `--github <url>` instead
of `--path` — `detect-changes`/`classify-changed` only work on git-ingested
projects. Run `detect-changes` more than once on the same project before
`assess-risks` to see code-churn risk predictions — it needs accumulated
history, not just one snapshot.

## 5. Run the API + dashboard

Two terminals:

```bash
# terminal 1 — backend API
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --reload
# -> http://localhost:8000 (check http://localhost:8000/health)

# terminal 2 — frontend
cd frontend
npm install
npm run dev
# -> http://localhost:5173
```

Open `http://localhost:5173`, paste a GitHub URL (or upload a `.zip`), and
use Classify / Apply pending / Detect changes from the dashboard. The Vite
dev server proxies `/projects`, `/jobs`, `/webhooks`, and `/health` to
`http://localhost:8000` (`frontend/vite.config.ts`), so the API must be
running on port 8000 or those calls return `index.html` instead of JSON.

Interactive API docs are at `http://localhost:8000/docs`.

## 6. Classify and apply are background jobs

`POST /projects/{id}/classify` and `POST /projects/{id}/apply` **do not
return results.** Each returns `202 Accepted` with a `Job` body and a
`Location: /jobs/{job_id}` header, and the work runs on a background thread
pool (`backend/app/jobs/queue.py`). Applying responds in milliseconds
instead of holding a request open for minutes, where a proxy or browser
timeout could discard a complete, paid-for run.

The flow is: start the job, poll it, then read results from the knowledge
base as usual.

```bash
# 1. start it — 202, with the job in the body and a Location header
curl -i -X POST http://localhost:8000/projects/<project_id>/apply \
  -H 'content-type: application/json' -d '{}'
# -> HTTP/1.1 202 Accepted
#    location: /jobs/job_ab12cd34ef
#    {"id":"job_ab12cd34ef","project_id":"...","kind":"apply","status":"queued",
#     "processed":0,"total":null,...}

# 2. poll until status is succeeded or failed
curl http://localhost:8000/jobs/job_ab12cd34ef
# -> {"status":"running","processed":12,"total":29,...}

# 3. read the results
curl http://localhost:8000/projects/<project_id>/recommendations
```

Job fields: `status` is one of `queued`, `running`, `succeeded`, `failed`;
`processed`/`total` give progress (`total` is `null` until the job reports
it); `error` carries the failure message when `status` is `failed`; `result`
holds a small count summary of what the job did. `GET
/projects/{project_id}/jobs` lists that project's jobs, newest first.

Both request bodies accept `{"provider": "anthropic"|"openai"}` to override
`APP_AI_PROVIDER`; `apply` also accepts `{"company_id": "<id>"}`.

**One job at a time per project.** Starting a second while one is queued or
running returns `409 Conflict`, because the knowledge base is a set of JSON
files that concurrent runs would interleave writes into. Different projects
still run in parallel, up to `APP_JOB_MAX_WORKERS`.

**Apply isolates failures per recommendation.** One bad generation no longer
discards the whole run — a failed recommendation gets `status: "failed"` and
a `failure_reason`, and the rest are still written. The dashboard shows
applied/failed/rejected badges and Applied/Failed counts.

Everything else is still a plain synchronous API call: `POST /projects`,
`POST /projects/upload`, `POST /projects/{id}/detect-changes`,
`POST /projects/{id}/classify-changed`, `POST /projects/{id}/assess-risks`,
`POST /projects/{id}/run-tests`, and the `GET` routes.

### GitHub webhook

`POST /webhooks/github/{project_id}` (HMAC-verified with
`APP_GITHUB_WEBHOOK_SECRET`) no longer does the work inline. A push is
acknowledged immediately with `{"status": "accepted", "job_id": "job_..."}`
and the pull-and-reclassify runs as a background job, because that work
takes far longer than GitHub's delivery timeout. A push arriving while the
previous one is still being processed reports `{"status": "skipped",
"reason": ...}` rather than failing the delivery, and a non-push event
reports `{"status": "ignored", ...}`.

## 7. Run the evaluation harness (optional, research use)

```bash
cd ..   # repo root, one level above backend/
backend/.venv/Scripts/python -m research.evaluation.run_evaluation \
  --config research/evaluation/target_repos.yaml
```

Edit `research/evaluation/target_repos.yaml` first to point at the repos and
variants (`framework` / `manual` / `standalone_llm`) you want to compare.
Results are written to `research/evaluation/results/results.csv`
(gitignored). Running `framework` or `standalone_llm` variants against many
repos makes real LLM API calls — check the cost columns in the output CSV.

The harness calls the pipeline directly, like the CLI, so it is synchronous
and doesn't use the job queue. Its coverage columns need Docker (see
[Prerequisites](#docker)).

## Troubleshooting

- **`ANTHROPIC_API_KEY is not configured`** — set `APP_ANTHROPIC_API_KEY` (see step 2), or pass `--provider openai` / switch `APP_AI_PROVIDER`. From the API this is a `400`, raised before the job is queued.
- **`202 Accepted` from classify/apply** — that's success, not an error. The work was queued; poll `GET /jobs/{job_id}` from the `Location` header, then read `GET /projects/{id}/recommendations` (see step 6).
- **`409 Conflict` from classify/apply** — this project already has a queued or running job; the response body names it. Wait for it to finish (poll it), or use `GET /projects/{id}/jobs` to find it. Only one job runs per project at a time.
- **"Docker Desktop is unable to start" (Windows)** — Docker Desktop needs WSL2. Run `wsl --status`; if WSL isn't installed, run `wsl --install` in an **Administrator** terminal, **reboot**, then start Docker Desktop and wait for the whale icon to settle. Confirm with `docker info`.
- **`Docker is required to execute target-repo tests...` / `The Docker CLI is installed but its daemon is not reachable`** — start Docker Desktop (see above), or skip `run-tests`; everything else works without it. `docker --version` succeeding proves nothing here — use `docker info`.
- **`could not build the test-runner image ...`** — the one-time image build needs network access, unlike the test run itself. Check connectivity and that Docker has disk space, then retry.
- **`run-tests` reports `error` with total 0** — the suite never ran to completion. Check `stderr` in the result: a dead Docker daemon, a container that failed to start, or a collection error in the target repo. This is deliberate; a run with zero results is never reported as `passed`.
- **`Node.js is required to parse JS/TS files...`** — install Node.js, or stick to Python-only repos.
- **`no workspace found for project_id ...`** — the `project_id` came from a different machine/session, or `backend/workspace/<id>/` was deleted; re-run `analyze`.
- **Dashboard throws a JSON parse error** — the backend isn't running on port 8000, so Vite's proxy returned `index.html`. Start uvicorn and check `http://localhost:8000/health`.
- **Job history vanished after restarting the API** — expected. Job records are in memory (`app/jobs/queue.py`), and finished ones are trimmed past a cap. Results are always persisted to the knowledge base by the pipeline, so a lost job record never means lost work.
