"""
Process management utilities for Craft Minecraft Server Manager
"""

import fcntl
import os
from pathlib import Path
from typing import Optional

import psutil


class ProcessManager:
    """Manages server processes with better tracking and control"""

    def __init__(self, name: str = "craft"):
        self.name = name
        self.pid_file = Path(f"{name}.pid")
        self.lock_file = Path(f"{name}.lock")
        self.lock_fd = None

    def acquire_lock(self) -> bool:
        """Acquire exclusive lock to prevent multiple instances"""
        try:
            self.lock_fd = open(self.lock_file, 'w')
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lock_fd.write(str(os.getpid()))
            self.lock_fd.flush()
            return True
        except (IOError, OSError):
            return False

    def release_lock(self):
        """Release the exclusive lock"""
        try:
            if self.lock_fd:
                fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
                self.lock_fd = None
            if self.lock_file.exists():
                self.lock_file.unlink()
        except (IOError, OSError):
            pass

    def save_pid(self, pid: int):
        """Save process ID to file"""
        self.pid_file.write_text(str(pid))

    def get_pid(self) -> Optional[int]:
        """Get saved process ID"""
        try:
            if self.pid_file.exists():
                return int(self.pid_file.read_text().strip())
        except (ValueError, IOError):
            pass
        return None

    def clear_pid(self):
        """Clear saved process ID"""
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except OSError:
                pass

    def is_process_running(self, pid: int = None) -> bool:
        """Check if process is actually running"""
        if pid is None:
            pid = self.get_pid()

        if not pid:
            return False

        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def get_process(self, pid: int = None) -> Optional[psutil.Process]:
        """Get psutil Process object"""
        if pid is None:
            pid = self.get_pid()

        if not pid:
            return None

        try:
            if psutil.pid_exists(pid):
                return psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        return None

    @staticmethod
    def find_java_processes(jar_name: str) -> list:
        """Find Java processes running the specified JAR"""
        processes = []

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if (proc.info['name'] == 'java' and
                        proc.info['cmdline'] and
                        any(jar_name in str(cmd) for cmd in proc.info['cmdline'])):
                    processes.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return processes

    @staticmethod
    def kill_process(pid: int, timeout: int = 10) -> bool:
        """Kill process gracefully with fallback to force kill"""
        try:
            process = psutil.Process(pid)

            # Try graceful termination first
            process.terminate()

            try:
                process.wait(timeout=timeout)
                return True
            except psutil.TimeoutExpired:
                # Force kill if graceful termination fails
                process.kill()
                try:
                    process.wait(timeout=5)
                    return True
                except psutil.TimeoutExpired:
                    return False

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return True  # Process already gone
        except Exception:
            return False

    def cleanup(self):
        """Clean up all process management files"""
        self.release_lock()
        self.clear_pid()

    def __enter__(self):
        """Context manager entry"""
        if not self.acquire_lock():
            raise RuntimeError("Could not acquire process lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()
