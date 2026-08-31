# Getting Started

Step-by-step setup for running Retestify locally. See [README.md](README.md)
for an architecture overview.

## Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| Python 3.11+ | backend, CLI | `python --version` |
| Node.js 18+ | JS/TS analysis, frontend dashboard | `node --version` |
| git | repo ingestion, change detection | `git --version` |
| Docker | executing target-repo test suites (`run-tests`) | `docker --version` |

Docker is optional for exploring the analysis/classification pipeline, but
required for `run-tests` / coverage — the test runner refuses to execute
target-repo code on the host if Docker isn't available, by design (see
README's "Known scope limits").

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

`[dev,ai,eval]` pulls in test tooling, the Anthropic/OpenAI SDKs, and the
evaluation harness's dependencies (PyYAML, pandas). Drop extras you don't
need yet — e.g. just `.[dev]` to run the test suite without AI provider SDKs.

Verify the install:

```bash
./.venv/Scripts/python -m pytest    # should show "N passed"
```

## 2. Configure API keys (optional, needed for classify/apply/eval)

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

# only needed for the GitHub webhook route
APP_GITHUB_WEBHOOK_SECRET=...
```

Without a key configured, `analyze`/ingestion/dashboard browsing all still
work — only `classify`, `apply`, and the evaluation harness's `framework`/
`standalone_llm` arms need one (the `manual` baseline doesn't).

## 3. JS/TS analyzer setup (optional, one-time)

Only needed if you'll analyze JavaScript/TypeScript repos:

```bash
cd backend/app/analyzers/javascript/parser_bridge
npm install
cd -
```

## 4. Try it via the CLI

```bash
cd backend
./.venv/Scripts/python -m app.cli analyze --path tests/fixtures/sample_python_repo
# -> prints a project_id, e.g. "project_id: a1b2c3d4e5f6"

./.venv/Scripts/python -m app.cli classify --project <project_id>   # needs an API key
./.venv/Scripts/python -m app.cli apply --project <project_id>
./.venv/Scripts/python -m app.cli run-tests --project <project_id>   # needs Docker
```

For a repo you want change-tracking on, ingest via `--github <url>` instead
of `--path` — `detect-changes`/`classify-changed` only work on git-ingested
projects.

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
use Classify / Apply pending / Detect changes from the dashboard.

## 6. Run the evaluation harness (optional, research use)

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

## Troubleshooting

- **`ANTHROPIC_API_KEY is not configured`** — set `APP_ANTHROPIC_API_KEY` (see step 2), or pass `--provider openai` / switch `APP_AI_PROVIDER`.
- **`Docker is required to execute target-repo tests...`** — install/start Docker Desktop, or skip `run-tests`; everything else works without it.
- **`Node.js is required to parse JS/TS files...`** — install Node.js, or stick to Python-only repos.
- **`no workspace found for project_id ...`** — the `project_id` came from a different machine/session, or `backend/workspace/<id>/` was deleted; re-run `analyze`.
