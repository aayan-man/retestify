# Retestify

AI-driven test case management framework.
Ingests a target repository (GitHub URL or ZIP), statically analyzes its source
and existing tests, and uses a pluggable AI Review Engine to decide which
tests to retain, modify, remove, or generate — with git-aware incremental
re-analysis, a dashboard, CI/CD hooks, and a research evaluation harness.

New here? See [GETTING_STARTED.md](GETTING_STARTED.md) for a full step-by-step
setup walkthrough (this README's "Running it" section below is the quick
reference). See [docs/PROJECT_GUIDE_QA.md](docs/PROJECT_GUIDE_QA.md) for a
research-cited write-up of deployment testing, performance testing,
recurring-risk prediction, per-company personalization, and why grounding
the AI Review Engine in static-analysis context beats a standalone LLM.

## Status

All 8 planned phases have an initial implementation:

**Core pipeline (Phases 1-5)**
- **Repo manager** — ingest from a local directory, `.zip` (zip-slip/size
  guarded), or GitHub URL (shallow clone).
- **Tech detector** — Python/pytest/unittest, JavaScript-TypeScript/Jest/Mocha,
  Java/JUnit, C++/GoogleTest/Catch2, Go/testing, C#/xUnit/NUnit/MSTest.
- **Static analyzers** (pluggable, `app/analyzers/base.py`) — Python via
  stdlib `ast`; JS/TS via a Node/`@babel/parser` bridge
  (`app/analyzers/javascript/parser_bridge/parse.js`); Java/C++/Go/C# share
  one `tree-sitter`-based implementation
  (`app/analyzers/treesitter/base.py`) with per-language node-type specs
  (`app/analyzers/{java,cpp,go,csharp}/analyzer.py`). All extract
  functions/classes/methods with metrics and content hashing.
- **Test analyzer** — discovers tests and maps them to source components by
  naming convention. Python tests are `test_*` functions; JS/TS tests are
  `test()`/`it()` calls; Java/C# tests are methods carrying a test
  annotation/attribute (`@Test`, `[Fact]`, `[Test]`, `[TestMethod]`); C++
  tests are `TEST`/`TEST_F`/`TEST_CASE` macro invocations; Go tests are
  `Test*` functions in `*_test.go` files — each handled by that analyzer's
  own `list_test_cases`.
- **Knowledge base** — Component/TestCase/ChangeRecord/Recommendation
  (pydantic), persisted as JSON under `backend/workspace/{project_id}/kb/`.

**AI Review Engine (Phases 3-4)**
- Pluggable `LLMProvider` interface (`app/ai_engine/providers/`) — Anthropic,
  or any OpenAI-compatible endpoint (including local models via `base_url`).
- `decision_engine` classifies each component's tests as retain/modify/remove
  (or generate, if none are mapped); `generator` writes new/improved tests as
  schema-validated, retry-on-failure structured output.
- `test_writer/` writes generated code per language. Python/JS/TS/Go/C++
  append a free-standing test to the conventional file; Java/C# use
  `test_writer/common.py::insert_method_into_class` since a bare test
  method isn't valid outside a class in those languages — it inserts into
  an existing test class or creates a minimal one. Existing test files are
  never rewritten in place.
- Each generated test brings its own imports, so `test_writer/
  python_imports.py` strips the ones the target file already has before
  appending — otherwise a file accumulates one `import pytest` per
  generated test (a real run reached twenty). It only drops a statement
  when every name it binds is already available, leaves imports scoped
  inside functions alone, and never touches the rest of the block, so
  comments and formatting survive. Python only; the other languages still
  append verbatim.
- `test_runner/` executes the target repo's suite (pytest/Jest today)
  **inside an isolated, network-disabled Docker container**; it fails
  loudly rather than ever falling back to running untrusted code on the
  host if Docker isn't available. Java/C++/Go/C# don't have a registered
  runner yet — `run_tests()` raises a clear `ValueError` for them rather
  than silently doing nothing (see Known scope limits).
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
- `app/jobs/queue.py` — the slow calls (`classify`, `apply`, and the
  webhook's pull-and-reclassify) return `202` with a job id and run on a
  background thread pool; clients poll `GET /jobs/{id}` for status and
  `processed`/`total` progress. Applying routinely runs for minutes, so
  holding the request open risked a proxy or browser timeout discarding a
  whole paid-for run — and GitHub's delivery timeout is far shorter than a
  reclassify takes. One job at a time per project, since the knowledge base
  is JSON files that concurrent runs would interleave writes into.
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

**Deployment/performance/risk assessment & personalization**
- `app/deployment_testing/checker.py` — static pre-deploy checks: hardcoded
  secrets, unpinned dependencies, undocumented required env vars, missing
  CI/container setup.
- `app/performance_testing/risk_analyzer.py` — static performance-risk
  triage (nested loops, high-complexity hot paths, unbounded recursion)
  from the same component metrics the analyzers already compute.
- `app/risk_prediction/` — structural code-smell detection (God Class/God
  Method/long parameter list/deep nesting) plus code-churn risk from this
  project's accumulated `ChangeRecord` history — the "what will this
  codebase face again" signal.
- `app/personalization/profile.py` — per-company `CompanyProfile`
  (style-guide text injected into generation prompts, plus threshold
  overrides), loaded from `backend/config/companies/*.json`.
- All four are wired into `pipeline.assess_risks()`, the
  `POST /projects/{id}/assess-risks` API route, and
  `python -m app.cli assess-risks --project <id> [--company <id>]`. See
  [docs/PROJECT_GUIDE_QA.md](docs/PROJECT_GUIDE_QA.md) for the research
  grounding behind each one.

## Known scope limits

- The job queue (`app/jobs/queue.py`) is in-process: job records live in
  memory, so a restart loses job *history* and running more than one worker
  process would give each its own queue. Results themselves are always
  persisted to the knowledge base by the pipeline, so a lost job record
  never means lost work. A shared broker would be the next step for a
  multi-process deployment.
- `detect-changes`, `assess-risks` and `run-tests` are still synchronous
  API calls; they're much shorter than classify/apply, but `run-tests` in
  particular could join the queue if suites get slow.
- The standalone-LLM baseline doesn't write/execute generated tests, so its
  coverage-delta metric is intentionally left unset (see its docstring).
- `accuracy` in the evaluation harness requires a human-labeled ground-truth
  mapping per repo; without one it's reported as absent, not estimated.
- Performance testing is static triage, not benchmark execution (needs
  Docker; see docs/PROJECT_GUIDE_QA.md §3).
- Churn-based risk prediction needs `detect_changes` to have run more than
  once on a project before it has any history to learn from.
- Java/C++/Go/C# support covers analysis, test discovery, classification,
  and generation — but not sandboxed execution yet (`run-tests` only has a
  registered runner for Python/JS today). Adding one is the natural next
  step (Maven/CTest/`go test -json`/`dotnet test`, each in its own Docker
  image, following the existing `test_runner/pytest_runner.py` pattern) but
  wasn't built without a way to verify it end-to-end in this environment.
- The Go analyzer treats a top-level `struct` as a class-equivalent so
  method→struct linkage and God-Class detection work, but Go doesn't
  actually have classes — this is a deliberate approximation, not a claim
  about Go's type system.
- Java's test-file placement assumes the common Maven/Gradle
  `src/main/java` → `src/test/java` layout; repos that don't follow it get
  a same-directory fallback instead.

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
