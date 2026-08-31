# Retestify

AI-driven test case management framework.
Ingests a target repository (GitHub URL or ZIP), statically analyzes its source
and existing tests, and uses a pluggable AI Review Engine to decide which
tests to retain, modify, remove, or generate — with git-aware incremental
re-analysis, a dashboard, CI/CD hooks, and a research evaluation harness.

## Status

All 8 planned phases have an initial implementation:

**Core pipeline (Phases 1-5)**
- **Repo manager** — ingest from a local directory, `.zip` (zip-slip/size
  guarded), or GitHub URL (shallow clone).
- **Tech detector** — Python/pytest/unittest and JavaScript-TypeScript/Jest/Mocha.
- **Static analyzers** (pluggable, `app/analyzers/base.py`) — Python via
  stdlib `ast`; JS/TS via a Node/`@babel/parser` bridge
  (`app/analyzers/javascript/parser_bridge/parse.js`) emitting the same IR
  as JSON. Both extract functions/classes/methods with metrics and content
  hashing.
- **Test analyzer** — discovers tests and maps them to source components by
  naming convention. Python tests are `test_*` functions; JS/TS tests are
  `test()`/`it()` calls — handled by each analyzer's own `list_test_cases`.
- **Knowledge base** — Component/TestCase/ChangeRecord/Recommendation
  (pydantic), persisted as JSON under `backend/workspace/{project_id}/kb/`.

**AI Review Engine (Phases 3-4)**
- Pluggable `LLMProvider` interface (`app/ai_engine/providers/`) — Anthropic,
  or any OpenAI-compatible endpoint (including local models via `base_url`).
- `decision_engine` classifies each component's tests as retain/modify/remove
  (or generate, if none are mapped); `generator` writes new/improved tests as
  schema-validated, retry-on-failure structured output.
- `test_writer/` appends generated code to the conventional test file per
  language — existing test files are never rewritten in place.
- `test_runner/` executes the target repo's suite (pytest/Jest) **inside an
  isolated, network-disabled Docker container**; it fails loudly rather than
  ever falling back to running untrusted code on the host if Docker isn't
  available.
- `reporting/audit_log.py` — every recommendation and test-file write is
  logged to `kb/audit_log.jsonl`.

**Git integration & incremental analysis (Phase 6)**
- `git_integration/` — commit tracking and `git pull` on GitHub-ingested
  workspaces.
- `change_detector/diff_ast.py` — diffs two component snapshots by
  `(file_path, qualified_name)` (not by id, since a component's id embeds
  its line number and shifts on unrelated edits), producing added/modified/
  deleted `ChangeRecord`s.
- `change_detector/impact.py` — a name-based call-graph heuristic that flags
  components whose `calls` list references a changed component, so
  `classify_changed_components` reclassifies only what's actually affected
  instead of the whole project.

**Dashboard, CI/CD, monitoring (Phase 7)**
- `app/main.py` + `app/api/` — a FastAPI backend wrapping the pipeline
  (projects, recommendations, changes, runs, reports, webhooks).
- `app/api/routes_webhooks.py` — a per-project GitHub webhook
  (`/webhooks/github/{project_id}`) with HMAC signature verification that
  triggers incremental detect-changes + classify-changed on push.
- `app/ci_integration/workflow_template.yml` — an alternative for target
  repos whose own CI can reach the API instead of registering a webhook.
- `app/monitoring/poller.py` — a fallback polling loop for repos without
  webhook access.
- `frontend/` — a React + TypeScript dashboard (Vite) with upload, live
  recommendation/change views, and one-click classify/apply/detect-changes.
  Verified end-to-end in-browser against the live API.

**Evaluation harness (Phase 8)**
- `research/evaluation/run_framework.py` — the framework's own arm
  (classify → apply → measure coverage before/after).
- `research/evaluation/baseline_manual.py` — "traditional testing": no AI,
  existing tests run as-is.
- `research/evaluation/baseline_standalone_llm.py` — bare LLM test
  generation with **no** static-analysis context, isolating whether the
  knowledge-base context actually helps.
- `research/evaluation/metrics.py` — execution time, coverage delta, token
  usage, and an `accuracy` metric that's only populated when a ground-truth
  decision mapping is supplied (there's no way to know the "correct"
  retain/modify/remove/generate call otherwise).
- `run_evaluation.py --config target_repos.yaml` drives all three arms
  across configured repos and writes a comparison CSV.

## Known scope limits

- API endpoints run pipeline calls synchronously (no job queue) — fine for a
  research prototype, worth revisiting before any real multi-user deployment.
- The standalone-LLM baseline doesn't write/execute generated tests, so its
  coverage-delta metric is intentionally left unset (see its docstring).
- `accuracy` in the evaluation harness requires a human-labeled ground-truth
  mapping per repo; without one it's reported as absent, not estimated.

## Running it

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -e ".[dev,ai,eval]"
./.venv/Scripts/python -m pytest

# JS/TS analysis requires Node.js; install the parser bridge's deps once:
cd app/analyzers/javascript/parser_bridge && npm install && cd -
```

### CLI

```bash
python -m app.cli analyze --path tests/fixtures/sample_python_repo   # -> project_id
python -m app.cli classify --project <id>       # needs ANTHROPIC_API_KEY or OPENAI_API_KEY
python -m app.cli apply --project <id>
python -m app.cli run-tests --project <id>       # needs Docker
python -m app.cli detect-changes --project <id>  # project must be --github ingested
python -m app.cli classify-changed --project <id>
```

### API + dashboard

```bash
# from backend/, with the venv active
uvicorn app.main:app --reload   # http://localhost:8000, see /health

# in another terminal
cd frontend && npm install && npm run dev   # http://localhost:5173
```

### Evaluation harness

```bash
cd ..   # repo root
backend/.venv/Scripts/python -m research.evaluation.run_evaluation \
  --config research/evaluation/target_repos.yaml
```
