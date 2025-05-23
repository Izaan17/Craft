"""
Minecraft server management for Craft Minecraft Server Manager
Simple process management for NeoForge/Minecraft servers
"""

import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any

import psutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import ConfigManager
from process_manager import ProcessManager
from stats import ServerStats

console = Console()

class MinecraftServer:
    """Simple Minecraft server process management"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.process_manager = ProcessManager("craft-server")
        self.stats = ServerStats()
        self.server_dir = Path(config.get("server_dir"))
        self.process = None

    def start(self) -> bool:
        """Start the Minecraft server"""
        if self.is_running():
            console.print("[yellow]⚠️  Server is already running[/yellow]")
            return False

        # Basic validation
        jar_path = self.server_dir / self.config.get("jar_name")
        if not jar_path.exists():
            console.print(f"[red]❌ JAR file not found: {jar_path}[/red]")
            console.print(f"[cyan]💡 Place your NeoForge server JAR at: {jar_path}[/cyan]")
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
        """Internal server start logic"""
        # Ensure server directory exists
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Build Java command
        java_cmd = self._build_java_command()

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task("Starting NeoForge server...", total=None)

            try:
                # Start server process
                self.process = subprocess.Popen(
                    java_cmd,
                    cwd=self.server_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )

                # Save PID
                self.process_manager.save_pid(self.process.pid)

                # Wait for process to stabilize
                if self._wait_for_startup():
                    psutil_process = psutil.Process(self.process.pid)
                    self.stats.set_process(psutil_process)
                    console.print("[green]✅ NeoForge server started successfully![/green]")
                    console.print(f"[dim]PID: {self.process.pid} | Working Dir: {self.server_dir}[/dim]")
                    return True
                else:
                    self._cleanup_failed_start()
                    return False

            except Exception as e:
                self._cleanup_failed_start()
                raise e

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

        # JAR file and nogui flag
        cmd.extend(["-jar", self.config.get("jar_name"), "nogui"])

        return cmd

    def _wait_for_startup(self, timeout: int = 60) -> bool:
        """Wait for server process to start properly"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.process:
                return False

            # Check if process terminated
            if self.process.poll() is not None:
                console.print("[red]❌ Server process terminated during startup[/red]")
                return False

            # Process is running, give it a moment to initialize
            if time.time() - start_time > 5:  # Wait at least 5 seconds
                return True

            time.sleep(1)

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
                # Send stop command to server
                if self.send_command("stop", silent=True):
                    console.print("[cyan]📤 Stop command sent[/cyan]")

                # Wait for graceful shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self.is_running():
                        break
                    time.sleep(1)
                else:
                    # Force stop if graceful shutdown failed
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
        """Check if server is running (process-based, no port checking)"""
        pid = self.process_manager.get_pid()
        if not pid:
            return False

        return self.process_manager.is_process_running(pid)

    def send_command(self, command: str, silent: bool = False) -> bool:
        """Send command to server console"""
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
            "config": self.config.get_summary()
        }

        if base_status["running"]:
            current_stats = self.stats.get_current_stats()
            base_status.update(current_stats)
            base_status["averages"] = self.stats.get_average_stats()
            base_status["peaks"] = self.stats.get_peak_stats()

        return base_status

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