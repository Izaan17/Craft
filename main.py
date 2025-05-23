#!/usr/bin/env python3
"""
Craft - Enhanced Minecraft Server Manager
Main entry point and command-line interface
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, IntPrompt

from config import ConfigManager
from server import MinecraftServer
from backup import BackupManager
from watchdog import Watchdog
from display import StatusDisplay
from utils import setup_signal_handlers

console = Console()

def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(
        prog="craft",
        description="🎮 Craft - Enhanced Minecraft Server Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  craft setup                             # Interactive configuration
  craft start                             # Start the server
  craft stop                              # Stop the server
  craft status --live                     # Live status monitoring
  craft backup --name weekend             # Create named backup
  craft restore                           # Interactive backup restore
  craft watchdog start                    # Start monitoring
  craft command say "Hello players!"      # Send server command
        """
    )

    parser.add_argument("--config", type=Path, default=Path("config.json"), help="Config file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup
    subparsers.add_parser("setup", help="Interactive configuration")

    # Server management
    subparsers.add_parser("start", help="Start server")
    subparsers.add_parser("stop", help="Stop server")
    subparsers.add_parser("restart", help="Restart server")

    # Status
    status_parser = subparsers.add_parser("status", help="Show server status")
    status_parser.add_argument("--live", "-l", action="store_true", help="Live status updates")

    # Backup management
    backup_parser = subparsers.add_parser("backup", help="Create backup")
    backup_parser.add_argument("--name", "-n", help="Backup name")

    subparsers.add_parser("list-backups", help="List backups")

    restore_parser = subparsers.add_parser("restore", help="Restore backup")
    restore_parser.add_argument("backup", nargs="?", help="Backup to restore")

    # Commands
    cmd_parser = subparsers.add_parser("command", help="Send server command")
    cmd_parser.add_argument("cmd", nargs="+", help="Command to send")

    # Watchdog
    watchdog_parser = subparsers.add_parser("watchdog", help="Manage watchdog")
    watchdog_parser.add_argument("action", choices=["start", "stop", "status"], help="Watchdog action")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()

    # Load configuration
    config = ConfigManager(args.config)

    if args.command == "setup":
        config.interactive_setup()
        return

    # Initialize components
    server = MinecraftServer(config)
    backup_manager = BackupManager(config)
    watchdog = Watchdog(server, backup_manager)

    try:
        if args.command == "start":
            if server.start():
                if config.get("watchdog_enabled"):
                    console.print("[cyan]Starting watchdog...[/cyan]")
                    watchdog.start()

        elif args.command == "stop":
            if config.get("backup_on_stop") and server.is_running():
                console.print("[cyan]Creating backup before stop...[/cyan]")
                backup_manager.create_backup("pre_stop")

            watchdog.stop()
            server.stop()

        elif args.command == "restart":
            if server.restart():
                if config.get("watchdog_enabled"):
                    watchdog.start()

        elif args.command == "status":
            StatusDisplay.show_status(server, watchdog, live_update=args.live)

        elif args.command == "backup":
            backup_manager.create_backup(args.name)

        elif args.command == "list-backups":
            StatusDisplay.show_backups(backup_manager.list_backups())

        elif args.command == "restore":
            backup_name = args.backup
            if not backup_name:
                backup_name = _interactive_backup_selection(backup_manager)
                if not backup_name:
                    return

            if server.is_running():
                if not Confirm.ask("Server is running. Stop and continue?", default=False):
                    return
                watchdog.stop()
                server.stop()

            backup_manager.restore_backup(backup_name, server.server_dir)

        elif args.command == "command":
            command = " ".join(args.cmd)
            server.send_command(command)

        elif args.command == "watchdog":
            if args.action == "start":
                watchdog.start()
            elif args.action == "stop":
                watchdog.stop()
            elif args.action == "status":
                StatusDisplay.show_watchdog_status(watchdog.get_status())

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

def _interactive_backup_selection(backup_manager):
    """Interactive backup selection"""
    backups = backup_manager.list_backups()
    if not backups:
        console.print("[red]No backups available[/red]")
        return None

    console.print("\n📁 Available backups:")
    for i, backup in enumerate(backups, 1):
        console.print(f"  {i}. {backup['name']} ({backup['size_mb']:.1f} MB)")

    try:
        choice = IntPrompt.ask("Select backup", choices=[str(i) for i in range(1, len(backups) + 1)])
        return backups[choice - 1]["name"]
    except (KeyboardInterrupt, EOFError):
        console.print("[yellow]Cancelled[/yellow]")
        return None

if __name__ == "__main__":
    main()