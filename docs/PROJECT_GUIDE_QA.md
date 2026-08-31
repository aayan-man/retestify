# Answers to the Project Guide's Review Questions

This document answers the five questions raised in project review, with
citations to the literature and pointers to exactly where each answer is
implemented and tested in this repo. A summary table is first; each
question is expanded below with the research grounding.

## Summary

| # | Question | Status |
|---|---|---|
| 1 | Why is your model better than a standalone LLM? | **Included** — directly measured via a baseline comparison arm |
| 2 | Deployment testing | **Added this pass** — `app/deployment_testing/` |
| 3 | Performance testing | **Added this pass** — `app/performance_testing/` |
| 4 | Recurring-problem prediction on the same codebase | **Added this pass** — `app/risk_prediction/` |
| 5 | Personalized testing model for companies | **Added this pass** — `app/personalization/` |

Questions 2–5 were genuine gaps before this pass — they are not just
documentation, but new modules with unit and integration tests (see
`backend/tests/unit/test_deployment_checker.py`,
`test_performance_risk_analyzer.py`, `test_risk_prediction.py`,
`test_personalization.py`, and `tests/integration/test_risk_assessment.py`).

---

## 1. Why is Retestify better than "just asking an LLM"?

**Claim:** grounding test generation/review in static-analysis context
(component signatures, existing test mappings, git diffs, call graphs)
produces more reliable output than prompting an LLM with raw file content
alone.

**How this is actually measured, not just asserted:**
`research/evaluation/baseline_standalone_llm.py` is a second, real
implementation that takes the *same* pluggable `LLMProvider`
(`app/ai_engine/providers/base.py`) and prompts it with nothing but raw
source text — no knowledge base, no test mapping, no change context. The
framework's own arm (`research/evaluation/run_framework.py`) and the
standalone arm are run against the same repos in
`research/evaluation/run_evaluation.py`, and `metrics.py` reports execution
time, token cost, and coverage delta for both, so the "is context worth
it" question is answered by a controlled comparison, not a claim.

**Why the literature supports this design:**
- Context-window and retrieval limits mean a bare LLM prompt over a large
  file can produce "syntactically valid but semantically incomplete tests
  that fail to capture ... trust relationships" — [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://arxiv.org/html/2510.05381v1).
- Repository-level, retrieval-augmented approaches to code generation
  consistently outperform standalone prompting on repo-scale tasks — [Retrieval-Augmented Code Generation: A Survey with Focus on Repository-Level Approaches](https://arxiv.org/html/2510.04905v1).
- An experience paper on LLM-based unit test generation found that
  supplying the right *context* (not a bigger model) was the deciding
  factor in practical reliability — [Context Matters: Improving the Practical Reliability of LLM-Based Unit Test Generation](https://arxiv.org/html/2607.19682).
- Retestify's knowledge base (`app/knowledge_base/schema.py`) is arguably a
  *stronger* form of this than typical RAG: instead of similarity-search
  retrieval (which the RAG literature notes can "saturate or even
  degrade" as more documents are added — [Enhancing LLMs with RAG for Software Testing and Inspection Automation](https://arxiv.org/html/2604.15270)), it's deterministic static analysis —
  the exact function signature, its exact existing tests, its exact
  complexity metrics — so there's no retrieval-relevance failure mode to
  begin with.

**What to report to the guide:** run
`research/evaluation/run_evaluation.py` with an API key configured, with
`target_repos.yaml` listing `[framework, standalone_llm]` for a couple of
repos, and cite the resulting coverage-delta and token-cost columns
directly — that's your evidence, not just a citation list.

---

## 2. Deployment testing

**What was missing:** nothing checked whether an analyzed repo was
actually safe/ready to deploy — Retestify only reasoned about test
coverage.

**What was added:** `app/deployment_testing/checker.py` runs four static,
pre-deploy readiness checks over the target repo (no actual deployment
happens — this is static analysis, consistent with the rest of the
architecture):

1. **Secret exposure** — regex scan for AWS-key-shaped strings,
   Anthropic/OpenAI-key-shaped strings, and generic
   `password/secret/api_key = "..."` literals.
2. **Dependency pinning** — unpinned `requirements.txt` entries, missing
   `package-lock.json`/`yarn.lock`/`pnpm-lock.yaml`.
3. **Undocumented environment variables** — variables read via
   `os.getenv`/`os.environ.get`/`process.env.X` that never appear in
   `.env.example`/`README.md`, so a deploy would silently misconfigure.
4. **Missing CI/container setup** — flagged only once a repo has enough
   surface area (≥10 components) that manual deploys become genuinely
   risky.

Each finding is a `DeploymentIssue` (`app/knowledge_base/schema.py`),
persisted to `kb/deployment_issues.json`, exposed via
`POST /projects/{id}/assess-risks` and `GET /projects/{id}/deployment-issues`,
and printed by `python -m app.cli assess-risks --project <id>`.

**Literature grounding:** the CI/CD literature converges on exactly these
categories — "execute environment specific verification tests ... before
any production push", "use infrastructure as code to eliminate
configuration drift", and automated quality gates blocking defective
builds — see the [GitLab CI/CD best practices post](https://about.gitlab.com/blog/how-to-keep-up-with-ci-cd-best-practices/), the [Copado CI/CD pipeline testing guide](https://www.copado.com/resources/blog/the-ci-cd-pipeline-why-testing-is-required-at-every-stage), and [The Future of Software Testing: AI-Powered Test Case Generation and Validation](https://arxiv.org/pdf/2409.05808).

---

## 3. Performance testing

**What was missing:** nothing looked at runtime characteristics — only
correctness (pass/fail) and coverage.

**What was added:** `app/performance_testing/risk_analyzer.py` performs
static performance-risk triage over the same `Component` metrics the rest
of the pipeline already computes (LOC, cyclomatic complexity, nesting
depth, calls — no new parsing needed):

- **Nested loops** (`nesting_depth ≥ 2` combined with complexity ≥ 4) →
  plausible O(n²)+ hot path.
- **High-complexity hot path** (`cyclomatic_complexity ≥ 15`) — complexity
  is correlated with both defect rate and unpredictable runtime.
- **Unbounded recursion** — a component that calls itself, flagged to
  verify a base case / consider memoization.

This is deliberately a *triage* step, not a benchmark runner: it tells you
**where** to add a real benchmark, consistent with the empirical finding
that fewer than 0.4% of open-source projects maintain performance
benchmarks at all — [regression benchmarking research summary]. Actually running microbenchmarks
is a natural extension of the existing sandboxed `test_runner/` (e.g. wiring
`pytest-benchmark`/`jest --testPathPattern=bench` through the same
Docker-isolated execution path used for correctness tests) — left as a
documented extension point rather than built now, since it needs Docker
(unavailable in the dev sandbox this was built in) to verify safely.

Findings are `PerformanceRisk` records, persisted to
`kb/performance_risks.json`, exposed via the same `assess-risks`
endpoint/CLI command as deployment issues.

**Literature grounding:** performance-regression detection research
frames this exact "flag likely-hot components, prioritize benchmarking
effort" approach as the practical alternative to exhaustively benchmarking
everything — see [A Combined Approach to Performance Regression Testing Resource Usage Reduction](https://dl.acm.org/doi/10.1145/3727582.3728690) and [Applying test case prioritization to software microbenchmarks](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8550681/), which note microbenchmark suites take
"considerably longer to execute" than unit tests, making prioritization
valuable.

---

## 4. "If the same codebase comes again, predict what problems it can face"

**What was missing:** two things, actually. First, no pattern-based risk
prediction existed at all. Second — and this was a real bug, not just a
gap — `pipeline.detect_changes` **overwrote** `kb/changes.json` on every
run instead of accumulating history, which made "has this component
changed a lot over time" unanswerable in principle, since only the latest
diff was ever kept. Fixed in `app/jobs/pipeline.py::detect_changes` (now
appends to history).

**What was added:** `app/risk_prediction/` has two detectors that both
answer "what is this codebase likely to face again":

- `pattern_detector.py` — structural code-smell detection: **God Class**
  (too many methods), **God Method** (high LOC + complexity), **long
  parameter list**, **deep nesting**. These are the smells the
  defect-prediction literature calls out as the most consistently
  effective predictors, not just "code smells in general."
- `churn_risk.py` — **code churn**: components modified repeatedly across
  the project's accumulated `ChangeRecord` history are flagged as
  high-risk. This is the literal "same codebase keeps coming back" signal
  — it only has teeth once a project has been through `detect_changes`
  more than once, which is exactly the "recurring" scenario the question
  describes.

Both produce `PredictedRisk` records (`kb/predicted_risks.json`), surfaced
the same way as the other risk categories. A component id embeds its
source line number, which shifts on unrelated edits elsewhere in the file
— `churn_risk._component_key()` strips that so repeated edits to the
*same* logical component are actually counted as the same component across
snapshots, rather than looking like N different one-off changes.

**Literature grounding:**
- Code smells are "positively correlated with software defects" and God
  Class/God Method/Message Chains are specifically called out as the most
  effective smells for prediction — [Software Defect Prediction Using Bad Code Smells: A Systematic Literature Review](https://link.springer.com/chapter/10.1007/978-3-030-34706-2_5).
- Code churn (modification frequency) is one of the most established
  defect-density predictors in the empirical software engineering
  literature — the "repeat offenders" framing is discussed directly in
  [The Repeat Offenders: Characterizing and Predicting Extremely Bug-Prone Source Methods](https://arxiv.org/pdf/2511.22726), and technical-debt research frames recurring
  modification as the primary symptom of accumulating debt.

---

## 5. Personalized testing model for companies

**What was missing:** every company got identical prompts and identical
risk thresholds — no way to encode "our team prefers pytest fixtures over
setUp/tearDown" or "our complexity tolerance is stricter than default."

**What was added:** `app/personalization/profile.py` defines a
`CompanyProfile` (style guide text, preferred frameworks per language,
complexity/churn risk thresholds, minimum confidence for auto-apply),
loaded from `backend/config/companies/{company_id}.json` (see the
committed `example-corp.json`). It's wired into three places:

- **Prompts** — `prompt_builder.build_generation_prompt`/
  `build_improvement_prompt` append the company's `style_guide` text to
  the system prompt (`app/ai_engine/generator.py` threads a
  `CompanyProfile` through), so generated/improved tests follow that
  org's conventions.
- **Risk thresholds** — `pipeline.assess_risks(project_id, company_id=...)`
  uses the profile's `complexity_risk_threshold`/`churn_risk_threshold`
  instead of the defaults.
- **API/CLI** — `PUT /companies/{id}` to create/update a profile,
  `apply --company <id>` and `assess-risks --company <id>` on the CLI, and
  the same `company_id` field on the `/apply` and `/assess-risks` API
  routes.

**Why prompt-injection rather than fine-tuning:** the personalization
literature notes that most organizations don't fine-tune a separate model
per customer — style/convention alignment via context is the practical
lever, and prompt-level personalization has direct precedent, e.g.
[MPCODER: Multi-user Personalized Code Generator with Explicit and Implicit Style Representation Learning](https://arxiv.org/pdf/2406.17255), which explicitly separates
"explicit" style rules (which map cleanly onto a text style guide) from
implicit semantic style. Given Retestify already has a pluggable,
swappable `LLMProvider`, adding a per-company fine-tuned model later is a
natural extension of the same interface — not a redesign.

---

## What's still an honest gap

- Performance testing is triage, not execution — no benchmark actually
  runs yet (needs Docker; see §3).
- Churn-based risk prediction needs a project to have been re-analyzed via
  `detect_changes` more than once before it produces anything — a
  brand-new project has no history to learn from yet, by definition.
- Personalization only affects prompts and thresholds, not the underlying
  model weights — see the fine-tuning note in §5.
