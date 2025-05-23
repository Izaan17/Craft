"""
Backup management for Craft Minecraft Server Manager
"""

import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import ConfigManager

console = Console()


class BackupManager:
    """Enhanced backup management with compression and verification"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.backup_dir = Path(config.get("backup_dir"))
        self.auto_backup_thread = None
        self.auto_backup_running = False
        self.backup_lock = threading.Lock()
        self._ensure_backup_dir()

    def _ensure_backup_dir(self):
        """Ensure backup directory exists"""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            console.print(f"[red]❌ Could not create backup directory: {e}[/red]")

    def create_backup(self, name: str = None, world_dir: Path = None) -> bool:
        """Create a backup of the world"""
        with self.backup_lock:
            if not world_dir:
                world_dir = Path(self.config.get("server_dir")) / "world"

            if not world_dir.exists():
                console.print(f"[red]❌ World directory not found: {world_dir}[/red]")
                return False

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{name or 'world'}_{timestamp}"
            backup_path = self.backup_dir / f"{backup_name}.zip"

            try:
                self._ensure_backup_dir()

                with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console
                ) as progress:
                    task = progress.add_task(f"Creating backup {backup_name}...", total=None)

                    # Create backup
                    shutil.make_archive(str(self.backup_dir / backup_name), 'zip', world_dir)

                    # Verify backup
                    if backup_path.exists() and backup_path.stat().st_size > 0:
                        size_mb = backup_path.stat().st_size / 1024 / 1024
                        console.print(f"[green]✅ Backup created: {backup_path.name} ({size_mb:.1f} MB)[/green]")

                        # Log backup details
                        self._log_backup(backup_path, size_mb)

                        # Cleanup old backups
                        self._cleanup_old_backups()
                        return True
                    else:
                        console.print("[red]❌ Backup verification failed[/red]")
                        return False

            except Exception as e:
                console.print(f"[red]❌ Backup failed: {e}[/red]")
                return False

    def _log_backup(self, backup_path: Path, size_mb: float):
        """Log backup creation details"""
        log_file = self.backup_dir / "backup.log"
        try:
            with open(log_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Created {backup_path.name} ({size_mb:.1f} MB)\n")
        except Exception:
            pass  # Logging failure shouldn't break backup

    def _cleanup_old_backups(self):
        """Remove old backups based on configuration"""
        try:
            backups = sorted(
                self.backup_dir.glob("*.zip"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            max_backups = self.config.get("max_backups")
            if len(backups) > max_backups:
                removed_count = 0
                for old_backup in backups[max_backups:]:
                    try:
                        size_mb = old_backup.stat().st_size / 1024 / 1024
                        old_backup.unlink()
                        console.print(f"[yellow]🗑️  Removed old backup: {old_backup.name} ({size_mb:.1f} MB)[/yellow]")
                        removed_count += 1

                        # Log removal
                        self._log_cleanup(old_backup.name, size_mb)

                    except Exception as e:
                        console.print(f"[red]❌ Could not remove {old_backup.name}: {e}[/red]")

                if removed_count > 0:
                    console.print(f"[cyan]🧹 Cleaned up {removed_count} old backup(s)[/cyan]")

        except Exception as e:
            console.print(f"[red]❌ Error during cleanup: {e}[/red]")

    def _log_cleanup(self, backup_name: str, size_mb: float):
        """Log backup cleanup"""
        log_file = self.backup_dir / "backup.log"
        try:
            with open(log_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Removed {backup_name} ({size_mb:.1f} MB)\n")
        except Exception:
            pass

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups"""
        backups = []
        if not self.backup_dir.exists():
            return backups

        try:
            for backup_file in sorted(self.backup_dir.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = backup_file.stat()
                backups.append({
                    "name": backup_file.name,
                    "path": backup_file,
                    "size_mb": stat.st_size / 1024 / 1024,
                    "created": datetime.fromtimestamp(stat.st_mtime),
                    "age_hours": (datetime.now().timestamp() - stat.st_mtime) / 3600
                })
        except Exception as e:
            console.print(f"[red]❌ Error listing backups: {e}[/red]")

        return backups

    def restore_backup(self, backup_name: str, server_dir: Path) -> bool:
        """Restore a backup"""
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            console.print(f"[red]❌ Backup not found: {backup_name}[/red]")
            return False

        world_dir = server_dir / "world"

        try:
            # Backup current world before restore
            if world_dir.exists():
                backup_current = server_dir / f"world_backup_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(world_dir), str(backup_current))
                console.print(f"[yellow]💾 Current world backed up to: {backup_current.name}[/yellow]")

            # Extract backup
            with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
            ) as progress:
                task = progress.add_task(f"Restoring {backup_name}...", total=None)
                shutil.unpack_archive(str(backup_path), str(server_dir))

            # Verify restore
            if world_dir.exists():
                console.print("[green]✅ Backup restored successfully[/green]")

                # Log restore
                self._log_restore(backup_name)
                return True
            else:
                console.print("[red]❌ Restore verification failed - world directory not found[/red]")
                return False

        except Exception as e:
            console.print(f"[red]❌ Restore failed: {e}[/red]")
            return False

    def _log_restore(self, backup_name: str):
        """Log backup restore"""
        log_file = self.backup_dir / "backup.log"
        try:
            with open(log_file, 'a') as f:
                f.write(f"{datetime.now().isoformat()} - Restored {backup_name}\n")
        except Exception:
            pass

    def verify_backup(self, backup_name: str) -> bool:
        """Verify backup integrity"""
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            return False

        try:
            import zipfile
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                # Test the zip file
                zip_file.testzip()

                # Check if it contains world data
                file_list = zip_file.namelist()
                has_world_data = any('level.dat' in f for f in file_list)

                return has_world_data

        except Exception:
            return False

    def get_backup_info(self, backup_name: str) -> Dict[str, Any]:
        """Get detailed information about a backup"""
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            return {}

        try:
            import zipfile
            stat = backup_path.stat()

            info = {
                "name": backup_name,
                "path": str(backup_path),
                "size_mb": stat.st_size / 1024 / 1024,
                "created": datetime.fromtimestamp(stat.st_mtime),
                "valid": False,
                "file_count": 0,
                "contains_level_dat": False
            }

            # Analyze zip contents
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                info["file_count"] = len(file_list)
                info["contains_level_dat"] = any('level.dat' in f for f in file_list)
                info["valid"] = True

            return info

        except Exception:
            return {"name": backup_name, "valid": False}

    def start_auto_backup(self):
        """Start automatic backup thread"""
        if not self.config.get("auto_backup") or self.auto_backup_running:
            return

        self.auto_backup_running = True
        self.auto_backup_thread = threading.Thread(target=self._auto_backup_loop, daemon=True)
        self.auto_backup_thread.start()

        interval_hours = self.config.get("backup_interval") / 3600
        console.print(f"[green]🔄 Auto-backup started (every {interval_hours:.1f}h)[/green]")

    def stop_auto_backup(self):
        """Stop automatic backup thread"""
        self.auto_backup_running = False
        if self.auto_backup_thread:
            self.auto_backup_thread.join(timeout=5)
        console.print("[yellow]⏹️  Auto-backup stopped[/yellow]")

    def _auto_backup_loop(self):
        """Auto-backup loop"""
        interval = self.config.get("backup_interval")

        while self.auto_backup_running:
            time.sleep(interval)
            if self.auto_backup_running:  # Check again after sleep
                try:
                    console.print("[cyan]🔄 Performing automatic backup...[/cyan]")
                    self.create_backup("auto")
                except Exception as e:
                    console.print(f"[red]❌ Auto-backup failed: {e}[/red]")

    def get_backup_stats(self) -> Dict[str, Any]:
        """Get backup statistics"""
        backups = self.list_backups()

        if not backups:
            return {
                "total_backups": 0,
                "total_size_mb": 0,
                "oldest": None,
                "newest": None,
                "average_size_mb": 0
            }

        total_size = sum(b["size_mb"] for b in backups)

        return {
            "total_backups": len(backups),
            "total_size_mb": total_size,
            "oldest": min(backups, key=lambda x: x["created"])["created"],
            "newest": max(backups, key=lambda x: x["created"])["created"],
            "average_size_mb": total_size / len(backups),
            "auto_backup_enabled": self.config.get("auto_backup"),
            "auto_backup_running": self.auto_backup_running,
            "backup_interval_hours": self.config.get("backup_interval") / 3600,
            "max_backups": self.config.get("max_backups")
        }

    def export_backup_logs(self, filename: str = None) -> str:
        """Export backup logs"""
        if not filename:
            filename = f"backup_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        log_file = self.backup_dir / "backup.log"

        try:
            if log_file.exists():
                shutil.copy(log_file, filename)
            else:
                # Create a summary if no log file exists
                backups = self.list_backups()
                with open(filename, 'w') as f:
                    f.write(f"Backup Summary - {datetime.now().isoformat()}\n")
                    f.write("=" * 50 + "\n\n")

                    for backup in backups:
                        f.write(f"{backup['created'].isoformat()} - {backup['name']} ({backup['size_mb']:.1f} MB)\n")

            console.print(f"[green]✅ Backup logs exported to: {filename}[/green]")
            return filename

        except Exception as e:
            console.print(f"[red]❌ Failed to export logs: {e}[/red]")
            return ""

    def cleanup_corrupted_backups(self) -> int:
        """Remove corrupted or invalid backup files"""
        removed_count = 0

        for backup_file in self.backup_dir.glob("*.zip"):
            if not self.verify_backup(backup_file.name):
                try:
                    size_mb = backup_file.stat().st_size / 1024 / 1024
                    backup_file.unlink()
                    console.print(
                        f"[yellow]🗑️  Removed corrupted backup: {backup_file.name} ({size_mb:.1f} MB)[/yellow]")
                    removed_count += 1
                except Exception as e:
                    console.print(f"[red]❌ Could not remove {backup_file.name}: {e}[/red]")

        if removed_count > 0:
            console.print(f"[cyan]🧹 Removed {removed_count} corrupted backup(s)[/cyan]")

        return removed_count
