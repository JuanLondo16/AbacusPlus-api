from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.models.user import User as models_User
from app.schemas.user import User as schemas_User, UserCreate
from app.core.config import get_db

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