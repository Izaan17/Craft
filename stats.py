"""
Statistics collection and monitoring for Craft Minecraft Server Manager

Provides comprehensive server performance monitoring, historical data tracking,
and alert generation with configurable thresholds and analysis capabilities.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

import psutil

from utils import handle_error, format_uptime

# Constants
DEFAULT_HISTORY_SIZE = 100
MAX_HISTORY_SIZE = 1000
STATS_COLLECTION_INTERVAL = 5  # seconds
CPU_SAMPLE_INTERVAL = 1  # seconds for CPU percentage calculation
MEMORY_WARNING_THRESHOLD = 80  # percent
CPU_WARNING_THRESHOLD = 75  # percent
THREAD_WARNING_THRESHOLD = 200


class StatsCollectionError(Exception):
    """Exception raised when statistics collection fails"""
    pass


class ServerStats:
    """Enhanced statistics collection and management with historical tracking"""

    def __init__(self, max_history: int = DEFAULT_HISTORY_SIZE):
        """
        Initialize statistics collector

        Args:
            max_history: Maximum number of historical entries to keep
        """
        self.max_history = min(max_history, MAX_HISTORY_SIZE)
        self.start_time: Optional[datetime] = None
        self.process: Optional[psutil.Process] = None
        self.stats_history: List[Dict[str, Any]] = []
        self._last_cpu_times: Optional[psutil.pcputimes] = None
        self._last_stats_time: Optional[float] = None

        # Performance tracking
        self._peak_memory = 0.0
        self._peak_cpu = 0.0
        self._peak_threads = 0

    def set_process(self, process: psutil.Process) -> bool:
        """
        Set the server process for monitoring with validation

        Args:
            process: psutil Process object to monitor

        Returns:
            bool: True if process set successfully, False otherwise
        """
        try:
            # Validate process is accessible
            _ = process.status()
            _ = process.create_time()

            self.process = process
            self.start_time = datetime.fromtimestamp(process.create_time())
            self._last_cpu_times = None
            self._last_stats_time = None

            # Reset peak tracking for new process
            self._peak_memory = 0.0
            self._peak_cpu = 0.0
            self._peak_threads = 0

            return True

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            handle_error(e, "Cannot set invalid process for monitoring")
            return False
        except Exception as e:
            handle_error(e, "Error setting process for monitoring")
            return False

    def clear_process(self) -> None:
        """Clear the current process and reset tracking"""
        self.process = None
        self.start_time = None
        self._last_cpu_times = None
        self._last_stats_time = None

    def get_current_stats(self) -> Dict[str, Any]:
        """
        Get current comprehensive server statistics

        Returns:
            Dict[str, Any]: Current statistics or offline stats if process unavailable
        """
        if not self.process or not self._is_process_running():
            return self._get_offline_stats()

        try:
            stats = self._collect_process_stats()
            self._update_peaks(stats)
            self._add_to_history(stats)
            return stats

        except Exception as e:
            handle_error(e, "Error collecting current statistics")
            self.clear_process()
            return self._get_offline_stats()

    def _is_process_running(self) -> bool:
        """Check if the tracked process is still running and accessible"""
        try:
            return self.process and self.process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception:
            return False

    def _collect_process_stats(self) -> Dict[str, Any]:
        """Collect comprehensive process statistics"""
        current_time = time.time()

        # Basic process information
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()

        # CPU information with proper timing
        cpu_percent = self._get_accurate_cpu_percent()

        # Process metadata
        num_threads = self.process.num_threads()

        # Network and file information (with error handling)
        connections, open_files = self._get_network_file_stats()

        # Calculate uptime
        uptime = datetime.now() - self.start_time if self.start_time else timedelta(0)

        stats = {
            "running": True,
            "pid": self.process.pid,
            "uptime": uptime,
            "memory_usage_mb": memory_info.rss / (1024 * 1024),
            "memory_vms_mb": memory_info.vms / (1024 * 1024),
            "memory_percent": memory_percent,
            "cpu_percent": cpu_percent,
            "threads": num_threads,
            "open_files": open_files,
            "connections": connections,
            "start_time": self.start_time,
            "timestamp": datetime.now(),
            "collection_time": current_time
        }

        # Add system context
        stats.update(self._get_system_context())

        self._last_stats_time = current_time
        return stats

    def _get_accurate_cpu_percent(self) -> float:
        """Get accurate CPU percentage with proper timing"""
        try:
            # Use interval for more accurate measurement if this is the first call
            # or enough time has passed since last measurement
            current_time = time.time()

            if (self._last_stats_time is None or
                    (current_time - self._last_stats_time) > STATS_COLLECTION_INTERVAL):
                return self.process.cpu_percent(interval=CPU_SAMPLE_INTERVAL)
            else:
                # Use cached measurement for frequent calls
                return self.process.cpu_percent()

        except Exception:
            return 0.0

    def _get_network_file_stats(self) -> Tuple[int, int]:
        """Get network connections and open files count with error handling"""
        connections = 0
        open_files = 0

        try:
            connections = len(self.process.connections())
        except (psutil.AccessDenied, OSError):
            pass

        try:
            open_files = len(self.process.open_files())
        except (psutil.AccessDenied, OSError):
            pass

        return connections, open_files

    def _get_system_context(self) -> Dict[str, Any]:
        """Get system-wide context for statistics"""
        try:
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()

            return {
                "system_cpu_count": cpu_count,
                "system_memory_total_mb": memory.total / (1024 * 1024),
                "system_memory_available_mb": memory.available / (1024 * 1024),
                "system_memory_percent": memory.percent
            }
        except Exception:
            return {}

    def _update_peaks(self, stats: Dict[str, Any]) -> None:
        """Update peak performance tracking"""
        self._peak_memory = max(self._peak_memory, stats.get("memory_usage_mb", 0))
        self._peak_cpu = max(self._peak_cpu, stats.get("cpu_percent", 0))
        self._peak_threads = max(self._peak_threads, stats.get("threads", 0))

    @staticmethod
    def _get_offline_stats() -> Dict[str, Any]:
        """Get statistics structure when server is offline"""
        return {
            "running": False,
            "pid": None,
            "uptime": timedelta(0),
            "memory_usage_mb": 0,
            "memory_vms_mb": 0,
            "memory_percent": 0,
            "cpu_percent": 0,
            "threads": 0,
            "open_files": 0,
            "connections": 0,
            "start_time": None,
            "timestamp": datetime.now(),
            "collection_time": time.time()
        }

    def _add_to_history(self, stats: Dict[str, Any]) -> None:
        """Add statistics to historical data with size management"""
        history_entry = {
            "timestamp": stats["timestamp"],
            "memory_mb": stats["memory_usage_mb"],
            "memory_percent": stats["memory_percent"],
            "cpu_percent": stats["cpu_percent"],
            "threads": stats["threads"],
            "connections": stats["connections"],
            "open_files": stats["open_files"]
        }

        self.stats_history.append(history_entry)

        # Maintain history size limit
        if len(self.stats_history) > self.max_history:
            self.stats_history = self.stats_history[-self.max_history:]

    def get_average_stats(self, minutes: int = 5) -> Dict[str, float]:
        """
        Get average statistics over specified time period

        Args:
            minutes: Time period in minutes to calculate average over

        Returns:
            Dict[str, float]: Average statistics
        """
        if not self.stats_history:
            return self._get_empty_averages()

        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            recent_stats = [s for s in self.stats_history if s["timestamp"] > cutoff_time]

            if not recent_stats:
                # Use most recent available data if no data in specified timeframe
                recent_stats = self.stats_history[-1:]

            return self._calculate_averages(recent_stats)

        except Exception as e:
            handle_error(e, f"Error calculating {minutes}-minute averages")
            return self._get_empty_averages()

    def _get_empty_averages(self) -> Dict[str, float]:
        """Get empty averages structure"""
        return {
            "avg_memory_mb": 0.0,
            "avg_memory_percent": 0.0,
            "avg_cpu_percent": 0.0,
            "avg_threads": 0.0,
            "avg_connections": 0.0,
            "avg_open_files": 0.0,
            "sample_count": 0
        }

    def _calculate_averages(self, stats_list: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate averages from statistics list"""
        if not stats_list:
            return self._get_empty_averages()

        count = len(stats_list)

        return {
            "avg_memory_mb": sum(s["memory_mb"] for s in stats_list) / count,
            "avg_memory_percent": sum(s["memory_percent"] for s in stats_list) / count,
            "avg_cpu_percent": sum(s["cpu_percent"] for s in stats_list) / count,
            "avg_threads": sum(s["threads"] for s in stats_list) / count,
            "avg_connections": sum(s["connections"] for s in stats_list) / count,
            "avg_open_files": sum(s["open_files"] for s in stats_list) / count,
            "sample_count": count
        }

    def get_peak_stats(self, minutes: int = 60) -> Dict[str, float]:
        """
        Get peak statistics over specified time period

        Args:
            minutes: Time period in minutes to find peaks over

        Returns:
            Dict[str, float]: Peak statistics
        """
        if not self.stats_history:
            return self._get_empty_peaks()

        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            recent_stats = [s for s in self.stats_history if s["timestamp"] > cutoff_time]

            if not recent_stats:
                # Use most recent data if no data in specified timeframe
                recent_stats = self.stats_history[-1:]

            return self._calculate_peaks(recent_stats)

        except Exception as e:
            handle_error(e, f"Error calculating {minutes}-minute peaks")
            return self._get_empty_peaks()

    def _get_empty_peaks(self) -> Dict[str, float]:
        """Get empty peaks structure"""
        return {
            "peak_memory_mb": 0.0,
            "peak_memory_percent": 0.0,
            "peak_cpu_percent": 0.0,
            "peak_threads": 0.0,
            "peak_connections": 0.0,
            "peak_open_files": 0.0,
            "sample_count": 0
        }

    def _calculate_peaks(self, stats_list: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate peak values from statistics list"""
        if not stats_list:
            return self._get_empty_peaks()

        return {
            "peak_memory_mb": max(s["memory_mb"] for s in stats_list),
            "peak_memory_percent": max(s["memory_percent"] for s in stats_list),
            "peak_cpu_percent": max(s["cpu_percent"] for s in stats_list),
            "peak_threads": max(s["threads"] for s in stats_list),
            "peak_connections": max(s["connections"] for s in stats_list),
            "peak_open_files": max(s["open_files"] for s in stats_list),
            "sample_count": len(stats_list)
        }

    def get_history(self, minutes: int = 30) -> List[Dict[str, Any]]:
        """
        Get historical statistics for specified time period

        Args:
            minutes: Time period in minutes to retrieve history for

        Returns:
            List[Dict[str, Any]]: Historical statistics
        """
        if not self.stats_history:
            return []

        try:
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            return [s for s in self.stats_history if s["timestamp"] > cutoff_time]
        except Exception as e:
            handle_error(e, f"Error retrieving {minutes}-minute history")
            return []

    def get_trend_analysis(self, minutes: int = 30) -> Dict[str, Any]:
        """
        Analyze trends in statistics over time period

        Args:
            minutes: Time period to analyze trends over

        Returns:
            Dict[str, Any]: Trend analysis results
        """
        history = self.get_history(minutes)

        if len(history) < 2:
            return {"insufficient_data": True}

        try:
            return self._analyze_trends(history)
        except Exception as e:
            handle_error(e, "Error analyzing trends")
            return {"error": str(e)}

    def _analyze_trends(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends in historical data"""
        if len(history) < 2:
            return {"insufficient_data": True}

        # Calculate trends for key metrics
        memory_trend = self._calculate_trend([s["memory_percent"] for s in history])
        cpu_trend = self._calculate_trend([s["cpu_percent"] for s in history])
        thread_trend = self._calculate_trend([s["threads"] for s in history])

        return {
            "memory_trend": memory_trend,
            "cpu_trend": cpu_trend,
            "thread_trend": thread_trend,
            "timespan_minutes": (history[-1]["timestamp"] - history[0]["timestamp"]).total_seconds() / 60,
            "sample_count": len(history)
        }

    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calculate trend information for a series of values"""
        if len(values) < 2:
            return {"direction": "stable", "change": 0.0}

        # Simple trend calculation using first and last values
        start_value = values[0]
        end_value = values[-1]
        change = end_value - start_value
        percent_change = (change / start_value * 100) if start_value > 0 else 0

        # Determine trend direction
        if abs(percent_change) < 5:
            direction = "stable"
        elif percent_change > 0:
            direction = "increasing"
        else:
            direction = "decreasing"

        return {
            "direction": direction,
            "change": change,
            "percent_change": percent_change,
            "start_value": start_value,
            "end_value": end_value
        }

    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """Get comprehensive system information"""
        try:
            system_info = {
                "cpu": {
                    "physical_cores": psutil.cpu_count(logical=False),
                    "logical_cores": psutil.cpu_count(logical=True),
                    "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else {},
                    "usage_per_core": psutil.cpu_percent(percpu=True, interval=1)
                },
                "memory": {
                    "total_gb": psutil.virtual_memory().total / (1024 ** 3),
                    "available_gb": psutil.virtual_memory().available / (1024 ** 3),
                    "percent_used": psutil.virtual_memory().percent,
                    "swap_total_gb": psutil.swap_memory().total / (1024 ** 3),
                    "swap_used_gb": psutil.swap_memory().used / (1024 ** 3)
                },
                "disk": {},
                "network": {},
                "processes": {
                    "total": len(psutil.pids()),
                    "java_processes": len([p for p in psutil.process_iter(['name'])
                                           if p.info['name'] and 'java' in p.info['name'].lower()])
                }
            }

            # Add disk information
            system_info["disk"] = ServerStats._get_disk_info()

            # Add network information
            system_info["network"] = ServerStats._get_network_info()

            return system_info

        except Exception as e:
            handle_error(e, "Error collecting system information")
            return {"error": str(e)}

    @staticmethod
    def _get_disk_info() -> Dict[str, Any]:
        """Get disk usage information"""
        try:
            disk_usage = psutil.disk_usage('/')
            return {
                "total_gb": disk_usage.total / (1024 ** 3),
                "used_gb": disk_usage.used / (1024 ** 3),
                "free_gb": disk_usage.free / (1024 ** 3),
                "percent_used": (disk_usage.used / disk_usage.total) * 100
            }
        except Exception:
            return {}

    @staticmethod
    def _get_network_info() -> Dict[str, Any]:
        """Get network statistics"""
        try:
            net_io = psutil.net_io_counters()
            return {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "errors_in": net_io.errin,
                "errors_out": net_io.errout,
                "dropped_in": net_io.dropin,
                "dropped_out": net_io.dropout
            }
        except Exception:
            return {}

    def export_stats(self, filename: Optional[str] = None) -> str:
        """
        Export comprehensive statistics to file

        Args:
            filename: Output filename, auto-generated if None

        Returns:
            str: Name of exported file
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"craft_stats_{timestamp}.json"

        try:
            export_data = {
                "export_metadata": {
                    "export_time": datetime.now().isoformat(),
                    "craft_version": "1.0.0",
                    "stats_version": "2.0"
                },
                "server_info": {
                    "start_time": self.start_time.isoformat() if self.start_time else None,
                    "current_stats": self.get_current_stats(),
                    "uptime": format_uptime(datetime.now() - self.start_time) if self.start_time else "0s"
                },
                "performance_summary": {
                    "averages_5min": self.get_average_stats(5),
                    "averages_30min": self.get_average_stats(30),
                    "averages_60min": self.get_average_stats(60),
                    "peaks_60min": self.get_peak_stats(60),
                    "trend_analysis": self.get_trend_analysis(30)
                },
                "system_info": self.get_system_info(),
                "historical_data": self._prepare_history_for_export(),
                "statistics": {
                    "total_samples": len(self.stats_history),
                    "history_timespan_hours": self._calculate_history_timespan(),
                    "peak_memory_ever": self._peak_memory,
                    "peak_cpu_ever": self._peak_cpu,
                    "peak_threads_ever": self._peak_threads
                }
            }

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=self._json_serializer)

            return filename

        except Exception as e:
            handle_error(e, "Failed to export statistics")
            return ""

    def _prepare_history_for_export(self) -> List[Dict[str, Any]]:
        """Prepare historical data for JSON export"""
        prepared_history = []

        for entry in self.stats_history:
            prepared_entry = entry.copy()
            # Convert datetime to ISO string
            if isinstance(prepared_entry.get("timestamp"), datetime):
                prepared_entry["timestamp"] = prepared_entry["timestamp"].isoformat()
            prepared_history.append(prepared_entry)

        return prepared_history

    def _calculate_history_timespan(self) -> float:
        """Calculate total timespan of historical data in hours"""
        if len(self.stats_history) < 2:
            return 0.0

        try:
            oldest = self.stats_history[0]["timestamp"]
            newest = self.stats_history[-1]["timestamp"]
            return (newest - oldest).total_seconds() / 3600
        except Exception:
            return 0.0

    @staticmethod
    def _json_serializer(obj):
        """Custom JSON serializer for complex objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def reset_stats(self) -> None:
        """Reset all statistics and history"""
        self.stats_history.clear()
        self._peak_memory = 0.0
        self._peak_cpu = 0.0
        self._peak_threads = 0
        self._last_cpu_times = None
        self._last_stats_time = None

    def get_memory_usage_prediction(self, minutes_ahead: int = 30) -> Dict[str, Any]:
        """
        Predict memory usage based on current trends

        Args:
            minutes_ahead: Minutes to predict ahead

        Returns:
            Dict[str, Any]: Memory usage prediction
        """
        history = self.get_history(60)  # Use last hour for prediction

        if len(history) < 5:
            return {"prediction_available": False, "reason": "Insufficient historical data"}

        try:
            memory_values = [s["memory_percent"] for s in history]
            trend = self._calculate_trend(memory_values)

            current_memory = memory_values[-1]

            if trend["direction"] == "stable":
                predicted_memory = current_memory
            else:
                # Simple linear extrapolation
                rate_per_minute = trend["change"] / len(history)  # Approximate rate per sample
                predicted_memory = current_memory + (rate_per_minute * minutes_ahead)

            # Ensure prediction is within reasonable bounds
            predicted_memory = max(0, min(100, predicted_memory))

            return {
                "prediction_available": True,
                "current_memory_percent": current_memory,
                "predicted_memory_percent": predicted_memory,
                "trend_direction": trend["direction"],
                "confidence": "low" if len(history) < 10 else "medium",
                "minutes_ahead": minutes_ahead
            }

        except Exception as e:
            handle_error(e, "Error calculating memory usage prediction")
            return {"prediction_available": False, "reason": f"Calculation error: {e}"}


class PerformanceMonitor:
    """Advanced performance monitoring and alerting with configurable thresholds"""

    def __init__(self, stats: ServerStats):
        """
        Initialize performance monitor

        Args:
            stats: ServerStats instance to monitor
        """
        self.stats = stats
        self.alerts: List[Dict[str, Any]] = []
        self.alert_history: List[Dict[str, Any]] = []

        # Configurable thresholds
        self.thresholds = {
            "memory_percent": MEMORY_WARNING_THRESHOLD,
            "cpu_percent": CPU_WARNING_THRESHOLD,
            "thread_count": THREAD_WARNING_THRESHOLD,
            "connection_spike_multiplier": 2.0,
            "file_descriptor_limit": 1000
        }

    def set_threshold(self, metric: str, value: float) -> bool:
        """
        Set alert threshold for a metric

        Args:
            metric: Metric name
            value: Threshold value

        Returns:
            bool: True if threshold set successfully
        """
        if metric in self.thresholds:
            self.thresholds[metric] = value
            return True
        return False

    def check_performance_alerts(self) -> List[Dict[str, Any]]:
        """
        Check for performance issues and return current alerts

        Returns:
            List[Dict[str, Any]]: List of current alerts
        """
        current_alerts = []
        current_stats = self.stats.get_current_stats()

        if not current_stats["running"]:
            return current_alerts

        try:
            # Memory usage alerts
            current_alerts.extend(self._check_memory_alerts(current_stats))

            # CPU usage alerts
            current_alerts.extend(self._check_cpu_alerts(current_stats))

            # Thread count alerts
            current_alerts.extend(self._check_thread_alerts(current_stats))

            # Connection alerts
            current_alerts.extend(self._check_connection_alerts(current_stats))

            # File descriptor alerts
            current_alerts.extend(self._check_file_descriptor_alerts(current_stats))

            # Update alert history
            self._update_alert_history(current_alerts)

            return current_alerts

        except Exception as e:
            handle_error(e, "Error checking performance alerts")
            return []

    def _check_memory_alerts(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for memory-related alerts"""
        alerts = []
        memory_percent = stats.get("memory_percent", 0)

        if memory_percent > 95:
            alerts.append({
                "type": "memory_critical",
                "severity": "critical",
                "message": f"Critical memory usage: {memory_percent:.1f}%",
                "value": memory_percent,
                "threshold": 95,
                "timestamp": datetime.now()
            })
        elif memory_percent > self.thresholds["memory_percent"]:
            alerts.append({
                "type": "memory_high",
                "severity": "warning",
                "message": f"High memory usage: {memory_percent:.1f}%",
                "value": memory_percent,
                "threshold": self.thresholds["memory_percent"],
                "timestamp": datetime.now()
            })

        return alerts

    def _check_cpu_alerts(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for CPU-related alerts"""
        alerts = []

        # Check current CPU usage
        cpu_percent = stats.get("cpu_percent", 0)
        if cpu_percent > 95:
            alerts.append({
                "type": "cpu_critical",
                "severity": "critical",
                "message": f"Critical CPU usage: {cpu_percent:.1f}%",
                "value": cpu_percent,
                "threshold": 95,
                "timestamp": datetime.now()
            })
        elif cpu_percent > self.thresholds["cpu_percent"]:
            alerts.append({
                "type": "cpu_high",
                "severity": "warning",
                "message": f"High CPU usage: {cpu_percent:.1f}%",
                "value": cpu_percent,
                "threshold": self.thresholds["cpu_percent"],
                "timestamp": datetime.now()
            })

        # Check sustained high CPU (5-minute average)
        avg_stats = self.stats.get_average_stats(5)
        avg_cpu = avg_stats.get("avg_cpu_percent", 0)
        if avg_cpu > self.thresholds["cpu_percent"]:
            alerts.append({
                "type": "cpu_sustained",
                "severity": "warning",
                "message": f"Sustained high CPU usage (5min avg): {avg_cpu:.1f}%",
                "value": avg_cpu,
                "threshold": self.thresholds["cpu_percent"],
                "timestamp": datetime.now()
            })

        return alerts

    def _check_thread_alerts(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for thread count alerts"""
        alerts = []
        thread_count = stats.get("threads", 0)

        if thread_count > self.thresholds["thread_count"]:
            severity = "critical" if thread_count > 500 else "warning"
            alerts.append({
                "type": "thread_count_high",
                "severity": severity,
                "message": f"High thread count: {thread_count}",
                "value": thread_count,
                "threshold": self.thresholds["thread_count"],
                "timestamp": datetime.now()
            })

        return alerts

    def _check_connection_alerts(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for connection-related alerts"""
        alerts = []

        # Check for connection spikes
        if len(self.stats.stats_history) > 10:
            recent_connections = [s["connections"] for s in self.stats.stats_history[-10:]]
            if recent_connections:
                avg_recent = sum(recent_connections) / len(recent_connections)
                current_connections = stats.get("connections", 0)
                spike_threshold = avg_recent * self.thresholds["connection_spike_multiplier"]

                if current_connections > spike_threshold and current_connections > 10:
                    alerts.append({
                        "type": "connection_spike",
                        "severity": "info",
                        "message": f"Connection spike detected: {current_connections} (avg: {avg_recent:.1f})",
                        "value": current_connections,
                        "average": avg_recent,
                        "timestamp": datetime.now()
                    })

        return alerts

    def _check_file_descriptor_alerts(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for file descriptor alerts"""
        alerts = []
        open_files = stats.get("open_files", 0)

        if open_files > self.thresholds["file_descriptor_limit"]:
            severity = "critical" if open_files > 2000 else "warning"
            alerts.append({
                "type": "file_descriptors_high",
                "severity": severity,
                "message": f"High open file count: {open_files}",
                "value": open_files,
                "threshold": self.thresholds["file_descriptor_limit"],
                "timestamp": datetime.now()
            })

        return alerts

    def _update_alert_history(self, current_alerts: List[Dict[str, Any]]) -> None:
        """Update alert history for trend analysis"""
        for alert in current_alerts:
            self.alert_history.append(alert.copy())

        # Keep only recent alert history (last 100 alerts)
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary with health assessment"""
        try:
            current = self.stats.get_current_stats()
            averages = self.stats.get_average_stats(60)
            peaks = self.stats.get_peak_stats(60)
            alerts = self.check_performance_alerts()

            return {
                "current": current,
                "averages_1h": averages,
                "peaks_1h": peaks,
                "alerts": alerts,
                "health_score": self._calculate_health_score(current, alerts),
                "performance_rating": self._get_performance_rating(current, alerts),
                "recommendations": self._get_performance_recommendations(current, alerts)
            }

        except Exception as e:
            handle_error(e, "Error getting performance summary")
            return {"error": str(e)}

    def _calculate_health_score(self, stats: Dict[str, Any], alerts: List[Dict[str, Any]]) -> int:
        """Calculate overall health score from 0-100"""
        if not stats.get("running", False):
            return 0

        score = 100

        # Deduct points for resource usage
        memory_percent = stats.get("memory_percent", 0)
        if memory_percent > 90:
            score -= 25
        elif memory_percent > 80:
            score -= 15
        elif memory_percent > 70:
            score -= 5

        cpu_percent = stats.get("cpu_percent", 0)
        if cpu_percent > 85:
            score -= 20
        elif cpu_percent > 70:
            score -= 10

        # Deduct points for alerts
        for alert in alerts:
            severity = alert.get("severity", "info")
            if severity == "critical":
                score -= 25
            elif severity == "warning":
                score -= 10
            elif severity == "info":
                score -= 5

        return max(0, int(score))

    def _get_performance_rating(self, stats: Dict[str, Any], alerts: List[Dict[str, Any]]) -> str:
        """Get performance rating based on current state"""
        health_score = self._calculate_health_score(stats, alerts)

        if health_score >= 90:
            return "excellent"
        elif health_score >= 75:
            return "good"
        elif health_score >= 50:
            return "fair"
        elif health_score >= 25:
            return "poor"
        else:
            return "critical"

    def _get_performance_recommendations(self, stats: Dict[str, Any],
                                         alerts: List[Dict[str, Any]]) -> List[str]:
        """Get performance improvement recommendations"""
        recommendations = []

        # Memory recommendations
        memory_percent = stats.get("memory_percent", 0)
        if memory_percent > 85:
            recommendations.append("Consider increasing server memory allocation")
        elif memory_percent > 75:
            recommendations.append("Monitor memory usage trends")

        # CPU recommendations
        cpu_percent = stats.get("cpu_percent", 0)
        if cpu_percent > 80:
            recommendations.append("Optimize server performance settings or upgrade CPU")
        elif cpu_percent > 70:
            recommendations.append("Monitor CPU usage for sustained high levels")

        # Thread recommendations
        thread_count = stats.get("threads", 0)
        if thread_count > 300:
            recommendations.append("High thread count detected - investigate for potential issues")

        # Alert-based recommendations
        critical_alerts = [a for a in alerts if a.get("severity") == "critical"]
        if critical_alerts:
            recommendations.append("Address critical alerts immediately")

        if not recommendations:
            recommendations.append("Performance is good - continue monitoring")

        return recommendations
