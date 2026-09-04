from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.domain.users.enums import AuthProvider


def test_phase2_tables_are_registered_in_metadata() -> None:
    assert {"users", "auth_identities", "auth_refresh_tokens", "projects", "assets"}.issubset(Base.metadata.tables)


def test_identity_model_is_provider_extensible() -> None:
    assert {item.value for item in AuthProvider} == {"telegram", "email", "google", "apple"}
