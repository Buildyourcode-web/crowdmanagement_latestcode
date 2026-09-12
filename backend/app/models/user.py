import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.role import Role


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    role: Mapped[Role] = relationship("Role", back_populates="users", lazy="selectin")
    event_accesses: Mapped[List["UserEventAccess"]] = relationship("UserEventAccess", back_populates="user", lazy="noload")
    site_accesses: Mapped[List["UserSiteAccess"]] = relationship("UserSiteAccess", back_populates="user", lazy="noload")

    @property
    def role_code(self) -> Optional[str]:
        rc = getattr(self, "_jwt_role", None)
        if rc:
            return rc
        try:
            return self.role.code if self.role else None
        except Exception:
            return None

    @property
    def role_name(self) -> Optional[str]:
        try:
            return self.role.name if self.role else None
        except Exception:
            return None

    @property
    def permissions_list(self) -> List[str]:
        perms = getattr(self, "_jwt_permissions", None)
        if perms is not None:
            return perms
        try:
            return [p.code for p in self.role.permissions] if self.role and self.role.permissions else []
        except Exception:
            return []

    @property
    def is_super_admin(self) -> bool:
        return self.role_code == "SUPER_ADMIN"

