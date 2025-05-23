import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.prompt import Prompt, Confirm

console = Console()

class Config:
    DEFAULTS = {
        "server_dir": "server",
        "jar_name": "server.jar",
        "memory": "2G",
        "screen_name": "minecraft",
        "backup_dir": "backups",
        "max_backups": 7,
        "watchdog_interval": 60,
        "auto_backup": True,
        "backup_interval": 3600,  # 1 hour in seconds
        "backup_on_stop": True,
        "log_level": "INFO",
        "server_port": 25565,
        "rcon_port": 25575,
        "rcon_password": "",
        "enable_rcon": False
    }

    def __init__(self, path: Path):
        self.path = path
        self.data = {}
        self.load()

    def load(self):
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
                # Validate and fix types
                self._validate_types()
            except (json.JSONDecodeError, Exception) as e:
                console.print(f"[red]Error loading config: {e}. Using defaults.[/red]")
                self.data = self.DEFAULTS.copy()
                self.save()
        else:
            self.data = self.DEFAULTS.copy()
            self.save()

    def _validate_types(self):
        """Ensure config values have correct types"""
        for key, default_value in self.DEFAULTS.items():
            if key in self.data:
                expected_type = type(default_value)
                current_value = self.data[key]

                if not isinstance(current_value, expected_type):
                    try:
                        if expected_type == bool:
                            self.data[key] = str(current_value).lower() in ('true', 'yes', '1', 'on')
                        elif expected_type == int:
                            self.data[key] = int(current_value)
                        elif expected_type == str:
                            self.data[key] = str(current_value)
                    except (ValueError, TypeError):
                        console.print(f"[yellow]Invalid value for {key}, using default[/yellow]")
                        self.data[key] = default_value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=4, sort_keys=True))

    def get(self, key: str) -> Any:
        return self.data.get(key, self.DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()

    def interactive_setup(self) -> None:
        """Launch a prompt-based setup to configure server settings."""
        console.print("[bold cyan]🎯 Minecraft Server Configuration Setup[/bold cyan]")
        console.print("[dim]Press Enter to keep current values[/dim]\n")

        for key, default in self.DEFAULTS.items():
            current = self.get(key)

            if isinstance(default, bool):
                val = Confirm.ask(f"{key.replace('_', ' ').title()}", default=current)
            else:
                prompt_text = f"{key.replace('_', ' ').title()}"
                if key.endswith('_interval'):
                    prompt_text += " (seconds)"
                elif key == 'memory':
                    prompt_text += " (e.g., 2G, 4G, 512M)"

                response = Prompt.ask(prompt_text, default=str(current))

                if isinstance(default, int):
                    try:
                        val = int(response)
                    except ValueError:
                        console.print(f"[yellow]Invalid number for {key}, keeping current value[/yellow]")
                        val = current
                else:
                    val = response

            self.set(key, val)

        console.print("\n[bold green]✅ Configuration saved successfully![/bold green]")