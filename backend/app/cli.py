import argparse
import sys

from app.jobs import pipeline


def main() -> None:
    # LLM output can contain Unicode punctuation (e.g. non-breaking hyphens)
    # that Windows' default console codepage (cp1252) can't encode; fall
    # back to replacement chars instead of crashing the whole command.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_p = sub.add_parser("analyze", help="Ingest and analyze a target repository")
    src = analyze_p.add_mutually_exclusive_group(required=True)
    src.add_argument("--path", help="Local path to a directory or .zip file")
    src.add_argument("--github", help="GitHub repository URL to clone")
    analyze_p.add_argument("--ref", help="Git branch/tag/commit to check out (with --github)")

    classify_p = sub.add_parser(
        "classify", help="Run AI classification (retain/modify/remove/generate) for an analyzed project"
    )
    classify_p.add_argument("--project", required=True, help="project_id from a previous `analyze` run")
    classify_p.add_argument("--provider", choices=["anthropic", "openai"], help="Override the configured AI provider")

    apply_p = sub.add_parser("apply", help="Generate/improve tests for pending recommendations and write them to disk")
    apply_p.add_argument("--project", required=True, help="project_id from a previous `classify` run")
    apply_p.add_argument("--provider", choices=["anthropic", "openai"], help="Override the configured AI provider")
    apply_p.add_argument("--company", help="Company profile id (app/personalization) to apply style-guide/threshold overrides")

    run_p = sub.add_parser("run-tests", help="Execute the target repo's test suite in a sandboxed container")
    run_p.add_argument("--project", required=True, help="project_id from a previous `analyze` run")
    run_p.add_argument("--language", default="python", help="Which test runner to use (default: python)")

    detect_p = sub.add_parser(
        "detect-changes", help="Pull new commits and diff against the stored knowledge base"
    )
    detect_p.add_argument("--project", required=True, help="project_id ingested via --github")

    classify_changed_p = sub.add_parser(
        "classify-changed", help="Incrementally reclassify only components touched by the last detected changes"
    )
    classify_changed_p.add_argument("--project", required=True, help="project_id from a previous `detect-changes` run")
    classify_changed_p.add_argument(
        "--provider", choices=["anthropic", "openai"], help="Override the configured AI provider"
    )

    assess_p = sub.add_parser(
        "assess-risks", help="Deployment-readiness, performance-risk, and defect-proneness prediction (static, no execution)"
    )
    assess_p.add_argument("--project", required=True, help="project_id from a previous `analyze` run")
    assess_p.add_argument("--company", help="Company profile id (app/personalization) to apply threshold overrides")

    args = parser.parse_args()

    if args.command == "analyze":
        workspace = pipeline.ingest_source(path=args.path, github_url=args.github, ref=args.ref)
        summary = pipeline.analyze(workspace)
        print(f"project_id: {summary.workspace.project_id}")
        print(f"workspace:  {summary.workspace.root}")
        print(f"languages:  {summary.stack.languages}")
        print(f"frameworks: {summary.stack.test_frameworks}")
        print(f"components: {summary.component_count}")
        print(f"tests:      {summary.test_count} ({summary.mapped_test_count} mapped)")
        if summary.parse_errors:
            print(f"parse errors ({len(summary.parse_errors)}):")
            for err in summary.parse_errors[:20]:
                print(f"  - {err}")

    elif args.command == "classify":
        recommendations = pipeline.classify_project(args.project, provider_name=args.provider)
        for rec in recommendations:
            print(f"[{rec.decision.upper():8}] {rec.component_id} (confidence={rec.confidence:.2f}) - {rec.rationale}")

    elif args.command == "apply":
        recommendations = pipeline.apply_recommendations(
            args.project, provider_name=args.provider, company_id=args.company
        )
        applied = [r for r in recommendations if r.status == "applied"]
        print(f"applied {len(applied)} recommendation(s)")
        for rec in applied:
            print(f"  {rec.decision}: {rec.generated_test_id}")

    elif args.command == "run-tests":
        result = pipeline.run_tests(args.project, language=args.language)
        print(f"run_id: {result.run_id}")
        print(f"status: {result.status}")
        print(f"passed: {result.passed}  failed: {result.failed}  errors: {result.errors}  skipped: {result.skipped}")
        if result.coverage_percent is not None:
            print(f"coverage: {result.coverage_percent:.1f}%")
        if result.stderr:
            print(f"stderr:\n{result.stderr}")

    elif args.command == "detect-changes":
        changes = pipeline.detect_changes(args.project)
        print(f"{len(changes)} change(s) detected")
        for c in changes:
            print(f"  [{c.change_type.upper():8}] {c.component_id} - {c.diff_summary}")

    elif args.command == "classify-changed":
        recommendations = pipeline.classify_changed_components(args.project, provider_name=args.provider)
        print(f"reclassified {len(recommendations)} affected component(s)")
        for rec in recommendations:
            print(f"[{rec.decision.upper():8}] {rec.component_id} (confidence={rec.confidence:.2f}) - {rec.rationale}")

    elif args.command == "assess-risks":
        assessment = pipeline.assess_risks(args.project, company_id=args.company)
        print(f"deployment issues: {len(assessment.deployment_issues)}")
        for issue in assessment.deployment_issues:
            loc = f"{issue.file_path}:{issue.line}" if issue.line else (issue.file_path or "")
            print(f"  [{issue.severity.upper():6}] {issue.category} {loc} - {issue.message}")
        print(f"performance risks: {len(assessment.performance_risks)}")
        for risk in assessment.performance_risks:
            print(f"  [{risk.severity.upper():6}] {risk.category} {risk.component_id} - {risk.message}")
        print(f"predicted risks: {len(assessment.predicted_risks)}")
        for risk in assessment.predicted_risks:
            print(f"  [{risk.severity.upper():6}] {risk.category} {risk.component_id} - {risk.message}")


if __name__ == "__main__":
    main()
