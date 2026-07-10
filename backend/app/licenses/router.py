from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta, timezone
from app.database import get_db
from app.auth.dependencies import get_current_user, get_current_admin
from app.users.models import User
from app.licenses.models import LicensePlan, UserLicense
from app.licenses.schemas import (
    LicensePlanCreate, LicensePlanUpdate, LicensePlanResponse,
    UserLicenseResponse, AssignLicenseRequest,
)

router = APIRouter(prefix="/licenses", tags=["licenses"])


@router.get("/plans", response_model=List[LicensePlanResponse])
async def list_active_plans(db: Session = Depends(get_db)):
    """List active plans (public, for purchase modal). Excludes default/registration plans."""
    plans = db.query(LicensePlan).filter(
        LicensePlan.is_active == True,
        LicensePlan.is_default == False
    ).all()
    return plans


@router.get("/plans/all", response_model=List[LicensePlanResponse])
async def list_all_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """List all plans including inactive (admin only)."""
    plans = db.query(LicensePlan).all()
    return plans


@router.post("/plans", response_model=LicensePlanResponse)
async def create_plan(
    plan_data: LicensePlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    data = plan_data.model_dump()

    # Only one plan can be default
    if data.get("is_default"):
        db.query(LicensePlan).filter(LicensePlan.is_default == True).update({"is_default": False})

    plan = LicensePlan(**data)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/plans/{plan_id}", response_model=LicensePlanResponse)
async def update_plan(
    plan_id: int,
    plan_data: LicensePlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    plan = db.query(LicensePlan).filter(LicensePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    update_data = plan_data.model_dump(exclude_unset=True)

    # Only one plan can be default
    if update_data.get("is_default"):
        db.query(LicensePlan).filter(
            LicensePlan.is_default == True,
            LicensePlan.id != plan_id
        ).update({"is_default": False})

    for field, value in update_data.items():
        setattr(plan, field, value)

    db.commit()
    db.refresh(plan)
    return plan


@router.get("/my", response_model=UserLicenseResponse | None)
async def get_my_license(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's active license."""
    now = datetime.now(timezone.utc)
    license = (
        db.query(UserLicense)
        .filter(
            UserLicense.user_id == current_user.id,
            UserLicense.is_active == True,
            UserLicense.expires_at > now
        )
        .order_by(UserLicense.expires_at.desc())
        .first()
    )
    if not license:
        return None

    return UserLicenseResponse(
        id=license.id,
        user_id=license.user_id,
        plan_id=license.plan_id,
        plan_name=license.plan.name,
        starts_at=license.starts_at,
        expires_at=license.expires_at,
        is_active=license.is_active,
        created_at=license.created_at,
    )


@router.post("/assign", response_model=UserLicenseResponse)
async def assign_license(
    data: AssignLicenseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Assign a license to a user (admin only)."""
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    plan = db.query(LicensePlan).filter(LicensePlan.id == data.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Тариф не найден")

    # Deactivate existing active licenses for this user
    db.query(UserLicense).filter(
        UserLicense.user_id == data.user_id,
        UserLicense.is_active == True
    ).update({"is_active": False})

    now = datetime.now(timezone.utc)
    license = UserLicense(
        user_id=data.user_id,
        plan_id=data.plan_id,
        starts_at=now,
        expires_at=now + timedelta(days=plan.duration_days),
        is_active=True,
    )
    db.add(license)
    db.commit()
    db.refresh(license)

    return UserLicenseResponse(
        id=license.id,
        user_id=license.user_id,
        plan_id=license.plan_id,
        plan_name=plan.name,
        starts_at=license.starts_at,
        expires_at=license.expires_at,
        is_active=license.is_active,
        created_at=license.created_at,
    )
