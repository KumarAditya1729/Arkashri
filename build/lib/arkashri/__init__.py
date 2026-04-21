# pyre-ignore-all-errors
"""Arkashri sovereign financial decision engine."""

# Single source of truth for the system version string.
# This is embedded in every seal bundle and used during verification.
# Changing this value will make old seals unverifiable — only bump on major protocol changes.
SYSTEM_VERSION: str = "Arkashri_OS_2.0_Enterprise"
