"""
Backup and disaster recovery services for production
Provides automated database backups, file backups, and recovery mechanisms
"""
from __future__ import annotations

import asyncio
import datetime
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiobotocore.session
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from arkashri.config import get_settings
from arkashri.db import AsyncSessionLocal
from arkashri.logging_config import audit_logger
from arkashri.utils.error_handling import handle_errors, ErrorContext

logger = structlog.get_logger(__name__)


class BackupType(str, Enum):
    DATABASE = "database"
    FILES = "files"
    CONFIGURATION = "configuration"
    FULL = "full"


class BackupStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CORRUPTED = "corrupted"


@dataclass
class BackupMetadata:
    """Backup metadata information"""
    backup_id: str
    backup_type: BackupType
    created_at: datetime.datetime
    file_path: str
    file_size: int
    checksum: str
    status: BackupStatus
    retention_days: int
    compressed: bool = True
    encrypted: bool = False


class DatabaseBackupService:
    """Database backup and recovery service"""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = structlog.get_logger("database_backup")
        self.backup_dir = Path("backups/database")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    @handle_errors()
    async def create_database_backup(
        self,
        backup_type: BackupType = BackupType.DATABASE,
        compress: bool = True
    ) -> BackupMetadata:
        """Create database backup"""
        backup_id = f"db_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        timestamp = datetime.datetime.now()
        
        self.logger.info("database_backup_started", backup_id=backup_id)
        
        # Create backup file path
        extension = ".sql.gz" if compress else ".sql"
        backup_path = self.backup_dir / f"{backup_id}{extension}"
        
        try:
            # Get database connection details
            db_url = self.settings.database_url
            
            # Create backup using pg_dump
            if "postgresql" in db_url:
                await self._create_postgresql_backup(db_url, backup_path, compress)
            else:
                raise ValueError(f"Unsupported database type: {db_url}")
            
            # Calculate checksum
            checksum = await self._calculate_checksum(backup_path)
            file_size = backup_path.stat().st_size
            
            # Create metadata
            metadata = BackupMetadata(
                backup_id=backup_id,
                backup_type=backup_type,
                created_at=timestamp,
                file_path=str(backup_path),
                file_size=file_size,
                checksum=checksum,
                status=BackupStatus.COMPLETED,
                retention_days=self.settings.backup_retention_days,
                compressed=compress
            )
            
            # Save metadata
            await self._save_backup_metadata(metadata)
            
            # Log audit event
            audit_logger.log_system_event(
                event_type="database_backup_completed",
                description=f"Database backup {backup_id} completed successfully",
                context={
                    "backup_id": backup_id,
                    "file_size": file_size,
                    "checksum": checksum
                }
            )
            
            self.logger.info(
                "database_backup_completed",
                backup_id=backup_id,
                file_size=file_size,
                checksum=checksum
            )
            
            return metadata
            
        except Exception as e:
            self.logger.error(
                "database_backup_failed",
                backup_id=backup_id,
                error=str(e)
            )
            
            # Clean up failed backup
            if backup_path.exists():
                backup_path.unlink()
            
            raise
    
    async def _create_postgresql_backup(
        self,
        db_url: str,
        backup_path: Path,
        compress: bool
    ):
        """Create PostgreSQL backup using pg_dump"""
        # Parse database URL
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        # Build pg_dump command
        cmd = [
            "pg_dump",
            f"--host={parsed.hostname}",
            f"--port={parsed.port or 5432}",
            f"--username={parsed.username}",
            f"--dbname={parsed.path.lstrip('/')}",
            "--no-password",
            "--verbose",
            "--clean",
            "--if-exists",
            "--format=custom",
            f"--file={backup_path}"
        ]
        
        # Set password environment variable
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password
        
        # Execute backup command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")
        
        # Compress if needed
        if compress and not backup_path.name.endswith('.gz'):
            await self._compress_file(backup_path)
    
    async def _compress_file(self, file_path: Path):
        """Compress file using gzip"""
        compressed_path = file_path.with_suffix(file_path.suffix + '.gz')
        
        with open(file_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove original file
        file_path.unlink()
    
    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    async def _save_backup_metadata(self, metadata: BackupMetadata):
        """Save backup metadata to file"""
        metadata_path = self.backup_dir / f"{metadata.backup_id}_metadata.json"
        
        with open(metadata_path, 'w') as f:
            json.dump({
                "backup_id": metadata.backup_id,
                "backup_type": metadata.backup_type.value,
                "created_at": metadata.created_at.isoformat(),
                "file_path": metadata.file_path,
                "file_size": metadata.file_size,
                "checksum": metadata.checksum,
                "status": metadata.status.value,
                "retention_days": metadata.retention_days,
                "compressed": metadata.compressed,
                "encrypted": metadata.encrypted
            }, f, indent=2)
    
    @handle_errors()
    async def restore_database_backup(
        self,
        backup_id: str,
        verify_checksum: bool = True
    ) -> bool:
        """Restore database from backup"""
        self.logger.info("database_restore_started", backup_id=backup_id)
        
        try:
            # Load backup metadata
            metadata = await self._load_backup_metadata(backup_id)
            if not metadata:
                raise ValueError(f"Backup metadata not found: {backup_id}")
            
            backup_path = Path(metadata.file_path)
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # Verify checksum if requested
            if verify_checksum:
                current_checksum = await self._calculate_checksum(backup_path)
                if current_checksum != metadata.checksum:
                    raise ValueError(f"Backup checksum mismatch: {backup_id}")
            
            # Get database URL
            db_url = self.settings.database_url
            
            # Restore using pg_restore
            if "postgresql" in db_url:
                await self._restore_postgresql_backup(db_url, backup_path)
            else:
                raise ValueError(f"Unsupported database type: {db_url}")
            
            # Log audit event
            audit_logger.log_system_event(
                event_type="database_restore_completed",
                description=f"Database restore from backup {backup_id} completed",
                context={
                    "backup_id": backup_id,
                    "restored_at": datetime.datetime.now().isoformat()
                }
            )
            
            self.logger.info("database_restore_completed", backup_id=backup_id)
            return True
            
        except Exception as e:
            self.logger.error(
                "database_restore_failed",
                backup_id=backup_id,
                error=str(e)
            )
            raise
    
    async def _restore_postgresql_backup(self, db_url: str, backup_path: Path):
        """Restore PostgreSQL backup using pg_restore"""
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        # Build pg_restore command
        cmd = [
            "pg_restore",
            f"--host={parsed.hostname}",
            f"--port={parsed.port or 5432}",
            f"--username={parsed.username}",
            f"--dbname={parsed.path.lstrip('/')}",
            "--no-password",
            "--verbose",
            "--clean",
            "--if-exists",
            str(backup_path)
        ]
        
        # Set password environment variable
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password
        
        # Execute restore command
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {stderr.decode()}")
    
    async def _load_backup_metadata(self, backup_id: str) -> Optional[BackupMetadata]:
        """Load backup metadata from file"""
        metadata_path = self.backup_dir / f"{backup_id}_metadata.json"
        
        if not metadata_path.exists():
            return None
        
        with open(metadata_path, 'r') as f:
            data = json.load(f)
        
        return BackupMetadata(
            backup_id=data["backup_id"],
            backup_type=BackupType(data["backup_type"]),
            created_at=datetime.datetime.fromisoformat(data["created_at"]),
            file_path=data["file_path"],
            file_size=data["file_size"],
            checksum=data["checksum"],
            status=BackupStatus(data["status"]),
            retention_days=data["retention_days"],
            compressed=data.get("compressed", True),
            encrypted=data.get("encrypted", False)
        )
    
    async def list_backups(self) -> List[BackupMetadata]:
        """List all available backups"""
        backups = []
        
        for metadata_file in self.backup_dir.glob("*_metadata.json"):
            backup_id = metadata_file.stem.replace("_metadata", "")
            metadata = await self._load_backup_metadata(backup_id)
            if metadata:
                backups.append(metadata)
        
        return sorted(backups, key=lambda x: x.created_at, reverse=True)
    
    async def cleanup_old_backups(self):
        """Clean up backups older than retention period"""
        self.logger.info("backup_cleanup_started")
        
        backups = await self.list_backups()
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.settings.backup_retention_days)
        
        cleaned_count = 0
        for backup in backups:
            if backup.created_at < cutoff_date:
                try:
                    # Remove backup file
                    backup_path = Path(backup.file_path)
                    if backup_path.exists():
                        backup_path.unlink()
                    
                    # Remove metadata file
                    metadata_path = self.backup_dir / f"{backup.backup_id}_metadata.json"
                    if metadata_path.exists():
                        metadata_path.unlink()
                    
                    cleaned_count += 1
                    
                    self.logger.info(
                        "backup_cleaned",
                        backup_id=backup.backup_id,
                        created_at=backup.created_at.isoformat()
                    )
                    
                except Exception as e:
                    self.logger.error(
                        "backup_cleanup_error",
                        backup_id=backup.backup_id,
                        error=str(e)
                    )
        
        self.logger.info("backup_cleanup_completed", cleaned_count=cleaned_count)


class FileBackupService:
    """File backup and recovery service"""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = structlog.get_logger("file_backup")
        self.backup_dir = Path("backups/files")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    @handle_errors()
    async def backup_files(self, source_dir: str, backup_id: Optional[str] = None) -> BackupMetadata:
        """Backup files from source directory"""
        if not backup_id:
            backup_id = f"files_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        timestamp = datetime.datetime.now()
        source_path = Path(source_dir)
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")
        
        self.logger.info("file_backup_started", backup_id=backup_id, source_dir=source_dir)
        
        # Create backup archive
        backup_path = self.backup_dir / f"{backup_id}.tar.gz"
        
        try:
            # Create tar.gz archive
            await self._create_tar_archive(source_path, backup_path)
            
            # Calculate checksum and size
            checksum = await self._calculate_checksum(backup_path)
            file_size = backup_path.stat().st_size
            
            # Create metadata
            metadata = BackupMetadata(
                backup_id=backup_id,
                backup_type=BackupType.FILES,
                created_at=timestamp,
                file_path=str(backup_path),
                file_size=file_size,
                checksum=checksum,
                status=BackupStatus.COMPLETED,
                retention_days=self.settings.backup_retention_days,
                compressed=True
            )
            
            # Save metadata
            await self._save_backup_metadata(metadata)
            
            self.logger.info(
                "file_backup_completed",
                backup_id=backup_id,
                file_size=file_size,
                source_dir=source_dir
            )
            
            return metadata
            
        except Exception as e:
            self.logger.error(
                "file_backup_failed",
                backup_id=backup_id,
                source_dir=source_dir,
                error=str(e)
            )
            
            # Clean up failed backup
            if backup_path.exists():
                backup_path.unlink()
            
            raise
    
    async def _create_tar_archive(self, source_path: Path, backup_path: Path):
        """Create tar.gz archive"""
        cmd = [
            "tar",
            "-czf",
            str(backup_path),
            "-C",
            str(source_path.parent),
            source_path.name
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"tar command failed: {stderr.decode()}")
    
    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    async def _save_backup_metadata(self, metadata: BackupMetadata):
        """Save backup metadata to file"""
        metadata_path = self.backup_dir / f"{metadata.backup_id}_metadata.json"
        
        with open(metadata_path, 'w') as f:
            json.dump({
                "backup_id": metadata.backup_id,
                "backup_type": metadata.backup_type.value,
                "created_at": metadata.created_at.isoformat(),
                "file_path": metadata.file_path,
                "file_size": metadata.file_size,
                "checksum": metadata.checksum,
                "status": metadata.status.value,
                "retention_days": metadata.retention_days,
                "compressed": metadata.compressed,
                "encrypted": metadata.encrypted
            }, f, indent=2)


class DisasterRecoveryService:
    """Disaster recovery coordination service"""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = structlog.get_logger("disaster_recovery")
        self.db_backup = DatabaseBackupService()
        self.file_backup = FileBackupService()
    
    async def create_full_backup(self) -> Dict[str, BackupMetadata]:
        """Create full system backup"""
        self.logger.info("full_backup_started")
        
        backups = {}
        
        try:
            # Database backup
            db_backup = await self.db_backup.create_database_backup()
            backups["database"] = db_backup
            
            # File backups
            if os.path.exists("uploads"):
                files_backup = await self.file_backup.backup_files("uploads")
                backups["uploads"] = files_backup
            
            # Configuration backup
            config_backup = await self.file_backup.backup_files(".")
            backups["configuration"] = config_backup
            
            self.logger.info("full_backup_completed", backups=len(backups))
            
            return backups
            
        except Exception as e:
            self.logger.error("full_backup_failed", error=str(e))
            raise
    
    async def test_recovery_procedures(self) -> bool:
        """Test disaster recovery procedures"""
        self.logger.info("recovery_test_started")
        
        try:
            # Create test backup
            test_backup = await self.db_backup.create_database_backup()
            
            # Test restore to a temporary database
            # This would require a test database setup
            # For now, we'll just verify the backup integrity
            
            # Verify backup exists and is readable
            backup_path = Path(test_backup.file_path)
            if not backup_path.exists():
                raise FileNotFoundError("Test backup file not found")
            
            # Verify checksum
            current_checksum = await self.db_backup._calculate_checksum(backup_path)
            if current_checksum != test_backup.checksum:
                raise ValueError("Test backup checksum mismatch")
            
            # Clean up test backup
            backup_path.unlink()
            metadata_path = self.db_backup.backup_dir / f"{test_backup.backup_id}_metadata.json"
            if metadata_path.exists():
                metadata_path.unlink()
            
            self.logger.info("recovery_test_completed", success=True)
            return True
            
        except Exception as e:
            self.logger.error("recovery_test_failed", error=str(e))
            return False


# Global backup service instances
database_backup_service = DatabaseBackupService()
file_backup_service = FileBackupService()
disaster_recovery_service = DisasterRecoveryService()
