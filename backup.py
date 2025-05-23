"""
Backup management for Craft Minecraft Server Manager

Handles creation, verification, restoration, and management of world backups
with compression, integrity checking, and automated cleanup features.
"""

import shutil
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import ConfigManager
from utils import handle_error, safe_delete_file, ensure_directory

console = Console()

# Constants
BACKUP_LOG_NAME = "backup.log"
MIN_BACKUP_SIZE = 1024  # 1KB minimum backup size
MAX_BACKUP_NAME_LENGTH = 50
BACKUP_FILE_EXTENSION = ".zip"


class BackupError(Exception):
    """Custom exception for backup-related errors"""
    pass


class BackupManager:
    """Enhanced backup management with comprehensive error handling and verification"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.backup_dir = Path(config.get("backup_dir"))
        self.auto_backup_thread: Optional[threading.Thread] = None
        self.auto_backup_running = False
        self.backup_lock = threading.Lock()

        self._initialize_backup_system()

    def _initialize_backup_system(self) -> None:
        """Initialize the backup system"""
        self._ensure_backup_directory()
        self._cleanup_corrupted_backups_on_startup()

    def _ensure_backup_directory(self) -> None:
        """Ensure backup directory exists with proper permissions"""
        try:
            ensure_directory(self.backup_dir)
        except Exception as e:
            handle_error(e, "Could not create backup directory")

    def _cleanup_corrupted_backups_on_startup(self) -> None:
        """Clean up any corrupted backups found during startup"""
        try:
            removed = self.cleanup_corrupted_backups()
            if removed > 0:
                console.print(f"[yellow]🧹 Cleaned up {removed} corrupted backup(s) on startup[/yellow]")
        except Exception as e:
            handle_error(e, "Failed to cleanup corrupted backups on startup")

    def create_backup(self, name: Optional[str] = None, world_dir: Optional[Path] = None) -> bool:
        """Create a backup of the world with comprehensive validation and error handling"""
        with self.backup_lock:
            try:
                world_path = self._determine_world_path(world_dir)
                backup_name = self._generate_backup_name(name)
                backup_path = self.backup_dir / f"{backup_name}{BACKUP_FILE_EXTENSION}"

                if not self._validate_backup_preconditions(world_path):
                    return False

                return self._execute_backup_creation(world_path, backup_path, backup_name)

            except Exception as e:
                handle_error(e, "Backup creation failed")
                return False

    def _determine_world_path(self, world_dir: Optional[Path]) -> Path:
        """Determine the world directory path"""
        if world_dir:
            return world_dir
        return Path(self.config.get("server_dir")) / "world"

    def _generate_backup_name(self, name: Optional[str]) -> str:
        """Generate a safe backup name"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = self._sanitize_backup_name(name) if name else "world"
        return f"{base_name}_{timestamp}"

    def _sanitize_backup_name(self, name: str) -> str:
        """Sanitize backup name to be filesystem-safe"""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join(c if c not in invalid_chars else '_' for c in name)

        # Limit length
        if len(sanitized) > MAX_BACKUP_NAME_LENGTH:
            sanitized = sanitized[:MAX_BACKUP_NAME_LENGTH]

        return sanitized.strip() or "backup"

    def _validate_backup_preconditions(self, world_path: Path) -> bool:
        """Validate preconditions for backup creation"""
        if not world_path.exists():
            console.print(f"[red]❌ World directory not found: {world_path}[/red]")
            return False

        if not world_path.is_dir():
            console.print(f"[red]❌ World path is not a directory: {world_path}[/red]")
            return False

        # Check if world directory has content
        if not any(world_path.iterdir()):
            console.print(f"[red]❌ World directory is empty: {world_path}[/red]")
            return False

        return True

    def _execute_backup_creation(self, world_path: Path, backup_path: Path, backup_name: str) -> bool:
        """Execute the actual backup creation process"""
        self._ensure_backup_directory()

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task(f"Creating backup {backup_name}...", total=None)

            try:
                # Create backup archive
                self._create_backup_archive(world_path, backup_path)

                # Verify backup integrity
                if self._verify_backup_creation(backup_path):
                    size_mb = backup_path.stat().st_size / (1024 * 1024)
                    console.print(f"[green]✅ Backup created: {backup_path.name} ({size_mb:.1f} MB)[/green]")

                    self._log_backup_creation(backup_path, size_mb)
                    self._cleanup_old_backups()
                    return True
                else:
                    self._cleanup_failed_backup(backup_path)
                    return False

            except Exception as e:
                self._cleanup_failed_backup(backup_path)
                raise BackupError(f"Backup creation failed: {e}") from e

    def _create_backup_archive(self, world_path: Path, backup_path: Path) -> None:
        """Create the backup archive with compression"""
        try:
            # Use zipfile for better control and compression
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                self._add_directory_to_zip(zipf, world_path, world_path.name)
        except Exception as e:
            raise BackupError(f"Failed to create archive: {e}") from e

    def _add_directory_to_zip(self, zipf: zipfile.ZipFile, dir_path: Path, arc_name: str) -> None:
        """Recursively add directory contents to zip file"""
        for file_path in dir_path.rglob('*'):
            if file_path.is_file():
                # Calculate relative path for archive
                rel_path = file_path.relative_to(dir_path.parent)
                try:
                    zipf.write(file_path, rel_path)
                except (OSError, zipfile.BadZipFile) as e:
                    console.print(f"[yellow]⚠️  Skipped file {file_path}: {e}[/yellow]")

    def _verify_backup_creation(self, backup_path: Path) -> bool:
        """Verify that backup was created successfully"""
        if not backup_path.exists():
            console.print("[red]❌ Backup file was not created[/red]")
            return False

        file_size = backup_path.stat().st_size
        if file_size < MIN_BACKUP_SIZE:
            console.print(f"[red]❌ Backup file too small ({file_size} bytes)[/red]")
            return False

        # Verify ZIP integrity
        return self.verify_backup(backup_path.name)

    def _cleanup_failed_backup(self, backup_path: Path) -> None:
        """Clean up failed backup file"""
        if backup_path.exists():
            safe_delete_file(backup_path)

    def _log_backup_creation(self, backup_path: Path, size_mb: float) -> None:
        """Log backup creation details"""
        log_file = self.backup_dir / BACKUP_LOG_NAME
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().isoformat()
                f.write(f"{timestamp} - Created {backup_path.name} ({size_mb:.1f} MB)\n")
        except Exception as e:
            # Logging failure shouldn't break backup
            console.print(f"[yellow]⚠️  Failed to log backup: {e}[/yellow]")

    def _cleanup_old_backups(self) -> None:
        """Remove old backups based on configuration"""
        try:
            backups = self._get_sorted_backups()
            max_backups = self.config.get("max_backups")

            if len(backups) <= max_backups:
                return

            removed_count = 0
            for old_backup in backups[max_backups:]:
                if self._remove_old_backup(old_backup):
                    removed_count += 1

            if removed_count > 0:
                console.print(f"[cyan]🧹 Cleaned up {removed_count} old backup(s)[/cyan]")

        except Exception as e:
            handle_error(e, "Error during backup cleanup")

    def _get_sorted_backups(self) -> List[Path]:
        """Get list of backup files sorted by modification time (newest first)"""
        return sorted(
            self.backup_dir.glob(f"*{BACKUP_FILE_EXTENSION}"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

    def _remove_old_backup(self, backup_path: Path) -> bool:
        """Remove an old backup file and log the action"""
        try:
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            backup_path.unlink()

            console.print(f"[yellow]🗑️  Removed old backup: {backup_path.name} ({size_mb:.1f} MB)[/yellow]")
            self._log_backup_removal(backup_path.name, size_mb)
            return True

        except Exception as e:
            console.print(f"[red]❌ Could not remove {backup_path.name}: {e}[/red]")
            return False

    def _log_backup_removal(self, backup_name: str, size_mb: float) -> None:
        """Log backup removal"""
        log_file = self.backup_dir / BACKUP_LOG_NAME
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().isoformat()
                f.write(f"{timestamp} - Removed {backup_name} ({size_mb:.1f} MB)\n")
        except Exception:
            pass

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups with detailed information"""
        backups = []

        if not self.backup_dir.exists():
            return backups

        try:
            for backup_file in self._get_sorted_backups():
                backup_info = self._get_backup_file_info(backup_file)
                if backup_info:
                    backups.append(backup_info)

        except Exception as e:
            handle_error(e, "Error listing backups")

        return backups

    def _get_backup_file_info(self, backup_file: Path) -> Optional[Dict[str, Any]]:
        """Get detailed information about a backup file"""
        try:
            stat = backup_file.stat()
            age_hours = (datetime.now().timestamp() - stat.st_mtime) / 3600

            return {
                "name": backup_file.name,
                "path": backup_file,
                "size_mb": stat.st_size / (1024 * 1024),
                "created": datetime.fromtimestamp(stat.st_mtime),
                "age_hours": age_hours,
                "valid": self.verify_backup(backup_file.name)
            }
        except Exception as e:
            handle_error(e, f"Failed to get info for backup: {backup_file.name}")
            return None

    def restore_backup(self, backup_name: str, server_dir: Path) -> bool:
        """Restore a backup with comprehensive validation and safety measures"""
        backup_path = self.backup_dir / backup_name

        if not self._validate_restore_preconditions(backup_path):
            return False

        try:
            return self._execute_backup_restore(backup_path, server_dir)
        except Exception as e:
            handle_error(e, "Backup restore failed")
            return False

    def _validate_restore_preconditions(self, backup_path: Path) -> bool:
        """Validate preconditions for backup restore"""
        if not backup_path.exists():
            console.print(f"[red]❌ Backup not found: {backup_path.name}[/red]")
            return False

        if not self.verify_backup(backup_path.name):
            console.print(f"[red]❌ Backup file is corrupted: {backup_path.name}[/red]")
            return False

        return True

    def _execute_backup_restore(self, backup_path: Path, server_dir: Path) -> bool:
        """Execute the backup restore process"""
        world_dir = server_dir / "world"

        try:
            # Create safety backup of current world
            if world_dir.exists():
                self._create_safety_backup(world_dir, server_dir)

            # Extract backup
            with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
            ) as progress:
                task = progress.add_task(f"Restoring {backup_path.name}...", total=None)
                self._extract_backup_archive(backup_path, server_dir)

            # Verify restore
            if self._verify_restore_success(world_dir):
                console.print("[green]✅ Backup restored successfully[/green]")
                self._log_backup_restore(backup_path.name)
                return True
            else:
                console.print("[red]❌ Restore verification failed[/red]")
                return False

        except Exception as e:
            raise BackupError(f"Restore process failed: {e}") from e

    def _create_safety_backup(self, world_dir: Path, server_dir: Path) -> None:
        """Create a safety backup of current world before restore"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safety_backup = server_dir / f"world_backup_before_restore_{timestamp}"

        try:
            shutil.move(str(world_dir), str(safety_backup))
            console.print(f"[yellow]💾 Current world backed up to: {safety_backup.name}[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠️  Could not create safety backup: {e}[/yellow]")

    def _extract_backup_archive(self, backup_path: Path, server_dir: Path) -> None:
        """Extract backup archive to server directory"""
        try:
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(server_dir)
        except Exception as e:
            raise BackupError(f"Failed to extract backup: {e}") from e

    def _verify_restore_success(self, world_dir: Path) -> bool:
        """Verify that restore was successful"""
        if not world_dir.exists():
            return False

        # Check for essential world files
        essential_files = ['level.dat']
        for file_name in essential_files:
            if not (world_dir / file_name).exists():
                console.print(f"[red]❌ Essential file missing: {file_name}[/red]")
                return False

        return True

    def _log_backup_restore(self, backup_name: str) -> None:
        """Log backup restore operation"""
        log_file = self.backup_dir / BACKUP_LOG_NAME
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().isoformat()
                f.write(f"{timestamp} - Restored {backup_name}\n")
        except Exception:
            pass

    def verify_backup(self, backup_name: str) -> bool:
        """Verify backup integrity comprehensively"""
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            return False

        try:
            return self._perform_backup_verification(backup_path)
        except Exception:
            return False

    def _perform_backup_verification(self, backup_path: Path) -> bool:
        """Perform comprehensive backup verification"""
        try:
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                # Test ZIP integrity
                bad_file = zip_file.testzip()
                if bad_file:
                    console.print(f"[red]❌ Corrupted file in backup: {bad_file}[/red]")
                    return False

                # Check for essential world data
                file_list = zip_file.namelist()

                # Look for level.dat in any subdirectory
                has_level_dat = any('level.dat' in f for f in file_list)
                if not has_level_dat:
                    console.print("[red]❌ Backup missing essential world data[/red]")
                    return False

                return True

        except zipfile.BadZipFile:
            console.print("[red]❌ Backup file is not a valid ZIP archive[/red]")
            return False
        except Exception as e:
            console.print(f"[red]❌ Verification failed: {e}[/red]")
            return False

    def get_backup_info(self, backup_name: str) -> Dict[str, Any]:
        """Get comprehensive information about a specific backup"""
        backup_path = self.backup_dir / backup_name

        if not backup_path.exists():
            return {"name": backup_name, "exists": False}

        try:
            stat = backup_path.stat()

            info = {
                "name": backup_name,
                "path": str(backup_path),
                "exists": True,
                "size_mb": stat.st_size / (1024 * 1024),
                "created": datetime.fromtimestamp(stat.st_mtime),
                "valid": False,
                "file_count": 0,
                "contains_level_dat": False,
                "compression_ratio": 0.0
            }

            # Analyze ZIP contents
            if self._analyze_backup_contents(backup_path, info):
                info["valid"] = True

            return info

        except Exception as e:
            return {
                "name": backup_name,
                "exists": True,
                "valid": False,
                "error": str(e)
            }

    def _analyze_backup_contents(self, backup_path: Path, info: Dict[str, Any]) -> bool:
        """Analyze backup file contents"""
        try:
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                info["file_count"] = len(file_list)
                info["contains_level_dat"] = any('level.dat' in f for f in file_list)

                # Calculate compression ratio
                compressed_size = backup_path.stat().st_size
                uncompressed_size = sum(zip_file.getinfo(name).file_size for name in file_list)
                if uncompressed_size > 0:
                    info["compression_ratio"] = compressed_size / uncompressed_size

                return True
        except Exception:
            return False

    def start_auto_backup(self) -> None:
        """Start automatic backup thread with proper error handling"""
        if not self.config.get("auto_backup") or self.auto_backup_running:
            return

        try:
            self.auto_backup_running = True
            self.auto_backup_thread = threading.Thread(target=self._auto_backup_loop, daemon=True)
            self.auto_backup_thread.start()

            interval_hours = self.config.get("backup_interval") / 3600
            console.print(f"[green]🔄 Auto-backup started (every {interval_hours:.1f}h)[/green]")

        except Exception as e:
            handle_error(e, "Failed to start auto-backup")
            self.auto_backup_running = False

    def stop_auto_backup(self) -> None:
        """Stop automatic backup thread safely"""
        if not self.auto_backup_running:
            return

        self.auto_backup_running = False

        if self.auto_backup_thread and self.auto_backup_thread.is_alive():
            self.auto_backup_thread.join(timeout=5)

        console.print("[yellow]⏹️  Auto-backup stopped[/yellow]")

    def _auto_backup_loop(self) -> None:
        """Auto-backup loop with robust error handling"""
        interval = self.config.get("backup_interval")
        consecutive_failures = 0
        max_failures = 3

        while self.auto_backup_running:
            try:
                time.sleep(interval)

                if not self.auto_backup_running:  # Check again after sleep
                    break

                console.print("[cyan]🔄 Performing automatic backup...[/cyan]")

                if self.create_backup("auto"):
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        console.print(f"[red]❌ Auto-backup disabled after {max_failures} consecutive failures[/red]")
                        self.auto_backup_running = False

            except Exception as e:
                handle_error(e, "Auto-backup error")
                consecutive_failures += 1

                if consecutive_failures >= max_failures:
                    console.print(f"[red]❌ Auto-backup disabled after {max_failures} consecutive failures[/red]")
                    self.auto_backup_running = False

    def get_backup_stats(self) -> Dict[str, Any]:
        """Get comprehensive backup statistics"""
        backups = self.list_backups()

        if not backups:
            return self._get_empty_backup_stats()

        total_size = sum(b["size_mb"] for b in backups)
        valid_backups = [b for b in backups if b.get("valid", False)]

        return {
            "total_backups": len(backups),
            "valid_backups": len(valid_backups),
            "corrupted_backups": len(backups) - len(valid_backups),
            "total_size_mb": total_size,
            "average_size_mb": total_size / len(backups),
            "oldest": min(backups, key=lambda x: x["created"])["created"],
            "newest": max(backups, key=lambda x: x["created"])["created"],
            "auto_backup_enabled": self.config.get("auto_backup"),
            "auto_backup_running": self.auto_backup_running,
            "backup_interval_hours": self.config.get("backup_interval") / 3600,
            "max_backups": self.config.get("max_backups"),
            "backup_directory": str(self.backup_dir)
        }

    def _get_empty_backup_stats(self) -> Dict[str, Any]:
        """Get backup stats when no backups exist"""
        return {
            "total_backups": 0,
            "valid_backups": 0,
            "corrupted_backups": 0,
            "total_size_mb": 0,
            "average_size_mb": 0,
            "oldest": None,
            "newest": None,
            "auto_backup_enabled": self.config.get("auto_backup"),
            "auto_backup_running": self.auto_backup_running,
            "backup_interval_hours": self.config.get("backup_interval") / 3600,
            "max_backups": self.config.get("max_backups"),
            "backup_directory": str(self.backup_dir)
        }

    def export_backup_logs(self, filename: Optional[str] = None) -> str:
        """Export backup logs with fallback to summary generation"""
        if not filename:
            filename = f"backup_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        log_file = self.backup_dir / BACKUP_LOG_NAME

        try:
            if log_file.exists():
                shutil.copy(log_file, filename)
            else:
                self._generate_backup_summary(filename)

            console.print(f"[green]✅ Backup logs exported to: {filename}[/green]")
            return filename

        except Exception as e:
            handle_error(e, "Failed to export backup logs")
            return ""

    def _generate_backup_summary(self, filename: str) -> None:
        """Generate backup summary when no log file exists"""
        backups = self.list_backups()

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Backup Summary - {datetime.now().isoformat()}\n")
            f.write("=" * 50 + "\n\n")

            if backups:
                for backup in backups:
                    created = backup['created'].isoformat()
                    name = backup['name']
                    size = backup['size_mb']
                    valid = "✓" if backup.get('valid', False) else "✗"
                    f.write(f"{created} - {name} ({size:.1f} MB) {valid}\n")
            else:
                f.write("No backups found\n")

    def cleanup_corrupted_backups(self) -> int:
        """Remove corrupted or invalid backup files"""
        removed_count = 0

        if not self.backup_dir.exists():
            return removed_count

        for backup_file in self.backup_dir.glob(f"*{BACKUP_FILE_EXTENSION}"):
            try:
                if not self.verify_backup(backup_file.name):
                    size_mb = backup_file.stat().st_size / (1024 * 1024)

                    if safe_delete_file(backup_file):
                        console.print(
                            f"[yellow]🗑️  Removed corrupted backup: {backup_file.name} ({size_mb:.1f} MB)[/yellow]")
                        removed_count += 1

            except Exception as e:
                console.print(f"[red]❌ Could not process {backup_file.name}: {e}[/red]")

        if removed_count > 0:
            console.print(f"[cyan]🧹 Removed {removed_count} corrupted backup(s)[/cyan]")

        return removed_count

    def optimize_backups(self) -> Dict[str, int]:
        """Optimize backup storage by removing duplicates and corrupted files"""
        results = {
            "corrupted_removed": 0,
            "duplicates_removed": 0,
            "space_saved_mb": 0
        }

        try:
            # Remove corrupted backups
            results["corrupted_removed"] = self.cleanup_corrupted_backups()

            # TODO: Implement duplicate detection based on content hashing
            # This would require comparing backup contents

            console.print(f"[green]✅ Backup optimization complete[/green]")

        except Exception as e:
            handle_error(e, "Backup optimization failed")

        return results
