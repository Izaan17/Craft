"""
Watchdog monitoring and auto-restart for Craft Minecraft Server Manager
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any

from rich.console import Console

from backup import BackupManager

console = Console()

class Watchdog:
    """Enhanced server monitoring and auto-restart"""

    def __init__(self, server, backup_manager: BackupManager):
        self.server = server
        self.backup_manager = backup_manager
        self.config = server.config
        self.running = False
        self.thread = None
        self.restart_count = 0
        self.last_restart = 0
        self.restart_history = []
        self.monitoring_stats = {
            "checks_performed": 0,
            "restarts_attempted": 0,
            "restarts_successful": 0,
            "start_time": None
        }

    def start(self):
        """Start the watchdog"""
        if not self.config.get("watchdog_enabled"):
            console.print("[yellow]⚠️  Watchdog is disabled in config[/yellow]")
            return False

        if self.running:
            console.print("[yellow]⚠️  Watchdog is already running[/yellow]")
            return False

        self.running = True
        self.monitoring_stats["start_time"] = datetime.now()
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

        # Start auto-backup
        self.backup_manager.start_auto_backup()

        interval = self.config.get("watchdog_interval")
        console.print(f"[green]🐕 Watchdog started (checking every {interval}s)[/green]")
        return True

    def stop(self):
        """Stop the watchdog"""
        if not self.running:
            console.print("[yellow]⚠️  Watchdog is not running[/yellow]")
            return

        self.running = False
        self.backup_manager.stop_auto_backup()

        if self.thread:
            self.thread.join(timeout=5)

        uptime = datetime.now() - self.monitoring_stats["start_time"] if self.monitoring_stats["start_time"] else timedelta(0)
        console.print(f"[yellow]🐕 Watchdog stopped (ran for {str(uptime).split('.')[0]})[/yellow]")

    def _monitor_loop(self):
        """Main monitoring loop"""
        interval = self.config.get("watchdog_interval")

        console.print(f"[cyan]🔍 Monitoring started (interval: {interval}s)[/cyan]")

        while self.running:
            try:
                self.monitoring_stats["checks_performed"] += 1

                # Check server status
                if not self.server.is_running():
                    self._handle_server_down()
                else:
                    # Server is running, reset restart count after cooldown period
                    if time.time() - self.last_restart > self.config.get("restart_cooldown"):
                        if self.restart_count > 0:
                            console.print(f"[green]✅ Server stable - reset restart count (was {self.restart_count})[/green]")
                            self.restart_count = 0

                # Perform health checks
                self._perform_health_checks()

                time.sleep(interval)

            except Exception as e:
                console.print(f"[red]🐕 Watchdog error: {e}[/red]")
                time.sleep(10)  # Wait before retrying on error

    def _handle_server_down(self):
        """Handle server crash/shutdown"""
        if not self.config.get("restart_on_crash"):
            console.print("[yellow]⚠️  Server is down but auto-restart is disabled[/yellow]")
            return

        current_time = time.time()
        max_restarts = self.config.get("max_restarts")
        cooldown = self.config.get("restart_cooldown")

        # Check restart limits
        if self.restart_count >= max_restarts:
            time_since_last = current_time - self.last_restart
            if time_since_last < cooldown:
                remaining = cooldown - time_since_last
                console.print(f"[red]🚫 Too many restarts ({self.restart_count}/{max_restarts}), waiting {remaining:.0f}s...[/red]")
                time.sleep(min(remaining, 60))  # Sleep max 60s in monitoring loop
                return
            else:
                # Reset restart count after cooldown
                console.print(f"[cyan]🔄 Cooldown period ended, resetting restart count[/cyan]")
                self.restart_count = 0

        self.monitoring_stats["restarts_attempted"] += 1
        console.print(f"[yellow]🔄 Server down! Attempting restart #{self.restart_count + 1}/{max_restarts}...[/yellow]")

        # Create backup before restart if configured
        if self.config.get("backup_on_stop"):
            try:
                console.print("[cyan]💾 Creating backup before restart...[/cyan]")
                self.backup_manager.create_backup("pre_restart")
            except Exception as e:
                console.print(f"[red]❌ Backup failed: {e}[/red]")

        # Attempt restart
        if self.server.start():
            self.restart_count += 1
            self.last_restart = current_time
            self.monitoring_stats["restarts_successful"] += 1

            # Log restart
            restart_entry = {
                "timestamp": datetime.now(),
                "restart_number": self.restart_count,
                "reason": "server_down"
            }
            self.restart_history.append(restart_entry)

            # Keep only last 20 restarts
            if len(self.restart_history) > 20:
                self.restart_history = self.restart_history[-20:]

            console.print(f"[green]✅ Server restarted successfully (attempt #{self.restart_count})[/green]")
        else:
            console.print("[red]❌ Failed to restart server[/red]")

    def _perform_health_checks(self):
        """Perform additional health checks on running server"""
        if not self.server.is_running():
            return

        try:
            # Check server responsiveness
            port_responsive = self.server._is_port_open(self.config.get("server_port"))
            if not port_responsive:
                console.print("[yellow]⚠️  Server port not responding[/yellow]")
                return

            # Get current stats for health monitoring
            stats = self.server.stats.get_current_stats()

            # Memory usage check
            memory_percent = stats.get("memory_percent", 0)
            if memory_percent > 95:
                console.print(f"[red]🚨 Critical memory usage: {memory_percent:.1f}%[/red]")
            elif memory_percent > 85:
                console.print(f"[yellow]⚠️  High memory usage: {memory_percent:.1f}%[/yellow]")

            # CPU usage check
            cpu_percent = stats.get("cpu_percent", 0)
            if cpu_percent > 90:
                console.print(f"[red]🚨 Critical CPU usage: {cpu_percent:.1f}%[/red]")

            # Thread count check (high thread count might indicate issues)
            thread_count = stats.get("threads", 0)
            if thread_count > 200:
                console.print(f"[yellow]⚠️  High thread count: {thread_count}[/yellow]")

        except Exception as e:
            console.print(f"[red]❌ Health check error: {e}[/red]")

    def force_restart(self, reason: str = "manual") -> bool:
        """Force a server restart outside of normal monitoring"""
        if not self.server.is_running():
            console.print("[yellow]⚠️  Server is not running[/yellow]")
            return self.server.start()

        console.print(f"[cyan]🔄 Force restart requested (reason: {reason})[/cyan]")

        # Create backup if configured
        if self.config.get("backup_on_stop"):
            try:
                console.print("[cyan]💾 Creating backup before restart...[/cyan]")
                self.backup_manager.create_backup("manual_restart")
            except Exception as e:
                console.print(f"[red]❌ Backup failed: {e}[/red]")

        # Restart server
        if self.server.restart():
            # Log the manual restart
            restart_entry = {
                "timestamp": datetime.now(),
                "restart_number": self.restart_count + 1,
                "reason": reason
            }
            self.restart_history.append(restart_entry)

            console.print("[green]✅ Force restart completed[/green]")
            return True
        else:
            console.print("[red]❌ Force restart failed[/red]")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive watchdog status"""
        uptime = None
        if self.monitoring_stats["start_time"]:
            uptime = datetime.now() - self.monitoring_stats["start_time"]

        status = {
            "running": self.running,
            "restart_count": self.restart_count,
            "last_restart": datetime.fromtimestamp(self.last_restart) if self.last_restart else None,
            "restart_history": self.restart_history[-10:],  # Last 10 restarts
            "auto_backup_running": self.backup_manager.auto_backup_running,
            "uptime": uptime,
            "monitoring_stats": self.monitoring_stats.copy(),
            "config": {
                "enabled": self.config.get("watchdog_enabled"),
                "interval": self.config.get("watchdog_interval"),
                "restart_on_crash": self.config.get("restart_on_crash"),
                "max_restarts": self.config.get("max_restarts"),
                "restart_cooldown": self.config.get("restart_cooldown")
            }
        }

        # Calculate success rate
        if self.monitoring_stats["restarts_attempted"] > 0:
            success_rate = (self.monitoring_stats["restarts_successful"] /
                            self.monitoring_stats["restarts_attempted"]) * 100
            status["restart_success_rate"] = success_rate
        else:
            status["restart_success_rate"] = 100

        return status

    def get_health_report(self) -> Dict[str, Any]:
        """Get a detailed health report"""
        status = self.get_status()
        server_stats = self.server.get_status()

        # Calculate health score
        health_score = 100
        issues = []

        # Check restart frequency
        if self.restart_count > 3:
            health_score -= 20
            issues.append(f"High restart count: {self.restart_count}")

        # Check if server is running
        if not server_stats.get("running", False):
            health_score -= 30
            issues.append("Server is not running")

        # Check resource usage
        if server_stats.get("running", False):
            memory_percent = server_stats.get("memory_percent", 0)
            cpu_percent = server_stats.get("cpu_percent", 0)

            if memory_percent > 90:
                health_score -= 15
                issues.append(f"High memory usage: {memory_percent:.1f}%")
            elif memory_percent > 80:
                health_score -= 5
                issues.append(f"Elevated memory usage: {memory_percent:.1f}%")

            if cpu_percent > 85:
                health_score -= 10
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")

        # Check backup system
        if not self.backup_manager.auto_backup_running and self.config.get("auto_backup"):
            health_score -= 10
            issues.append("Auto-backup not running")

        health_score = max(0, health_score)

        # Determine health status
        if health_score >= 90:
            health_status = "excellent"
        elif health_score >= 75:
            health_status = "good"
        elif health_score >= 50:
            health_status = "fair"
        elif health_score >= 25:
            health_status = "poor"
        else:
            health_status = "critical"

        return {
            "health_score": health_score,
            "health_status": health_status,
            "issues": issues,
            "uptime": status["uptime"],
            "monitoring_enabled": status["running"],
            "restart_success_rate": status["restart_success_rate"],
            "last_check": datetime.now(),
            "recommendations": self._get_recommendations(health_score, issues)
        }

    def _get_recommendations(self, health_score: int, issues: List[str]) -> List[str]:
        """Get recommendations based on health status"""
        recommendations = []

        if health_score < 50:
            recommendations.append("Consider reviewing server configuration")
            recommendations.append("Check server logs for errors")

        if "High memory usage" in str(issues):
            recommendations.append("Increase server memory allocation")
            recommendations.append("Check for memory leaks")

        if "High CPU usage" in str(issues):
            recommendations.append("Optimize server performance settings")
            recommendations.append("Consider upgrading hardware")

        if "High restart count" in str(issues):
            recommendations.append("Investigate cause of frequent crashes")
            recommendations.append("Review recent server changes")

        if "Auto-backup not running" in str(issues):
            recommendations.append("Enable auto-backup in configuration")
            recommendations.append("Manually create backup")

        if not recommendations:
            recommendations.append("Server health is good")
            recommendations.append("Continue regular monitoring")

        return recommendations

    def export_monitoring_data(self, filename: str = None) -> str:
        """Export monitoring data and logs"""
        if not filename:
            filename = f"watchdog_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        import json

        export_data = {
            "export_time": datetime.now().isoformat(),
            "watchdog_status": self.get_status(),
            "health_report": self.get_health_report(),
            "server_status": self.server.get_status(),
            "backup_stats": self.backup_manager.get_backup_stats()
        }

        # Convert datetime objects to strings for JSON
        def json_serial(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, timedelta):
                return str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")

        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=json_serial)

        console.print(f"[green]✅ Monitoring data exported to: {filename}[/green]")
        return filename