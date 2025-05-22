import sys

from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

def print_info(message: str):
    console.print(f"[bold cyan]ℹ [INFO][/bold cyan] {message}")

def print_success(message: str):
    console.print(f"[bold green]✅ [SUCCESS][/bold green] {message}")

def print_error(message: str):
    console.print(f"[bold red]❌ [ERROR][/bold red] {message}")

def print_warning(message: str):
    console.print(f"[bold yellow]⚠ [WARNING][/bold yellow] {message}")

def setup_logging(log_file: str = "craft_manager.log", level: str = "INFO"):
    """Setup logging with rotation and retention"""
    logger.remove()  # Remove default handler

    # Add file handler
    logger.add(
        log_file,
        rotation="10 MB",
        retention="30 days",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"
    )

    # Add console handler for errors
    logger.add(
        sys.stderr,
        level="ERROR",
        format="<red>{level}</red>: {message}"
    )

    logger.debug("Logging initialized")

def format_uptime(seconds: float) -> str:
    """Format uptime in human readable format"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds/60:.0f}m"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f"{days}d {hours}h"

def display_status_table(server_status: dict, watchdog_status: dict = None):
    """Display a formatted status table"""
    table = Table(title="🎮 Minecraft Server Status", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    # Server status
    status_color = "green" if server_status['running'] else "red"
    status_text = "🟢 Running" if server_status['running'] else "🔴 Stopped"
    table.add_row("Status", f"[{status_color}]{status_text}[/{status_color}]")

    table.add_row("Screen Session", "✅ Active" if server_status['screen_session'] else "❌ Inactive")
    table.add_row("Port Open", "✅ Open" if server_status['port_open'] else "❌ Closed")

    if server_status['memory_usage']:
        table.add_row("Memory Usage", f"{server_status['memory_usage']:.1f} MB")

    if server_status['cpu_usage'] is not None:
        table.add_row("CPU Usage", f"{server_status['cpu_usage']:.1f}%")

    if server_status['uptime']:
        table.add_row("Uptime", format_uptime(server_status['uptime']))

    # Watchdog status
    if watchdog_status:
        table.add_row("", "")  # Separator
        watchdog_color = "green" if watchdog_status['running'] else "red"
        watchdog_text = "🟢 Active" if watchdog_status['running'] else "🔴 Inactive"
        table.add_row("Watchdog", f"[{watchdog_color}]{watchdog_text}[/{watchdog_color}]")

        if watchdog_status['restart_count'] > 0:
            table.add_row("Restart Count", str(watchdog_status['restart_count']))

    console.print(table)
