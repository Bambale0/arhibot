from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class AuthProvider(StrEnum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"
