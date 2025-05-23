"""
Process management utilities for Craft Minecraft Server Manager

Handles server process tracking, locking, and control with robust error handling
and cross-platform compatibility for process management operations.
"""

import fcntl
import os
import signal
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

import psutil

from utils import handle_error, safe_delete_file

# Constants
DEFAULT_KILL_TIMEOUT = 10
JAVA_PROCESS_NAME = "java"
LOCK_ACQUIRE_TIMEOUT = 5
PROCESS_SEARCH_TIMEOUT = 30


class ProcessLockError(Exception):
    """Exception raised when process lock operations fail"""
    pass


class ProcessManager:
    """Enhanced process management with robust tracking and control capabilities"""

    def __init__(self, name: str = "craft"):
        """Initialize process manager with specified name prefix"""
        self.name = name
        self.pid_file = Path(f"{name}.pid")
        self.lock_file = Path(f"{name}.lock")
        self.lock_fd: Optional[int] = None

        # Ensure clean state on initialization
        self._cleanup_stale_lock()

    def _cleanup_stale_lock(self) -> None:
        """Clean up stale lock files from previous runs"""
        try:
            if self.lock_file.exists():
                # Try to read the PID from lock file
                lock_content = self.lock_file.read_text().strip()
                if lock_content.isdigit():
                    lock_pid = int(lock_content)

                    # Check if the process is still running
                    if not psutil.pid_exists(lock_pid):
                        # Stale lock file, remove it
                        safe_delete_file(self.lock_file)

        except (ValueError, OSError):
            # Invalid lock file, remove it
            safe_delete_file(self.lock_file)

    def acquire_lock(self) -> bool:
        """
        Acquire exclusive lock to prevent multiple instances

        Returns:
            bool: True if lock acquired successfully, False otherwise
        """
        try:
            return self._attempt_lock_acquisition()
        except Exception as e:
            handle_error(e, "Failed to acquire process lock")
            return False

    def _attempt_lock_acquisition(self) -> bool:
        """Attempt to acquire the process lock"""
        if self.lock_fd is not None:
            # Already have lock
            return True

        try:
            # Open lock file for writing
            self.lock_fd = os.open(str(self.lock_file), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)

            # Try to acquire exclusive lock (non-blocking)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Write our PID to the lock file
            current_pid = str(os.getpid()).encode()
            os.write(self.lock_fd, current_pid)
            os.fsync(self.lock_fd)

            return True

        except (IOError, OSError) as e:
            # Lock acquisition failed
            if self.lock_fd is not None:
                try:
                    os.close(self.lock_fd)
                except OSError:
                    pass
                self.lock_fd = None
            return False

    def release_lock(self) -> None:
        """Release the exclusive lock safely"""
        try:
            if self.lock_fd is not None:
                # Release file lock
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)
                self.lock_fd = None

            # Remove lock file
            safe_delete_file(self.lock_file)

        except (IOError, OSError) as e:
            handle_error(e, "Error releasing process lock")

    def save_pid(self, pid: int) -> bool:
        """
        Save process ID to file with validation

        Args:
            pid: Process ID to save

        Returns:
            bool: True if saved successfully, False otherwise
        """
        if not isinstance(pid, int) or pid <= 0:
            handle_error(ValueError(f"Invalid PID: {pid}"), "Cannot save invalid PID")
            return False

        try:
            # Verify process exists before saving
            if not psutil.pid_exists(pid):
                handle_error(ValueError(f"Process {pid} does not exist"), "Cannot save non-existent PID")
                return False

            self.pid_file.write_text(str(pid), encoding='utf-8')
            return True

        except (OSError, IOError) as e:
            handle_error(e, f"Failed to save PID {pid}")
            return False

    def get_pid(self) -> Optional[int]:
        """
        Get saved process ID with validation

        Returns:
            Optional[int]: Process ID if valid, None otherwise
        """
        try:
            if not self.pid_file.exists():
                return None

            pid_text = self.pid_file.read_text(encoding='utf-8').strip()

            if not pid_text.isdigit():
                # Invalid PID format, clean up
                safe_delete_file(self.pid_file)
                return None

            pid = int(pid_text)

            # Validate that PID is reasonable
            if pid <= 0 or pid > 4194304:  # Max PID on most systems
                safe_delete_file(self.pid_file)
                return None

            return pid

        except (ValueError, OSError, IOError) as e:
            handle_error(e, "Error reading PID file")
            safe_delete_file(self.pid_file)
            return None

    def clear_pid(self) -> bool:
        """
        Clear saved process ID

        Returns:
            bool: True if cleared successfully, False otherwise
        """
        try:
            return safe_delete_file(self.pid_file)
        except Exception as e:
            handle_error(e, "Failed to clear PID file")
            return False

    def is_process_running(self, pid: Optional[int] = None) -> bool:
        """
        Check if process is actually running with comprehensive validation

        Args:
            pid: Process ID to check, uses saved PID if None

        Returns:
            bool: True if process is running, False otherwise
        """
        if pid is None:
            pid = self.get_pid()

        if not pid:
            return False

        try:
            # Check if PID exists in system
            if not psutil.pid_exists(pid):
                return False

            # Get process object and check if it's actually running
            process = psutil.Process(pid)
            return process.is_running()

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception as e:
            handle_error(e, f"Error checking process {pid}")
            return False

    def get_process(self, pid: Optional[int] = None) -> Optional[psutil.Process]:
        """
        Get psutil Process object with error handling

        Args:
            pid: Process ID to get, uses saved PID if None

        Returns:
            Optional[psutil.Process]: Process object if accessible, None otherwise
        """
        if pid is None:
            pid = self.get_pid()

        if not pid:
            return None

        try:
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)
                # Verify process is accessible
                _ = process.status()  # This will raise exception if not accessible
                return process
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except Exception as e:
            handle_error(e, f"Error accessing process {pid}")

        return None

    def find_java_processes(self, jar_name: str, server_dir: Optional[Path] = None) -> List[int]:
        """
        Find Java processes running the specified JAR with enhanced filtering

        Args:
            jar_name: Name of JAR file to search for
            server_dir: Optional server directory to filter by working directory

        Returns:
            List[int]: List of matching process PIDs
        """
        if not jar_name:
            return []

        matching_processes = []
        search_start = time.time()

        try:
            for process in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
                # Timeout protection for long searches
                if time.time() - search_start > PROCESS_SEARCH_TIMEOUT:
                    break

                try:
                    if not self._is_java_process(process):
                        continue

                    if self._matches_jar_criteria(process, jar_name, server_dir):
                        matching_processes.append(process.info['pid'])

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Process disappeared or inaccessible, skip
                    continue
                except Exception:
                    # Other errors, skip this process
                    continue

        except Exception as e:
            handle_error(e, "Error searching for Java processes")

        return matching_processes

    def _is_java_process(self, process: psutil.Process) -> bool:
        """Check if process is a Java process"""
        process_name = process.info.get('name', '').lower()
        return process_name == JAVA_PROCESS_NAME or process_name.startswith('java')

    def _matches_jar_criteria(self, process: psutil.Process, jar_name: str, server_dir: Optional[Path]) -> bool:
        """Check if Java process matches our criteria"""
        cmdline = process.info.get('cmdline', [])
        if not cmdline:
            return False

        # Convert cmdline to string for searching
        cmdline_str = ' '.join(cmdline)

        # Check for JAR file in command line
        jar_in_cmdline = (jar_name in cmdline_str and '-jar' in cmdline_str)

        if not jar_in_cmdline:
            return False

        # If server directory specified, check working directory
        if server_dir:
            process_cwd = process.info.get('cwd', '')
            if process_cwd and str(server_dir) not in process_cwd:
                return False

        return True

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """
        Get comprehensive information about a process

        Args:
            pid: Process ID to get information for

        Returns:
            Dict[str, Any]: Process information dictionary
        """
        try:
            process = psutil.Process(pid)

            # Gather comprehensive process information
            info = {
                "pid": pid,
                "name": process.name(),
                "status": process.status(),
                "create_time": process.create_time(),
                "cpu_percent": process.cpu_percent(),
                "num_threads": process.num_threads(),
                "accessible": True
            }

            # Add optional information that might not be accessible
            self._add_optional_process_info(info, process)

            return info

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            return {
                "pid": pid,
                "accessible": False,
                "error": str(e),
                "error_type": type(e).__name__
            }
        except Exception as e:
            handle_error(e, f"Error getting process info for PID {pid}")
            return {
                "pid": pid,
                "accessible": False,
                "error": str(e),
                "error_type": "UnknownError"
            }

    def _add_optional_process_info(self, info: Dict[str, Any], process: psutil.Process) -> None:
        """Add optional process information that might not be accessible"""
        optional_fields = {
            "cmdline": lambda: process.cmdline(),
            "cwd": lambda: process.cwd(),
            "memory_info": lambda: process.memory_info(),
            "open_files": lambda: len(process.open_files()),
            "connections": lambda: len(process.connections()),
            "username": lambda: process.username()
        }

        for field_name, getter in optional_fields.items():
            try:
                info[field_name] = getter()
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                info[field_name] = "Access Denied"
            except Exception:
                info[field_name] = "Unknown"

    def kill_process(self, pid: int, timeout: int = DEFAULT_KILL_TIMEOUT, force: bool = False) -> bool:
        """
        Kill process gracefully with fallback to force kill

        Args:
            pid: Process ID to kill
            timeout: Timeout for graceful termination
            force: If True, skip graceful termination and force kill immediately

        Returns:
            bool: True if process was killed successfully, False otherwise
        """
        try:
            process = psutil.Process(pid)

            if force:
                return self._force_kill_process(process)
            else:
                return self._graceful_kill_process(process, timeout)

        except psutil.NoSuchProcess:
            # Process already gone
            return True
        except (psutil.AccessDenied, psutil.ZombieProcess) as e:
            handle_error(e, f"Cannot kill process {pid}")
            return False
        except Exception as e:
            handle_error(e, f"Error killing process {pid}")
            return False

    def _graceful_kill_process(self, process: psutil.Process, timeout: int) -> bool:
        """Attempt graceful process termination"""
        try:
            # Send TERM signal for graceful shutdown
            process.terminate()

            # Wait for process to terminate gracefully
            try:
                process.wait(timeout=timeout)
                return True
            except psutil.TimeoutExpired:
                # Graceful termination failed, force kill
                return self._force_kill_process(process)

        except psutil.NoSuchProcess:
            return True
        except Exception:
            # Graceful termination failed, try force kill
            return self._force_kill_process(process)

    def _force_kill_process(self, process: psutil.Process) -> bool:
        """Force kill process immediately"""
        try:
            process.kill()

            # Wait briefly to confirm termination
            try:
                process.wait(timeout=5)
                return True
            except psutil.TimeoutExpired:
                # Process is really stubborn
                return False

        except psutil.NoSuchProcess:
            return True
        except Exception as e:
            handle_error(e, f"Force kill failed for process {process.pid}")
            return False

    def kill_process_tree(self, pid: int, timeout: int = DEFAULT_KILL_TIMEOUT) -> Dict[str, Any]:
        """
        Kill process and all its children

        Args:
            pid: Root process ID
            timeout: Timeout for graceful termination

        Returns:
            Dict[str, Any]: Results of the operation
        """
        results = {
            "killed_processes": [],
            "failed_processes": [],
            "total_killed": 0,
            "success": False
        }

        try:
            parent = psutil.Process(pid)

            # Get all child processes
            children = parent.children(recursive=True)
            processes_to_kill = children + [parent]

            # Terminate all processes
            for process in processes_to_kill:
                try:
                    process.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Wait for graceful termination
            gone, alive = psutil.wait_procs(processes_to_kill, timeout=timeout)

            # Force kill any remaining processes
            for process in alive:
                try:
                    process.kill()
                    results["killed_processes"].append(process.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    results["failed_processes"].append({
                        "pid": process.pid,
                        "error": str(e)
                    })

            # Final wait for force-killed processes
            if alive:
                gone2, still_alive = psutil.wait_procs(alive, timeout=5)
                gone.extend(gone2)

                for process in still_alive:
                    results["failed_processes"].append({
                        "pid": process.pid,
                        "error": "Process survived force kill"
                    })

            results["killed_processes"].extend([p.pid for p in gone])
            results["total_killed"] = len(gone)
            results["success"] = len(results["failed_processes"]) == 0

        except psutil.NoSuchProcess:
            results["success"] = True  # Process already gone
        except Exception as e:
            handle_error(e, f"Error killing process tree for PID {pid}")
            results["failed_processes"].append({
                "pid": pid,
                "error": str(e)
            })

        return results

    def send_signal(self, pid: int, sig: int) -> bool:
        """
        Send signal to process

        Args:
            pid: Process ID
            sig: Signal number

        Returns:
            bool: True if signal sent successfully, False otherwise
        """
        try:
            process = psutil.Process(pid)

            if os.name == 'nt':  # Windows
                # Windows has limited signal support
                if sig in (signal.SIGTERM, signal.SIGKILL):
                    if sig == signal.SIGTERM:
                        process.terminate()
                    else:
                        process.kill()
                    return True
                else:
                    return False
            else:  # Unix-like systems
                os.kill(pid, sig)
                return True

        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
            handle_error(e, f"Failed to send signal {sig} to process {pid}")
            return False
        except Exception as e:
            handle_error(e, f"Error sending signal {sig} to process {pid}")
            return False

    def get_system_process_stats(self) -> Dict[str, Any]:
        """
        Get system-wide process statistics

        Returns:
            Dict[str, Any]: System process statistics
        """
        try:
            stats = {
                "total_processes": 0,
                "running_processes": 0,
                "sleeping_processes": 0,
                "zombie_processes": 0,
                "java_processes": 0,
                "total_memory_mb": 0,
                "total_cpu_percent": 0
            }

            for process in psutil.process_iter(['pid', 'name', 'status']):
                try:
                    stats["total_processes"] += 1

                    status = process.info.get('status', '')
                    if status == psutil.STATUS_RUNNING:
                        stats["running_processes"] += 1
                    elif status == psutil.STATUS_SLEEPING:
                        stats["sleeping_processes"] += 1
                    elif status == psutil.STATUS_ZOMBIE:
                        stats["zombie_processes"] += 1

                    # Count Java processes
                    name = process.info.get('name', '').lower()
                    if name == JAVA_PROCESS_NAME or name.startswith('java'):
                        stats["java_processes"] += 1

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return stats

        except Exception as e:
            handle_error(e, "Error getting system process stats")
            return {}

    def cleanup(self) -> None:
        """Clean up all process management resources"""
        try:
            self.release_lock()
            self.clear_pid()
        except Exception as e:
            handle_error(e, "Error during process manager cleanup")

    def __enter__(self):
        """Context manager entry - acquire lock"""
        if not self.acquire_lock():
            raise ProcessLockError("Could not acquire process lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources"""
        self.cleanup()

    def __del__(self):
        """Destructor - ensure cleanup"""
        try:
            self.cleanup()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass


class ProcessMonitor:
    """Process monitoring utilities for health checking and resource tracking"""

    def __init__(self, process_manager: ProcessManager):
        self.process_manager = process_manager

    def monitor_process_health(self, pid: Optional[int] = None) -> Dict[str, Any]:
        """
        Monitor process health metrics

        Args:
            pid: Process ID to monitor, uses saved PID if None

        Returns:
            Dict[str, Any]: Health metrics and status
        """
        if pid is None:
            pid = self.process_manager.get_pid()

        if not pid:
            return {
                "healthy": False,
                "reason": "No process ID available",
                "metrics": {}
            }

        try:
            process = psutil.Process(pid)

            # Gather health metrics
            metrics = {
                "memory_percent": process.memory_percent(),
                "cpu_percent": process.cpu_percent(),
                "num_threads": process.num_threads(),
                "num_fds": process.num_fds() if hasattr(process, 'num_fds') else 0,
                "status": process.status(),
                "create_time": process.create_time(),
                "uptime_seconds": time.time() - process.create_time()
            }

            # Determine health status
            health_status = self._evaluate_process_health(metrics)

            return {
                "healthy": health_status["healthy"],
                "reason": health_status.get("reason", ""),
                "warnings": health_status.get("warnings", []),
                "metrics": metrics
            }

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return {
                "healthy": False,
                "reason": f"Process not accessible: {e}",
                "metrics": {}
            }
        except Exception as e:
            handle_error(e, f"Error monitoring process health for PID {pid}")
            return {
                "healthy": False,
                "reason": f"Monitoring error: {e}",
                "metrics": {}
            }

    def _evaluate_process_health(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate process health based on metrics"""
        health = {"healthy": True, "warnings": []}

        # Check memory usage
        memory_percent = metrics.get("memory_percent", 0)
        if memory_percent > 95:
            health["healthy"] = False
            health["reason"] = f"Critical memory usage: {memory_percent:.1f}%"
        elif memory_percent > 85:
            health["warnings"].append(f"High memory usage: {memory_percent:.1f}%")

        # Check process status
        status = metrics.get("status", "")
        if status == psutil.STATUS_ZOMBIE:
            health["healthy"] = False
            health["reason"] = "Process is zombie"
        elif status in (psutil.STATUS_STOPPED, psutil.STATUS_TRACING_STOP):
            health["healthy"] = False
            health["reason"] = f"Process is stopped ({status})"

        # Check thread count (high thread count might indicate issues)
        thread_count = metrics.get("num_threads", 0)
        if thread_count > 500:
            health["warnings"].append(f"Very high thread count: {thread_count}")
        elif thread_count > 200:
            health["warnings"].append(f"High thread count: {thread_count}")

        return health
