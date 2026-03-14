# pyre-ignore-all-errors
from arkashri.models import ClientRole
from arkashri.services.security import build_system_context, hash_api_key


def test_hash_api_key_is_stable() -> None:
    raw_key = "ark_example_key"
    first = hash_api_key(raw_key)
    second = hash_api_key(raw_key)

    assert first == second
    assert len(first) == 64


def test_build_system_context_is_admin() -> None:
    ctx = build_system_context()
    assert ctx.is_system is True
    assert ctx.role == ClientRole.ADMIN
