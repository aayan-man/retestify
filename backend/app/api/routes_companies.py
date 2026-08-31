from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.personalization.profile import CompanyProfile, list_company_profiles, load_company_profile, save_company_profile

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyProfile])
def list_companies():
    return list_company_profiles()


@router.get("/{company_id}", response_model=CompanyProfile)
def get_company(company_id: str):
    profile = load_company_profile(company_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"no company profile found for id {company_id!r}")
    return profile


@router.put("/{company_id}", response_model=CompanyProfile)
def upsert_company(company_id: str, profile: CompanyProfile):
    if profile.company_id != company_id:
        raise HTTPException(status_code=400, detail="company_id in body must match the URL")
    save_company_profile(profile)
    return profile
