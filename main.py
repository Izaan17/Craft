#!/usr/bin/env python3
"""
Craft - Enhanced Minecraft Server Manager
Main entry point and command-line interface

A robust, feature-rich Minecraft server management tool with monitoring,
backup management, and process control capabilities.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import psutil
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from rich.table import Table

from backup import BackupManager
from config import ConfigManager
from display import StatusDisplay
from server import MinecraftServer
from utils import setup_signal_handlers, handle_error
from watchdog import Watchdog

# Constants
CRAFT_VERSION = "1.0.0"
DEFAULT_CONFIG_FILE = "config.json"

console = Console()


class CraftCLI:
    """Main CLI application class"""

    def __init__(self):
        self.config: Optional[ConfigManager] = None
        self.server: Optional[MinecraftServer] = None
        self.backup_manager: Optional[BackupManager] = None
        self.watchdog: Optional[Watchdog] = None

    def create_parser(self) -> argparse.ArgumentParser:
        """Create and configure the argument parser"""
        parser = argparse.ArgumentParser(
            prog="craft",
            description="🎮 Craft - Enhanced Minecraft Server Manager",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=self._get_help_examples()
        )

        parser.add_argument("--config", type=Path, default=Path(DEFAULT_CONFIG_FILE),
                            help="Config file path")
        parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
        parser.add_argument("--version", action="version", version=f"Craft {CRAFT_VERSION}")

        self._add_subcommands(parser)
        return parser

    def _get_help_examples(self) -> str:
        """Get help examples string"""
        return """
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

    def _add_subcommands(self, parser: argparse.ArgumentParser) -> None:
        """Add all subcommands to the parser"""
        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Setup and configuration
        subparsers.add_parser("setup", help="Interactive configuration")
        subparsers.add_parser("config-info", help="Show configuration file location")

        # Server management
        subparsers.add_parser("start", help="Start server")
        self._add_stop_parser(subparsers)
        subparsers.add_parser("restart", help="Restart server")

        # Status and monitoring
        self._add_status_parser(subparsers)
        subparsers.add_parser("debug", help="Show detailed debug information")
        subparsers.add_parser("fix", help="Attempt to fix common issues")
        self._add_logs_parser(subparsers)

        # Backup management
        self._add_backup_parsers(subparsers)

        # Commands
        self._add_command_parser(subparsers)

        # Watchdog
        self._add_watchdog_parser(subparsers)

    def _add_stop_parser(self, subparsers) -> None:
        """Add stop command parser"""
        stop_parser = subparsers.add_parser("stop", help="Stop server")
        stop_parser.add_argument("--graceful", "-g", action="store_true",
                                 help="Try graceful shutdown first")
        stop_parser.add_argument("--timeout", "-t", type=int,
                                 help="Timeout for graceful shutdown")

    def _add_status_parser(self, subparsers) -> None:
        """Add status command parser"""
        status_parser = subparsers.add_parser("status", help="Show server status")
        status_parser.add_argument("--live", "-l", action="store_true",
                                   help="Live status updates")
        status_parser.add_argument("--debug", "-d", action="store_true",
                                   help="Show debug information")

    def _add_logs_parser(self, subparsers) -> None:
        """Add logs command parser"""
        logs_parser = subparsers.add_parser("logs", help="Show server logs")
        logs_parser.add_argument("--lines", "-n", type=int, default=20,
                                 help="Number of lines to show")

    def _add_backup_parsers(self, subparsers) -> None:
        """Add backup-related command parsers"""
        backup_parser = subparsers.add_parser("backup", help="Create backup")
        backup_parser.add_argument("--name", "-n", help="Backup name")

        subparsers.add_parser("list-backups", help="List backups")

        restore_parser = subparsers.add_parser("restore", help="Restore backup")
        restore_parser.add_argument("backup", nargs="?", help="Backup to restore")

    def _add_command_parser(self, subparsers) -> None:
        """Add command parser"""
        cmd_parser = subparsers.add_parser("command", help="Send server command")
        cmd_parser.add_argument("cmd", nargs="+", help="Command to send")

    def _add_watchdog_parser(self, subparsers) -> None:
        """Add watchdog command parser"""
        watchdog_parser = subparsers.add_parser("watchdog", help="Manage watchdog")
        watchdog_parser.add_argument("action", choices=["start", "stop", "status"],
                                     help="Watchdog action")

    def initialize_components(self, config_path: Path) -> None:
        """Initialize all components"""
        try:
            self.config = ConfigManager(config_path)
            self.server = MinecraftServer(self.config)
            self.backup_manager = BackupManager(self.config)
            self.watchdog = Watchdog(self.server, self.backup_manager)
        except Exception as e:
            handle_error(e, "Failed to initialize components")
            sys.exit(1)

    def run(self) -> None:
        """Main application entry point"""
        parser = self.create_parser()
        args = parser.parse_args()

        if not args.command:
            parser.print_help()
            return

        # Setup signal handlers for graceful shutdown
        setup_signal_handlers()

        try:
            if args.command == "setup":
                self._handle_setup(args)
            else:
                self.initialize_components(args.config)
                self._dispatch_command(args)

        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled[/yellow]")
        except Exception as e:
            handle_error(e, "Application error")
            if args.verbose:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    def _handle_setup(self, args) -> None:
        """Handle setup command"""
        config = ConfigManager(args.config)
        config.interactive_setup()

    def _dispatch_command(self, args) -> None:
        """Dispatch commands to appropriate handlers"""
        command_handlers = {
            "start": self._handle_start,
            "stop": self._handle_stop,
            "restart": self._handle_restart,
            "status": self._handle_status,
            "debug": self._handle_debug,
            "fix": self._handle_fix,
            "logs": self._handle_logs,
            "config-info": self._handle_config_info,
            "backup": self._handle_backup,
            "list-backups": self._handle_list_backups,
            "restore": self._handle_restore,
            "command": self._handle_command,
            "watchdog": self._handle_watchdog,
        }

        handler = command_handlers.get(args.command)
        if handler:
            handler(args)
        else:
            console.print(f"[red]Unknown command: {args.command}[/red]")

    def _handle_start(self, args) -> None:
        """Handle start command"""
        if self.server.start():
            if self.config.get("watchdog_enabled"):
                console.print("[cyan]Starting watchdog...[/cyan]")
                self.watchdog.start()

    def _handle_stop(self, args) -> None:
        """Handle stop command"""
        if self.config.get("backup_on_stop") and self.server.is_running():
            console.print("[cyan]Creating backup before stop...[/cyan]")
            self.backup_manager.create_backup("pre_stop")

        self.watchdog.stop()

        # Handle stop arguments
        force_stop = not getattr(args, 'graceful', False)
        timeout = getattr(args, 'timeout', None)

        self.server.stop(force=force_stop, timeout=timeout)

    def _handle_restart(self, args) -> None:
        """Handle restart command"""
        if self.server.restart():
            if self.config.get("watchdog_enabled"):
                self.watchdog.start()

    def _handle_status(self, args) -> None:
        """Handle status command"""
        if getattr(args, 'debug', False):
            StatusDisplay.show_debug_status(self.server)
        else:
            StatusDisplay.show_status(self.server, self.watchdog,
                                      live_update=getattr(args, 'live', False))

    def _handle_debug(self, args) -> None:
        """Handle debug command"""
        StatusDisplay.show_debug_status(self.server)

    def _handle_fix(self, args) -> None:
        """Handle fix command"""
        FixUtility(self.server).fix_common_issues()

    def _handle_logs(self, args) -> None:
        """Handle logs command"""
        LogViewer.show_server_logs(self.server, args.lines)

    def _handle_config_info(self, args) -> None:
        """Handle config-info command"""
        ConfigInfoDisplay.show_config_info(self.config)

    def _handle_backup(self, args) -> None:
        """Handle backup command"""
        self.backup_manager.create_backup(getattr(args, 'name', None))

    def _handle_list_backups(self, args) -> None:
        """Handle list-backups command"""
        StatusDisplay.show_backups(self.backup_manager.list_backups())

    def _handle_restore(self, args) -> None:
        """Handle restore command"""
        backup_name = getattr(args, 'backup', None)
        if not backup_name:
            backup_name = BackupSelector.interactive_backup_selection(self.backup_manager)
            if not backup_name:
                return

        if self.server.is_running():
            if not Confirm.ask("Server is running. Stop and continue?", default=False):
                return
            self.watchdog.stop()
            self.server.stop()

        self.backup_manager.restore_backup(backup_name, self.server.server_dir)

    def _handle_command(self, args) -> None:
        """Handle command command"""
        command = " ".join(args.cmd)
        self.server.send_command(command)

    def _handle_watchdog(self, args) -> None:
        """Handle watchdog command"""
        if args.action == "start":
            self.watchdog.start()
        elif args.action == "stop":
            self.watchdog.stop()
        elif args.action == "status":
            StatusDisplay.show_watchdog_status(self.watchdog.get_status())


class ConfigInfoDisplay:
    """Utility class for displaying configuration information"""

    @staticmethod
    def show_config_info(config: ConfigManager) -> None:
        """Show configuration file information"""
        console.print(Panel.fit("📁 Configuration Information", style="bold cyan"))

        table = Table(show_header=False, box=None)
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Config File", str(config.config_path))
        table.add_row("Config Directory", str(config.config_path.parent))
        table.add_row("File Exists", "✅ Yes" if config.config_path.exists() else "❌ No")

        if config.config_path.exists():
            stat = config.config_path.stat()
            table.add_row("File Size", f"{stat.st_size} bytes")
            table.add_row("Last Modified",
                          datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"))

        # Show key config values
        table.add_row("", "")  # Separator
        ConfigInfoDisplay._add_config_values(table, config)

        console.print(table)
        ConfigInfoDisplay._show_config_tips(config)

    @staticmethod
    def _add_config_values(table: Table, config: ConfigManager) -> None:
        """Add configuration values to the table"""
        config_items = [
            ("Server Directory", "server_dir"),
            ("JAR Name", "jar_name"),
            ("Memory Max", "memory_max"),
            ("Watchdog Enabled", "watchdog_enabled"),
            ("Auto Backup", "auto_backup"),
            ("Force Stop", "force_stop")
        ]

        for label, key in config_items:
            value = config.get(key)
            if isinstance(value, bool):
                display_value = "✅ Yes" if value else "❌ No"
            else:
                display_value = str(value)
            table.add_row(label, display_value)

    @staticmethod
    def _show_config_tips(config: ConfigManager) -> None:
        """Show configuration tips"""
        console.print(f"\n[cyan]💡 Edit config:[/cyan] craft setup")
        console.print(f"[cyan]💡 View config:[/cyan] cat {config.config_path}")


class LogViewer:
    """Utility class for viewing server logs"""

    @staticmethod
    def show_server_logs(server: MinecraftServer, lines: int = 20) -> None:
        """Show recent server logs with colored output"""
        console.print(f"[cyan]📋 Last {lines} lines of server logs:[/cyan]\n")

        log_lines = server.get_log_tail(lines)

        if not log_lines:
            LogViewer._show_no_logs_message()
            return

        for line in log_lines:
            LogViewer._print_colored_log_line(line.rstrip())

    @staticmethod
    def _show_no_logs_message() -> None:
        """Show message when no logs are found"""
        console.print("[yellow]⚠️  No log files found[/yellow]")
        console.print("[dim]Logs should appear in server/logs/latest.log after the server starts[/dim]")

    @staticmethod
    def _print_colored_log_line(line: str) -> None:
        """Print a log line with appropriate coloring"""
        if not line:
            return

        # Basic log level coloring
        if "[ERROR]" in line or "ERROR" in line:
            console.print(f"[red]{line}[/red]")
        elif "[WARN]" in line or "WARN" in line:
            console.print(f"[yellow]{line}[/yellow]")
        elif "[INFO]" in line or "INFO" in line:
            console.print(f"[white]{line}[/white]")
        else:
            console.print(f"[dim]{line}[/dim]")


class FixUtility:
    """Utility class for fixing common server issues"""

    def __init__(self, server: MinecraftServer):
        self.server = server

    def fix_common_issues(self) -> None:
        """Attempt to fix common server detection issues"""
        console.print("[cyan]🔧 Attempting to fix common issues...[/cyan]\n")

        status = self.server.get_status()
        debug_info = status.get("debug_info", {})
        fixed_issues = []

        fixed_issues.extend(self._fix_stale_pid_file(debug_info))
        fixed_issues.extend(self._fix_orphaned_processes(debug_info, status))
        fixed_issues.extend(self._fix_lock_file(status))
        fixed_issues.extend(self._fix_dead_process_reference())

        self._report_results(fixed_issues, status)

    def _fix_stale_pid_file(self, debug_info: dict) -> list:
        """Fix stale PID file"""
        issues_fixed = []
        saved_pid = debug_info.get("saved_pid")

        if saved_pid and not debug_info.get("pid_exists", False):
            console.print("[yellow]🔧 Removing stale PID file...[/yellow]")
            try:
                self.server.process_manager.clear_pid()
                issues_fixed.append("Removed stale PID file")
            except Exception as e:
                console.print(f"[red]❌ Failed to clear PID file: {e}[/red]")

        return issues_fixed

    def _fix_orphaned_processes(self, debug_info: dict, status: dict) -> list:
        """Fix orphaned server processes"""
        issues_fixed = []
        java_processes = debug_info.get("java_process_pids", [])

        if java_processes and not status["running"]:
            console.print("[yellow]🔧 Found orphaned server process, attempting to adopt...[/yellow]")

            for java_pid in java_processes:
                try:
                    proc = psutil.Process(java_pid)
                    if str(self.server.server_dir) in proc.cwd():
                        self.server.process_manager.save_pid(java_pid)
                        self.server.stats.set_process(proc)
                        console.print(f"[green]✅ Adopted process {java_pid}[/green]")
                        issues_fixed.append(f"Adopted orphaned process {java_pid}")
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    console.print(f"[yellow]⚠️  Could not adopt process {java_pid}: {e}[/yellow]")
                    continue

        return issues_fixed

    def _fix_lock_file(self, status: dict) -> list:
        """Fix stale lock file"""
        issues_fixed = []

        if not status["running"] and self.server.process_manager.lock_file.exists():
            console.print("[yellow]🔧 Clearing stale lock file...[/yellow]")
            try:
                self.server.process_manager.release_lock()
                issues_fixed.append("Cleared stale lock file")
            except Exception as e:
                console.print(f"[red]❌ Failed to clear lock file: {e}[/red]")

        return issues_fixed

    def _fix_dead_process_reference(self) -> list:
        """Fix dead process reference"""
        issues_fixed = []

        if self.server.process and self.server.process.poll() is not None:
            console.print("[yellow]🔧 Clearing dead process reference...[/yellow]")
            self.server.process = None
            issues_fixed.append("Cleared dead process reference")

        return issues_fixed

    def _report_results(self, fixed_issues: list, status: dict) -> None:
        """Report fix results to user"""
        if fixed_issues:
            console.print(f"\n[green]✅ Fixed {len(fixed_issues)} issue(s):[/green]")
            for issue in fixed_issues:
                console.print(f"  • {issue}")

            self._check_post_fix_status()
        else:
            self._show_no_fixes_message(status)

    def _check_post_fix_status(self) -> None:
        """Check status after applying fixes"""
        console.print(f"\n[cyan]Checking status again...[/cyan]")
        new_status = self.server.get_status()

        if new_status["running"]:
            console.print("[green]🎉 Server is now detected as running![/green]")
            if new_status.get("can_send_commands", False):
                console.print("[green]✅ Command sending is available[/green]")
            else:
                console.print(
                    "[yellow]⚠️  Commands not available (server was adopted). Use 'craft restart' to enable.[/yellow]")
        else:
            console.print("[yellow]⚠️  Server still not detected. Try 'craft debug' for more info.[/yellow]")

    def _show_no_fixes_message(self, status: dict) -> None:
        """Show message when no fixes were applied"""
        console.print("[yellow]⚠️  No fixable issues found. Try 'craft debug' for detailed information.[/yellow]")

        if not status["running"]:
            console.print("\n[cyan]💡 Next steps:[/cyan]")
            console.print("  • Check if NeoForge is actually running: ps aux | grep java")
            console.print("  • Try starting the server: craft start")
            console.print("  • Check server logs: craft logs")
            console.print("  • Get detailed debug info: craft debug")


class BackupSelector:
    """Utility class for interactive backup selection"""

    @staticmethod
    def interactive_backup_selection(backup_manager: BackupManager) -> Optional[str]:
        """Interactive backup selection with user-friendly interface"""
        backups = backup_manager.list_backups()
        if not backups:
            console.print("[red]No backups available[/red]")
            return None

        console.print("\n📁 Available backups:")
        for i, backup in enumerate(backups, 1):
            age_hours = backup.get('age_hours', 0)
            age_str = BackupSelector._format_backup_age(age_hours)
            console.print(f"  {i}. {backup['name']} ({backup['size_mb']:.1f} MB) - {age_str}")

        try:
            choice = IntPrompt.ask("Select backup",
                                   choices=[str(i) for i in range(1, len(backups) + 1)])
            return backups[choice - 1]["name"]
        except (KeyboardInterrupt, EOFError):
            console.print("[yellow]Cancelled[/yellow]")
            return None

    @staticmethod
    def _format_backup_age(age_hours: float) -> str:
        """Format backup age in human readable format"""
        if age_hours < 1:
            return f"{age_hours * 60:.0f}m ago"
        elif age_hours < 24:
            return f"{age_hours:.1f}h ago"
        else:
            return f"{age_hours / 24:.1f}d ago"


def main():
    """Main application entry point"""
    app = CraftCLI()
    app.run()


if __name__ == "__main__":
    main()
