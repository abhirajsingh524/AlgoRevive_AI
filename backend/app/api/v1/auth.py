from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, get_database
from app.core.errors import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse
from app.services.audit_service import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    req: UserRegisterRequest,
    db: Session = Depends(get_database),
) -> User:
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == req.email.lower()).first()
    if existing_user:
        raise AppException(
            status_code=400,
            detail="Email already registered",
            code="EMAIL_ALREADY_REGISTERED",
        )

    hashed_pw = hash_password(req.password)
    user = User(
        email=req.email.lower(),
        hashed_password=hashed_pw,
        full_name=req.full_name,
        is_active=True,
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Log audit
    log_audit(
        db=db,
        user_id=user.id,
        action="REGISTER",
        entity="user",
        entity_id=user.id,
        meta={"email": user.email},
    )

    return user


@router.post("/login", response_model=TokenResponse)
def login(
    req: UserLoginRequest,
    db: Session = Depends(get_database),
) -> TokenResponse:
    user = db.query(User).filter(User.email == req.email.lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise AppException(
            status_code=401,
            detail="Invalid credentials",
            code="INVALID_CREDENTIALS",
        )

    if not user.is_active:
        raise AppException(
            status_code=403,
            detail="User account is disabled",
            code="USER_INACTIVE",
        )

    access_token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role}
    )

    # Log audit
    log_audit(
        db=db,
        user_id=user.id,
        action="LOGIN",
        entity="user",
        entity_id=user.id,
        meta={"email": user.email},
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
