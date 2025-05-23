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
                # Start server process with proper encoding
                self.process = subprocess.Popen(
                    java_cmd,
                    cwd=self.server_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace',  # Handle encoding errors gracefully
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
                    console.print("[cyan]💡 Commands can be sent with: craft command <command>[/cyan]")
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

    def _wait_for_startup(self, timeout: int = 90) -> bool:
        """Wait for server process to start properly (NeoForge needs more time)"""
        start_time = time.time()

        console.print("[dim]Waiting for NeoForge to initialize (this may take a while)...[/dim]")

        while time.time() - start_time < timeout:
            if not self.process:
                return False

            # Check if process terminated
            poll_result = self.process.poll()
            if poll_result is not None:
                console.print(f"[red]❌ Server process terminated during startup (exit code: {poll_result})[/red]")
                # Try to get some output for debugging
                try:
                    if self.process.stdout:
                        output = self.process.stdout.read()
                        if output:
                            console.print(f"[red]Last output: {output[-200:]}[/red]")
                except:
                    pass
                return False

            # Check if process is responsive (basic check)
            elapsed = time.time() - start_time

            # NeoForge typically takes 30-60 seconds to start
            if elapsed > 10:  # Wait at least 10 seconds for NeoForge
                try:
                    # Check if process is still alive and using reasonable resources
                    proc = psutil.Process(self.process.pid)
                    if proc.is_running():
                        # If it's been running for a while and seems stable, consider it started
                        if elapsed > 30:
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    return False

            # Show progress dots
            if int(elapsed) % 10 == 0 and elapsed > 0:
                console.print(f"[dim]Still starting... ({elapsed:.0f}s elapsed)[/dim]")

            time.sleep(2)

        console.print(f"[red]❌ Server startup timeout ({timeout}s)[/red]")
        console.print(
            "[yellow]💡 NeoForge servers can take 1-2 minutes to start. Try increasing timeout or check logs.[/yellow]")
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

    def stop(self, force: bool = None, timeout: int = None) -> bool:
        """Stop the server (defaults to force stop for faster shutdown)"""
        if not self.is_running():
            console.print("[yellow]⚠️  Server is not running[/yellow]")
            return True

        # Use config defaults if not specified
        if force is None:
            force = self.config.get("force_stop", True)
        if timeout is None:
            timeout = self.config.get("stop_timeout", 10)

        if force:
            console.print("[cyan]🔧 Force stopping server...[/cyan]")
            return self._force_stop()
        else:
            # Try graceful stop first
            with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
            ) as progress:
                task = progress.add_task("Stopping server gracefully...", total=None)

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
                        console.print("[yellow]⚠️  Graceful shutdown timeout, forcing stop...[/yellow]")
                        return self._force_stop()

                    self._cleanup_after_stop()
                    console.print("[green]✅ Server stopped gracefully[/green]")
                    return True

                except Exception as e:
                    console.print(f"[red]❌ Error during graceful stop: {e}[/red]")
                    console.print("[yellow]⚠️  Falling back to force stop...[/yellow]")
                    return self._force_stop()

    def _force_stop(self) -> bool:
        """Force stop the server"""
        try:
            # First try to terminate gracefully, then kill if needed
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
                # No PID found, try to cleanup anyway
                self._cleanup_after_stop()
                console.print("[yellow]⚠️  No PID found, cleaned up tracking files[/yellow]")
                return True

        except Exception as e:
            console.print(f"[red]❌ Error during force stop: {e}[/red]")
            # Try cleanup anyway
            try:
                self._cleanup_after_stop()
            except:
                pass
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
        """Check if server is running (multiple detection methods)"""
        # Method 1: Check saved PID
        pid = self.process_manager.get_pid()
        if pid and self.process_manager.is_process_running(pid):
            # Ensure stats are tracking this process
            if not self.stats.process or self.stats.process.pid != pid:
                try:
                    psutil_process = psutil.Process(pid)
                    self.stats.set_process(psutil_process)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return True

        # Method 2: Check if we have a direct process reference
        if self.process and self.process.poll() is None:
            # Update the saved PID if it's different
            actual_pid = self.process.pid
            if pid != actual_pid:
                self.process_manager.save_pid(actual_pid)
            return True

        # Method 3: Look for Java processes running our JAR
        jar_name = self.config.get("jar_name")
        java_processes = self.process_manager.find_java_processes(jar_name)

        if java_processes:
            # Found a Java process running our JAR, adopt it
            for java_pid in java_processes:
                try:
                    # Verify it's actually our server by checking working directory
                    java_process = psutil.Process(java_pid)
                    if str(self.server_dir) in java_process.cwd():
                        # This is our server, update tracking
                        self.process_manager.save_pid(java_pid)
                        self.stats.set_process(java_process)
                        console.print(f"[yellow]📡 Adopted running server process (PID: {java_pid})[/yellow]")
                        # Note: We can't send commands to adopted processes
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        # No server found
        return False

    def can_send_commands(self) -> bool:
        """Check if we can send commands to the server"""
        return (self.process is not None and
                self.process.poll() is None and
                self.process.stdin is not None)

    def send_command(self, command: str, silent: bool = False) -> bool:
        """Send command to server console"""
        if not self.is_running():
            if not silent:
                console.print("[red]❌ Server is not running[/red]")
            return False

        if not self.can_send_commands():
            if not silent:
                console.print("[yellow]⚠️  Cannot send commands to adopted server process[/yellow]")
                console.print("[cyan]💡 Restart the server with Craft to enable command sending:[/cyan]")
                console.print("   craft restart")
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
                console.print(f"[red]❌ Failed to send command: {e}[/red]")

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive server status"""
        is_running = self.is_running()

        base_status = {
            "running": is_running,
            "can_send_commands": self.can_send_commands() if is_running else False,
            "config": self.config.get_summary(),
            "debug_info": self._get_debug_info()
        }

        if is_running:
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
            base_status.update(current_stats)
            base_status["averages"] = self.stats.get_average_stats()
            base_status["peaks"] = self.stats.get_peak_stats()

        return base_status

    def _get_debug_info(self) -> Dict[str, Any]:
        """Get debug information for troubleshooting"""
        debug_info = {}

        # PID file info
        pid = self.process_manager.get_pid()
        debug_info["saved_pid"] = pid
        debug_info["pid_file_exists"] = self.process_manager.pid_file.exists()

        # Process info
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

        # Direct process reference
        if self.process:
            debug_info["direct_process_poll"] = self.process.poll()
            debug_info["direct_process_pid"] = getattr(self.process, 'pid', None)
            debug_info["has_stdin"] = self.process.stdin is not None
        else:
            debug_info["direct_process"] = None

        # Java processes
        jar_name = self.config.get("jar_name")
        try:
            java_processes = self.process_manager.find_java_processes(jar_name)
            debug_info["java_processes_found"] = len(java_processes)
            debug_info["java_process_pids"] = java_processes
        except Exception as e:
            debug_info["java_search_error"] = str(e)
            debug_info["java_processes_found"] = 0
            debug_info["java_process_pids"] = []

        # Command capability
        debug_info["can_send_commands"] = self.can_send_commands()

        return debug_info

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
