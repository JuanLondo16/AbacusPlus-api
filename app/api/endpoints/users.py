from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from app.models.user import User as models_User
from app.schemas.user import User as schemas_User, UserCreate
from app.core.config import get_db
from app.services.auth import AuthService, ACCESS_TOKEN_EXPIRE_MINUTES
from datetime import datetime,timedelta, timezone

router = APIRouter()

@router.post("/users/", response_model=schemas_User, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    Crea un nuevo usuario.
    
    Args:
        user: Datos del usuario a crear
        db: Sesión de la base de datos
        
    Returns:
        El usuario creado
    
    Raises:
        HTTPException: Si el username o email ya existen
    """
    # Verificar si el username ya existe
    db_user = db.query(models_User).filter(models_User.username == user.username).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Verificar si el email ya existe
    db_user = db.query(models_User).filter(models_User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Crear el usuario
    try:
        db_user = models_User(
            username=user.username,
            email=user.email,
            password=user.password,  # El setter de password maneja el hashing
            full_name=user.full_name,
            tenant_id=user.tenant_id
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        # Convertir el modelo SQLAlchemy a un esquema Pydantic
        return schemas_User.from_orm(db_user)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear el usuario: {str(e)}"
        )

@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Autentica un usuario y devuelve un JWT en una cookie HTTP-only.
    
    Args:
        form_data: Datos del formulario de login
        db: Sesión de la base de datos
        
    Returns:
        Respuesta con cookie HTTP-only
        
    Raises:
        HTTPException: Si las credenciales son incorrectas
    """
    auth_service = AuthService(db)
    user = auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Crear token de acceso
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    
    # Actualizar último login
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Crear respuesta con cookie
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    return {"detail": "Login successful"}