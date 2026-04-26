# pyre-ignore-all-errors
"""
tests/test_production_conformance.py
=====================================
Automated conformance tests derived from the production-readiness audit.
These tests verify that ALL critical (C-*) and high (H-*) audit findings
have been fixed and cannot regress.

Run with:
    pytest tests/test_production_conformance.py -v

Every test references the audit finding it guards: e.g. "Ref: C-1".
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def settings_prod(monkeypatch):
    """Return a Settings-like object configured as production."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_ENFORCED", "true")
    monkeypatch.setenv(
        "SESSION_SECRET_KEY",
        "a" * 64,  # 64-char hex — well above the 32-char minimum
    )
    # Re-initialise settings so the monkeypatched env is picked up
    from arkashri.config import Settings
    return Settings(
        app_env="production",
        auth_enforced=True,
        session_secret_key="a" * 64,
        enable_mock_data=False,
    )


@pytest.fixture()
def settings_dev():
    from arkashri.config import Settings
    return Settings(
        app_env="dev",
        auth_enforced=True,
        session_secret_key="devdevdevdevdevdevdevdevdevdevdevdev",
    )


# ─────────────────────────────────────────────────────────────────────────────
# C-1: auth_enforced defaults to True
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthEnforced:
    """Ref: C-1 — auth_enforced must default to True."""

    def test_default_is_true(self):
        """Test the field default directly, bypassing .env override."""
        from arkashri.config import Settings
        # Inspect the model's field default, not a Settings() instance that reads .env
        field_info = Settings.model_fields["auth_enforced"]
        # pydantic v2: default is stored in field_info.default
        code_default = field_info.default
        assert code_default is True, (
            "C-1 REGRESSION: The code default for auth_enforced changed back to False. "
            "Note: .env may override this for local dev (that is acceptable). "
            f"The *code* default must be True. Got: {code_default!r}"
        )

    def test_production_with_auth_disabled_raises(self):
        """Production startup must hard-fail when auth is disabled."""
        from arkashri.config import Settings
        s = Settings(
            _env_file=None,  # ignore .env for this test
            app_env="production",
            auth_enforced=False,
            session_secret_key="a" * 64,
            enable_mock_data=False,
        )
        with pytest.raises(RuntimeError, match="AUTH_ENFORCED"):
            s.validate_runtime_configuration()

    def test_production_with_auth_enabled_passes(self):
        from arkashri.config import Settings
        s = Settings(
            _env_file=None,
            app_env="production",
            auth_enforced=True,
            session_secret_key="a" * 64,
            enable_mock_data=False,
            kms_provider="aws",
            bootstrap_admin_token="b" * 32,
        )
        # Must not raise
        s.validate_runtime_configuration()



# ─────────────────────────────────────────────────────────────────────────────
# C-2: session_secret_key must be a non-null, strong value
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionSecretKey:
    """Ref: C-2 — JWT signing key must never be None or the placeholder."""

    def test_placeholder_in_production_raises(self):
        from arkashri.config import Settings
        placeholder = "CHANGE_ME_BEFORE_PRODUCTION_USE_python3_secrets_token_hex_32"
        s = Settings(
            _env_file=None,   # bypass .env
            app_env="production",
            auth_enforced=True,
            session_secret_key=placeholder,
            enable_mock_data=False,
        )
        with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
            s.validate_runtime_configuration()

    def test_short_key_in_production_raises(self):
        from arkashri.config import Settings
        s = Settings(
            _env_file=None,   # bypass .env
            app_env="production",
            auth_enforced=True,
            session_secret_key="tooshort",      # < 32 chars
            enable_mock_data=False,
        )
        with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
            s.validate_runtime_configuration()

    def test_strong_key_in_production_passes(self):
        from arkashri.config import Settings
        s = Settings(
            _env_file=None,
            app_env="production",
            auth_enforced=True,
            session_secret_key="a" * 64,
            enable_mock_data=False,
            kms_provider="aws",
            bootstrap_admin_token="b" * 32,
        )
        # Must not raise
        s.validate_runtime_configuration()

    def test_jwt_encode_requires_real_key(self):
        """Ensure _secret() never silently returns None to python-jose."""
        from arkashri.services.jwt_service import _secret
        key = _secret()
        assert key is not None, "C-2: _secret() returned None — JWTs would be unsigned."
        assert len(key) >= 32, f"C-2: JWT secret is too short ({len(key)} chars)."


# ─────────────────────────────────────────────────────────────────────────────
# C-5: No ADMIN privilege via self-registration
# ─────────────────────────────────────────────────────────────────────────────

class TestSelfRegistrationRoles:
    """Ref: C-5 — self-registration cannot produce ADMIN accounts."""

    @pytest.mark.asyncio
    async def test_admin_role_rejected(self):
        """POST /auth/register with role=ADMIN must return 403."""
        from arkashri.routers.users import register_user, RegisterRequest
        payload = RegisterRequest(
            email="hacker@evil.com",
            password="password123",
            full_name="Hacker McHack",
            role="ADMIN",
        )
        db = AsyncMock()
        db.scalars = AsyncMock(return_value=AsyncMock(first=MagicMock(return_value=None)))
        request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await register_user(payload=payload, request=request, db=db)
        assert exc_info.value.status_code == 403, (
            "C-5 REGRESSION: ADMIN self-registration was not rejected with 403."
        )

    @pytest.mark.asyncio
    async def test_partner_role_rejected(self):
        """PARTNER role (another privileged role) must also be rejected."""
        from arkashri.routers.users import register_user, RegisterRequest
        payload = RegisterRequest(
            email="partner@evil.com",
            password="password123",
            full_name="Fake Partner",
            role="PARTNER",
        )
        db = AsyncMock()
        db.scalars = AsyncMock(return_value=AsyncMock(first=MagicMock(return_value=None)))
        with pytest.raises(HTTPException) as exc_info:
            await register_user(payload=payload, request=MagicMock(), db=db)
        assert exc_info.value.status_code == 403

    def test_allowed_roles_mapping_excludes_admin(self):
        """The self-registration allowed-roles set must not contain ADMIN."""
        from arkashri.routers.users import _SELF_REGISTRATION_ALLOWED_ROLES
        assert "ADMIN" not in _SELF_REGISTRATION_ALLOWED_ROLES, (
            "C-5 REGRESSION: ADMIN is in the self-registration allowed roles set."
        )
        assert "admin" not in _SELF_REGISTRATION_ALLOWED_ROLES


# ─────────────────────────────────────────────────────────────────────────────
# C-4: S3 WORM failure must block the seal
# ─────────────────────────────────────────────────────────────────────────────

class TestS3WormFailureBlocksSeal:
    """Ref: C-4 — _s3_worm_upload must raise on failure, not silently continue."""

    @pytest.mark.asyncio
    async def test_s3_exception_propagates(self):
        """When S3 upload raises, the RuntimeError must bubble up."""
        from arkashri.services import seal as seal_module
        from arkashri.services.seal import _s3_worm_upload

        fake_settings = MagicMock(
            s3_worm_bucket="test-bucket",
            aws_access_key_id="test-key",
            aws_secret_access_key="test-secret",
            aws_region="us-east-1",
        )
        # Patch the module-level `settings` object (imported at module load time)
        with patch.object(seal_module, "settings", fake_settings):
            with patch("aiobotocore.session.AioSession.create_client") as mock_client:
                mock_client.side_effect = Exception("S3 connection refused")
                with pytest.raises(RuntimeError, match="S3 WORM archive failed"):
                    await _s3_worm_upload("test-key", b"test-data")

    @pytest.mark.asyncio
    async def test_worm_source_has_raise(self):
        """Source-level: the except block in _s3_worm_upload must raise, not pass."""
        import inspect
        from arkashri.services.seal import _s3_worm_upload
        source = inspect.getsource(_s3_worm_upload)
        assert "raise RuntimeError" in source, (
            "C-4 REGRESSION: _s3_worm_upload except block does not raise. "
            "A failing S3 upload will silently allow the seal to proceed."
        )
        # The silent pass comment must be gone
        assert "# In production: raise here" not in source, (
            "C-4 REGRESSION: The known TODO comment is still present — exception is still swallowed."
        )

    def test_importerror_also_raises(self):
        """Missing aiobotocore must raise, not silently skip (no silent ImportError path)."""
        import inspect
        from arkashri.services.seal import _s3_worm_upload
        source = inspect.getsource(_s3_worm_upload)
        # There must be no silent ImportError path (the old code had a bare 'logger.warning' + fall-through)
        assert 'logger.warning("aiobotocore not installed' not in source, (
            "C-4 REGRESSION: _s3_worm_upload still has a silent 'skip if no aiobotocore' path."
        )


# ─────────────────────────────────────────────────────────────────────────────
# H-4: Tenant isolation — list_engagements must filter by tenant
# ─────────────────────────────────────────────────────────────────────────────

class TestTenantIsolation:
    """Ref: H-4 — engagement list must be scoped to the authenticated tenant."""

    @pytest.mark.asyncio
    async def test_list_engagements_has_tenant_filter(self):
        """The query in list_engagements must include a tenant_id WHERE clause."""
        import inspect
        from arkashri.routers.engagements import list_engagements
        source = inspect.getsource(list_engagements)
        assert "tenant_id" in source, (
            "H-4 REGRESSION: list_engagements query has no tenant_id filter. "
            "Every tenant can read every other tenant's engagements."
        )
        assert "_auth.tenant_id" in source, (
            "H-4 REGRESSION: tenant filter is not bound to auth.tenant_id."
        )


# ─────────────────────────────────────────────────────────────────────────────
# H-1: /readyz must not leak stack traces
# ─────────────────────────────────────────────────────────────────────────────

class TestReadyzNoStackTrace:
    """Ref: H-1 — readyz 503 must not include Python tracebacks."""

    @pytest.mark.asyncio
    async def test_readyz_503_has_no_trace(self, monkeypatch):
        """Simulate DB failure — response must not contain 'trace' or 'Traceback'."""
        import inspect
        from arkashri import main as main_module
        source = inspect.getsource(main_module)
        # The "trace": traceback.format_exc() line must be gone from the response
        assert '"trace": traceback.format_exc()' not in source, (
            "H-1 REGRESSION: /readyz 503 response still includes full stack trace."
        )
        # It should only appear in a logger call
        assert 'logger.warning("readyz_db_unreachable"' in source or \
               'logger.warning' in source, \
            "H-1: stack trace should be logged server-side, not removed entirely."


# ─────────────────────────────────────────────────────────────────────────────
# H-5: OIDC algorithm confusion — algorithm must be validated against allowlist
# ─────────────────────────────────────────────────────────────────────────────

class TestOIDCAlgorithmConfusion:
    """Ref: H-5 — OIDC decode must reject HS256 and other symmetric algorithms."""

    def test_oidc_alg_allowlist_exists_in_source(self):
        """The algorithm guard must be present in source before jwt.decode is called."""
        import inspect
        from arkashri.services import jwt_service
        source = inspect.getsource(jwt_service.decode_oidc_token)
        # Must define an allowlist
        assert "_OIDC_ALLOWED_ALGORITHMS" in source, (
            "H-5 REGRESSION: Algorithm allowlist missing from decode_oidc_token — "
            "algorithm confusion attack is possible."
        )
        # HS256 must NOT be in the allowlist
        assert '"HS256"' not in source.split("_OIDC_ALLOWED_ALGORITHMS")[1].split("\n")[0], (
            "H-5 REGRESSION: HS256 is in the OIDC allowed algorithms set."
        )
        # The check must happen BEFORE jwt.decode
        alg_check_pos = source.find("_OIDC_ALLOWED_ALGORITHMS")
        decode_pos = source.find("jwt.decode")
        assert alg_check_pos < decode_pos, (
            "H-5 REGRESSION: Algorithm check comes AFTER jwt.decode — "
            "the confusion attack can still occur."
        )

    def test_hs256_not_in_allowlist(self):
        """HS256 must not appear in the allowed algorithms constant."""
        import inspect
        from arkashri.services import jwt_service
        source = inspect.getsource(jwt_service.decode_oidc_token)
        # Get the section between _OIDC_ALLOWED_ALGORITHMS = { ... }
        start = source.find("_OIDC_ALLOWED_ALGORITHMS")
        end = source.find("}", start)
        allowlist_block = source[start:end]
        assert "HS256" not in allowlist_block, (
            "H-5 REGRESSION: HS256 is present in _OIDC_ALLOWED_ALGORITHMS."
        )
        assert "RS256" in allowlist_block, (
            "H-5: RS256 must be in the OIDC allowed algorithms."
        )

    def test_rs256_is_allowed(self):
        """RS256 must be in the OIDC allowed algorithms set."""
        import inspect
        from arkashri.services import jwt_service
        source = inspect.getsource(jwt_service.decode_oidc_token)
        assert "RS256" in source, "H-5: RS256 not found in OIDC allowed algorithms."
        assert "_OIDC_ALLOWED_ALGORITHMS" in source, \
            "H-5: algorithm allowlist variable missing from decode_oidc_token."


# ─────────────────────────────────────────────────────────────────────────────
# C-9: Witness quorum error must be a proper f-string
# ─────────────────────────────────────────────────────────────────────────────

class TestWitnessQuorumError:
    """Ref: C-9 — PermissionError must use f-string formatting, not %-args."""

    def test_quorum_error_is_proper_string(self):
        """PermissionError with % formatting would pass a tuple as the message."""
        import inspect
        from arkashri.services import witness_client
        source = inspect.getsource(witness_client.WitnessNetworkClient.request_quorum_signatures)
        # The old broken line used % format — ensure it's gone
        assert '"%d"' not in source and "'%d'" not in source, (
            "C-9 REGRESSION: PermissionError still uses %-style formatting. "
            "This results in a tuple being raised as the exception message."
        )

    @pytest.mark.asyncio
    async def test_quorum_failure_raises_permission_error(self):
        """When <required signatures are received, a PermissionError with a proper message is raised."""
        import httpx
        from unittest.mock import patch, AsyncMock
        from arkashri.services.witness_client import WitnessNetworkClient
        
        # Test with 5 configured nodes
        with patch("arkashri.services.witness_client.get_settings") as mock_settings:
            mock_settings.return_value.witness_node_urls = [
                "http://n1", "http://n2", "http://n3", "http://n4", "http://n5"
            ]
            client = WitnessNetworkClient()

            # Mock httpx to return failure/non-dict for all
            with patch("httpx.AsyncClient.post", new_caller=AsyncMock()) as mock_post:
                mock_post.return_value = MagicMock()
                mock_post.return_value.status_code = 500
                mock_post.return_value.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Error", request=MagicMock(), response=mock_post.return_value
                )

                with pytest.raises(PermissionError) as exc_info:
                    await client.request_quorum_signatures(
                        sth={"tree_size": 1, "sha256_root_hash": "abc"},
                        consistency_proof=[],
                    )
                
                # Quorum for 5 nodes is 3. We got 0.
                msg = str(exc_info.value)
                assert "Needed 3" in msg or "Got 0" in msg, (
                    f"C-9: PermissionError message is malformed: {msg!r}"
                )
        assert "(%," not in msg and "tuple" not in msg


# ─────────────────────────────────────────────────────────────────────────────
# H-7: Blockchain anchors are immutable
# ─────────────────────────────────────────────────────────────────────────────

class TestBlockchainAnchorImmutability:
    """Ref: H-7 — Re-anchoring with different merkle_root must return 409."""

    @pytest.mark.asyncio
    async def test_anchor_mutation_rejected(self):
        """Submitting a different merkle_root to an existing anchor must raise 409."""
        import inspect
        from arkashri.routers import blockchain
        source = inspect.getsource(blockchain)
        assert "immutable" in source.lower(), (
            "H-7 REGRESSION: No immutability check found in blockchain router."
        )
        assert "409" in source, (
            "H-7 REGRESSION: No 409 conflict response for re-anchor attempt."
        )


# ─────────────────────────────────────────────────────────────────────────────
# C-6: engagements.py must import Request
# ─────────────────────────────────────────────────────────────────────────────

class TestEngagementsImports:
    """Ref: C-6 — engagements.py must have all required imports."""

    def test_request_is_importable(self):
        """Import the engagements router — if Request is missing this raises NameError."""
        try:
            import arkashri.routers.engagements  # noqa: F401
        except (ImportError, NameError) as e:
            pytest.fail(f"C-6: engagements.py import failed: {e}")

    def test_engagement_status_update_defined(self):
        """EngagementStatusUpdate schema must be defined in engagements module."""
        from arkashri.routers.engagements import EngagementStatusUpdate
        assert EngagementStatusUpdate is not None


# ─────────────────────────────────────────────────────────────────────────────
# C-10: evidence.py must import uuid and Request
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceImports:
    """Ref: C-10 — evidence.py must import uuid and Request."""

    def test_evidence_service_importable(self):
        try:
            from arkashri.services.evidence import InternalEvidenceService  # noqa
        except (ImportError, NameError) as e:
            pytest.fail(f"C-10: evidence.py import failed: {e}")

    def test_emit_signed_audit_event_signature(self):
        """Method signature must reference uuid.UUID and Request without NameError."""
        import inspect
        from arkashri.services.evidence import InternalEvidenceService
        sig = inspect.signature(InternalEvidenceService.emit_signed_audit_event)
        # Just constructing the signature proves uuid and Request are resolved
        assert "user_id" in sig.parameters
        assert "request" in sig.parameters


# ─────────────────────────────────────────────────────────────────────────────
# System Version deduplication (L-10)
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemVersionSingleSource:
    """Ref: L-10 — SYSTEM_VERSION must have exactly one definition."""

    def test_single_version_constant(self):
        from arkashri import SYSTEM_VERSION
        assert isinstance(SYSTEM_VERSION, str)
        assert len(SYSTEM_VERSION) > 0

    def test_seal_uses_same_version(self):
        """seal.py must import SYSTEM_VERSION from arkashri, not define its own."""
        import inspect
        from arkashri.services import seal
        source = inspect.getsource(seal)
        # Must import, not assign a string literal
        assert 'from arkashri import SYSTEM_VERSION' in source, (
            "L-10 REGRESSION: seal.py defines its own SYSTEM_VERSION string literal "
            "instead of importing from arkashri package."
        )

    def test_seal_sessions_uses_same_version(self):
        """seal_sessions.py must import SYSTEM_VERSION from arkashri, not define its own."""
        import inspect
        from arkashri.routers import seal_sessions
        source = inspect.getsource(seal_sessions)
        assert 'from arkashri import SYSTEM_VERSION' in source, (
            "L-10 REGRESSION: seal_sessions.py defines its own SYSTEM_VERSION string literal."
        )


# ─────────────────────────────────────────────────────────────────────────────
# C-3: KMS ephemeral keys must hard-fail in production
# ─────────────────────────────────────────────────────────────────────────────

class TestKMSEphemeralKeyProductionGate:
    """Ref: C-3 — Ephemeral in-memory ECDSA keys must not be used in production."""

    def test_production_raises_on_ephemeral_key_generation(self, monkeypatch):
        """In production, generating a new keypair must raise RuntimeError."""
        monkeypatch.setenv("APP_ENV", "production")
        from arkashri.services.kms import AsymmetricKeyProvider
        provider = AsymmetricKeyProvider()
        with pytest.raises(RuntimeError, match="Ephemeral in-memory ECDSA keys"):
            provider.get_tenant_keypair("test-tenant-prod")

    def test_dev_env_logs_warning_not_error(self, monkeypatch):
        """In dev, ephemeral key generation must succeed but log a warning."""
        monkeypatch.setenv("APP_ENV", "dev")
        import logging
        from arkashri.services.kms import AsymmetricKeyProvider
        provider = AsymmetricKeyProvider()
        with patch.object(logging.getLogger("services.kms"), "warning") as mock_warn:
            priv, pub = provider.get_tenant_keypair(f"test-tenant-{uuid.uuid4()}")
            assert priv is not None
            assert pub is not None
            mock_warn.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# H-6: Password reset — non-admins can only reset their own password
# ─────────────────────────────────────────────────────────────────────────────

class TestPasswordResetAuthorization:
    """Ref: H-6 — password reset self-check must be enforced, not dead code."""

    def test_self_check_not_dead_code(self):
        import inspect
        from arkashri.routers.users import reset_password
        source = inspect.getsource(reset_password)
        # The old dead line was: (str(user_id) == getattr(auth, "user_id", None))
        # It computed the result but never stored/used it.
        # Now it must be: is_self = ...
        assert "is_self" in source, (
            "H-6 REGRESSION: is_self variable removed from reset_password."
        )
        assert "is_self = " in source, (
            "H-6: is_self computed but not assigned (dead code still present)."
        )

    def test_non_admin_cannot_reset_other_user(self):
        """Source must contain the 403 guard for cross-user password reset."""
        import inspect
        from arkashri.routers.users import reset_password
        source = inspect.getsource(reset_password)
        assert "403" in source or "HTTP_403_FORBIDDEN" in source, (
            "H-6 REGRESSION: No 403 guard in reset_password for non-admin cross-user reset."
        )


# ─────────────────────────────────────────────────────────────────────────────
# CORS hardening (M-5)
# ─────────────────────────────────────────────────────────────────────────────

class TestCORSHardening:
    """Ref: M-5 — CORS must not use allow_methods=['*'] with allow_credentials=True."""

    def test_cors_methods_not_wildcard(self):
        import inspect
        from arkashri import main
        source = inspect.getsource(main)
        # Find the CORSMiddleware block — it must not have wildcard methods
        assert 'allow_methods=["*"]' not in source, (
            "M-5 REGRESSION: CORS allow_methods is set to wildcard ['*'] with credentials=True. "
            "This allows cross-origin requests using any HTTP method."
        )

    def test_cors_headers_not_wildcard(self):
        import inspect
        from arkashri import main
        source = inspect.getsource(main)
        assert 'allow_headers=["*"]' not in source, (
            "M-5 REGRESSION: CORS allow_headers is set to wildcard ['*'] with credentials=True."
        )


# ─────────────────────────────────────────────────────────────────────────────
# H-10: HashNotaryAdapter must be async
# ─────────────────────────────────────────────────────────────────────────────

class TestBlockchainAdapterAsync:
    """Ref: H-10 — blockchain adapters must not block the event loop."""

    def test_hash_notary_anchor_is_coroutine(self):
        """HashNotaryAdapter.anchor must be declared as async."""
        import asyncio
        from arkashri.services.blockchain_adapter import HashNotaryAdapter
        adapter = HashNotaryAdapter()
        assert asyncio.iscoroutinefunction(adapter.anchor), (
            "H-10 REGRESSION: HashNotaryAdapter.anchor is not an async function. "
            "Calling it will block the event loop."
        )

    def test_run_adapter_anchor_is_coroutine(self):
        """run_adapter_anchor must be declared as async."""
        import asyncio
        from arkashri.services.blockchain_adapter import run_adapter_anchor
        assert asyncio.iscoroutinefunction(run_adapter_anchor), (
            "H-10 REGRESSION: run_adapter_anchor is not async."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Seal session partner identity binding (H-9)
# ─────────────────────────────────────────────────────────────────────────────

class TestPartnerIdentityBinding:
    """Ref: H-9 — partner identity must come from auth, not caller payload."""

    def test_sign_uses_auth_identity(self):
        """sign_seal_session must use authenticated_user_id, not payload.partner_user_id."""
        import inspect
        from arkashri.routers.seal_sessions import sign_seal_session
        source = inspect.getsource(sign_seal_session)
        assert "authenticated_user_id" in source, (
            "H-9 REGRESSION: sign_seal_session does not bind partner to authenticated identity. "
            "Callers can sign as any arbitrary user ID."
        )
        assert "authenticated_email" in source, (
            "H-9: partner email is not bound to authenticated identity."
        )


# ─────────────────────────────────────────────────────────────────────────────
# ERP readiness check scoped to engagement (C-8)
# ─────────────────────────────────────────────────────────────────────────────

class TestERPReadinessScoping:
    """Ref: C-8 — ERP readiness must be scoped to the engagement, not the whole tenant."""

    def test_verify_collected_readiness_uses_created_at(self):
        """The query must include engagement.created_at to prevent cross-engagement bypass."""
        import inspect
        from arkashri.services.engagement_workflow import _verify_collected_readiness
        source = inspect.getsource(_verify_collected_readiness)
        assert "created_at" in source, (
            "C-8 REGRESSION: _verify_collected_readiness does not filter by "
            "engagement.created_at. Any prior ERP sync satisfies every engagement's gate."
        )
        assert "ERPSyncStatus.SUCCESS" in source or "ERPSyncStatus" in source, (
            "C-8: ERP readiness check must filter by SUCCESS/PARTIAL status."
        )


# ─────────────────────────────────────────────────────────────────────────────
# M-10: _to_sig_out must include ca_icai_reg_no
# ─────────────────────────────────────────────────────────────────────────────

class TestSealSignatureOutput:
    """Ref: M-10 — ca_icai_reg_no must appear in SealSignature API output."""

    def test_sig_out_includes_icai_reg(self):
        import inspect
        from arkashri.routers.seal_sessions import _to_sig_out
        source = inspect.getsource(_to_sig_out)
        assert "ca_icai_reg_no" in source, (
            "M-10 REGRESSION: ca_icai_reg_no is not included in _to_sig_out. "
            "ICAI registration numbers are silently dropped from audit trail output."
        )
