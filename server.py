"""
Server management module for Craft Minecraft Server Manager

Handles Minecraft server process lifecycle, monitoring, and command execution
with robust error handling and process tracking.
"""

import shlex
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

import psutil
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import ConfigManager
from process_manager import ProcessManager
from stats import ServerStats
from utils import handle_error

console = Console()

# Constants
DEFAULT_STARTUP_TIMEOUT = 90
MIN_STARTUP_WAIT = 10
PROGRESS_UPDATE_INTERVAL = 10
MAX_LOG_LINES = 1000


class ServerError(Exception):
    """Custom exception for server-related errors"""
    pass


class MinecraftServer:
    """Enhanced Minecraft server process management with robust error handling"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.process_manager = ProcessManager("craft-server")
        self.stats = ServerStats()
        self.server_dir = Path(config.get("server_dir"))
        self.process: Optional[subprocess.Popen] = None

        # Ensure server directory exists
        self._ensure_server_directory()

    def _ensure_server_directory(self) -> None:
        """Ensure the server directory exists"""
        try:
            self.server_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            handle_error(e, f"Failed to create server directory: {self.server_dir}")

    def start(self) -> bool:
        """Start the Minecraft server with comprehensive validation and error handling"""
        try:
            if self.is_running():
                console.print("[yellow]⚠️  Server is already running[/yellow]")
                return False

            if not self._validate_startup_requirements():
                return False

            if not self._acquire_server_lock():
                return False

            return self._execute_server_start()

        except Exception as e:
            self._cleanup_failed_start()
            handle_error(e, "Failed to start server")
            return False

    def _validate_startup_requirements(self) -> bool:
        """Validate all requirements before starting the server"""
        jar_path = self.server_dir / self.config.get("jar_name")

        if not jar_path.exists():
            console.print(f"[red]❌ JAR file not found: {jar_path}[/red]")
            console.print(f"[cyan]💡 Place your NeoForge server JAR at: {jar_path}[/cyan]")
            return False

        if not jar_path.is_file():
            console.print(f"[red]❌ JAR path is not a file: {jar_path}[/red]")
            return False

        # Check Java availability
        if not self._check_java_availability():
            return False

        # Validate memory settings
        if not self._validate_memory_settings():
            return False

        return True

    def _check_java_availability(self) -> bool:
        """Check if Java is available and accessible"""
        try:
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            console.print("[red]❌ Java not found or not accessible[/red]")
            console.print("[cyan]💡 Ensure Java is installed and in your PATH[/cyan]")
            return False

    def _validate_memory_settings(self) -> bool:
        """Validate memory configuration settings"""
        from utils import validate_memory_setting, parse_memory_to_mb

        memory_min = self.config.get("memory_min")
        memory_max = self.config.get("memory_max")

        if not validate_memory_setting(memory_min):
            console.print(f"[red]❌ Invalid minimum memory setting: {memory_min}[/red]")
            return False

        if not validate_memory_setting(memory_max):
            console.print(f"[red]❌ Invalid maximum memory setting: {memory_max}[/red]")
            return False

        min_mb = parse_memory_to_mb(memory_min)
        max_mb = parse_memory_to_mb(memory_max)

        if min_mb and max_mb and min_mb > max_mb:
            console.print("[red]❌ Minimum memory cannot be greater than maximum memory[/red]")
            return False

        return True

    def _acquire_server_lock(self) -> bool:
        """Acquire exclusive server lock"""
        if not self.process_manager.acquire_lock():
            console.print("[red]❌ Another server instance is running[/red]")
            return False
        return True

    def _execute_server_start(self) -> bool:
        """Execute the actual server startup process"""
        java_cmd = self._build_java_command()

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task("Starting NeoForge server...", total=None)

            try:
                self.process = self._create_server_process(java_cmd)
                self.process_manager.save_pid(self.process.pid)

                if self._wait_for_startup():
                    self._finalize_successful_start()
                    return True
                else:
                    self._cleanup_failed_start()
                    return False

            except Exception as e:
                self._cleanup_failed_start()
                raise ServerError(f"Server startup failed: {e}") from e

    def _build_java_command(self) -> List[str]:
        """Build the complete Java command for starting the server"""
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

    def _create_server_process(self, java_cmd: List[str]) -> subprocess.Popen:
        """Create the server subprocess with proper configuration"""
        return subprocess.Popen(
            java_cmd,
            cwd=self.server_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            universal_newlines=True
        )

    def _wait_for_startup(self, timeout: int = DEFAULT_STARTUP_TIMEOUT) -> bool:
        """Wait for server process to start properly with detailed progress tracking"""
        start_time = time.time()
        console.print("[dim]Waiting for NeoForge to initialize (this may take a while)...[/dim]")

        while time.time() - start_time < timeout:
            if not self._is_process_alive():
                self._handle_startup_failure()
                return False

            elapsed = time.time() - start_time

            # NeoForge typically takes 30-60 seconds to start
            if elapsed > MIN_STARTUP_WAIT:
                if self._check_process_stability(elapsed):
                    return True

            self._show_startup_progress(elapsed)
            time.sleep(2)

        console.print(f"[red]❌ Server startup timeout ({timeout}s)[/red]")
        self._show_startup_timeout_help()
        return False

    def _is_process_alive(self) -> bool:
        """Check if the server process is still alive"""
        if not self.process:
            return False

        poll_result = self.process.poll()
        return poll_result is None

    def _handle_startup_failure(self) -> None:
        """Handle server process termination during startup"""
        if self.process:
            exit_code = self.process.poll()
            console.print(f"[red]❌ Server process terminated during startup (exit code: {exit_code})[/red]")

            # Try to get some output for debugging
            self._show_startup_error_output()

    def _show_startup_error_output(self) -> None:
        """Show error output from failed startup"""
        try:
            if self.process and self.process.stdout:
                output = self.process.stdout.read()
                if output:
                    console.print(f"[red]Last output: {output[-200:]}[/red]")
        except Exception:
            pass

    def _check_process_stability(self, elapsed: float) -> bool:
        """Check if the process is stable and ready"""
        try:
            proc = psutil.Process(self.process.pid)
            if proc.is_running():
                # If it's been running for a reasonable time and seems stable
                if elapsed > 30:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

        return False

    def _show_startup_progress(self, elapsed: float) -> None:
        """Show periodic startup progress messages"""
        if int(elapsed) % PROGRESS_UPDATE_INTERVAL == 0 and elapsed > 0:
            console.print(f"[dim]Still starting... ({elapsed:.0f}s elapsed)[/dim]")

    def _show_startup_timeout_help(self) -> None:
        """Show helpful message when startup times out"""
        console.print(
            "[yellow]💡 NeoForge servers can take 1-2 minutes to start. "
            "Try increasing timeout or check logs.[/yellow]"
        )

    def _finalize_successful_start(self) -> None:
        """Finalize successful server start"""
        psutil_process = psutil.Process(self.process.pid)
        self.stats.set_process(psutil_process)

        console.print("[green]✅ NeoForge server started successfully![/green]")
        console.print(f"[dim]PID: {self.process.pid} | Working Dir: {self.server_dir}[/dim]")
        console.print("[cyan]💡 Commands can be sent with: craft command <command>[/cyan]")

    def _cleanup_failed_start(self) -> None:
        """Cleanup after failed server start"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        self.process_manager.clear_pid()
        self.process_manager.release_lock()
        self.stats.clear_process()
        self.process = None

    def stop(self, force: Optional[bool] = None, timeout: Optional[int] = None) -> bool:
        """Stop the server with configurable shutdown method"""
        if not self.is_running():
            console.print("[yellow]⚠️  Server is not running[/yellow]")
            return True

        # Use config defaults if not specified
        if force is None:
            force = self.config.get("force_stop", True)
        if timeout is None:
            timeout = self.config.get("stop_timeout", 10)

        try:
            if force:
                return self._force_stop()
            else:
                return self._graceful_stop(timeout)
        except Exception as e:
            handle_error(e, "Error during server stop")
            return self._force_stop()

    def _graceful_stop(self, timeout: int) -> bool:
        """Attempt graceful server shutdown"""
        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task("Stopping server gracefully...", total=None)

            try:
                if self.send_command("stop", silent=True):
                    console.print("[cyan]📤 Stop command sent[/cyan]")

                if self._wait_for_graceful_shutdown(timeout):
                    self._cleanup_after_stop()
                    console.print("[green]✅ Server stopped gracefully[/green]")
                    return True
                else:
                    console.print("[yellow]⚠️  Graceful shutdown timeout, forcing stop...[/yellow]")
                    return self._force_stop()

            except Exception as e:
                console.print(f"[red]❌ Error during graceful stop: {e}[/red]")
                console.print("[yellow]⚠️  Falling back to force stop...[/yellow]")
                return self._force_stop()

    def _wait_for_graceful_shutdown(self, timeout: int) -> bool:
        """Wait for graceful shutdown to complete"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.is_running():
                return True
            time.sleep(1)
        return False

    def _force_stop(self) -> bool:
        """Force stop the server process"""
        console.print("[cyan]🔧 Force stopping server...[/cyan]")

        try:
            pid = self.process_manager.get_pid()
            if pid:
                success = self.process_manager.kill_process(pid, timeout=5)
                if success:
                    self._cleanup_after_stop()
                    console.print("[green]✅ Server force stopped[/green]")
                    return True
                else:
                    console.print("[red]❌ Failed to force stop server[/red]")
                    return False
            else:
                self._cleanup_after_stop()
                console.print("[yellow]⚠️  No PID found, cleaned up tracking files[/yellow]")
                return True

        except Exception as e:
            handle_error(e, "Error during force stop")
            # Try cleanup anyway
            try:
                self._cleanup_after_stop()
            except Exception:
                pass
            return False

    def _cleanup_after_stop(self) -> None:
        """Cleanup resources after server stop"""
        self.process = None
        self.process_manager.cleanup()
        self.stats.clear_process()

    def restart(self) -> bool:
        """Restart the server with proper sequencing"""
        console.print("[cyan]🔄 Restarting server...[/cyan]")

        if self.is_running():
            if not self.stop():
                console.print("[red]❌ Failed to stop server for restart[/red]")
                return False

        # Brief pause to ensure clean shutdown
        time.sleep(2)
        return self.start()

    def is_running(self) -> bool:
        """Check if server is running using multiple detection methods"""
        # Method 1: Check saved PID
        if self._check_saved_pid():
            return True

        # Method 2: Check direct process reference
        if self._check_direct_process():
            return True

        # Method 3: Look for orphaned Java processes
        if self._check_orphaned_processes():
            return True

        return False

    def _check_saved_pid(self) -> bool:
        """Check if saved PID corresponds to running server"""
        pid = self.process_manager.get_pid()
        if pid and self.process_manager.is_process_running(pid):
            # Ensure stats are tracking this process
            self._ensure_stats_tracking(pid)
            return True
        return False

    def _check_direct_process(self) -> bool:
        """Check direct process reference"""
        if self.process and self.process.poll() is None:
            # Update the saved PID if it's different
            actual_pid = self.process.pid
            saved_pid = self.process_manager.get_pid()
            if saved_pid != actual_pid:
                self.process_manager.save_pid(actual_pid)
            return True
        return False

    def _check_orphaned_processes(self) -> bool:
        """Look for and adopt orphaned Java processes"""
        jar_name = self.config.get("jar_name")
        java_processes = self.process_manager.find_java_processes(jar_name)

        for java_pid in java_processes:
            if self._try_adopt_process(java_pid):
                return True

        return False

    def _try_adopt_process(self, java_pid: int) -> bool:
        """Try to adopt an orphaned Java process"""
        try:
            java_process = psutil.Process(java_pid)
            if str(self.server_dir) in java_process.cwd():
                # This is our server, update tracking
                self.process_manager.save_pid(java_pid)
                self.stats.set_process(java_process)
                console.print(f"[yellow]📡 Adopted running server process (PID: {java_pid})[/yellow]")
                # Note: We can't send commands to adopted processes
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return False

    def _ensure_stats_tracking(self, pid: int) -> None:
        """Ensure stats are tracking the correct process"""
        if not self.stats.process or self.stats.process.pid != pid:
            try:
                psutil_process = psutil.Process(pid)
                self.stats.set_process(psutil_process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def can_send_commands(self) -> bool:
        """Check if we can send commands to the server"""
        return (self.process is not None and
                self.process.poll() is None and
                self.process.stdin is not None)

    def send_command(self, command: str, silent: bool = False) -> bool:
        """Send command to server console with comprehensive error handling"""
        if not command.strip():
            if not silent:
                console.print("[red]❌ Command cannot be empty[/red]")
            return False

        if not self.is_running():
            if not silent:
                console.print("[red]❌ Server is not running[/red]")
            return False

        if not self.can_send_commands():
            if not silent:
                self._show_command_limitation_message()
            return False

        try:
            self.process.stdin.write(f"{command}\n")
            self.process.stdin.flush()
            if not silent:
                console.print(f"[green]📤 Command sent: {command}[/green]")
            return True

        except BrokenPipeError:
            if not silent:
                console.print("[red]❌ Server stdin pipe is broken - server may have crashed[/red]")
        except Exception as e:
            if not silent:
                handle_error(e, "Failed to send command")

        return False

    def _show_command_limitation_message(self) -> None:
        """Show message about command limitations for adopted processes"""
        console.print("[yellow]⚠️  Cannot send commands to adopted server process[/yellow]")
        console.print("[cyan]💡 Restart the server with Craft to enable command sending:[/cyan]")
        console.print("   craft restart")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive server status with detailed information"""
        is_running = self.is_running()

        base_status = {
            "running": is_running,
            "can_send_commands": self.can_send_commands() if is_running else False,
            "config": self.config.get_summary(),
            "debug_info": self._get_debug_info(),
            "world_info": self.get_world_info()
        }

        if is_running:
            self._update_status_with_runtime_info(base_status)

        return base_status

    def _update_status_with_runtime_info(self, status: Dict[str, Any]) -> None:
        """Update status with runtime information"""
        # Ensure stats are tracking the current process
        pid = self.process_manager.get_pid()
        if pid and (not self.stats.process or self.stats.process.pid != pid):
            try:
                psutil_process = psutil.Process(pid)
                self.stats.set_process(psutil_process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Get current stats
        current_stats = self.stats.get_current_stats()
        status.update(current_stats)
        status["averages"] = self.stats.get_average_stats()
        status["peaks"] = self.stats.get_peak_stats()

    def _get_debug_info(self) -> Dict[str, Any]:
        """Get comprehensive debug information for troubleshooting"""
        debug_info = {}

        # PID file information
        self._add_pid_debug_info(debug_info)

        # Process information
        self._add_process_debug_info(debug_info)

        # Direct process reference information
        self._add_direct_process_debug_info(debug_info)

        # Java processes information
        self._add_java_processes_debug_info(debug_info)

        # Command capability
        debug_info["can_send_commands"] = self.can_send_commands()

        return debug_info

    def _add_pid_debug_info(self, debug_info: Dict[str, Any]) -> None:
        """Add PID-related debug information"""
        pid = self.process_manager.get_pid()
        debug_info["saved_pid"] = pid
        debug_info["pid_file_exists"] = self.process_manager.pid_file.exists()

        if pid:
            debug_info["pid_exists"] = psutil.pid_exists(pid)
            try:
                proc = psutil.Process(pid)
                debug_info["process_running"] = proc.is_running()
                debug_info["process_name"] = proc.name()
                debug_info["process_cwd"] = proc.cwd()
                debug_info["process_status"] = proc.status()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                debug_info["process_error"] = str(e)

    def _add_process_debug_info(self, debug_info: Dict[str, Any]) -> None:
        """Add process-related debug information"""
        # This is handled in _add_pid_debug_info
        pass

    def _add_direct_process_debug_info(self, debug_info: Dict[str, Any]) -> None:
        """Add direct process reference debug information"""
        if self.process:
            debug_info["direct_process_poll"] = self.process.poll()
            debug_info["direct_process_pid"] = getattr(self.process, 'pid', None)
            debug_info["has_stdin"] = self.process.stdin is not None
        else:
            debug_info["direct_process"] = None

    def _add_java_processes_debug_info(self, debug_info: Dict[str, Any]) -> None:
        """Add Java processes debug information"""
        jar_name = self.config.get("jar_name")
        try:
            java_processes = self.process_manager.find_java_processes(jar_name)
            debug_info["java_processes_found"] = len(java_processes)
            debug_info["java_process_pids"] = java_processes
        except Exception as e:
            debug_info["java_search_error"] = str(e)
            debug_info["java_processes_found"] = 0
            debug_info["java_process_pids"] = []

    def get_process_health(self) -> Dict[str, Any]:
        """Get detailed process health information"""
        pid = self.process_manager.get_pid()
        if not pid:
            return {"healthy": False, "reason": "No PID found"}

        try:
            proc = psutil.Process(pid)

            health_info = {
                "healthy": True,
                "pid": pid,
                "status": proc.status(),
                "running": proc.is_running(),
                "memory_mb": proc.memory_info().rss / 1024 / 1024,
                "cpu_percent": proc.cpu_percent(),
                "threads": proc.num_threads(),
                "create_time": proc.create_time(),
                "cwd": proc.cwd()
            }

            # Check for concerning states
            if proc.status() == 'zombie':
                health_info["healthy"] = False
                health_info["reason"] = "Process is zombie"
            elif not proc.is_running():
                health_info["healthy"] = False
                health_info["reason"] = "Process not running"

            return health_info

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return {
                "healthy": False,
                "reason": f"Cannot access process: {e}",
                "pid": pid
            }

    def get_world_info(self) -> Dict[str, Any]:
        """Get comprehensive world information"""
        world_dir = self.server_dir / "world"

        info = {
            "exists": world_dir.exists(),
            "size_mb": 0,
            "last_modified": None,
            "player_data_count": 0
        }

        if world_dir.exists():
            try:
                info.update(self._calculate_world_metrics(world_dir))
            except Exception as e:
                handle_error(e, "Failed to calculate world metrics")

        return info

    def _calculate_world_metrics(self, world_dir: Path) -> Dict[str, Any]:
        """Calculate various world metrics"""
        total_size = 0
        file_count = 0
        latest_mtime = 0

        for file_path in world_dir.rglob('*'):
            if file_path.is_file():
                stat = file_path.stat()
                total_size += stat.st_size
                file_count += 1
                latest_mtime = max(latest_mtime, stat.st_mtime)

        # Count player data files
        playerdata_dir = world_dir / "playerdata"
        player_count = 0
        if playerdata_dir.exists():
            player_count = len(list(playerdata_dir.glob("*.dat")))

        return {
            "size_mb": total_size / (1024 * 1024),
            "file_count": file_count,
            "last_modified": latest_mtime if latest_mtime > 0 else None,
            "player_data_count": player_count
        }

    def get_log_tail(self, lines: int = 50) -> List[str]:
        """Get last N lines from server log with multiple fallback locations"""
        log_files = [
            self.server_dir / "logs" / "latest.log",
            self.server_dir / "server.log",
            self.server_dir / "logs" / "debug.log"
        ]

        for log_file in log_files:
            if log_file.exists():
                try:
                    return self._read_log_file_tail(log_file, lines)
                except Exception as e:
                    handle_error(e, f"Failed to read log file: {log_file}")
                    continue

        return []

    def _read_log_file_tail(self, log_file: Path, lines: int) -> List[str]:
        """Read the tail of a log file safely"""
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
            return all_lines[-lines:] if all_lines else []

    def export_config(self, filename: Optional[str] = None) -> str:
        """Export comprehensive server configuration and status"""
        if not filename:
            from datetime import datetime
            filename = f"craft_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        import json
        from datetime import datetime

        export_data = {
            "config": self.config.data,
            "status": self.get_status(),
            "world_info": self.get_world_info(),
            "export_time": datetime.now().isoformat(),
            "craft_version": "1.0.0"
        }

        try:
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)

            console.print(f"[green]✅ Configuration exported to: {filename}[/green]")
            return filename
        except Exception as e:
            handle_error(e, "Failed to export configuration")
            return ""
