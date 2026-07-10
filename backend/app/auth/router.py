from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.users.models import User
from app.licenses.models import LicensePlan, UserLicense
from app.auth.jwt import verify_password, get_password_hash, create_access_token
from app.auth.dependencies import get_current_admin

router = APIRouter(prefix="/auth", tags=["auth"])


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован"
        )

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    # Check if this is the first user (auto-admin)
    user_count = db.query(User).count()

    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Этот email уже зарегистрирован"
        )

    # First user becomes admin
    role = "admin" if user_count == 0 else "user"

    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=role,
        is_active=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Auto-assign default plan (e.g. Trial) if one is configured
    default_plan = db.query(LicensePlan).filter(
        LicensePlan.is_default == True,
        LicensePlan.is_active == True
    ).first()

    if default_plan:
        now = datetime.now(timezone.utc)
        default_license = UserLicense(
            user_id=user.id,
            plan_id=default_plan.id,
            starts_at=now,
            expires_at=now + timedelta(days=default_plan.duration_days),
            is_active=True,
        )
        db.add(default_license)
        db.commit()

    return user
