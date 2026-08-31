from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from app.config import settings


class CompanyProfile(BaseModel):
    """Per-organization overrides for the AI Review Engine and risk
    analyzers. The literature on LLM code personalization (see
    docs/PROJECT_GUIDE_QA.md) points at style/convention alignment as the
    main lever available without fine-tuning a model per customer — so this
    profile is injected into prompts as text, plus a few numeric threshold
    overrides for the static risk analyzers, rather than requiring a
    separate fine-tuned model per company."""

    company_id: str
    display_name: str
    style_guide: str | None = None  # free-text conventions injected into generation/improvement prompts
    preferred_frameworks: dict[str, str] = Field(default_factory=dict)  # language -> framework override
    complexity_risk_threshold: int = 10
    churn_risk_threshold: int = 3
    min_confidence_for_auto_apply: float = 0.75


def _profiles_dir() -> Path:
    return settings.workspace_root.parent / "config" / "companies"


def load_company_profile(company_id: str) -> CompanyProfile | None:
    path = _profiles_dir() / f"{company_id}.json"
    if not path.exists():
        return None
    return CompanyProfile.model_validate_json(path.read_text(encoding="utf-8"))


def save_company_profile(profile: CompanyProfile) -> None:
    path = _profiles_dir() / f"{profile.company_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")


def list_company_profiles() -> list[CompanyProfile]:
    profiles_dir = _profiles_dir()
    if not profiles_dir.exists():
        return []
    return [
        CompanyProfile.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(profiles_dir.glob("*.json"))
    ]
