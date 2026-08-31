from __future__ import annotations

import argparse
import csv
import dataclasses
from pathlib import Path

import yaml

from .baseline_manual import run_manual_baseline
from .baseline_standalone_llm import run_standalone_llm_baseline
from .metrics import RunMetrics
from .run_framework import run_framework


def run_all(config_path: str, provider_name: str | None = None) -> list[RunMetrics]:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    results: list[RunMetrics] = []

    for entry in config.get("repos", []):
        github_url = entry.get("github_url")
        path = entry.get("path")
        language = entry.get("language", "python")

        for variant in entry.get("variants", ["framework"]):
            if variant == "framework":
                results.append(
                    run_framework(repo_path=path, github_url=github_url, provider_name=provider_name, language=language)
                )
            elif variant == "manual":
                results.append(run_manual_baseline(repo_path=path, github_url=github_url, language=language))
            elif variant == "standalone_llm":
                from app.ai_engine.providers.factory import get_provider

                results.append(
                    run_standalone_llm_baseline(get_provider(provider_name), repo_path=path, github_url=github_url)
                )
            else:
                raise ValueError(f"unknown variant {variant!r} for repo {github_url or path!r}")

    return results


def _write_csv(results: list[RunMetrics], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in dataclasses.fields(RunMetrics)]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = dataclasses.asdict(r)
            row["decision_counts"] = str(row["decision_counts"])
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the comparative evaluation study across configured repos.")
    parser.add_argument("--config", default=str(Path(__file__).parent / "target_repos.yaml"))
    parser.add_argument("--provider", choices=["anthropic", "openai"])
    parser.add_argument("--out", default=str(Path(__file__).parent / "results" / "results.csv"))
    args = parser.parse_args()

    results = run_all(args.config, provider_name=args.provider)
    out_path = Path(args.out)
    _write_csv(results, out_path)

    for r in results:
        cov = (
            f"{r.coverage_before:.1f}% -> {r.coverage_after:.1f}%"
            if r.coverage_before is not None and r.coverage_after is not None
            else "n/a"
        )
        print(f"[{r.variant:24}] {r.repo}  time={r.execution_time_s:.1f}s  coverage={cov}  tokens_in={r.total_input_tokens}")

    print(f"\nwrote {len(results)} result(s) to {out_path}")


if __name__ == "__main__":
    main()
