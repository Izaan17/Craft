"""
Utility functions for Craft Minecraft Server Manager
"""

import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

console = Console()


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""

    def signal_handler(signum, frame):
        console.print(f"\n[yellow]Received signal {signum}, shutting down gracefully...[/yellow]")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def format_bytes(bytes_value: int) -> str:
    """Format bytes in human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f"{days}d {hours}h"


def format_uptime(uptime: timedelta) -> str:
    """Format uptime timedelta in readable format"""
    total_seconds = int(uptime.total_seconds())
    return format_duration(total_seconds)


def validate_memory_setting(memory_str: str) -> bool:
    """Validate memory setting format (e.g., 2G, 512M)"""
    if not memory_str:
        return False

    memory_str = memory_str.upper().strip()

    if memory_str.endswith('G'):
        try:
            value = float(memory_str[:-1])
            return 0.1 <= value <= 64  # Reasonable range
        except ValueError:
            return False
    elif memory_str.endswith('M'):
        try:
            value = float(memory_str[:-1])
            return 100 <= value <= 65536  # Reasonable range
        except ValueError:
            return False

    return False


def parse_memory_to_mb(memory_str: str) -> Optional[int]:
    """Parse memory string to MB value"""
    if not validate_memory_setting(memory_str):
        return None

    memory_str = memory_str.upper().strip()

    try:
        if memory_str.endswith('G'):
            return int(float(memory_str[:-1]) * 1024)
        elif memory_str.endswith('M'):
            return int(float(memory_str[:-1]))
    except ValueError:
        return None

    return None


def check_java_installation() -> Dict[str, Any]:
    """Check Java installation and version"""
    import subprocess

    try:
        result = subprocess.run(
            ['java', '-version'],
            capture_output=True,
            text=True,
            timeout=10
        )

        version_output = result.stderr or result.stdout

        # Parse Java version
        java_version = "Unknown"
        if "version" in version_output:
            # Extract version number
            import re
            version_match = re.search(r'"(\d+\.\d+\.\d+)', version_output)
            if version_match:
                java_version = version_match.group(1)
            else:
                # Try newer format (Java 9+)
                version_match = re.search(r'version "(\d+)', version_output)
                if version_match:
                    java_version = f"{version_match.group(1)}.x.x"

        return {
            "installed": True,
            "version": java_version,
            "output": version_output.strip()
        }

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return {
            "installed": False,
            "version": None,
            "output": "Java not found or not accessible"
        }


def check_system_resources() -> Dict[str, Any]:
    """Check available system resources"""
    try:
        import psutil

        # Memory info
        memory = psutil.virtual_memory()

        # CPU info
        cpu_count = psutil.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=1)

        # Disk info
        disk = psutil.disk_usage('/')

        return {
            "memory": {
                "total_gb": memory.total / (1024 ** 3),
                "available_gb": memory.available / (1024 ** 3),
                "percent_used": memory.percent
            },
            "cpu": {
                "cores": cpu_count,
                "usage_percent": cpu_percent
            },
            "disk": {
                "total_gb": disk.total / (1024 ** 3),
                "free_gb": disk.free / (1024 ** 3),
                "percent_used": (disk.used / disk.total) * 100
            }
        }

    except ImportError:
        return {"error": "psutil not available"}
    except Exception as e:
        return {"error": str(e)}


def validate_port(port: int) -> bool:
    """Validate port number"""
    return 1024 <= port <= 65535


def is_port_available(port: int, host: str = 'localhost') -> bool:
    """Check if port is available for binding"""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False


def find_available_port(start_port: int = 25565, max_attempts: int = 10) -> Optional[int]:
    """Find an available port starting from start_port"""
    for port in range(start_port, start_port + max_attempts):
        if validate_port(port) and is_port_available(port):
            return port
    return None


def check_process_health(pid: int) -> Dict[str, Any]:
    """Check the health of a process by PID"""
    try:
        import psutil
        proc = psutil.Process(pid)

        return {
            "exists": True,
            "running": proc.is_running(),
            "status": proc.status(),
            "memory_mb": proc.memory_info().rss / 1024 / 1024,
            "cpu_percent": proc.cpu_percent(),
            "threads": proc.num_threads(),
            "create_time": proc.create_time()
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {
            "exists": False,
            "error": "Process not accessible"
        }


def safe_delete_file(file_path: Path, max_attempts: int = 3) -> bool:
    """Safely delete a file with retries"""
    for attempt in range(max_attempts):
        try:
            if file_path.exists():
                file_path.unlink()
            return True
        except (OSError, PermissionError) as e:
            if attempt == max_attempts - 1:
                console.print(f"[red]Failed to delete {file_path}: {e}[/red]")
                return False
            time.sleep(0.5)
    return False


def ensure_directory(dir_path: Path, mode: int = 0o755) -> bool:
    """Ensure directory exists with proper permissions"""
    try:
        dir_path.mkdir(parents=True, exist_ok=True, mode=mode)
        return True
    except (OSError, PermissionError) as e:
        console.print(f"[red]Failed to create directory {dir_path}: {e}[/red]")
        return False


def get_file_age(file_path: Path) -> Optional[timedelta]:
    """Get age of a file"""
    try:
        if file_path.exists():
            mtime = file_path.stat().st_mtime
            age = datetime.now().timestamp() - mtime
            return timedelta(seconds=age)
    except OSError:
        pass
    return None


def rotate_log_file(log_path: Path, max_size_mb: int = 10, keep_backups: int = 5) -> bool:
    """Rotate log file if it's too large"""
    try:
        if not log_path.exists():
            return True

        size_mb = log_path.stat().st_size / (1024 * 1024)

        if size_mb > max_size_mb:
            # Rotate existing backups
            for i in range(keep_backups - 1, 0, -1):
                old_backup = log_path.with_suffix(f".{i}")
                new_backup = log_path.with_suffix(f".{i + 1}")

                if old_backup.exists():
                    if new_backup.exists():
                        new_backup.unlink()
                    old_backup.rename(new_backup)

            # Move current log to .1
            backup_path = log_path.with_suffix(".1")
            if backup_path.exists():
                backup_path.unlink()
            log_path.rename(backup_path)

            console.print(f"[cyan]📝 Rotated log file: {log_path.name}[/cyan]")
            return True

    except (OSError, PermissionError) as e:
        console.print(f"[red]Failed to rotate log {log_path}: {e}[/red]")
        return False

    return True


def cleanup_old_files(directory: Path, pattern: str, max_age_days: int = 30) -> int:
    """Clean up old files matching pattern"""
    if not directory.exists():
        return 0

    removed_count = 0
    cutoff_time = datetime.now() - timedelta(days=max_age_days)

    try:
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        removed_count += 1
                        console.print(f"[yellow]🗑️  Removed old file: {file_path.name}[/yellow]")
                    except OSError as e:
                        console.print(f"[red]Failed to remove {file_path}: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error during cleanup: {e}[/red]")

    return removed_count


def create_system_info_report() -> Dict[str, Any]:
    """Create comprehensive system information report"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "platform": {
            "system": os.name,
            "platform": sys.platform
        },
        "python": {
            "version": sys.version,
            "executable": sys.executable
        },
        "java": check_java_installation(),
        "resources": check_system_resources(),
        "craft": {
            "version": "1.0.0",  # This could be read from a version file
            "install_path": str(Path(__file__).parent.absolute())
        }
    }

    return report


def export_system_report(filename: str = None) -> str:
    """Export system information to file"""
    if not filename:
        filename = f"craft_system_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    import json

    report = create_system_info_report()

    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        console.print(f"[green]✅ System report exported to: {filename}[/green]")
        return filename

    except Exception as e:
        console.print(f"[red]❌ Failed to export system report: {e}[/red]")
        return ""


def check_dependencies() -> Dict[str, bool]:
    """Check if all required dependencies are available"""
    dependencies = {}

    # Check psutil
    try:
        import psutil
        dependencies["psutil"] = True
    except ImportError:
        dependencies["psutil"] = False

    # Check rich
    try:
        import rich
        dependencies["rich"] = True
    except ImportError:
        dependencies["rich"] = False

    # Check Java
    java_info = check_java_installation()
    dependencies["java"] = java_info["installed"]

    return dependencies


def validate_installation() -> bool:
    """Validate that Craft is properly installed"""
    issues = []

    # Check dependencies
    deps = check_dependencies()
    for dep, available in deps.items():
        if not available:
            issues.append(f"Missing dependency: {dep}")

    # Check Java version
    java_info = check_java_installation()
    if java_info["installed"]:
        version = java_info["version"]
        # Very basic version check - should be more sophisticated
        if version and not (version.startswith("1.8") or version.startswith("11") or
                            version.startswith("17") or version.startswith("21")):
            issues.append(f"Java version may not be optimal: {version}")

    # Check system resources
    resources = check_system_resources()
    if "error" not in resources:
        memory_gb = resources["memory"]["total_gb"]
        if memory_gb < 2:
            issues.append(f"Low system memory: {memory_gb:.1f}GB (recommend 4GB+)")

        disk_free = resources["disk"]["free_gb"]
        if disk_free < 1:
            issues.append(f"Low disk space: {disk_free:.1f}GB (recommend 5GB+)")

    if issues:
        console.print("[red]Installation validation issues:[/red]")
        for issue in issues:
            console.print(f"  ❌ {issue}")
        return False
    else:
        console.print("[green]✅ Installation validation passed[/green]")
        return True


def get_recommended_memory() -> str:
    """Get recommended memory allocation based on system memory"""
    resources = check_system_resources()

    if "error" in resources:
        return "2G"  # Safe default

    total_memory_gb = resources["memory"]["total_gb"]

    # Leave some memory for the OS and other processes
    if total_memory_gb >= 16:
        return "8G"
    elif total_memory_gb >= 8:
        return "4G"
    elif total_memory_gb >= 4:
        return "2G"
    else:
        return "1G"


def create_desktop_shortcut(install_path: Path) -> bool:
    """Create desktop shortcut for Craft (Linux/macOS)"""
    try:
        desktop_path = Path.home() / "Desktop"
        if not desktop_path.exists():
            return False

        shortcut_path = desktop_path / "Craft Server Manager.desktop"

        shortcut_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Craft Server Manager
Comment=Minecraft Server Manager
Exec=python3 {install_path / 'craft.py'}
Icon={install_path / 'icon.png'}
Terminal=true
Categories=Game;
"""

        shortcut_path.write_text(shortcut_content)
        shortcut_path.chmod(0o755)

        console.print(f"[green]✅ Desktop shortcut created: {shortcut_path}[/green]")
        return True

    except Exception as e:
        console.print(f"[yellow]⚠️  Could not create desktop shortcut: {e}[/yellow]")
        return False


class ConfigurationError(Exception):
    """Raised when configuration is invalid"""
    pass


class ServerError(Exception):
    """Raised when server operations fail"""
    pass


class BackupError(Exception):
    """Raised when backup operations fail"""
    pass


def handle_error(error: Exception, context: str = ""):
    """Handle and log errors consistently"""
    error_type = type(error).__name__
    error_message = str(error)

    if context:
        console.print(f"[red]❌ {context}: {error_type} - {error_message}[/red]")
    else:
        console.print(f"[red]❌ {error_type}: {error_message}[/red]")

    # Could also log to file here if logging is configured


def retry_operation(func, max_attempts: int = 3, delay: float = 1.0,
                    exceptions: tuple = (Exception,)) -> Any:
    """Retry an operation with exponential backoff"""
    for attempt in range(max_attempts):
        try:
            return func()
        except exceptions as e:
            if attempt == max_attempts - 1:
                raise e

            wait_time = delay * (2 ** attempt)
            console.print(f"[yellow]⚠️  Attempt {attempt + 1} failed, retrying in {wait_time:.1f}s...[/yellow]")
            time.sleep(wait_time)

    return None
