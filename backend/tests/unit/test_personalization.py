from app.ai_engine.prompts import prompt_builder
from app.personalization.profile import CompanyProfile, load_company_profile


def test_example_company_profile_loads():
    profile = load_company_profile("example-corp")
    assert profile is not None
    assert profile.company_id == "example-corp"
    assert profile.style_guide
    assert profile.complexity_risk_threshold == 8


def test_unknown_company_profile_returns_none():
    assert load_company_profile("does-not-exist-co") is None


def test_style_guide_is_injected_into_system_prompt(tmp_path):
    (tmp_path / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    from app.knowledge_base.schema import Component, ComponentMetrics

    comp = Component(
        id="py:mod.py:add:1",
        project_id="proj_test",
        language="python",
        kind="function",
        name="add",
        qualified_name="mod.add",
        file_path="mod.py",
        line_start=1,
        line_end=2,
        metrics=ComponentMetrics(loc=2, cyclomatic_complexity=1, nesting_depth=0, num_params=2),
        content_hash="sha256:deadbeef",
    )

    system_without, _ = prompt_builder.build_generation_prompt(comp, tmp_path, "pytest")
    system_with, _ = prompt_builder.build_generation_prompt(comp, tmp_path, "pytest", style_guide="Use fixtures.")

    assert "Use fixtures." not in system_without
    assert "Use fixtures." in system_with


def test_company_profile_roundtrip(tmp_path, monkeypatch):
    from app.config import settings
    from app.personalization import profile as profile_module

    monkeypatch.setattr(settings, "workspace_root", tmp_path / "workspace")
    profile = CompanyProfile(company_id="acme", display_name="Acme Inc", style_guide="Be terse.")
    profile_module.save_company_profile(profile)

    loaded = profile_module.load_company_profile("acme")
    assert loaded == profile
    assert any(p.company_id == "acme" for p in profile_module.list_company_profiles())
