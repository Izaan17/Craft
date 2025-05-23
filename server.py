"""
Minecraft server management for Craft Minecraft Server Manager
"""

import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import ConfigManager
from process_manager import ProcessManager
from stats import ServerStats

console = Console()


class MinecraftServer:
    """Enhanced Minecraft server management"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.process_manager = ProcessManager("craft-server")
        self.stats = ServerStats()
        self.server_dir = Path(config.get("server_dir"))
        self.process = None
        self.console_output = []

    def start(self) -> bool:
        """Start the Minecraft server"""
        if self.is_running():
            console.print("[yellow]⚠️  Server is already running[/yellow]")
            return False

        # Validate configuration first
        if not self.config.validate_server_setup():
            console.print("[red]❌ Server setup validation failed[/red]")
            return False

        # Acquire lock
        if not self.process_manager.acquire_lock():
            console.print("[red]❌ Another server instance is running[/red]")
            return False

        try:
            return self._start_server()
        except Exception as e:
            self.process_manager.release_lock()
            console.print(f"[red]❌ Failed to start server: {e}[/red]")
            return False

    def _start_server(self) -> bool:
        """Simplified server start without any file modifications"""
        if self.is_running():
            console.print("[yellow]⚠️  Server is already running[/yellow]")
            return False

        if not self.process_manager.acquire_lock():
            console.print("[red]❌ Another server instance is running[/red]")
            return False

        jar_path = self.server_dir / self.config.get("jar_name")
        if not jar_path.exists():
            console.print(f"[red]❌ JAR file not found: {jar_path}[/red]")
            return False

        try:
            # Build basic Java command
            java_cmd = [
                "java",
                f"-Xms{self.config.get('memory_min')}",
                f"-Xmx{self.config.get('memory_max')}",
                "-jar", self.config.get("jar_name"), "nogui"
            ]

            # Start process
            self.process = subprocess.Popen(
                java_cmd,
                cwd=self.server_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True
            )

            self.process_manager.save_pid(self.process.pid)
            console.print("[green]✅ Server process launched![/green]")
            return True

        except Exception as e:
            self.process_manager.release_lock()
            console.print(f"[red]❌ Failed to start server: {e}[/red]")
            return False

    def _build_java_command(self) -> List[str]:
        """Build the Java command for starting the server"""
        cmd = ["java"]

        # Memory settings
        cmd.extend([
            f"-Xms{self.config.get('memory_min')}",
            f"-Xmx{self.config.get('memory_max')}"
        ])

        # Additional Java arguments
        java_args = self.config.get("java_args")
        if java_args:
            cmd.extend(shlex.split(java_args))

        # JAR file
        cmd.extend(["-jar", self.config.get("jar_name"), "nogui"])

        return cmd

    def _wait_for_startup(self, timeout: int = 120) -> bool:
        """Wait for server to start up properly"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.process or self.process.poll() is not None:
                console.print("[red]❌ Server process terminated during startup[/red]")
                return False

            # Check if server port is open
            if self._is_port_open(self.config.get("server_port")):
                time.sleep(3)  # Give it a moment to fully initialize
                return True

            time.sleep(2)

        console.print(f"[red]❌ Server startup timeout ({timeout}s)[/red]")
        return False

    def _cleanup_failed_start(self):
        """Cleanup after failed start"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass

        self.process_manager.clear_pid()
        self.process_manager.release_lock()
        self.stats.clear_process()

    def stop(self, timeout: int = 30) -> bool:
        """Stop the server gracefully"""
        if not self.is_running():
            console.print("[yellow]⚠️  Server is not running[/yellow]")
            return True

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task("Stopping server...", total=None)

            try:
                # Send stop command
                if self.send_command("stop", silent=True):
                    console.print("[cyan]📤 Stop command sent[/cyan]")

                # Wait for graceful shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self.is_running():
                        break
                    time.sleep(1)
                else:
                    # Force stop
                    console.print("[yellow]⚠️  Forcing server shutdown...[/yellow]")
                    return self._force_stop()

                self._cleanup_after_stop()
                console.print("[green]✅ Server stopped gracefully[/green]")
                return True

            except Exception as e:
                console.print(f"[red]❌ Error stopping server: {e}[/red]")
                return self._force_stop()

    def _force_stop(self) -> bool:
        """Force stop the server"""
        try:
            pid = self.process_manager.get_pid()
            if pid and self.process_manager.kill_process(pid):
                self._cleanup_after_stop()
                console.print("[green]✅ Server force stopped[/green]")
                return True
            else:
                console.print("[red]❌ Failed to force stop server[/red]")
                return False

        except Exception as e:
            console.print(f"[red]❌ Error during force stop: {e}[/red]")
            return False

    def _cleanup_after_stop(self):
        """Cleanup after server stop"""
        self.process = None
        self.process_manager.cleanup()
        self.stats.clear_process()

    def restart(self) -> bool:
        """Restart the server"""
        console.print("[cyan]🔄 Restarting server...[/cyan]")

        if self.is_running():
            if not self.stop():
                return False

        time.sleep(2)  # Brief pause
        return self.start()

    def is_running(self) -> bool:
        """Check if server is running"""
        pid = self.process_manager.get_pid()
        if not pid:
            return False

        return self.process_manager.is_process_running(pid)

    def _is_port_open(self, port: int) -> bool:
        """Check if port is open"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                return s.connect_ex(('localhost', port)) == 0
        except:
            return False

    def send_command(self, command: str, silent: bool = False) -> bool:
        """Send command to server"""
        if not self.is_running():
            if not silent:
                console.print("[red]❌ Server is not running[/red]")
            return False

        try:
            if self.process and self.process.stdin:
                self.process.stdin.write(f"{command}\n")
                self.process.stdin.flush()
                if not silent:
                    console.print(f"[green]📤 Command sent: {command}[/green]")
                return True
        except Exception as e:
            if not silent:
                console.print(f"[red]❌ Failed to send command: {e}[/red]")

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive server status"""
        base_status = {
            "running": self.is_running(),
            "port_open": self._is_port_open(self.config.get("server_port")),
            "config": self.config.get_summary()
        }

        if base_status["running"]:
            current_stats = self.stats.get_current_stats()
            base_status.update(current_stats)
            base_status["averages"] = self.stats.get_average_stats()
            base_status["peaks"] = self.stats.get_peak_stats()

        return base_status

    def get_players(self) -> Optional[List[str]]:
        """Get list of online players (requires RCON or log parsing)"""
        # This could be implemented with RCON if enabled
        # For now, return None to indicate feature not implemented
        return None

    def get_world_info(self) -> Dict[str, Any]:
        """Get world information"""
        world_dir = self.server_dir / "world"

        info = {
            "exists": world_dir.exists(),
            "size_mb": 0,
            "last_modified": None
        }

        if world_dir.exists():
            try:
                # Calculate world size
                total_size = sum(
                    f.stat().st_size
                    for f in world_dir.rglob('*')
                    if f.is_file()
                )
                info["size_mb"] = total_size / 1024 / 1024

                # Get last modified time
                info["last_modified"] = max(
                    f.stat().st_mtime
                    for f in world_dir.rglob('*')
                    if f.is_file()
                )

            except Exception:
                pass

        return info

    def get_log_tail(self, lines: int = 50) -> List[str]:
        """Get last N lines from server log"""
        log_files = [
            self.server_dir / "logs" / "latest.log",
            self.server_dir / "server.log"
        ]

        for log_file in log_files:
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        return f.readlines()[-lines:]
                except Exception:
                    continue

        return []

    def export_config(self, filename: str = None) -> str:
        """Export server configuration"""
        if not filename:
            from datetime import datetime
            filename = f"craft_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        import json

        export_data = {
            "config": self.config.data,
            "status": self.get_status(),
            "world_info": self.get_world_info(),
            "export_time": datetime.now().isoformat()
        }

        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        return filename
