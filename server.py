import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

from config import Config
from utils import print_info, print_error, print_success, print_warning


class MinecraftServer:
    def __init__(self, config: Config):
        self.config = config
        self.server_dir = Path(self.config.get("server_dir"))
        self.jar_name = self.config.get("jar_name")
        self.memory = self.config.get("memory")
        self.screen_name = self.config.get("screen_name")
        self.server_port = self.config.get("server_port")

    def start(self) -> bool:
        """Start the Minecraft server"""
        if self.is_running():
            print_error("Server is already running.")
            return False

        jar_path = self.server_dir / self.jar_name
        if not jar_path.exists():
            print_error(f"Jar file not found: {jar_path}")
            return False

        # Ensure server directory exists
        self.server_dir.mkdir(parents=True, exist_ok=True)

        # Accept EULA if needed
        eula_path = self.server_dir / "eula.txt"
        if not eula_path.exists():
            print_info("Creating EULA acceptance...")
            eula_path.write_text("eula=true\n")

        print_info(f"Starting server with {self.memory} memory...")
        cmd = f"screen -dmS {self.screen_name} bash -c 'cd {self.server_dir} && java -Xmx{self.memory} -jar {self.jar_name} nogui'"

        try:
            subprocess.run(cmd, shell=True, check=True)
            # Wait a moment for server to start
            time.sleep(3)
            if self.is_running():
                print_success("Server started successfully!")
                return True
            else:
                print_error("Server failed to start properly.")
                return False
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to start server: {e}")
            return False

    def stop(self, timeout: int = 30) -> bool:
        """Stop the Minecraft server gracefully"""
        if not self.is_running():
            print_error("Server is not running.")
            return False

        print_info("Sending stop command to server...")
        self.send_command("stop")

        # Wait for graceful shutdown
        for i in range(timeout):
            if not self.is_running():
                print_success("Server stopped gracefully.")
                return True
            time.sleep(1)

        # Force kill if still running
        print_warning("Server didn't stop gracefully, forcing shutdown...")
        return self._force_stop()

    def _force_stop(self) -> bool:
        """Force stop the server if graceful shutdown fails"""
        try:
            # Kill the screen session
            subprocess.run(f"screen -S {self.screen_name} -X quit", shell=True)

            # Find and kill Java processes
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if (proc.info['name'] == 'java' and
                            any(self.jar_name in cmd for cmd in proc.info['cmdline'] or [])):
                        proc.terminate()
                        proc.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    pass

            time.sleep(2)
            if not self.is_running():
                print_success("Server force stopped.")
                return True
            else:
                print_error("Failed to stop server.")
                return False
        except Exception as e:
            print_error(f"Error during force stop: {e}")
            return False

    def restart(self) -> bool:
        """Restart the server"""
        print_info("Restarting server...")
        if self.is_running():
            if not self.stop():
                return False
        return self.start()

    def is_running(self) -> bool:
        """Check if server is actually running (more robust than just screen check)"""
        # Check if screen session exists
        result = subprocess.run(["screen", "-ls"], capture_output=True, text=True)
        if self.screen_name not in result.stdout:
            return False

        # Check if port is in use
        return self._is_port_in_use(self.server_port)

    def _is_port_in_use(self, port: int) -> bool:
        """Check if the Minecraft server port is in use"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result == 0
        except Exception:
            return False

    def get_status(self) -> dict:
        """Get detailed server status"""
        is_running = self.is_running()
        status = {
            'running': is_running,
            'screen_session': self._has_screen_session(),
            'port_open': self._is_port_in_use(self.server_port),
            'memory_usage': None,
            'cpu_usage': None,
            'uptime': None
        }

        if is_running:
            # Try to get process info
            try:
                for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent', 'create_time']):
                    try:
                        if (proc.info['name'] == 'java' and
                                any(self.jar_name in cmd for cmd in proc.info['cmdline'] or [])):
                            status['memory_usage'] = proc.info['memory_info'].rss / 1024 / 1024  # MB
                            status['cpu_usage'] = proc.cpu_percent()
                            status['uptime'] = time.time() - proc.info['create_time']
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception:
                pass

        return status

    def _has_screen_session(self) -> bool:
        """Check if screen session exists"""
        result = subprocess.run(["screen", "-ls"], capture_output=True, text=True)
        return self.screen_name in result.stdout

    def send_command(self, command: str) -> bool:
        """Send command to the server"""
        if not self.is_running():
            print_error("Server is not running.")
            return False

        try:
            cmd = f"screen -S {self.screen_name} -X stuff '{command}\\n'"
            subprocess.run(cmd, shell=True, check=True)
            print_success(f"Command sent: {command}")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to send command: {e}")
            return False

    def get_players(self) -> Optional[list]:
        """Get list of online players (requires log parsing or RCON)"""
        # This would require log file parsing or RCON implementation
        # For now, return None to indicate feature not implemented
        return None