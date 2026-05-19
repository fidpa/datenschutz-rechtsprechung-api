"""
Token Management für Password Reset
Token-Modelle für Datenschutz-Rechtsprechung API
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID, INET
from datetime import datetime, timedelta
from typing import Optional
import secrets
import logging

from .user import Base, get_db_session, WebUser

logger = logging.getLogger(__name__)


class WebAuthToken(Base):
    """Authentication tokens for password reset, etc."""

    __tablename__ = "web_auth_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(100), unique=True, nullable=False)
    user_id = Column(UUID, ForeignKey("web_users.id"), nullable=False)
    token_type = Column(String(20), default="password_reset")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    used_at = Column(DateTime)
    ip_address = Column(INET)
    user_agent = Column(Text)

    # Relationship (falls ORM-Queries nötig werden)
    # user = relationship("WebUser", backref="auth_tokens")

    @classmethod
    def create_reset_token(cls, user_id: str, expires_hours: int = 1) -> Optional[str]:
        """Create password reset token"""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

            with get_db_session() as session:
                # Invalidate old tokens for this user
                session.execute(
                    text(
                        """
                    UPDATE web_auth_tokens 
                    SET used = true, used_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id 
                      AND token_type = 'password_reset' 
                      AND used = false
                    """
                    ),
                    {"user_id": user_id},
                )

                # Create new token
                session.execute(
                    text(
                        """
                    INSERT INTO web_auth_tokens 
                    (token, user_id, token_type, expires_at)
                    VALUES (:token, :user_id, 'password_reset', :expires_at)
                    """
                    ),
                    {"token": token, "user_id": user_id, "expires_at": expires_at},
                )
                session.commit()

                logger.info(f"Password reset token created for user {user_id}")
                return token

        except Exception as e:
            logger.error(f"Error creating reset token: {e}")
            return None

    @classmethod
    def validate_reset_token(cls, token: str) -> Optional["WebUser"]:
        """Validate and return user for reset token"""
        try:
            with get_db_session() as session:
                result = session.execute(
                    text(
                        """
                    SELECT u.id, u.username, u.email, u.first_name, u.last_name,
                           u.password_hash, u.is_admin, u.is_active, u.created_at,
                           u.last_login, u.department, u.role
                    FROM web_auth_tokens t
                    JOIN web_users u ON t.user_id = u.id
                    WHERE t.token = :token
                      AND t.token_type = 'password_reset'
                      AND t.used = false
                      AND t.expires_at > CURRENT_TIMESTAMP
                      AND u.is_active = true
                    """
                    ),
                    {"token": token},
                )

                row = result.fetchone()
                if row:
                    # Manually create WebUser object
                    from .user import WebUser

                    user = WebUser()
                    user.id = row[0]
                    user.username = row[1]
                    user.email = row[2]
                    user.first_name = row[3]
                    user.last_name = row[4]
                    user.password_hash = row[5]
                    user.is_admin = row[6]
                    user.is_active = row[7]
                    user.created_at = row[8]
                    user.last_login = row[9]
                    user.department = row[10]
                    user.role = row[11]

                    logger.info(f"Valid reset token found for user: {user.username}")
                    return user

                logger.warning(f"Invalid or expired reset token: {token[:10]}...")
                return None

        except Exception as e:
            logger.error(f"Error validating reset token: {e}")
            return None

    @classmethod
    def use_token(cls, token: str, ip_address: str = None, user_agent: str = None) -> bool:
        """Mark token as used"""
        try:
            with get_db_session() as session:
                result = session.execute(
                    text(
                        """
                    UPDATE web_auth_tokens 
                    SET used = true, used_at = CURRENT_TIMESTAMP,
                        ip_address = :ip_address, user_agent = :user_agent
                    WHERE token = :token AND used = false
                    """
                    ),
                    {"token": token, "ip_address": ip_address, "user_agent": user_agent},
                )
                session.commit()

                if result.rowcount > 0:
                    logger.info(f"Token marked as used: {token[:10]}...")
                    return True
                else:
                    logger.warning(f"Token not found or already used: {token[:10]}...")
                    return False

        except Exception as e:
            logger.error(f"Error using token: {e}")
            return False

    @classmethod
    def cleanup_expired_tokens(cls) -> int:
        """Clean up expired tokens (für Maintenance)"""
        try:
            with get_db_session() as session:
                result = session.execute(
                    text(
                        """
                    DELETE FROM web_auth_tokens 
                    WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '7 days'
                    """
                    )
                )
                count = result.rowcount
                session.commit()

                if count > 0:
                    logger.info(f"Cleaned up {count} expired tokens")
                return count

        except Exception as e:
            logger.error(f"Error cleaning up expired tokens: {e}")
            return 0

    @classmethod
    def get_token_stats(cls) -> dict:
        """Get token statistics (für Admin Dashboard)"""
        try:
            with get_db_session() as session:
                result = session.execute(
                    text(
                        """
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE used = false) as active,
                        COUNT(*) FILTER (WHERE used = true) as used,
                        COUNT(*) FILTER (WHERE expires_at < CURRENT_TIMESTAMP) as expired
                    FROM web_auth_tokens
                    WHERE token_type = 'password_reset'
                    """
                    )
                )
                row = result.fetchone()

                return {
                    "total": row[0] or 0,
                    "active": row[1] or 0,
                    "used": row[2] or 0,
                    "expired": row[3] or 0,
                }

        except Exception as e:
            logger.error(f"Error getting token stats: {e}")
            return {"total": 0, "active": 0, "used": 0, "expired": 0}
