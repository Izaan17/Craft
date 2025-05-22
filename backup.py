import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import List

from utils import print_info, print_success, print_error, print_warning


class BackupManager:
    def __init__(self, config):
        self.config = config
        self.server_dir = Path(config.get("server_dir"))
        self.backup_dir = Path(config.get("backup_dir"))
        self.max_backups = config.get("max_backups")
        self.backup_interval = config.get("backup_interval")
        self.auto_backup_enabled = config.get("auto_backup")
        self.backup_thread = None
        self.stop_event = threading.Event()

    def backup_world(self, backup_name: str = None) -> bool:
        """Create a backup of the world"""
        world_dir = self.server_dir / "world"
        if not world_dir.exists():
            print_error(f"World directory not found at {world_dir}")
            return False

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if backup_name:
            archive_name = self.backup_dir / f"{backup_name}_{timestamp}"
        else:
            archive_name = self.backup_dir / f"world_backup_{timestamp}"

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            print_info(f"Creating backup: {archive_name.name}.zip")

            # Create the archive
            shutil.make_archive(str(archive_name), 'zip', world_dir)

            # Verify backup was created
            zip_file = Path(f"{archive_name}.zip")
            if zip_file.exists() and zip_file.stat().st_size > 0:
                print_success(f"Backup created: {zip_file.name} ({self._format_size(zip_file.stat().st_size)})")
                self._cleanup_old_backups()
                return True
            else:
                print_error("Backup file was not created properly")
                return False

        except Exception as e:
            print_error(f"Backup failed: {e}")
            return False

    def _cleanup_old_backups(self):
        """Remove old backups based on max_backups setting"""
        try:
            backups = sorted(self.backup_dir.glob("world_backup_*.zip"), key=lambda x: x.stat().st_mtime)

            if len(backups) > self.max_backups:
                to_remove = backups[:-self.max_backups]
                for old_backup in to_remove:
                    print_info(f"Removing old backup: {old_backup.name}")
                    old_backup.unlink()

                if to_remove:
                    print_success(f"Cleaned up {len(to_remove)} old backup(s)")

        except Exception as e:
            print_error(f"Error during backup cleanup: {e}")

    def list_backups(self) -> List[dict]:
        """List all available backups with details"""
        backups = []
        if not self.backup_dir.exists():
            return backups

        for backup_file in sorted(self.backup_dir.glob("world_backup_*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
            stat = backup_file.stat()
            backups.append({
                'name': backup_file.name,
                'size': stat.st_size,
                'size_formatted': self._format_size(stat.st_size),
                'created': datetime.fromtimestamp(stat.st_mtime),
                'path': backup_file
            })

        return backups

    def restore_backup(self, backup_name: str) -> bool:
        """Restore a backup (server should be stopped first)"""
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            print_error(f"Backup not found: {backup_name}")
            return False

        world_dir = self.server_dir / "world"

        try:
            # Backup current world before restore
            if world_dir.exists():
                backup_current = self.server_dir / f"world_backup_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                print_info(f"Backing up current world to {backup_current.name}")
                shutil.move(str(world_dir), str(backup_current))

            # Extract backup
            print_info(f"Restoring backup: {backup_name}")
            shutil.unpack_archive(str(backup_path), str(self.server_dir))

            print_success("Backup restored successfully")
            return True

        except Exception as e:
            print_error(f"Restore failed: {e}")
            return False

    def start_auto_backup(self):
        """Start automatic backup thread"""
        if not self.auto_backup_enabled:
            return

        if self.backup_thread and self.backup_thread.is_alive():
            print_warning("Auto backup is already running")
            return

        self.stop_event.clear()
        self.backup_thread = threading.Thread(target=self._auto_backup_loop, daemon=True)
        self.backup_thread.start()
        print_success(f"Auto backup started (interval: {self.backup_interval}s)")

    def stop_auto_backup(self):
        """Stop automatic backup thread"""
        if self.backup_thread and self.backup_thread.is_alive():
            self.stop_event.set()
            print_info("Auto backup stopped")

    def _auto_backup_loop(self):
        """Auto backup loop running in separate thread"""
        while not self.stop_event.wait(self.backup_interval):
            try:
                # Only backup if world directory exists
                world_dir = self.server_dir / "world"
                if world_dir.exists():
                    print_info("Performing automatic backup...")
                    self.backup_world("auto")
                else:
                    print_warning("World directory not found, skipping auto backup")
            except Exception as e:
                print_error(f"Auto backup error: {e}")

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"