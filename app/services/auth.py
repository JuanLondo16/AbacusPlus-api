from datetime import datetime, timedelta
from typing import Optional, Dict

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import get_db, load_dotenv
from app.models.user import User as models_User
from app.schemas.user import User as schemas_User
import os

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

class AuthService:
    def __init__(self, db: Session = Depends(get_db)):
        self.db = db

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_user(self, username: str) -> Optional[models_User]:
        return self.db.query(models_User).filter(models_User.username == username).first()

    def authenticate_user(self, username: str, password: str) -> Optional[models_User]:
        user = self.get_user(username)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        to_encode.update({"exp": expire})
        try:
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            return encoded_jwt
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error creating access token: {str(e)}"
            )

    def get_current_user(self, token: str = Depends(oauth2_scheme)) -> schemas_User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise credentials_exception
        except jwt.PyJWTError:
            raise credentials_exception
        user = self.get_user(username=username)
        if user is None:
            raise credentials_exception
        return schemas_User.from_orm(user)

    def get_current_active_user(self, current_user: schemas_User = Depends(get_current_user)) -> schemas_User:
        if not current_user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        return current_user
