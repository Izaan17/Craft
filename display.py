"""
Status display and UI for Craft Minecraft Server Manager

Provides comprehensive status displays, live monitoring, and formatted output
for server status, debug information, and system metrics.
"""

import time
from datetime import datetime
from typing import Dict, List, Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from utils import handle_error, format_uptime

console = Console()

# Display constants
REFRESH_RATE = 1  # seconds
MAX_RESTART_HISTORY = 10
CHART_WIDTH = 60
STATUS_COLORS = {
    "running": "green",
    "stopped": "red",
    "warning": "yellow",
    "info": "cyan",
    "error": "red"
}


class StatusDisplay:
    """Enhanced status display with live updates and comprehensive information"""

    @staticmethod
    def show_debug_status(server) -> None:
        """Show detailed debug information with enhanced troubleshooting"""
        try:
            status = server.get_status()
            debug_info = status.get("debug_info", {})

            StatusDisplay._show_debug_header(status)
            StatusDisplay._show_debug_table(debug_info)
            StatusDisplay._show_troubleshooting_tips(status, debug_info)

        except Exception as e:
            handle_error(e, "Failed to display debug status")

    @staticmethod
    def _show_debug_header(status: Dict[str, Any]) -> None:
        """Show debug information header"""
        console.print(Panel.fit("🔍 Debug Information", style="bold yellow"))

        running = status["running"]
        status_color = STATUS_COLORS["running" if running else "stopped"]
        status_text = "🟢 Running" if running else "🔴 Stopped"
        console.print(f"Server Status: [{status_color}]{status_text}[/{status_color}]\n")

    @staticmethod
    def _show_debug_table(debug_info: Dict[str, Any]) -> None:
        """Show comprehensive debug information table"""
        debug_table = Table(title="Debug Details", show_header=True)
        debug_table.add_column("Component", style="cyan", no_wrap=True)
        debug_table.add_column("Value", style="white")
        debug_table.add_column("Status", style="white")

        StatusDisplay._add_pid_debug_rows(debug_table, debug_info)
        StatusDisplay._add_process_debug_rows(debug_table, debug_info)
        StatusDisplay._add_command_debug_rows(debug_table, debug_info)
        StatusDisplay._add_java_debug_rows(debug_table, debug_info)

        console.print(debug_table)

    @staticmethod
    def _add_pid_debug_rows(table: Table, debug_info: Dict[str, Any]) -> None:
        """Add PID-related debug information to table"""
        saved_pid = debug_info.get("saved_pid")
        table.add_row("Saved PID", str(saved_pid) if saved_pid else "None",
                      "✅" if saved_pid else "❌")

        table.add_row("PID File Exists", str(debug_info.get("pid_file_exists", False)),
                      "✅" if debug_info.get("pid_file_exists") else "❌")

        if saved_pid:
            table.add_row("PID Exists in System", str(debug_info.get("pid_exists", False)),
                          "✅" if debug_info.get("pid_exists") else "❌")

            table.add_row("Process Running", str(debug_info.get("process_running", False)),
                          "✅" if debug_info.get("process_running") else "❌")

            process_name = debug_info.get("process_name", "Unknown")
            table.add_row("Process Name", process_name, "")

            process_cwd = debug_info.get("process_cwd", "Unknown")
            table.add_row("Working Directory", process_cwd, "")

    @staticmethod
    def _add_process_debug_rows(table: Table, debug_info: Dict[str, Any]) -> None:
        """Add process reference debug information"""
        direct_poll = debug_info.get("direct_process_poll")
        if debug_info.get("direct_process") is not None:
            if direct_poll is not None:
                table.add_row("Direct Process", f"Poll result: {direct_poll}",
                              "❌ (terminated)" if direct_poll is not None else "✅")
            else:
                table.add_row("Direct Process", "Running", "✅")

            has_stdin = debug_info.get("has_stdin", False)
            table.add_row("STDIN Available", str(has_stdin),
                          "✅" if has_stdin else "❌")
        else:
            table.add_row("Direct Process", "No reference", "❌")

    @staticmethod
    def _add_command_debug_rows(table: Table, debug_info: Dict[str, Any]) -> None:
        """Add command capability debug information"""
        can_commands = debug_info.get("can_send_commands", False)
        table.add_row("Can Send Commands", str(can_commands),
                      "✅" if can_commands else "❌")

    @staticmethod
    def _add_java_debug_rows(table: Table, debug_info: Dict[str, Any]) -> None:
        """Add Java processes debug information"""
        java_count = debug_info.get("java_processes_found", 0)
        java_pids = debug_info.get("java_process_pids", [])

        table.add_row("Java Processes", f"{java_count} found",
                      "✅" if java_count > 0 else "❌")

        if java_pids:
            table.add_row("Java PIDs", ", ".join(map(str, java_pids)), "")

        # Show any errors
        if "process_error" in debug_info:
            table.add_row("Process Error", debug_info["process_error"], "❌")

        if "java_search_error" in debug_info:
            table.add_row("Java Search Error", debug_info["java_search_error"], "❌")

    @staticmethod
    def _show_troubleshooting_tips(status: Dict[str, Any], debug_info: Dict[str, Any]) -> None:
        """Show contextual troubleshooting tips"""
        console.print("\n[bold cyan]💡 Troubleshooting Tips:[/bold cyan]")

        running = status["running"]
        if not running:
            StatusDisplay._show_stopped_server_tips(debug_info)
        else:
            StatusDisplay._show_running_server_tips(status, debug_info)

    @staticmethod
    def _show_stopped_server_tips(debug_info: Dict[str, Any]) -> None:
        """Show tips for stopped server"""
        saved_pid = debug_info.get("saved_pid")
        java_count = debug_info.get("java_processes_found", 0)

        if not saved_pid:
            console.print("  • No PID found - server may not have been started with Craft")
            console.print("  • Try: craft start")
        elif not debug_info.get("pid_exists"):
            console.print("  • Saved PID doesn't exist - server may have crashed")
            console.print("  • Try: craft start")
        elif java_count > 0:
            console.print("  • Java processes found but not tracked correctly")
            console.print("  • Server may have been started outside of Craft")
            console.print("  • Try: craft stop && craft start")

    @staticmethod
    def _show_running_server_tips(status: Dict[str, Any], debug_info: Dict[str, Any]) -> None:
        """Show tips for running server"""
        uptime = status.get("uptime")
        if uptime:
            uptime_str = format_uptime(uptime)
            console.print(f"  ✅ Server running normally (uptime: {uptime_str})")

        can_commands = debug_info.get("can_send_commands", False)
        if not can_commands:
            console.print("  ⚠️  Cannot send commands to this server process")
            console.print("  • Server was likely started outside of Craft")
            console.print("  • Use 'craft restart' to enable command functionality")
            console.print("  • Or stop the server manually and use 'craft start'")
        else:
            console.print("  ✅ Command sending is available")
            console.print("  • Try: craft command list")
            console.print("  • Try: craft command say Hello World")

    @staticmethod
    def show_status(server, watchdog, live_update: bool = False) -> None:
        """Show comprehensive server status with optional live updates"""
        try:
            if live_update:
                StatusDisplay._show_live_status(server, watchdog)
            else:
                display = StatusDisplay._create_status_display(server, watchdog)
                console.print(display)
        except Exception as e:
            handle_error(e, "Failed to display status")

    @staticmethod
    def _show_live_status(server, watchdog) -> None:
        """Show live updating status display"""
        try:
            with Live(
                    StatusDisplay._create_status_display(server, watchdog),
                    refresh_per_second=REFRESH_RATE,
                    console=console
            ) as live:
                while True:
                    time.sleep(1)
                    live.update(StatusDisplay._create_status_display(server, watchdog))
        except KeyboardInterrupt:
            console.print("\n[yellow]Live update stopped[/yellow]")
        except Exception as e:
            handle_error(e, "Live status update failed")

    @staticmethod
    def _create_status_display(server, watchdog) -> Layout:
        """Create comprehensive status display layout"""
        layout = Layout()

        # Create layout structure
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )

        layout["main"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        layout["right"].split_column(
            Layout(name="right_top"),
            Layout(name="right_bottom")
        )

        # Get status data
        server_status = server.get_status()
        watchdog_status = watchdog.get_status()

        # Populate layout sections
        StatusDisplay._populate_header(layout["header"])
        StatusDisplay._populate_server_panel(layout["left"], server_status)
        StatusDisplay._populate_monitoring_panel(layout["right_top"], watchdog_status)
        StatusDisplay._populate_system_panel(layout["right_bottom"], server_status)
        StatusDisplay._populate_footer(layout["footer"])

        return layout

    @staticmethod
    def _populate_header(layout: Layout) -> None:
        """Populate header section"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        layout.update(
            Panel.fit(
                f"🎮 Craft Server Manager - {current_time}",
                style="bold cyan"
            )
        )

    @staticmethod
    def _populate_server_panel(layout: Layout, server_status: Dict[str, Any]) -> None:
        """Populate server status panel"""
        status_table = StatusDisplay._create_server_status_table(server_status)
        border_style = STATUS_COLORS["running" if server_status["running"] else "stopped"]

        layout.update(
            Panel(status_table, title="🖥️  Server Status", border_style=border_style)
        )

    @staticmethod
    def _populate_monitoring_panel(layout: Layout, watchdog_status: Dict[str, Any]) -> None:
        """Populate monitoring status panel"""
        monitoring_table = StatusDisplay._create_monitoring_table(watchdog_status)
        layout.update(
            Panel(monitoring_table, title="🐕 Monitoring", border_style="yellow")
        )

    @staticmethod
    def _populate_system_panel(layout: Layout, server_status: Dict[str, Any]) -> None:
        """Populate system information panel"""
        system_table = StatusDisplay._create_system_table(server_status)
        layout.update(
            Panel(system_table, title="⚙️  System", border_style="blue")
        )

    @staticmethod
    def _populate_footer(layout: Layout) -> None:
        """Populate footer section"""
        footer_text = "Press Ctrl+C to exit | 🔄 Live updating..."
        layout.update(Panel.fit(footer_text, style="dim"))

    @staticmethod
    def _create_server_status_table(status: Dict[str, Any]) -> Table:
        """Create detailed server status table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        if status["running"]:
            StatusDisplay._add_running_server_rows(table, status)
        else:
            table.add_row("Status", "[red]🔴 Stopped[/red]")

        StatusDisplay._add_configuration_rows(table, status.get("config", {}))

        return table

    @staticmethod
    def _add_running_server_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add rows for running server status"""
        table.add_row("Status", "[green]🟢 Running[/green]")
        table.add_row("PID", str(status["pid"]))

        # Command capability with helpful hint
        can_command = status.get("can_send_commands", False)
        command_text = "[green]✅ Available[/green]" if can_command else "[yellow]⚠️  Limited[/yellow]"
        table.add_row("Commands", command_text)

        if not can_command:
            table.add_row("", "[dim]Use 'craft restart' to enable[/dim]")

        # Uptime
        uptime = status.get("uptime")
        uptime_str = format_uptime(uptime) if uptime else "Unknown"
        table.add_row("Uptime", uptime_str)

        # Resource usage with color coding
        StatusDisplay._add_resource_usage_rows(table, status)

        # Performance metrics
        StatusDisplay._add_performance_rows(table, status)

        # Average performance data
        StatusDisplay._add_average_performance_rows(table, status)

    @staticmethod
    def _add_resource_usage_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add resource usage information with color coding"""
        # Memory usage
        memory_mb = status.get("memory_usage_mb", 0)
        memory_pct = status.get("memory_percent", 0)
        memory_color = StatusDisplay._get_resource_color(memory_pct, 70, 90)
        table.add_row("Memory", f"[{memory_color}]{memory_mb:.1f} MB ({memory_pct:.1f}%)[/{memory_color}]")

        # CPU usage
        cpu_pct = status.get("cpu_percent", 0)
        cpu_color = StatusDisplay._get_resource_color(cpu_pct, 50, 80)
        table.add_row("CPU", f"[{cpu_color}]{cpu_pct:.1f}%[/{cpu_color}]")

    @staticmethod
    def _add_performance_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add performance metrics"""
        table.add_row("Threads", str(status.get("threads", 0)))
        table.add_row("Connections", str(status.get("connections", 0)))

    @staticmethod
    def _add_average_performance_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add average performance data"""
        averages = status.get("averages", {})
        if averages:
            table.add_row("", "")  # Separator
            table.add_row("Avg Memory (5m)", f"{averages.get('avg_memory_mb', 0):.1f} MB")
            table.add_row("Avg CPU (5m)", f"{averages.get('avg_cpu_percent', 0):.1f}%")

    @staticmethod
    def _add_configuration_rows(table: Table, config: Dict[str, Any]) -> None:
        """Add configuration information"""
        table.add_row("", "")  # Separator
        table.add_row("JAR", config.get("jar_name", "Unknown"))
        table.add_row("Max Memory", config.get("memory_max", "Unknown"))
        table.add_row("Server Type", config.get("server_type", "Minecraft"))

    @staticmethod
    def _get_resource_color(percentage: float, warning_threshold: float, critical_threshold: float) -> str:
        """Get color based on resource usage percentage"""
        if percentage >= critical_threshold:
            return "red"
        elif percentage >= warning_threshold:
            return "yellow"
        else:
            return "green"

    @staticmethod
    def _create_monitoring_table(watchdog_status: Dict[str, Any]) -> Table:
        """Create comprehensive monitoring status table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Watchdog status with detailed state information
        StatusDisplay._add_watchdog_status_rows(table, watchdog_status)

        # Restart information
        StatusDisplay._add_restart_info_rows(table, watchdog_status)

        # Monitoring statistics
        StatusDisplay._add_monitoring_stats_rows(table, watchdog_status)

        return table

    @staticmethod
    def _add_watchdog_status_rows(table: Table, watchdog_status: Dict[str, Any]) -> None:
        """Add watchdog status information"""
        running = watchdog_status["running"]
        thread_alive = watchdog_status.get("thread_alive", False)
        running_flag = watchdog_status.get("running_flag", False)

        if running:
            watchdog_text = "[green]🟢 Active[/green]"
        else:
            watchdog_text = "[red]🔴 Inactive[/red]"
            # Show debug info if not running properly
            if running_flag and not thread_alive:
                watchdog_text += " [dim](thread died)[/dim]"
            elif not running_flag:
                watchdog_text += " [dim](stopped)[/dim]"

        table.add_row("Watchdog", watchdog_text)

        # Uptime
        uptime = watchdog_status.get("uptime")
        if uptime and running:
            uptime_str = format_uptime(uptime)
            table.add_row("Monitor Uptime", uptime_str)

        # Auto-backup status
        backup_running = watchdog_status.get("auto_backup_running", False)
        backup_text = "[green]🟢 Active[/green]" if backup_running else "[red]🔴 Inactive[/red]"
        table.add_row("Auto Backup", backup_text)

    @staticmethod
    def _add_restart_info_rows(table: Table, watchdog_status: Dict[str, Any]) -> None:
        """Add restart information"""
        restart_count = watchdog_status.get("restart_count", 0)

        if restart_count > 0:
            restart_color = "yellow" if restart_count < 3 else "red"
            table.add_row("Restarts", f"[{restart_color}]{restart_count}[/{restart_color}]")

            last_restart = watchdog_status.get("last_restart")
            if last_restart:
                last_restart_str = last_restart.strftime("%H:%M:%S")
                table.add_row("Last Restart", last_restart_str)
        else:
            table.add_row("Restarts", "[green]0[/green]")

        # Success rate
        success_rate = watchdog_status.get("restart_success_rate", 100)
        rate_color = StatusDisplay._get_success_rate_color(success_rate)
        table.add_row("Success Rate", f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]")

    @staticmethod
    def _add_monitoring_stats_rows(table: Table, watchdog_status: Dict[str, Any]) -> None:
        """Add monitoring statistics"""
        monitoring_stats = watchdog_status.get("monitoring_stats", {})
        if monitoring_stats:
            table.add_row("", "")  # Separator
            table.add_row("Checks", str(monitoring_stats.get("checks_performed", 0)))

    @staticmethod
    def _get_success_rate_color(success_rate: float) -> str:
        """Get color for success rate display"""
        if success_rate < 80:
            return "red"
        elif success_rate < 95:
            return "yellow"
        else:
            return "green"

    @staticmethod
    def _create_system_table(status: Dict[str, Any]) -> Table:
        """Create system information table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # World information
        StatusDisplay._add_world_info_rows(table, status)

        # Server configuration
        StatusDisplay._add_server_config_rows(table, status)

        # Performance peaks
        StatusDisplay._add_performance_peaks_rows(table, status)

        return table

    @staticmethod
    def _add_world_info_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add world information"""
        world_info = status.get("world_info", {})
        if world_info.get("exists", False):
            size_mb = world_info.get("size_mb", 0)
            table.add_row("World Size", f"{size_mb:.1f} MB")

            player_count = world_info.get("player_data_count", 0)
            if player_count > 0:
                table.add_row("Players", str(player_count))

    @staticmethod
    def _add_server_config_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add server configuration information"""
        config = status.get("config", {})
        server_type = config.get("server_type", "Minecraft")
        table.add_row("Server Type", server_type)

    @staticmethod
    def _add_performance_peaks_rows(table: Table, status: Dict[str, Any]) -> None:
        """Add performance peak information"""
        if status.get("running") and "peaks" in status:
            peaks = status["peaks"]
            table.add_row("", "")  # Separator
            table.add_row("Peak Memory", f"{peaks.get('peak_memory_mb', 0):.1f} MB")
            table.add_row("Peak CPU", f"{peaks.get('peak_cpu_percent', 0):.1f}%")

    @staticmethod
    def show_backups(backups: List[Dict[str, Any]]) -> None:
        """Display backup list in a comprehensive table"""
        if not backups:
            console.print("[yellow]📁 No backups found[/yellow]")
            return

        try:
            table = Table(title="📁 Available Backups", show_header=True, header_style="bold magenta")
            table.add_column("Name", style="cyan", no_wrap=True)
            table.add_column("Size", style="white", justify="right")
            table.add_column("Created", style="white")
            table.add_column("Age", style="dim")
            table.add_column("Status", style="white")

            for backup in backups:
                StatusDisplay._add_backup_row(table, backup)

            console.print(table)
            StatusDisplay._show_backup_summary(backups)

        except Exception as e:
            handle_error(e, "Failed to display backups")

    @staticmethod
    def _add_backup_row(table: Table, backup: Dict[str, Any]) -> None:
        """Add a single backup row to the table"""
        # Calculate age
        age_hours = backup.get("age_hours", 0)
        age_str = StatusDisplay._format_age(age_hours)

        # Status indicator
        is_valid = backup.get("valid", False)
        status_text = "✅ Valid" if is_valid else "❌ Invalid"

        table.add_row(
            backup["name"],
            f"{backup['size_mb']:.1f} MB",
            backup["created"].strftime("%Y-%m-%d %H:%M"),
            age_str,
            status_text
        )

    @staticmethod
    def _format_age(age_hours: float) -> str:
        """Format backup age in human readable format"""
        if age_hours < 1:
            return f"{age_hours * 60:.0f}m"
        elif age_hours < 24:
            return f"{age_hours:.1f}h"
        else:
            return f"{age_hours / 24:.1f}d"

    @staticmethod
    def _show_backup_summary(backups: List[Dict[str, Any]]) -> None:
        """Show backup summary statistics"""
        total_size = sum(b["size_mb"] for b in backups)
        valid_count = sum(1 for b in backups if b.get("valid", False))

        console.print(f"\n[dim]Total: {len(backups)} backups, {total_size:.1f} MB, {valid_count} valid[/dim]")

    @staticmethod
    def show_watchdog_status(status: Dict[str, Any]) -> None:
        """Display comprehensive watchdog status"""
        try:
            table = Table(title="🐕 Watchdog Status", show_header=True, header_style="bold yellow")
            table.add_column("Property", style="cyan")
            table.add_column("Value", style="white")

            StatusDisplay._add_watchdog_basic_status(table, status)
            StatusDisplay._add_watchdog_configuration(table, status)
            StatusDisplay._add_watchdog_statistics(table, status)

            console.print(table)

            # Show recent restart history if available
            restart_history = status.get("restart_history", [])
            if restart_history:
                StatusDisplay._show_restart_history(restart_history)

        except Exception as e:
            handle_error(e, "Failed to display watchdog status")

    @staticmethod
    def _add_watchdog_basic_status(table: Table, status: Dict[str, Any]) -> None:
        """Add basic watchdog status information"""
        watchdog_color = STATUS_COLORS["running" if status["running"] else "stopped"]
        watchdog_text = "🟢 Running" if status["running"] else "🔴 Stopped"
        table.add_row("Status", f"[{watchdog_color}]{watchdog_text}[/{watchdog_color}]")

        uptime = status.get("uptime")
        if uptime:
            uptime_str = format_uptime(uptime)
            table.add_row("Uptime", uptime_str)

    @staticmethod
    def _add_watchdog_configuration(table: Table, status: Dict[str, Any]) -> None:
        """Add watchdog configuration information"""
        config = status.get("config", {})

        table.add_row("Enabled", "✅ Yes" if config.get("enabled") else "❌ No")
        table.add_row("Check Interval", f"{config.get('interval', 0)}s")
        table.add_row("Auto Restart", "✅ Yes" if config.get("restart_on_crash") else "❌ No")
        table.add_row("Max Restarts", str(config.get("max_restarts", 0)))
        table.add_row("Cooldown", f"{config.get('restart_cooldown', 0)}s")

    @staticmethod
    def _add_watchdog_statistics(table: Table, status: Dict[str, Any]) -> None:
        """Add watchdog statistics"""
        table.add_row("", "")  # Separator
        table.add_row("Restart Count", str(status.get("restart_count", 0)))

        last_restart = status.get("last_restart")
        if last_restart:
            table.add_row("Last Restart", last_restart.strftime("%Y-%m-%d %H:%M:%S"))

        success_rate = status.get("restart_success_rate", 100)
        rate_color = StatusDisplay._get_success_rate_color(success_rate)
        table.add_row("Success Rate", f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]")

        # Monitoring stats
        monitoring_stats = status.get("monitoring_stats", {})
        if monitoring_stats:
            table.add_row("", "")  # Separator
            table.add_row("Total Checks", str(monitoring_stats.get("checks_performed", 0)))
            table.add_row("Restart Attempts", str(monitoring_stats.get("restarts_attempted", 0)))
            table.add_row("Successful Restarts", str(monitoring_stats.get("restarts_successful", 0)))

    @staticmethod
    def _show_restart_history(restart_history: List[Dict[str, Any]]) -> None:
        """Show recent restart history table"""
        if not restart_history:
            return

        console.print("\n")
        table = Table(title="📊 Recent Restart History", show_header=True, header_style="bold red")
        table.add_column("Time", style="white")
        table.add_column("Attempt #", style="yellow")
        table.add_column("Reason", style="cyan")

        # Show last 10 restarts
        for restart in restart_history[-MAX_RESTART_HISTORY:]:
            timestamp = restart.get("timestamp")

            if isinstance(timestamp, str):
                time_str = timestamp
            elif isinstance(timestamp, datetime):
                time_str = timestamp.strftime("%m-%d %H:%M:%S")

            table.add_row(
                time_str,
                str(restart.get("restart_number", "?")),
                restart.get("reason", "unknown")
            )

        console.print(table)

    @staticmethod
    def show_health_report(health_report: Dict[str, Any]) -> None:
        """Display comprehensive health report"""
        try:
            StatusDisplay._show_health_score_panel(health_report)
            StatusDisplay._show_health_issues(health_report)
            StatusDisplay._show_health_recommendations(health_report)
            StatusDisplay._show_health_summary_table(health_report)

        except Exception as e:
            handle_error(e, "Failed to display health report")

    @staticmethod
    def _show_health_score_panel(health_report: Dict[str, Any]) -> None:
        """Show health score panel"""
        score = health_report.get("health_score", 0)
        status = health_report.get("health_status", "unknown")

        score_color = StatusDisplay._get_health_score_color(score)

        health_panel = Panel.fit(
            f"[bold {score_color}]{score}/100 - {status.upper()}[/bold {score_color}]",
            title="🏥 Health Score",
            border_style=score_color
        )

        console.print(health_panel)

    @staticmethod
    def _get_health_score_color(score: int) -> str:
        """Get color for health score"""
        if score >= 80:
            return "green"
        elif score >= 60:
            return "yellow"
        else:
            return "red"

    @staticmethod
    def _show_health_issues(health_report: Dict[str, Any]) -> None:
        """Show health issues"""
        issues = health_report.get("issues", [])
        if issues:
            console.print("\n[bold red]🚨 Issues Detected:[/bold red]")
            for issue in issues:
                console.print(f"  • {issue}")

    @staticmethod
    def _show_health_recommendations(health_report: Dict[str, Any]) -> None:
        """Show health recommendations"""
        recommendations = health_report.get("recommendations", [])
        if recommendations:
            console.print("\n[bold cyan]💡 Recommendations:[/bold cyan]")
            for rec in recommendations:
                console.print(f"  • {rec}")

    @staticmethod
    def _show_health_summary_table(health_report: Dict[str, Any]) -> None:
        """Show health summary table"""
        console.print("\n")
        table = Table(title="📈 Health Summary", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        score = health_report.get("health_score", 0)
        status = health_report.get("health_status", "unknown")
        score_color = StatusDisplay._get_health_score_color(score)

        table.add_row("Health Score", f"[{score_color}]{score}/100[/{score_color}]")
        table.add_row("Status", f"[{score_color}]{status.title()}[/{score_color}]")

        uptime = health_report.get("uptime")
        if uptime:
            uptime_str = format_uptime(uptime)
            table.add_row("Monitor Uptime", uptime_str)

        monitoring_enabled = health_report.get("monitoring_enabled", False)
        table.add_row("Monitoring", "✅ Enabled" if monitoring_enabled else "❌ Disabled")

        success_rate = health_report.get("restart_success_rate", 100)
        rate_color = StatusDisplay._get_success_rate_color(success_rate)
        table.add_row("Restart Success", f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]")

        console.print(table)

    @staticmethod
    def show_performance_chart(stats_history: List[Dict[str, Any]], width: int = CHART_WIDTH) -> None:
        """Show ASCII performance charts for memory and CPU usage"""
        if not stats_history or len(stats_history) < 2:
            console.print("[yellow]Not enough data for performance chart[/yellow]")
            return

        try:
            console.print("\n[bold]📊 Performance Trends (Last Hour)[/bold]")

            memory_values = [s.get("memory_mb", 0) for s in stats_history]
            cpu_values = [s.get("cpu_percent", 0) for s in stats_history]

            memory_chart = StatusDisplay._create_ascii_chart(memory_values, "Memory (MB)", width)
            cpu_chart = StatusDisplay._create_ascii_chart(cpu_values, "CPU (%)", width)

            console.print(Panel(memory_chart, title="💾 Memory Usage"))
            console.print(Panel(cpu_chart, title="🖥️  CPU Usage"))

        except Exception as e:
            handle_error(e, "Failed to create performance chart")

    @staticmethod
    def _create_ascii_chart(values: List[float], title: str, width: int = CHART_WIDTH) -> str:
        """Create a simple ASCII chart from values"""
        if not values:
            return "No data available"

        max_val = max(values) if values else 0
        min_val = min(values) if values else 0

        if max_val == min_val:
            return f"{title}: Constant at {max_val:.1f}"

        chart_lines = [f"Max: {max_val:.1f}"]

        # Show last 20 data points
        recent_values = values[-20:] if len(values) > 20 else values

        for i, value in enumerate(recent_values):
            # Normalize value to chart width
            if max_val > min_val:
                normalized = int(((value - min_val) / (max_val - min_val)) * (width - 1))
            else:
                normalized = 0

            # Create bar representation
            bar = "█" * normalized + "░" * (width - normalized - len(f"{value:.1f}"))
            chart_lines.append(f"{bar} {value:.1f}")

        chart_lines.append(f"Min: {min_val:.1f}")

        return "\n".join(chart_lines)


class PerformanceDisplay:
    """Specialized display for performance monitoring"""

    @staticmethod
    def show_performance_dashboard(server, stats_history: List[Dict[str, Any]]) -> None:
        """Show comprehensive performance dashboard"""
        try:
            console.print(Panel.fit("📊 Performance Dashboard", style="bold cyan"))

            current_status = server.get_status()

            if current_status.get("running"):
                PerformanceDisplay._show_current_performance(current_status)
                PerformanceDisplay._show_performance_trends(stats_history)
                PerformanceDisplay._show_performance_alerts(current_status)
            else:
                console.print("[yellow]Server is not running - no performance data available[/yellow]")

        except Exception as e:
            handle_error(e, "Failed to display performance dashboard")

    @staticmethod
    def _show_current_performance(status: Dict[str, Any]) -> None:
        """Show current performance metrics"""
        table = Table(title="Current Performance", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Current", style="white")
        table.add_column("Average (5m)", style="dim")
        table.add_column("Peak (1h)", style="yellow")

        # Get performance data
        current = {
            "memory_mb": status.get("memory_usage_mb", 0),
            "memory_percent": status.get("memory_percent", 0),
            "cpu_percent": status.get("cpu_percent", 0),
            "threads": status.get("threads", 0)
        }

        averages = status.get("averages", {})
        peaks = status.get("peaks", {})

        # Add performance rows
        table.add_row(
            "Memory Usage",
            f"{current['memory_mb']:.1f} MB ({current['memory_percent']:.1f}%)",
            f"{averages.get('avg_memory_mb', 0):.1f} MB",
            f"{peaks.get('peak_memory_mb', 0):.1f} MB"
        )

        table.add_row(
            "CPU Usage",
            f"{current['cpu_percent']:.1f}%",
            f"{averages.get('avg_cpu_percent', 0):.1f}%",
            f"{peaks.get('peak_cpu_percent', 0):.1f}%"
        )

        table.add_row(
            "Threads",
            str(current['threads']),
            "-",
            "-"
        )

        console.print(table)

    @staticmethod
    def _show_performance_trends(stats_history: List[Dict[str, Any]]) -> None:
        """Show performance trends"""
        if stats_history:
            StatusDisplay.show_performance_chart(stats_history)

    @staticmethod
    def _show_performance_alerts(status: Dict[str, Any]) -> None:
        """Show performance alerts and warnings"""
        alerts = []

        memory_percent = status.get("memory_percent", 0)
        cpu_percent = status.get("cpu_percent", 0)

        if memory_percent > 90:
            alerts.append(("🚨", "Critical memory usage", f"{memory_percent:.1f}%", "red"))
        elif memory_percent > 80:
            alerts.append(("⚠️", "High memory usage", f"{memory_percent:.1f}%", "yellow"))

        if cpu_percent > 85:
            alerts.append(("🚨", "Critical CPU usage", f"{cpu_percent:.1f}%", "red"))
        elif cpu_percent > 70:
            alerts.append(("⚠️", "High CPU usage", f"{cpu_percent:.1f}%", "yellow"))

        if alerts:
            console.print("\n[bold]Performance Alerts[/bold]")
            for icon, message, value, color in alerts:
                console.print(f"  {icon} [{color}]{message}: {value}[/{color}]")
