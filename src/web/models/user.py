"""
Datenschutz-Rechtsprechung API User Model
User-Modell für PostgreSQL mit SQLAlchemy
"""
from flask_login import UserMixin
from sqlalchemy import Column, String, Boolean, DateTime, UUID, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import bcrypt
from datetime import datetime
from typing import Optional
import logging
import os

logger = logging.getLogger(__name__)

# SQLAlchemy Setup für direkte DB-Verbindung (für Auth)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://dsr_user:dsr_password@localhost:5432/datenschutz_rechtsprechung_api",
)
engine = create_engine(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db_session():
    """Create database session"""
    return SessionLocal()


class WebUser(Base, UserMixin):
    """Flask-Login kompatible User-Klasse für Datenschutz-Rechtsprechung API"""

    __tablename__ = "web_users"

    id = Column(UUID, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100))
    first_name = Column(String(50))
    last_name = Column(String(50))
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    department = Column(String(100))
    role = Column(String(50), default="viewer")

    # Flask-Login required methods
    def get_id(self):
        """Flask-Login method to get user ID"""
        return str(self.id)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    # Convenience properties
    @property
    def full_name(self):
        first = self.first_name or ""
        last = self.last_name or ""
        return f"{first} {last}".strip() or self.username

    def check_password(self, password: str) -> bool:
        """Verify password against bcrypt hash"""
        try:
            return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    @classmethod
    def set_password(cls, password: str) -> str:
        """Generate bcrypt password hash"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def to_dict(self) -> dict:
        """Convert user to dictionary (without sensitive data)"""
        return {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "is_admin": self.is_admin,
            "is_active": self.is_active,
            "role": self.role,
            "department": self.department,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

    @classmethod
    def get_by_username(cls, username: str) -> Optional["WebUser"]:
        """Get user by username"""
        try:
            with get_db_session() as session:
                return (
                    session.query(cls)
                    .filter(cls.username == username, cls.is_active == True)
                    .first()
                )
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            return None

    @classmethod
    def get_by_id(cls, user_id: str) -> Optional["WebUser"]:
        """Get user by ID"""
        try:
            with get_db_session() as session:
                return session.query(cls).filter(cls.id == user_id, cls.is_active == True).first()
        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            return None

    @classmethod
    def get_by_email(cls, email: str) -> Optional["WebUser"]:
        """Get user by email"""
        try:
            with get_db_session() as session:
                return session.query(cls).filter(cls.email == email, cls.is_active == True).first()
        except Exception as e:
            logger.error(f"Error getting user by email {email}: {e}")
            return None

    @classmethod
    def authenticate(cls, username: str, password: str) -> Optional["WebUser"]:
        """Authenticate user with username and password"""
        try:
            user = cls.get_by_username(username)
            if user and user.check_password(password):
                # Update last login
                with get_db_session() as session:
                    db_user = session.merge(user)
                    db_user.last_login = datetime.utcnow()
                    session.commit()
                    session.refresh(db_user)
                    user.last_login = db_user.last_login

                logger.info(f"User authenticated successfully: {username}")
                return user
            else:
                logger.warning(f"Authentication failed: {username}")
                return None
        except Exception as e:
            logger.error(f"Authentication error for {username}: {e}")
            return None

    def update_password(self, new_password: str) -> bool:
        """Update user password"""
        try:
            with get_db_session() as session:
                db_user = session.merge(self)
                db_user.password_hash = self.set_password(new_password)
                db_user.updated_at = datetime.utcnow()
                session.commit()
                session.refresh(db_user)
                self.password_hash = db_user.password_hash
                logger.info(f"Password updated for user: {self.username}")
                return True
        except Exception as e:
            logger.error(f"Error updating password for {self.username}: {e}")
            return False

    def __repr__(self):
        return f"<WebUser {self.username}>"


class AuthManager:
    """Authentication Manager für Datenschutz-Rechtsprechung API"""

    @staticmethod
    def authenticate(username: str, password: str) -> Optional[WebUser]:
        """Authenticate user - Wrapper for WebUser.authenticate"""
        return WebUser.authenticate(username, password)

    @staticmethod
    def load_user(user_id: str) -> Optional[WebUser]:
        """Load user by ID - für Flask-Login user_loader"""
        return WebUser.get_by_id(user_id)

    @staticmethod
    def get_user_by_email(email: str) -> Optional[WebUser]:
        """Get user by email - für Password Reset"""
        return WebUser.get_by_email(email)

    @staticmethod
    def create_user(
        username: str,
        email: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
        is_admin: bool = False,
        role: str = "viewer",
    ) -> Optional[WebUser]:
        """Create new user (für Admin-Panel später)"""
        try:
            with get_db_session() as session:
                # Check if user already exists
                existing = (
                    session.query(WebUser)
                    .filter((WebUser.username == username) | (WebUser.email == email))
                    .first()
                )

                if existing:
                    logger.warning(f"User creation failed - already exists: {username}")
                    return None

                # Create new user with SQL to get UUID
                result = session.execute(
                    text(
                        """
                    INSERT INTO web_users (username, email, first_name, last_name, 
                                         password_hash, is_admin, role)
                    VALUES (:username, :email, :first_name, :last_name, 
                           :password_hash, :is_admin, :role)
                    RETURNING id
                    """
                    ),
                    {
                        "username": username,
                        "email": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "password_hash": WebUser.set_password(password),
                        "is_admin": is_admin,
                        "role": role,
                    },
                )
                user_id = result.fetchone()[0]
                session.commit()

                logger.info(f"User created successfully: {username} ({user_id})")
                return WebUser.get_by_id(str(user_id))

        except Exception as e:
            logger.error(f"Error creating user {username}: {e}")
            return None

    @staticmethod
    def test_connection() -> bool:
        """Test database connection"""
        try:
            with get_db_session() as session:
                result = session.execute(text("SELECT COUNT(*) FROM web_users"))
                count = result.fetchone()[0]
                logger.info(f"Database connection test successful - {count} users")
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
