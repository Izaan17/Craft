"""
Statistics collection and monitoring for Craft Minecraft Server Manager
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any

import psutil


class ServerStats:
    """Collects and manages server statistics"""

    def __init__(self, max_history: int = 100):
        self.start_time = None
        self.process = None
        self.stats_history = []
        self.max_history = max_history
        self._last_cpu_times = None

    def set_process(self, process: psutil.Process):
        """Set the server process for monitoring"""
        self.process = process
        self.start_time = datetime.fromtimestamp(process.create_time())
        self._last_cpu_times = None

    def clear_process(self):
        """Clear the current process"""
        self.process = None
        self.start_time = None
        self._last_cpu_times = None

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current server statistics"""
        if not self.process or not self._is_process_running():
            return self._get_offline_stats()

        try:
            # Memory information
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()

            # CPU information
            cpu_percent = self.process.cpu_percent()

            # Process information
            num_threads = self.process.num_threads()

            # Connection information
            try:
                connections = len(self.process.connections())
                open_files = len(self.process.open_files())
            except (psutil.AccessDenied, OSError):
                connections = 0
                open_files = 0

            # Calculate uptime
            uptime = datetime.now() - self.start_time if self.start_time else timedelta(0)

            stats = {
                "running": True,
                "pid": self.process.pid,
                "uptime": uptime,
                "memory_usage_mb": memory_info.rss / 1024 / 1024,
                "memory_percent": memory_percent,
                "cpu_percent": cpu_percent,
                "threads": num_threads,
                "open_files": open_files,
                "connections": connections,
                "start_time": self.start_time,
                "timestamp": datetime.now()
            }

            # Add to history
            self._add_to_history(stats)

            return stats

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.clear_process()
            return self._get_offline_stats()

    def _is_process_running(self) -> bool:
        """Check if the tracked process is still running"""
        try:
            return self.process and self.process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    @staticmethod
    def _get_offline_stats() -> Dict[str, Any]:
        """Get stats when server is offline"""
        return {
            "running": False,
            "pid": None,
            "uptime": timedelta(0),
            "memory_usage_mb": 0,
            "memory_percent": 0,
            "cpu_percent": 0,
            "threads": 0,
            "open_files": 0,
            "connections": 0,
            "start_time": None,
            "timestamp": datetime.now()
        }

    def _add_to_history(self, stats: Dict[str, Any]):
        """Add stats to historical data"""
        history_entry = {
            "timestamp": stats["timestamp"],
            "memory_mb": stats["memory_usage_mb"],
            "cpu_percent": stats["cpu_percent"],
            "connections": stats["connections"]
        }

        self.stats_history.append(history_entry)

        # Keep only max_history entries
        if len(self.stats_history) > self.max_history:
            self.stats_history = self.stats_history[-self.max_history:]

    def get_average_stats(self, minutes: int = 5) -> Dict[str, float]:
        """Get average statistics over time period"""
        if not self.stats_history:
            return {"avg_memory_mb": 0, "avg_cpu_percent": 0, "avg_connections": 0}

        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_stats = [s for s in self.stats_history if s["timestamp"] > cutoff_time]

        if not recent_stats:
            # If no recent stats, use the last available data
            recent_stats = self.stats_history[-1:]

        return {
            "avg_memory_mb": sum(s["memory_mb"] for s in recent_stats) / len(recent_stats),
            "avg_cpu_percent": sum(s["cpu_percent"] for s in recent_stats) / len(recent_stats),
            "avg_connections": sum(s["connections"] for s in recent_stats) / len(recent_stats)
        }

    def get_peak_stats(self, minutes: int = 60) -> Dict[str, float]:
        """Get peak statistics over time period"""
        if not self.stats_history:
            return {"peak_memory_mb": 0, "peak_cpu_percent": 0, "peak_connections": 0}

        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_stats = [s for s in self.stats_history if s["timestamp"] > cutoff_time]

        if not recent_stats:
            recent_stats = self.stats_history[-1:]

        return {
            "peak_memory_mb": max(s["memory_mb"] for s in recent_stats),
            "peak_cpu_percent": max(s["cpu_percent"] for s in recent_stats),
            "peak_connections": max(s["connections"] for s in recent_stats)
        }

    def get_history(self, minutes: int = 30) -> List[Dict[str, Any]]:
        """Get historical stats for the specified time period"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [s for s in self.stats_history if s["timestamp"] > cutoff_time]

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Get system-wide information"""
        try:
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu_cores": cpu_count,
                "cpu_usage_system": psutil.cpu_percent(interval=1),
                "memory_total_gb": memory.total / 1024 / 1024 / 1024,
                "memory_available_gb": memory.available / 1024 / 1024 / 1024,
                "memory_percent_used": memory.percent,
                "disk_total_gb": disk.total / 1024 / 1024 / 1024,
                "disk_free_gb": disk.free / 1024 / 1024 / 1024,
                "disk_percent_used": (disk.used / disk.total) * 100
            }
        except Exception:
            return {}

    def export_stats(self, filename: str = None) -> str:
        """Export statistics to a file"""
        if not filename:
            filename = f"craft_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        import json

        export_data = {
            "export_time": datetime.now().isoformat(),
            "server_start_time": self.start_time.isoformat() if self.start_time else None,
            "current_stats": self.get_current_stats(),
            "averages_5min": self.get_average_stats(5),
            "averages_60min": self.get_average_stats(60),
            "peaks_60min": self.get_peak_stats(60),
            "system_info": self.get_system_info(),
            "history": [
                {
                    **entry,
                    "timestamp": entry["timestamp"].isoformat()
                }
                for entry in self.stats_history
            ]
        }

        # Convert timedelta to string for JSON serialization
        current_stats = export_data["current_stats"]
        if isinstance(current_stats.get("uptime"), timedelta):
            current_stats["uptime"] = str(current_stats["uptime"])

        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        return filename


class PerformanceMonitor:
    """Advanced performance monitoring and alerting"""

    def __init__(self, stats: ServerStats):
        self.stats = stats
        self.alerts = []
        self.thresholds = {
            "memory_percent": 90,  # Alert if memory usage > 90%
            "cpu_percent": 80,  # Alert if CPU usage > 80% for sustained period
            "connection_spike": 50  # Alert if connections spike suddenly
        }

    def check_performance_alerts(self) -> List[Dict[str, Any]]:
        """Check for performance issues and return alerts"""
        alerts = []
        current_stats = self.stats.get_current_stats()

        if not current_stats["running"]:
            return alerts

        # Memory usage alert
        if current_stats["memory_percent"] > self.thresholds["memory_percent"]:
            alerts.append({
                "type": "memory_high",
                "severity": "warning",
                "message": f"High memory usage: {current_stats['memory_percent']:.1f}%",
                "value": current_stats["memory_percent"],
                "threshold": self.thresholds["memory_percent"]
            })

        # CPU usage alert (check 5-minute average)
        avg_stats = self.stats.get_average_stats(5)
        if avg_stats["avg_cpu_percent"] > self.thresholds["cpu_percent"]:
            alerts.append({
                "type": "cpu_high",
                "severity": "warning",
                "message": f"High CPU usage (5min avg): {avg_stats['avg_cpu_percent']:.1f}%",
                "value": avg_stats["avg_cpu_percent"],
                "threshold": self.thresholds["cpu_percent"]
            })

        # Connection monitoring
        if len(self.stats.stats_history) > 10:
            recent_connections = [s["connections"] for s in self.stats.stats_history[-10:]]
            if recent_connections:
                avg_recent = sum(recent_connections) / len(recent_connections)
                current_connections = current_stats["connections"]

                if current_connections > avg_recent * 2 and current_connections > 10:
                    alerts.append({
                        "type": "connection_spike",
                        "severity": "info",
                        "message": f"Connection spike detected: {current_connections} (avg: {avg_recent:.1f})",
                        "value": current_connections,
                        "average": avg_recent
                    })

        return alerts

    def set_threshold(self, metric: str, value: float):
        """Set alert threshold for a metric"""
        self.thresholds[metric] = value

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of performance metrics"""
        current = self.stats.get_current_stats()
        averages = self.stats.get_average_stats(60)  # 1 hour
        peaks = self.stats.get_peak_stats(60)
        alerts = self.check_performance_alerts()

        return {
            "current": current,
            "averages_1h": averages,
            "peaks_1h": peaks,
            "alerts": alerts,
            "health_score": self._calculate_health_score(current, alerts)
        }

    @staticmethod
    def _calculate_health_score(stats: Dict[str, Any], alerts: List[Dict[str, Any]]) -> int:
        """Calculate a health score from 0-100"""
        if not stats["running"]:
            return 0

        score = 100

        # Deduct points for high resource usage
        if stats["memory_percent"] > 80:
            score -= min(20, (stats["memory_percent"] - 80) * 2)

        if stats["cpu_percent"] > 70:
            score -= min(15, (stats["cpu_percent"] - 70) * 0.5)

        # Deduct points for alerts
        for alert in alerts:
            if alert["severity"] == "warning":
                score -= 10
            elif alert["severity"] == "error":
                score -= 20

        return max(0, int(score))
