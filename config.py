"""
Configuration management for Craft Minecraft Server Manager

Handles loading, validation, and interactive setup of server configuration
with platform-specific directory handling and comprehensive validation.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt

from utils import handle_error, validate_memory_setting, parse_memory_to_mb

console = Console()

# Configuration constants
MIN_MEMORY_MB = 512
MAX_MEMORY_MB = 65536
MIN_BACKUP_INTERVAL = 300  # 5 minutes
MAX_BACKUP_INTERVAL = 86400  # 24 hours
DEFAULT_JAVA_ARGS = (
    "-XX:+UseG1GC -XX:+UnlockExperimentalVMOptions -XX:MaxGCPauseMillis=100 "
    "-XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 "
    "-XX:G1HeapRegionSize=32M"
)


class ConfigurationError(Exception):
    """Custom exception for configuration-related errors"""
    pass


def get_config_dir() -> Path:
    """Get the appropriate configuration directory for the platform"""
    if os.name == 'nt':  # Windows
        config_dir = Path(os.environ.get('APPDATA', Path.home())) / 'craft'
    else:  # Linux/macOS
        # Use XDG_CONFIG_HOME if set, otherwise ~/.config
        xdg_config = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config:
            config_dir = Path(xdg_config) / 'craft'
        else:
            config_dir = Path.home() / '.config' / 'craft'

    return config_dir


class ConfigManager:
    """Enhanced configuration management with comprehensive validation and defaults"""

    # Default configuration values
    DEFAULTS = {
        "server_dir": "server",
        "jar_name": "neoforge-server.jar",
        "memory_min": "2G",
        "memory_max": "4G",
        "java_args": DEFAULT_JAVA_ARGS,
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
        "console_history": 1000,
        "force_stop": True,
        "stop_timeout": 10
    }

    # Configuration validation rules
    VALIDATION_RULES = {
        "memory_min": lambda x: validate_memory_setting(x),
        "memory_max": lambda x: validate_memory_setting(x),
        "max_backups": lambda x: isinstance(x, int) and 1 <= x <= 100,
        "backup_interval": lambda x: isinstance(x, int) and MIN_BACKUP_INTERVAL <= x <= MAX_BACKUP_INTERVAL,
        "watchdog_interval": lambda x: isinstance(x, int) and 5 <= x <= 300,
        "max_restarts": lambda x: isinstance(x, int) and 1 <= x <= 20,
        "restart_cooldown": lambda x: isinstance(x, int) and 60 <= x <= 3600,
        "console_history": lambda x: isinstance(x, int) and 100 <= x <= 10000,
        "stop_timeout": lambda x: isinstance(x, int) and 5 <= x <= 120
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager with platform-appropriate defaults"""
        self.config_path = self._determine_config_path(config_path)
        self.data: Dict[str, Any] = {}
        self._shown_location = False

        self._ensure_config_directory()
        self.load()
        self._show_config_location()

    def _determine_config_path(self, config_path: Optional[Path]) -> Path:
        """Determine the configuration file path"""
        if config_path is None:
            config_dir = get_config_dir()
            return config_dir / "config.json"
        return Path(config_path)

    def _ensure_config_directory(self) -> None:
        """Ensure configuration directory exists"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ConfigurationError(f"Failed to create config directory: {e}") from e

    def _show_config_location(self) -> None:
        """Show configuration location on first run"""
        if not self._shown_location:
            console.print(f"[dim]Config: {self.config_path}[/dim]")
            self._shown_location = True

    def load(self) -> None:
        """Load configuration from file with comprehensive error handling"""
        if self.config_path.exists():
            try:
                self._load_existing_config()
            except (json.JSONDecodeError, IOError) as e:
                handle_error(e, "Error loading config")
                self._create_default_config()
        else:
            self._create_default_config()

    def _load_existing_config(self) -> None:
        """Load existing configuration file"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        self._validate_and_migrate_config()

    def _create_default_config(self) -> None:
        """Create default configuration"""
        self.data = self.DEFAULTS.copy()
        self.save()
        console.print("[yellow]Created default configuration[/yellow]")

    def _validate_and_migrate_config(self) -> None:
        """Validate and migrate configuration to current version"""
        has_changes = False

        # Add missing keys with defaults
        for key, default_value in self.DEFAULTS.items():
            if key not in self.data:
                self.data[key] = default_value
                has_changes = True

        # Validate and fix existing values
        for key, value in self.data.items():
            if key in self.VALIDATION_RULES:
                if not self._validate_config_value(key, value):
                    console.print(f"[yellow]Invalid value for {key}, using default[/yellow]")
                    self.data[key] = self.DEFAULTS.get(key)
                    has_changes = True

        # Type validation and coercion
        has_changes |= self._perform_type_validation()

        # Cross-field validation
        has_changes |= self._perform_cross_field_validation()

        if has_changes:
            self.save()

    def _validate_config_value(self, key: str, value: Any) -> bool:
        """Validate a single configuration value"""
        validator = self.VALIDATION_RULES.get(key)
        if validator:
            try:
                return validator(value)
            except Exception:
                return False
        return True

    def _perform_type_validation(self) -> bool:
        """Perform type validation and coercion"""
        has_changes = False

        for key, default_value in self.DEFAULTS.items():
            if key not in self.data:
                continue

            current_value = self.data[key]
            expected_type = type(default_value)

            if type(current_value) != expected_type:
                try:
                    if expected_type == bool:
                        self.data[key] = self._coerce_to_bool(current_value)
                    elif expected_type == int:
                        self.data[key] = int(current_value)
                    elif expected_type == str:
                        self.data[key] = str(current_value)
                    has_changes = True
                except (ValueError, TypeError):
                    console.print(f"[yellow]Type error for {key}, using default[/yellow]")
                    self.data[key] = default_value
                    has_changes = True

        return has_changes

    def _coerce_to_bool(self, value: Any) -> bool:
        """Coerce value to boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value)

    def _perform_cross_field_validation(self) -> bool:
        """Perform validation across multiple fields"""
        has_changes = False

        # Validate memory settings
        if self._fix_memory_settings():
            has_changes = True

        # Validate backup settings
        if self._fix_backup_settings():
            has_changes = True

        return has_changes

    def _fix_memory_settings(self) -> bool:
        """Fix memory settings if invalid"""
        memory_min = self.data.get("memory_min")
        memory_max = self.data.get("memory_max")

        if not (validate_memory_setting(memory_min) and validate_memory_setting(memory_max)):
            return False

        min_mb = parse_memory_to_mb(memory_min)
        max_mb = parse_memory_to_mb(memory_max)

        if min_mb and max_mb and min_mb > max_mb:
            console.print("[yellow]Minimum memory > maximum memory, fixing...[/yellow]")
            self.data["memory_min"] = self.data["memory_max"]
            return True

        return False

    def _fix_backup_settings(self) -> bool:
        """Fix backup settings if invalid"""
        has_changes = False

        # Ensure backup interval is reasonable
        interval = self.data.get("backup_interval", 3600)
        if not isinstance(interval, int) or interval < MIN_BACKUP_INTERVAL:
            self.data["backup_interval"] = 3600
            has_changes = True

        # Ensure max backups is reasonable
        max_backups = self.data.get("max_backups", 10)
        if not isinstance(max_backups, int) or max_backups < 1:
            self.data["max_backups"] = 10
            has_changes = True

        return has_changes

    def save(self) -> None:
        """Save configuration to file with error handling"""
        try:
            self._ensure_config_directory()
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, sort_keys=True)
        except OSError as e:
            raise ConfigurationError(f"Failed to save configuration: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with fallback to defaults"""
        return self.data.get(key, default or self.DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Set configuration value with validation"""
        if key in self.VALIDATION_RULES:
            if not self._validate_config_value(key, value):
                raise ConfigurationError(f"Invalid value for {key}: {value}")

        self.data[key] = value
        self.save()

    def interactive_setup(self) -> None:
        """Interactive configuration setup with comprehensive guidance"""
        try:
            self._show_setup_header()
            self._setup_server_settings()
            self._setup_performance_settings()
            self._setup_backup_settings()
            self._setup_monitoring_settings()
            self._setup_shutdown_settings()
            self._show_setup_completion()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Setup cancelled[/yellow]")
        except Exception as e:
            handle_error(e, "Setup failed")

    def _show_setup_header(self) -> None:
        """Show setup header"""
        console.print(Panel.fit("🎯 Craft NeoForge Server Configuration", style="bold cyan"))
        console.print("[dim]Press Enter to keep current values[/dim]\n")

    def _setup_server_settings(self) -> None:
        """Setup basic server settings"""
        console.print("[bold]Server Settings[/bold]")

        self.set("server_dir", Prompt.ask("Server directory", default=self.get("server_dir")))

        current_jar = self.get("jar_name")
        self._suggest_jar_naming(current_jar)

        self.set("jar_name", Prompt.ask("JAR filename", default=current_jar))
        self.set("memory_min", self._prompt_memory_setting("minimum", self.get("memory_min")))
        self.set("memory_max", self._prompt_memory_setting("maximum", self.get("memory_max")))

    def _suggest_jar_naming(self, current_jar: str) -> None:
        """Suggest better JAR naming if needed"""
        if "server.jar" in current_jar:
            console.print("[yellow]💡 Consider renaming to neoforge-server.jar for clarity[/yellow]")

    def _prompt_memory_setting(self, setting_type: str, default: str) -> str:
        """Prompt for memory setting with validation"""
        while True:
            value = Prompt.ask(f"{setting_type.capitalize()} memory (e.g., 2G)", default=default)
            if validate_memory_setting(value):
                return value
            console.print("[red]❌ Invalid memory format. Use format like '2G' or '1024M'[/red]")

    def _setup_performance_settings(self) -> None:
        """Setup performance-related settings"""
        console.print("\n[bold]Performance Settings[/bold]")
        console.print("[dim]NeoForge works best with G1GC and specific optimizations[/dim]")

        if Confirm.ask("Configure Java arguments (recommended for NeoForge)?", default=True):
            self._configure_java_arguments()

    def _configure_java_arguments(self) -> None:
        """Configure Java arguments with recommendations"""
        current_args = self.get("java_args")
        console.print(f"[dim]Current: {current_args}[/dim]")

        if Confirm.ask("Use NeoForge-optimized Java arguments?", default=True):
            self.set("java_args", DEFAULT_JAVA_ARGS)
            console.print("[green]✅ Applied NeoForge-optimized settings[/green]")
        else:
            new_args = Prompt.ask("Custom Java arguments", default=current_args)
            self.set("java_args", new_args)

    def _setup_backup_settings(self) -> None:
        """Setup backup-related settings"""
        console.print("\n[bold]Backup Settings[/bold]")

        self.set("auto_backup", Confirm.ask("Enable automatic backups", default=self.get("auto_backup")))

        if self.get("auto_backup"):
            self._configure_backup_schedule()

        self.set("max_backups", self._prompt_backup_count())
        self.set("backup_on_stop", Confirm.ask("Backup on server stop", default=self.get("backup_on_stop")))

    def _configure_backup_schedule(self) -> None:
        """Configure backup scheduling"""
        interval_hours = self.get("backup_interval") // 3600

        while True:
            new_interval = IntPrompt.ask("Backup interval (hours)", default=interval_hours)
            if 1 <= new_interval <= 24:
                self.set("backup_interval", new_interval * 3600)
                break
            console.print("[red]❌ Backup interval must be between 1 and 24 hours[/red]")

    def _prompt_backup_count(self) -> int:
        """Prompt for maximum backup count with validation"""
        while True:
            count = IntPrompt.ask("Maximum backups to keep", default=self.get("max_backups"))
            if 1 <= count <= 100:
                return count
            console.print("[red]❌ Backup count must be between 1 and 100[/red]")

    def _setup_monitoring_settings(self) -> None:
        """Setup monitoring and watchdog settings"""
        console.print("\n[bold]Monitoring Settings[/bold]")

        self.set("watchdog_enabled",
                 Confirm.ask("Enable watchdog monitoring", default=self.get("watchdog_enabled")))

        if self.get("watchdog_enabled"):
            self._configure_watchdog_settings()

    def _configure_watchdog_settings(self) -> None:
        """Configure detailed watchdog settings"""
        self.set("restart_on_crash",
                 Confirm.ask("Auto-restart on crash", default=self.get("restart_on_crash")))

        if self.get("restart_on_crash"):
            self._configure_restart_settings()

    def _configure_restart_settings(self) -> None:
        """Configure restart-related settings"""
        self.set("max_restarts",
                 IntPrompt.ask("Max restart attempts", default=self.get("max_restarts")))

        cooldown_mins = self.get("restart_cooldown") // 60
        new_cooldown = IntPrompt.ask("Restart cooldown (minutes)", default=cooldown_mins)
        self.set("restart_cooldown", new_cooldown * 60)

    def _setup_shutdown_settings(self) -> None:
        """Setup server shutdown settings"""
        console.print("\n[bold]Shutdown Settings[/bold]")
        console.print("[dim]NeoForge servers can be slow to stop gracefully[/dim]")

        force_stop_default = self.get("force_stop", True)
        self.set("force_stop",
                 Confirm.ask("Use force stop by default (faster)", default=force_stop_default))

        if not self.get("force_stop"):
            timeout_default = self.get("stop_timeout", 10)
            self.set("stop_timeout",
                     IntPrompt.ask("Graceful stop timeout (seconds)", default=timeout_default))

    def _show_setup_completion(self) -> None:
        """Show setup completion message"""
        console.print("\n[bold green]✅ Configuration saved![/bold green]")
        console.print(f"[dim]Config file: {self.config_path.absolute()}[/dim]")
        console.print("\n[cyan]💡 Note: NeoForge handles server ports, EULA, and server.properties automatically[/cyan]")

    def validate_server_setup(self) -> bool:
        """Validate that server is properly configured for operation"""
        issues = []

        issues.extend(self._validate_server_files())
        issues.extend(self._validate_directories())
        issues.extend(self._validate_memory_configuration())
        issues.extend(self._validate_backup_configuration())

        if issues:
            self._show_validation_issues(issues)
            return False

        console.print("[green]✅ Server configuration is valid[/green]")
        return True

    def _validate_server_files(self) -> list:
        """Validate server files exist"""
        issues = []

        server_dir = Path(self.get("server_dir"))
        jar_path = server_dir / self.get("jar_name")

        if not server_dir.exists():
            issues.append(f"Server directory doesn't exist: {server_dir}")

        if not jar_path.exists():
            issues.append(f"NeoForge server JAR not found: {jar_path}")
            issues.append("Download NeoForge from: https://neoforged.net/")

        return issues

    def _validate_directories(self) -> list:
        """Validate required directories can be created"""
        issues = []

        backup_dir = Path(self.get("backup_dir"))
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            issues.append(f"Cannot create backup directory: {backup_dir}")

        return issues

    def _validate_memory_configuration(self) -> list:
        """Validate memory configuration"""
        issues = []

        memory_min = self.get("memory_min")
        memory_max = self.get("memory_max")

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

        return issues

    def _validate_backup_configuration(self) -> list:
        """Validate backup configuration"""
        issues = []

        if self.get("auto_backup"):
            interval = self.get("backup_interval")
            if interval < MIN_BACKUP_INTERVAL or interval > MAX_BACKUP_INTERVAL:
                issues.append(f"Backup interval out of range: {interval}s")

        max_backups = self.get("max_backups")
        if not isinstance(max_backups, int) or max_backups < 1:
            issues.append(f"Invalid max_backups value: {max_backups}")

        return issues

    def _show_validation_issues(self, issues: list) -> None:
        """Show validation issues to user"""
        console.print("[red]Configuration issues found:[/red]")
        for issue in issues:
            console.print(f"  ❌ {issue}")

    def get_summary(self) -> Dict[str, Union[str, bool]]:
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

    def export_config(self, filename: Optional[str] = None) -> str:
        """Export configuration to a file"""
        if not filename:
            from datetime import datetime
            filename = f"craft_config_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            export_data = {
                "config": self.data,
                "defaults": self.DEFAULTS,
                "export_time": datetime.now().isoformat(),
                "config_path": str(self.config_path),
                "craft_version": "1.0.0"
            }

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=str)

            console.print(f"[green]✅ Configuration exported to: {filename}[/green]")
            return filename
        except Exception as e:
            handle_error(e, "Failed to export configuration")
            return ""

    def import_config(self, filename: str) -> bool:
        """Import configuration from a file"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                import_data = json.load(f)

            if "config" in import_data:
                self.data = import_data["config"]
                self._validate_and_migrate_config()
                self.save()
                console.print(f"[green]✅ Configuration imported from: {filename}[/green]")
                return True
            else:
                console.print("[red]❌ Invalid configuration file format[/red]")
                return False

        except Exception as e:
            handle_error(e, "Failed to import configuration")
            return False

    def reset_to_defaults(self) -> None:
        """Reset configuration to default values"""
        if Confirm.ask("Reset all settings to defaults?", default=False):
            self.data = self.DEFAULTS.copy()
            self.save()
            console.print("[green]✅ Configuration reset to defaults[/green]")
