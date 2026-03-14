# pyre-ignore-all-errors
"""
Production configuration management system
Provides environment-specific configuration loading and validation
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

import structlog
from pydantic import BaseModel, ValidationError

from arkashri.config import get_settings

logger = structlog.get_logger(__name__)


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ConfigurationSource(str, Enum):
    FILE = "file"
    ENVIRONMENT = "environment"
    VAULT = "vault"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    KUBERNETES = "kubernetes"


@dataclass
class ConfigurationRule:
    """Configuration validation rule"""
    key: str
    required: bool = True
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    allowed_values: Optional[List[str]] = None
    sensitive: bool = False
    description: str = ""


class ProductionConfigManager:
    """Production-ready configuration management"""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = structlog.get_logger("config_manager")
        
        # Define configuration rules
        self.config_rules = self._define_config_rules()
        
        # Configuration cache
        self._config_cache: Dict[str, Any] = {}
        
        # Environment detection
        self.environment = self._detect_environment()
        
        # Load configuration
        self._load_configuration()
    
    def _detect_environment(self) -> Environment:
        """Detect current environment"""
        env_var = os.getenv("APP_ENV", self.settings.app_env).lower()
        
        if env_var in ["prod", "production"]:
            return Environment.PRODUCTION
        elif env_var in ["staging", "stage"]:
            return Environment.STAGING
        else:
            return Environment.DEVELOPMENT
    
    def _define_config_rules(self) -> List[ConfigurationRule]:
        """Define configuration validation rules"""
        return [
            # Database configuration
            ConfigurationRule(
                key="database_url",
                required=True,
                pattern=r"^(postgresql|mysql)://.*",
                description="Database connection URL"
            ),
            ConfigurationRule(
                key="db_pool_size",
                required=False,
                allowed_values=["10", "20", "50", "100"],
                description="Database connection pool size"
            ),
            
            # Security configuration
            ConfigurationRule(
                key="session_secret_key",
                required=True,
                min_length=32,
                sensitive=True,
                description="Session encryption key"
            ),
            ConfigurationRule(
                key="seal_key_v1",
                required=self.environment == Environment.PRODUCTION,
                min_length=32,
                sensitive=True,
                description="Cryptographic seal key"
            ),
            
            # External services
            ConfigurationRule(
                key="redis_url",
                required=self.environment != Environment.DEVELOPMENT,
                pattern=r"^redis://.*",
                description="Redis connection URL"
            ),
            ConfigurationRule(
                key="openai_api_key",
                required=self.environment != Environment.DEVELOPMENT,
                min_length=20,
                sensitive=True,
                description="OpenAI API key"
            ),
            ConfigurationRule(
                key="sentry_dsn",
                required=self.environment == Environment.PRODUCTION,
                pattern=r"^https://.*",
                sensitive=True,
                description="Sentry DSN for error tracking"
            ),
            
            # AWS configuration
            ConfigurationRule(
                key="aws_access_key_id",
                required=self.environment == Environment.PRODUCTION,
                min_length=16,
                sensitive=True,
                description="AWS access key"
            ),
            ConfigurationRule(
                key="aws_secret_access_key",
                required=self.environment == Environment.PRODUCTION,
                min_length=20,
                sensitive=True,
                description="AWS secret key"
            ),
            
            # Feature flags
            ConfigurationRule(
                key="auth_enforced",
                required=False,
                allowed_values=["true", "false"],
                description="Enable authentication enforcement"
            ),
            ConfigurationRule(
                key="backup_enabled",
                required=False,
                allowed_values=["true", "false"],
                description="Enable automated backups"
            ),
        ]
    
    def _load_configuration(self):
        """Load configuration from multiple sources"""
        self.logger.info("loading_configuration", environment=self.environment.value)
        
        # Load from environment variables
        self._load_from_environment()
        
        # Load from configuration files
        self._load_from_files()
        
        # Load from external sources in production
        if self.environment == Environment.PRODUCTION:
            self._load_from_external_sources()
        
        # Validate configuration
        self._validate_configuration()
        
        # Log configuration status
        self._log_configuration_status()
    
    def _load_from_environment(self):
        """Load configuration from environment variables"""
        for rule in self.config_rules:
            value = os.getenv(rule.key.upper())
            if value:
                self._config_cache[rule.key] = value
                self.logger.debug("config_loaded_from_env", key=rule.key)
    
    def _load_from_files(self):
        """Load configuration from files"""
        config_files = [
            f".env.{self.environment.value}",
            f".env.{self.environment.value}.local",
            "config.json",
            f"config.{self.environment.value}.json"
        ]
        
        for config_file in config_files:
            config_path = Path(config_file)
            if config_path.exists():
                try:
                    if config_path.suffix == ".json":
                        self._load_json_config(config_path)
                    else:
                        self._load_env_config(config_path)
                    
                    self.logger.info("config_loaded_from_file", file=config_file)
                    
                except Exception as e:
                    self.logger.error("config_file_load_error", file=config_file, error=str(e))
    
    def _load_env_config(self, config_path: Path):
        """Load configuration from .env file"""
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    self._config_cache[key] = value
    
    def _load_json_config(self, config_path: Path):
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            config_data = json.load(f)
            self._config_cache.update(config_data)
    
    def _load_from_external_sources(self):
        """Load configuration from external sources"""
        # This would integrate with:
        # - HashiCorp Vault
        # - AWS Secrets Manager
        # - Kubernetes Secrets
        # - Azure Key Vault
        
        # For now, just log that this would be implemented
        self.logger.info("external_config_sources_not_implemented")
    
    def _validate_configuration(self):
        """Validate loaded configuration"""
        errors = []
        warnings = []
        
        for rule in self.config_rules:
            value = self._config_cache.get(rule.key)
            
            if rule.required and not value:
                errors.append(f"Required configuration missing: {rule.key}")
                continue
            
            if value:
                # Validate length constraints
                if rule.min_length and len(value) < rule.min_length:
                    errors.append(f"Configuration {rule.key} too short (min: {rule.min_length})")
                
                if rule.max_length and len(value) > rule.max_length:
                    errors.append(f"Configuration {rule.key} too long (max: {rule.max_length})")
                
                # Validate pattern
                if rule.pattern:
                    import re
                    if not re.match(rule.pattern, value):
                        errors.append(f"Configuration {rule.key} doesn't match pattern: {rule.pattern}")
                
                # Validate allowed values
                if rule.allowed_values and value not in rule.allowed_values:
                    errors.append(f"Configuration {rule.key} not in allowed values: {rule.allowed_values}")
        
        # Report validation results
        if errors:
            error_msg = "Configuration validation failed: " + "; ".join(errors)
            self.logger.error("config_validation_failed", errors=errors)
            raise ValueError(error_msg)
        
        if warnings:
            self.logger.warning("config_validation_warnings", warnings=warnings)
        
        self.logger.info("config_validation_passed")
    
    def _log_configuration_status(self):
        """Log configuration status (without sensitive data)"""
        config_status = {
            "environment": self.environment.value,
            "total_config_keys": len(self._config_cache),
            "sensitive_keys": len([r for r in self.config_rules if r.sensitive and r.key in self._config_cache]),
            "missing_required": len([r for r in self.config_rules if r.required and r.key not in self._config_cache])
        }
        
        self.logger.info("configuration_status", **config_status)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self._config_cache.get(key, default)
    
    def get_sensitive(self, key: str, default: Any = None) -> Any:
        """Get sensitive configuration value"""
        value = self._config_cache.get(key, default)
        
        # Log access to sensitive configuration
        rule = next((r for r in self.config_rules if r.key == key), None)
        if rule and rule.sensitive:
            self.logger.info("sensitive_config_accessed", key=key)
        
        return value
    
    def reload(self):
        """Reload configuration"""
        self._config_cache.clear()
        self._load_configuration()
        self.logger.info("configuration_reloaded")
    
    def export_safe_config(self) -> Dict[str, Any]:
        """Export configuration without sensitive values"""
        safe_config = {}
        
        for key, value in self._config_cache.items():
            rule = next((r for r in self.config_rules if r.key == key), None)
            
            if rule and rule.sensitive:
                safe_config[key] = "***REDACTED***"
            else:
                safe_config[key] = value
        
        return safe_config
    
    def validate_feature_flags(self) -> Dict[str, bool]:
        """Validate and return feature flags"""
        feature_flags = {
            "auth_enforced": self.get("auth_enforced", "false").lower() == "true",
            "backup_enabled": self.get("backup_enabled", "false").lower() == "true",
            "performance_monitoring": self.get("enable_performance_monitoring", "false").lower() == "true",
            "request_logging": self.get("enable_request_logging", "true").lower() == "true",
            "compression": self.get("enable_compression", "true").lower() == "true",
        }
        
        # Validate feature flag combinations
        if self.environment == Environment.PRODUCTION:
            # Production should have auth enforced
            if not feature_flags["auth_enforced"]:
                self.logger.warning("production_auth_not_enforced")
            
            # Production should have monitoring enabled
            if not feature_flags["performance_monitoring"]:
                self.logger.warning("production_monitoring_disabled")
        
        return feature_flags


# Global configuration manager instance
config_manager = ProductionConfigManager()
