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
- A passing schema only proves the `code` field is a *string*, so
  `ai_engine/code_validation.py` checks the string itself before it can
  reach disk: Python is parsed with `ast`, and a response that emitted
  `\n` as two literal characters (which collapses a whole test onto one
  unparseable line) is unescaped only when that demonstrably fixes the
  parse, so a repair is never applied on a guess.
  `unresolved_repo_import()` resolves each `from <repo module> import ...`
  against the target repo and rejects a symbol that module doesn't
  define — the hallucinated-class case that otherwise only surfaces once
  the suite runs. It's deliberately conservative, since a false rejection
  costs a component its test: it descends into conditional blocks (plenty
  of libraries define their API inside `if PY3:`), skips modules that bind
  names dynamically or that it can't resolve to a file, and ignores stdlib
  and third-party imports entirely. `complete_structured()` takes a
  `postprocess` hook, so these semantic rejections get the same corrective
  retry that schema mismatches already had.
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
- Applying isolates each recommendation (`app/jobs/pipeline.py`): if
  generation or the write fails, that one recommendation is stored with the
  `"failed"` status and a `failure_reason` and the run continues, instead of
  one bad component discarding every test already written in a long,
  paid-for loop.
- `test_runner/` executes the target repo's suite (pytest/Jest today)
  **inside an isolated, network-disabled Docker container**; it fails
  loudly rather than ever falling back to running untrusted code on the
  host if Docker isn't available. "Available" means the daemon answers, not
  that the binary exists: `docker_available()` probes it with `docker info`,
  because an installed-but-stopped Docker Desktop leaves the CLI on `PATH`
  while every `docker run` fails, and `docker_unavailable_reason()`
  distinguishes "not on PATH" from "daemon down" in the message. A
  `docker run` that exits 125/126/127 (the run itself failed, or the command
  wasn't invocable) raises `ContainerExecutionError`, so a container that
  never started can't be mistaken for a suite that ran and reported
  nothing — a non-zero exit from the test command itself is a real result
  and returns normally. `base.overall_status()` likewise reports a run with
  zero test results as `error`, never `passed`: no failures is only good
  news when something actually ran. Java/C++/Go/C# don't have a registered
  runner yet — `run_tests()` raises a clear `ValueError` for them rather
  than silently doing nothing (see Known scope limits).
- The suite runs with networking disabled, so its tooling can't be installed
  from inside the run — `sandbox_exec.ensure_runner_image()` bakes
  pytest/coverage (or jest) into a `retestify-runner:*` image once, at build
  time, where there *is* a network. Installing at run time instead was the
  original design and could never work: pip got
  `Temporary failure in name resolution` every time, and the resulting
  empty run was then reported as a pass.
- `run_tests()` persists each `RunResult` to `kb/runs.json`, and
  `GET /projects/{id}/report` carries the latest one, so the dashboard can
  show pass counts and coverage without re-running a suite.
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
  (projects, recommendations, jobs, changes, runs, reports, risks,
  companies, webhooks).
- `app/jobs/queue.py` — the slow calls run on a background thread pool:
  `classify` and `apply` return `202` with the job record and a `Location`
  header, and the webhook acknowledges the push immediately with its job id;
  clients poll `GET /jobs/{id}` for status and `processed`/`total`
  progress. Applying routinely runs for minutes, so
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
  Recommendation cards carry an applied/failed/rejected badge (a failed one
  shows its `failure_reason` in place of the now-stale rationale), the
  summary strip counts applied/failed, and the buttons poll their job and
  report live progress ("Applying... 12/29") instead of freezing for the
  length of the run.
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
- `detect-changes`, `classify-changed`, `assess-risks` and `run-tests` are
  still synchronous API calls. Most are much shorter than classify/apply,
  but `classify-changed` is an LLM call per changed component (it only runs
  as a job when a webhook triggers it, not when called directly) and
  `run-tests` grows with the target suite, so both could join the queue.
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

`POST /projects/{id}/classify` and `POST /projects/{id}/apply` return `202`
with a job record (and a `Location` header) rather than the results —
poll `GET /jobs/{id}` until its status is `succeeded`/`failed`, reading
`processed`/`total` for progress, then fetch
`GET /projects/{id}/recommendations` as usual. A second job for the same
project while one is active returns `409`. The dashboard's buttons do
exactly this; the CLI still runs both in-process and blocks.

### Evaluation harness

```bash
cd ..   # repo root
backend/.venv/Scripts/python -m research.evaluation.run_evaluation \
  --config research/evaluation/target_repos.yaml
```
