"""
Status display and UI for Craft Minecraft Server Manager
"""

import time
from datetime import datetime
from typing import Dict, List, Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

console = Console()


class StatusDisplay:
    """Enhanced status display with live updates"""

    @staticmethod
    def show_debug_status(server):
        """Show detailed debug information"""
        status = server.get_status()
        debug_info = status.get("debug_info", {})

        console.print(Panel.fit("🔍 Debug Information", style="bold yellow"))

        # Main status
        running = status["running"]
        status_color = "green" if running else "red"
        status_text = "🟢 Running" if running else "🔴 Stopped"
        console.print(f"Server Status: [{status_color}]{status_text}[/{status_color}]\n")

        # Debug table
        debug_table = Table(title="Debug Details", show_header=True)
        debug_table.add_column("Component", style="cyan", no_wrap=True)
        debug_table.add_column("Value", style="white")
        debug_table.add_column("Status", style="white")

        # PID information
        saved_pid = debug_info.get("saved_pid")
        debug_table.add_row("Saved PID", str(saved_pid) if saved_pid else "None",
                            "✅" if saved_pid else "❌")

        debug_table.add_row("PID File Exists", str(debug_info.get("pid_file_exists", False)),
                            "✅" if debug_info.get("pid_file_exists") else "❌")

        if saved_pid:
            debug_table.add_row("PID Exists in System", str(debug_info.get("pid_exists", False)),
                                "✅" if debug_info.get("pid_exists") else "❌")

            debug_table.add_row("Process Running", str(debug_info.get("process_running", False)),
                                "✅" if debug_info.get("process_running") else "❌")

            debug_table.add_row("Process Name", debug_info.get("process_name", "Unknown"), "")
            debug_table.add_row("Working Directory", debug_info.get("process_cwd", "Unknown"), "")

        # Direct process reference
        direct_poll = debug_info.get("direct_process_poll")
        if debug_info.get("direct_process") is not None:
            if direct_poll is not None:
                debug_table.add_row("Direct Process", f"Poll result: {direct_poll}",
                                    "❌ (terminated)" if direct_poll is not None else "✅")
            else:
                debug_table.add_row("Direct Process", "Running", "✅")

            # Show stdin capability
            has_stdin = debug_info.get("has_stdin", False)
            debug_table.add_row("STDIN Available", str(has_stdin),
                                "✅" if has_stdin else "❌")
        else:
            debug_table.add_row("Direct Process", "No reference", "❌")

        # Command capability
        can_commands = debug_info.get("can_send_commands", False)
        debug_table.add_row("Can Send Commands", str(can_commands),
                            "✅" if can_commands else "❌")

        # Java processes
        java_count = debug_info.get("java_processes_found", 0)
        java_pids = debug_info.get("java_process_pids", [])
        debug_table.add_row("Java Processes", f"{java_count} found",
                            "✅" if java_count > 0 else "❌")

        if java_pids:
            debug_table.add_row("Java PIDs", ", ".join(map(str, java_pids)), "")

        # Show any errors
        if "process_error" in debug_info:
            debug_table.add_row("Process Error", debug_info["process_error"], "❌")

        if "java_search_error" in debug_info:
            debug_table.add_row("Java Search Error", debug_info["java_search_error"], "❌")

        console.print(debug_table)

        # Suggestions
        console.print("\n[bold cyan]💡 Troubleshooting Tips:[/bold cyan]")

        if not running:
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
        else:
            if status.get("uptime"):
                uptime_str = str(status["uptime"]).split('.')[0]
                console.print(f"  ✅ Server running normally (uptime: {uptime_str})")

            # Command capability warnings
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
    def show_status(server, watchdog, live_update: bool = False):
        """Show comprehensive server status"""

        def create_status_display():
            layout = Layout()

            # Split into header, main content, and footer
            layout.split_column(
                Layout(name="header", size=3),
                Layout(name="main"),
                Layout(name="footer", size=3)
            )

            # Split main content into left and right panels
            layout["main"].split_row(
                Layout(name="left"),
                Layout(name="right")
            )

            # Split right panel into top and bottom
            layout["right"].split_column(
                Layout(name="right_top"),
                Layout(name="right_bottom")
            )

            # Get current status data
            server_status = server.get_status()
            watchdog_status = watchdog.get_status()

            # Header
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            layout["header"].update(
                Panel.fit(
                    f"🎮 Craft Server Manager - {current_time}",
                    style="bold cyan"
                )
            )

            # Main server status table
            status_table = StatusDisplay._create_server_status_table(server_status)
            layout["left"].update(Panel(status_table, title="🖥️  Server Status",
                                        border_style="green" if server_status["running"] else "red"))

            # Monitoring status
            monitoring_table = StatusDisplay._create_monitoring_table(watchdog_status)
            layout["right_top"].update(Panel(monitoring_table, title="🐕 Monitoring", border_style="yellow"))

            # System info
            system_table = StatusDisplay._create_system_table(server_status)
            layout["right_bottom"].update(Panel(system_table, title="⚙️  System", border_style="blue"))

            # Footer
            footer_text = "Press Ctrl+C to exit"
            if live_update:
                footer_text += " | 🔄 Live updating..."

            layout["footer"].update(
                Panel.fit(footer_text, style="dim")
            )

            return layout

        if live_update:
            with Live(create_status_display(), refresh_per_second=1, console=console) as live:
                try:
                    while True:
                        time.sleep(1)
                        live.update(create_status_display())
                except KeyboardInterrupt:
                    console.print("\n[yellow]Live update stopped[/yellow]")
        else:
            console.print(create_status_display())

    @staticmethod
    def _create_server_status_table(status: Dict[str, Any]) -> Table:
        """Create server status table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Server status
        if status["running"]:
            status_text = "[green]🟢 Running[/green]"
            table.add_row("Status", status_text)
            table.add_row("PID", str(status["pid"]))

            # Command capability
            can_command = status.get("can_send_commands", False)
            command_text = "[green]✅ Available[/green]" if can_command else "[yellow]⚠️  Limited[/yellow]"
            table.add_row("Commands", command_text)

            if not can_command:
                table.add_row("", "[dim]Use 'craft restart' to enable[/dim]")

            # Uptime
            uptime_str = str(status["uptime"]).split('.')[0] if status["uptime"] else "Unknown"
            table.add_row("Uptime", uptime_str)

            # Memory
            memory_mb = status["memory_usage_mb"]
            memory_pct = status["memory_percent"]
            memory_color = "green" if memory_pct < 70 else "yellow" if memory_pct < 90 else "red"
            table.add_row("Memory", f"[{memory_color}]{memory_mb:.1f} MB ({memory_pct:.1f}%)[/{memory_color}]")

            # CPU
            cpu_pct = status["cpu_percent"]
            cpu_color = "green" if cpu_pct < 50 else "yellow" if cpu_pct < 80 else "red"
            table.add_row("CPU", f"[{cpu_color}]{cpu_pct:.1f}%[/{cpu_color}]")

            # Other stats
            table.add_row("Threads", str(status["threads"]))
            table.add_row("Connections", str(status["connections"]))

            # Averages
            if "averages" in status:
                avg = status["averages"]
                table.add_row("", "")  # Separator
                table.add_row("Avg Memory (5m)", f"{avg['avg_memory_mb']:.1f} MB")
                table.add_row("Avg CPU (5m)", f"{avg['avg_cpu_percent']:.1f}%")
        else:
            table.add_row("Status", "[red]🔴 Stopped[/red]")

        # Configuration info
        config = status.get("config", {})
        table.add_row("", "")  # Separator
        table.add_row("JAR", config.get("jar_name", "Unknown"))
        table.add_row("Max Memory", config.get("memory_max", "Unknown"))
        table.add_row("Server Type", config.get("server_type", "Minecraft"))

        return table

    @staticmethod
    def _create_monitoring_table(watchdog_status: Dict[str, Any]) -> Table:
        """Create monitoring status table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # Watchdog status with more detail
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
        if watchdog_status["uptime"] and running:
            uptime_str = str(watchdog_status["uptime"]).split('.')[0]
            table.add_row("Monitor Uptime", uptime_str)

        # Auto-backup
        if watchdog_status["auto_backup_running"]:
            backup_text = "[green]🟢 Active[/green]"
        else:
            backup_text = "[red]🔴 Inactive[/red]"
        table.add_row("Auto Backup", backup_text)

        # Restart info
        restart_count = watchdog_status["restart_count"]
        if restart_count > 0:
            restart_color = "yellow" if restart_count < 3 else "red"
            table.add_row("Restarts", f"[{restart_color}]{restart_count}[/{restart_color}]")

            if watchdog_status["last_restart"]:
                last_restart = watchdog_status["last_restart"].strftime("%H:%M:%S")
                table.add_row("Last Restart", last_restart)
        else:
            table.add_row("Restarts", "[green]0[/green]")

        # Success rate
        success_rate = watchdog_status.get("restart_success_rate", 100)
        if success_rate < 80:
            rate_color = "red"
        elif success_rate < 95:
            rate_color = "yellow"
        else:
            rate_color = "green"
        table.add_row("Success Rate", f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]")

        # Monitoring stats
        if "monitoring_stats" in watchdog_status:
            stats = watchdog_status["monitoring_stats"]
            table.add_row("", "")  # Separator
            table.add_row("Checks", str(stats.get("checks_performed", 0)))

        return table

    @staticmethod
    def _create_system_table(status: Dict[str, Any]) -> Table:
        """Create system information table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        # World info if available
        if "world_info" in status:
            world = status["world_info"]
            if world.get("exists", False):
                table.add_row("World Size", f"{world.get('size_mb', 0):.1f} MB")

        # Server type
        config = status.get("config", {})
        server_type = config.get("server_type", "Minecraft")
        table.add_row("Server Type", server_type)

        # Performance indicators
        if status["running"] and "peaks" in status:
            peaks = status["peaks"]
            table.add_row("", "")  # Separator
            table.add_row("Peak Memory", f"{peaks['peak_memory_mb']:.1f} MB")
            table.add_row("Peak CPU", f"{peaks['peak_cpu_percent']:.1f}%")

        return table

    @staticmethod
    def show_backups(backups: List[Dict[str, Any]]):
        """Display backup list in a nice table"""
        if not backups:
            console.print("[yellow]📁 No backups found[/yellow]")
            return

        table = Table(title="📁 Available Backups", show_header=True, header_style="bold magenta")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Size", style="white", justify="right")
        table.add_column("Created", style="white")
        table.add_column("Age", style="dim")

        for backup in backups:
            # Calculate age
            age = backup.get("age_hours", 0)
            if age < 1:
                age_str = f"{age * 60:.0f}m"
            elif age < 24:
                age_str = f"{age:.1f}h"
            else:
                age_str = f"{age / 24:.1f}d"

            table.add_row(
                backup["name"],
                f"{backup['size_mb']:.1f} MB",
                backup["created"].strftime("%Y-%m-%d %H:%M"),
                age_str
            )

        console.print(table)

    @staticmethod
    def show_watchdog_status(status: Dict[str, Any]):
        """Display detailed watchdog status"""
        table = Table(title="🐕 Watchdog Status", show_header=True, header_style="bold yellow")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")

        # Basic status
        watchdog_color = "green" if status["running"] else "red"
        watchdog_text = "🟢 Running" if status["running"] else "🔴 Stopped"
        table.add_row("Status", f"[{watchdog_color}]{watchdog_text}[/{watchdog_color}]")

        # Configuration
        config = status.get("config", {})
        table.add_row("Enabled", "✅ Yes" if config.get("enabled") else "❌ No")
        table.add_row("Check Interval", f"{config.get('interval', 0)}s")
        table.add_row("Auto Restart", "✅ Yes" if config.get("restart_on_crash") else "❌ No")
        table.add_row("Max Restarts", str(config.get("max_restarts", 0)))
        table.add_row("Cooldown", f"{config.get('restart_cooldown', 0)}s")

        # Statistics
        table.add_row("", "")  # Separator
        table.add_row("Restart Count", str(status["restart_count"]))

        if status["last_restart"]:
            table.add_row("Last Restart", status["last_restart"].strftime("%Y-%m-%d %H:%M:%S"))

        success_rate = status.get("restart_success_rate", 100)
        rate_color = "green" if success_rate >= 95 else "yellow" if success_rate >= 80 else "red"
        table.add_row("Success Rate", f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]")

        if status["uptime"]:
            uptime_str = str(status["uptime"]).split('.')[0]
            table.add_row("Uptime", uptime_str)

        # Monitoring stats
        if "monitoring_stats" in status:
            stats = status["monitoring_stats"]
            table.add_row("", "")  # Separator
            table.add_row("Total Checks", str(stats.get("checks_performed", 0)))
            table.add_row("Restart Attempts", str(stats.get("restarts_attempted", 0)))
            table.add_row("Successful Restarts", str(stats.get("restarts_successful", 0)))

        console.print(table)

        # Show recent restart history
        if status["restart_history"]:
            StatusDisplay._show_restart_history(status["restart_history"])

    @staticmethod
    def _show_restart_history(restart_history: List[Dict[str, Any]]):
        """Show restart history table"""
        if not restart_history:
            return

        console.print("\n")
        table = Table(title="📊 Recent Restart History", show_header=True, header_style="bold red")
        table.add_column("Time", style="white")
        table.add_column("Attempt #", style="yellow")
        table.add_column("Reason", style="cyan")

        for restart in restart_history[-10:]:  # Show last 10
            timestamp = restart["timestamp"]
            if isinstance(timestamp, str):
                time_str = timestamp
            else:
                time_str = timestamp.strftime("%m-%d %H:%M:%S")

            table.add_row(
                time_str,
                str(restart["restart_number"]),
                restart.get("reason", "unknown")
            )

        console.print(table)

    @staticmethod
    def show_health_report(health_report: Dict[str, Any]):
        """Display health report"""
        # Health score panel
        score = health_report["health_score"]
        status = health_report["health_status"]

        score_color = "green" if score >= 80 else "yellow" if score >= 60 else "red"

        health_panel = Panel.fit(
            f"[bold {score_color}]{score}/100 - {status.upper()}[/bold {score_color}]",
            title="🏥 Health Score",
            border_style=score_color
        )

        console.print(health_panel)

        # Issues and recommendations
        if health_report["issues"]:
            console.print("\n[bold red]🚨 Issues Detected:[/bold red]")
            for issue in health_report["issues"]:
                console.print(f"  • {issue}")

        if health_report["recommendations"]:
            console.print("\n[bold cyan]💡 Recommendations:[/bold cyan]")
            for rec in health_report["recommendations"]:
                console.print(f"  • {rec}")

        # Summary table
        console.print("\n")
        table = Table(title="📈 Health Summary", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Health Score", f"[{score_color}]{score}/100[/{score_color}]")
        table.add_row("Status", f"[{score_color}]{status.title()}[/{score_color}]")

        if health_report["uptime"]:
            uptime_str = str(health_report["uptime"]).split('.')[0]
            table.add_row("Monitor Uptime", uptime_str)

        table.add_row("Monitoring", "✅ Enabled" if health_report["monitoring_enabled"] else "❌ Disabled")

        success_rate = health_report["restart_success_rate"]
        rate_color = "green" if success_rate >= 95 else "yellow" if success_rate >= 80 else "red"
        table.add_row("Restart Success", f"[{rate_color}]{success_rate:.1f}%[/{rate_color}]")

        console.print(table)

    @staticmethod
    def show_performance_chart(stats_history: List[Dict[str, Any]], width: int = 60):
        """Show a simple ASCII performance chart"""
        if not stats_history or len(stats_history) < 2:
            console.print("[yellow]Not enough data for performance chart[/yellow]")
            return

        # Memory usage chart
        memory_values = [s["memory_mb"] for s in stats_history]
        cpu_values = [s["cpu_percent"] for s in stats_history]

        console.print("\n[bold]📊 Performance Trends (Last Hour)[/bold]")

        # Simple text-based chart
        memory_chart = StatusDisplay._create_ascii_chart(memory_values, "Memory (MB)", width)
        cpu_chart = StatusDisplay._create_ascii_chart(cpu_values, "CPU (%)", width)

        console.print(Panel(memory_chart, title="💾 Memory Usage"))
        console.print(Panel(cpu_chart, title="🖥️  CPU Usage"))

    @staticmethod
    def _create_ascii_chart(values: List[float], title: str, width: int = 60) -> str:
        """Create a simple ASCII chart"""
        if not values:
            return "No data available"

        max_val = max(values)
        min_val = min(values)

        if max_val == min_val:
            return f"{title}: Constant at {max_val:.1f}"

        # Normalize values to chart width
        normalized = []
        for val in values:
            if max_val > min_val:
                norm = int(((val - min_val) / (max_val - min_val)) * (width - 1))
            else:
                norm = 0
            normalized.append(norm)

        # Create chart
        chart_lines = [f"Max: {max_val:.1f}"]

        # Add scale

        # Create bars
        for i, norm_val in enumerate(normalized[-20:]):  # Show last 20 points
            bar = "█" * norm_val + "░" * (width - norm_val - len(str(values[i])))
            chart_lines.append(f"{bar} {values[i]:.1f}")

        chart_lines.append(f"Min: {min_val:.1f}")

        return "\n".join(chart_lines)
