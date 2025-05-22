import argparse
import sys
from pathlib import Path

from backup import BackupManager
from config import Config
from server import MinecraftServer
from utils import (
    print_success, print_error, print_info, print_warning,
    setup_logging, display_status_table, console
)
from watchdog import Watchdog


def main():
    parser = argparse.ArgumentParser(
        prog="craft-manager",
        description="🎮 Advanced Minecraft Server Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  craft-manager setup                    # Interactive configuration
  craft-manager start                    # Start the server
  craft-manager status --detailed        # Show detailed status
  craft-manager backup --name weekend    # Create named backup
  craft-manager watch start             # Start watchdog with auto-backup
  craft-manager restore                  # Interactive backup restore
        """
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.json"),
        help="Path to config file (default: config.json)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Setup command
    subparsers.add_parser("setup", help="Interactive server configuration")

    # Server commands
    subparsers.add_parser("start", help="Start the Minecraft server")
    subparsers.add_parser("stop", help="Stop the Minecraft server")
    subparsers.add_parser("restart", help="Restart the Minecraft server")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show server status")
    status_parser.add_argument("--detailed", "-d", action="store_true", help="Show detailed status")

    # Backup commands
    backup_parser = subparsers.add_parser("backup", help="Create world backup")
    backup_parser.add_argument("--name", "-n", help="Custom backup name")

    subparsers.add_parser("list-backups", help="List all backups")

    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("backup", nargs="?", help="Backup file name to restore")

    # Command sending
    cmd_parser = subparsers.add_parser("command", help="Send command to server")
    cmd_parser.add_argument("cmd", nargs="+", help="Command to send")

    # Watchdog commands
    watch_parser = subparsers.add_parser("watch", help="Manage watchdog")
    watch_parser.add_argument("action", choices=["start", "stop", "status"], help="Watchdog action")

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(level=log_level)

    # Load configuration
    config = Config(args.config)

    if args.command == "setup":
        config.interactive_setup()
        return

    if not args.command:
        parser.print_help()
        return

    # Initialize components
    server = MinecraftServer(config)
    backup_manager = BackupManager(config)

    try:
        if args.command == "start":
            server.start()

        elif args.command == "stop":
            # Backup on stop if enabled
            if config.get("backup_on_stop") and server.is_running():
                print_info("Creating backup before stopping server...")
                backup_manager.backup_world("pre_stop")
            server.stop()

        elif args.command == "restart":
            server.restart()

        elif args.command == "status":
            server_status = server.get_status()

            if args.detailed:
                # Show detailed status with watchdog info
                watchdog = Watchdog(args.config)
                watchdog_status = watchdog.get_status()
                display_status_table(server_status, watchdog_status)

                # Show recent backups
                backups = backup_manager.list_backups()
                if backups:
                    console.print("\n📁 Recent Backups:")
                    for backup in backups[:3]:
                        console.print(f"  • {backup['name']} ({backup['size_formatted']}) - {backup['created'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # Simple status
                if server_status['running']:
                    print_success("Server is running")
                else:
                    print_error("Server is not running")

        elif args.command == "backup":
            backup_name = args.name if hasattr(args, 'name') and args.name else None
            backup_manager.backup_world(backup_name)

        elif args.command == "list-backups":
            backups = backup_manager.list_backups()
            if not backups:
                print_info("No backups found")
            else:
                console.print("\n📁 Available Backups:")
                for backup in backups:
                    console.print(f"  • {backup['name']} ({backup['size_formatted']}) - {backup['created'].strftime('%Y-%m-%d %H:%M:%S')}")

        elif args.command == "restore":
            if hasattr(args, 'backup') and args.backup:
                backup_name = args.backup
            else:
                # Interactive selection
                backups = backup_manager.list_backups()
                if not backups:
                    print_error("No backups available")
                    return

                console.print("\nAvailable backups:")
                for i, backup in enumerate(backups, 1):
                    console.print(f"  {i}. {backup['name']} ({backup['size_formatted']}) - {backup['created'].strftime('%Y-%m-%d %H:%M:%S')}")

                try:
                    choice = int(input("\nSelect backup number: ")) - 1
                    backup_name = backups[choice]['name']
                except (ValueError, IndexError):
                    print_error("Invalid selection")
                    return

            if server.is_running():
                print_warning("Server is running. It should be stopped before restoring.")
                response = input("Stop server and continue? (y/N): ")
                if response.lower() != 'y':
                    return
                server.stop()

            backup_manager.restore_backup(backup_name)

        elif args.command == "command":
            command = " ".join(args.cmd)
            server.send_command(command)

        elif args.command == "watch":
            watchdog = Watchdog(args.config)

            if args.action == "start":
                watchdog.start()
            elif args.action == "stop":
                watchdog.stop()
            elif args.action == "status":
                status = watchdog.get_status()
                if status['running']:
                    print_success("Watchdog is running")
                    if status['restart_count'] > 0:
                        print_info(f"Restart count: {status['restart_count']}")
                else:
                    print_error("Watchdog is not running")

    except KeyboardInterrupt:
        print_info("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()