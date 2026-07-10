from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.users.models import User
from app.users.schemas import UserCreate, UserUpdate, UserResponse
from app.auth.dependencies import get_current_admin, get_current_user
from app.auth.jwt import get_password_hash
from app.licenses.models import UserLicense

router = APIRouter(prefix="/users", tags=["users"])


def _get_license_info(db: Session, user_id: int) -> dict:
    """Get license status info for a user."""
    now = datetime.now(timezone.utc)
    license = (
        db.query(UserLicense)
        .filter(
            UserLicense.user_id == user_id,
            UserLicense.is_active == True,
        )
        .order_by(UserLicense.expires_at.desc())
        .first()
    )

    if not license:
        return {"license_status": "none", "license_plan_name": None, "license_expires_at": None, "license_badge_color": None}

    plan = license.plan

    if license.expires_at < now:
        return {
            "license_status": "expired",
            "license_plan_name": plan.name,
            "license_expires_at": license.expires_at,
            "license_badge_color": plan.badge_color,
        }

    license_status = "trial" if plan.is_default else "active"

    return {
        "license_status": license_status,
        "license_plan_name": plan.name,
        "license_expires_at": license.expires_at,
        "license_badge_color": plan.badge_color,
    }


def _user_to_response(db: Session, user: User) -> dict:
    """Convert user model to response dict with license info."""
    data = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }
    data.update(_get_license_info(db, user.id))
    return data


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _user_to_response(db, current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    update_data = user_data.model_dump(exclude_unset=True)
    # Don't allow self role/is_active change
    update_data.pop('role', None)
    update_data.pop('is_active', None)
    if 'password' in update_data:
        update_data['hashed_password'] = get_password_hash(update_data.pop('password'))
    for field, value in update_data.items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return _user_to_response(db, current_user)


@router.get("", response_model=List[UserResponse])
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    users = db.query(User).all()
    return [_user_to_response(db, u) for u in users]


@router.post("", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот email уже зарегистрирован"
        )

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return _user_to_response(db, user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    update_data = user_data.model_dump(exclude_unset=True)
    if 'password' in update_data:
        update_data['hashed_password'] = get_password_hash(update_data.pop('password'))
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return _user_to_response(db, user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить самого себя"
        )

    # Delete associated licenses first to avoid FK constraint violation
    db.query(UserLicense).filter(UserLicense.user_id == user_id).delete()
    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}
