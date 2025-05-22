import time
import threading
from pathlib import Path
from config import Config
from server import MinecraftServer
from backup import BackupManager
from utils import print_info, print_error, print_success, print_warning

class Watchdog:
    def __init__(self, config_path: Path):
        self.config = Config(config_path)
        self.server = MinecraftServer(self.config)
        self.backup_manager = BackupManager(self.config)
        self.interval = self.config.get("watchdog_interval")
        self.running = False
        self.thread = None
        self.restart_count = 0
        self.last_restart = 0

    def start(self):
        """Start the watchdog"""
        if self.running:
            print_warning("Watchdog is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

        # Start auto backup if enabled
        self.backup_manager.start_auto_backup()

        print_success("Watchdog started successfully")

    def stop(self):
        """Stop the watchdog"""
        if not self.running:
            print_warning("Watchdog is not running")
            return

        self.running = False
        self.backup_manager.stop_auto_backup()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        print_info("Watchdog stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        print_info(f"Watchdog monitoring started (interval: {self.interval}s)")

        while self.running:
            try:
                if not self.server.is_running():
                    self._handle_server_down()
                else:
                    # Reset restart count if server is running fine
                    if time.time() - self.last_restart > 300:  # 5 minutes
                        self.restart_count = 0

                time.sleep(self.interval)

            except Exception as e:
                print_error(f"Watchdog error: {e}")
                time.sleep(10)  # Wait before retrying

    def _handle_server_down(self):
        """Handle server down situation"""
        current_time = time.time()

        # Prevent restart loops
        if self.restart_count >= 3:
            if current_time - self.last_restart < 600:  # 10 minutes
                print_error("Too many restarts, waiting before next attempt...")
                time.sleep(300)  # Wait 5 minutes
                return
            else:
                self.restart_count = 0

        print_error("Server is down! Attempting restart...")

        if self.server.start():
            self.restart_count += 1
            self.last_restart = current_time
            print_success(f"Server restarted successfully (attempt #{self.restart_count})")
        else:
            print_error("Failed to restart server")

    def get_status(self) -> dict:
        """Get watchdog status"""
        return {
            'running': self.running,
            'restart_count': self.restart_count,
            'last_restart': self.last_restart,
            'auto_backup_enabled': self.backup_manager.auto_backup_enabled
        }
