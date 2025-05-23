"""
Configuration management for Craft Minecraft Server Manager
"""

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt

console = Console()

class ConfigManager:
    """Enhanced configuration management with validation"""

    DEFAULTS = {
        "server_dir": "server",
        "jar_name": "neoforge-server.jar",
        "memory_min": "2G",
        "memory_max": "4G",
        "java_args": "-XX:+UseG1GC -XX:+UnlockExperimentalVMOptions -XX:MaxGCPauseMillis=100 -XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M",
        "backup_dir": "backups",
        "max_backups": 10,
        "auto_backup": True,
        "backup_interval": 3600,  # 1 hour
        "backup_on_stop": True,
        "watchdog_enabled": True,
        "watchdog_interval": 30,  # 30 seconds
        "restart_on_crash": True,
        "max_restarts": 5,
        "restart_cooldown": 300,  # 5 minutes
        "log_level": "INFO",
        "console_history": 1000
    }

    def __init__(self, config_path: Path = Path("config.json")):
        self.config_path = config_path
        self.data = {}
        self.load()

    def load(self):
        """Load configuration from file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    self.data = json.load(f)
                self._validate_config()
            except (json.JSONDecodeError, IOError) as e:
                console.print(f"[red]Error loading config: {e}[/red]")
                self._create_default_config()
        else:
            self._create_default_config()

    def _create_default_config(self):
        """Create default configuration"""
        self.data = self.DEFAULTS.copy()
        self.save()
        console.print("[yellow]Created default configuration[/yellow]")

    def _validate_config(self):
        """Validate and fix configuration values"""
        for key, default_value in self.DEFAULTS.items():
            if key not in self.data:
                self.data[key] = default_value
                continue

            # Type validation
            if type(self.data[key]) != type(default_value):
                try:
                    if isinstance(default_value, bool):
                        self.data[key] = str(self.data[key]).lower() in ('true', 'yes', '1', 'on')
                    elif isinstance(default_value, int):
                        self.data[key] = int(self.data[key])
                    elif isinstance(default_value, str):
                        self.data[key] = str(self.data[key])
                except (ValueError, TypeError):
                    console.print(f"[yellow]Invalid value for {key}, using default[/yellow]")
                    self.data[key] = default_value

    def save(self):
        """Save configuration to file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.data, f, indent=4, sort_keys=True)

    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.data.get(key, default or self.DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.data[key] = value
        self.save()

    def interactive_setup(self):
        """Interactive configuration setup"""
        console.print(Panel.fit("🎯 Craft NeoForge Server Configuration", style="bold cyan"))
        console.print("[dim]Press Enter to keep current values[/dim]\n")

        # Server settings
        console.print("[bold]Server Settings[/bold]")
        self.set("server_dir", Prompt.ask("Server directory", default=self.get("server_dir")))

        current_jar = self.get("jar_name")
        if "server.jar" in current_jar:
            # Suggest NeoForge naming
            console.print("[yellow]💡 Consider renaming to neoforge-server.jar for clarity[/yellow]")

        self.set("jar_name", Prompt.ask("JAR filename", default=self.get("jar_name")))
        self.set("memory_min", Prompt.ask("Minimum memory (e.g., 2G)", default=self.get("memory_min")))
        self.set("memory_max", Prompt.ask("Maximum memory (e.g., 4G)", default=self.get("memory_max")))

        # Advanced Java settings
        console.print("\n[bold]Performance Settings[/bold]")
        console.print("[dim]NeoForge works best with G1GC and specific optimizations[/dim]")
        if Confirm.ask("Configure Java arguments (recommended for NeoForge)?", default=True):
            current_args = self.get("java_args")
            console.print(f"[dim]Current: {current_args}[/dim]")

            # Suggest NeoForge-optimized settings
            suggested_args = "-XX:+UseG1GC -XX:+UnlockExperimentalVMOptions -XX:MaxGCPauseMillis=100 -XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M"

            use_suggested = Confirm.ask("Use NeoForge-optimized Java arguments?", default=True)
            if use_suggested:
                self.set("java_args", suggested_args)
                console.print("[green]✅ Applied NeoForge-optimized settings[/green]")
            else:
                new_args = Prompt.ask("Custom Java arguments", default=current_args)
                self.set("java_args", new_args)

        # Backup settings
        console.print("\n[bold]Backup Settings[/bold]")
        self.set("auto_backup", Confirm.ask("Enable automatic backups", default=self.get("auto_backup")))
        if self.get("auto_backup"):
            interval_hours = self.get("backup_interval") // 3600
            new_interval = IntPrompt.ask("Backup interval (hours)", default=interval_hours)
            self.set("backup_interval", new_interval * 3600)

        self.set("max_backups", IntPrompt.ask("Maximum backups to keep", default=self.get("max_backups")))
        self.set("backup_on_stop", Confirm.ask("Backup on server stop", default=self.get("backup_on_stop")))

        # Monitoring settings
        console.print("\n[bold]Monitoring Settings[/bold]")
        self.set("watchdog_enabled", Confirm.ask("Enable watchdog monitoring", default=self.get("watchdog_enabled")))

        if self.get("watchdog_enabled"):
            self.set("restart_on_crash", Confirm.ask("Auto-restart on crash", default=self.get("restart_on_crash")))

            if self.get("restart_on_crash"):
                self.set("max_restarts", IntPrompt.ask("Max restart attempts", default=self.get("max_restarts")))
                cooldown_mins = self.get("restart_cooldown") // 60
                new_cooldown = IntPrompt.ask("Restart cooldown (minutes)", default=cooldown_mins)
                self.set("restart_cooldown", new_cooldown * 60)

        console.print("\n[bold green]✅ Configuration saved![/bold green]")
        console.print(f"[dim]Config file: {self.config_path.absolute()}[/dim]")
        console.print("\n[cyan]💡 Note: NeoForge handles server ports, EULA, and server.properties automatically[/cyan]")

    def validate_server_setup(self) -> bool:
        """Validate that server is properly configured"""
        issues = []

        server_dir = Path(self.get("server_dir"))
        jar_path = server_dir / self.get("jar_name")

        if not server_dir.exists():
            issues.append(f"Server directory doesn't exist: {server_dir}")

        if not jar_path.exists():
            issues.append(f"NeoForge server JAR not found: {jar_path}")
            issues.append("Download NeoForge from: https://neoforged.net/")

        backup_dir = Path(self.get("backup_dir"))
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            issues.append(f"Cannot create backup directory: {backup_dir}")

        # Check memory settings
        memory_min = self.get("memory_min")
        memory_max = self.get("memory_max")

        from utils import validate_memory_setting, parse_memory_to_mb

        if not validate_memory_setting(memory_min):
            issues.append(f"Invalid minimum memory setting: {memory_min}")

        if not validate_memory_setting(memory_max):
            issues.append(f"Invalid maximum memory setting: {memory_max}")

        # Check that max >= min
        if validate_memory_setting(memory_min) and validate_memory_setting(memory_max):
            min_mb = parse_memory_to_mb(memory_min)
            max_mb = parse_memory_to_mb(memory_max)
            if min_mb and max_mb and min_mb > max_mb:
                issues.append("Minimum memory cannot be greater than maximum memory")

        if issues:
            console.print("[red]Configuration issues found:[/red]")
            for issue in issues:
                console.print(f"  ❌ {issue}")
            return False

        return True

    def get_summary(self) -> dict:
        """Get configuration summary for display"""
        return {
            "server_jar": f"{self.get('server_dir')}/{self.get('jar_name')}",
            "memory": f"{self.get('memory_min')} - {self.get('memory_max')}",
            "auto_backup": "Enabled" if self.get("auto_backup") else "Disabled",
            "backup_interval": f"{self.get('backup_interval') // 3600}h" if self.get("auto_backup") else "N/A",
            "watchdog": "Enabled" if self.get("watchdog_enabled") else "Disabled",
            "auto_restart": "Enabled" if self.get("restart_on_crash") else "Disabled",
            "server_type": "NeoForge"
        }