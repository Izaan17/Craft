# 🎮 Craft - Modular Minecraft Server Manager

A completely modular, enterprise-grade Minecraft server management system built for reliability, monitoring, and ease of
use.

## 🏗️ Architecture

Craft is built with a clean, modular architecture that separates concerns and makes the codebase maintainable:

```
craft/
├── craft.py              # Main CLI entry point
├── config.py             # Configuration management
├── server.py             # Minecraft server operations
├── backup.py             # Backup and restore system
├── watchdog.py           # Monitoring and auto-restart
├── stats.py              # Performance statistics
├── process_manager.py    # Process management utilities
├── display.py            # Rich UI and status display
├── utils.py              # Utility functions
├── __init__.py           # Package initialization
└── requirements.txt      # Python dependencies
```

## ✨ Features

### 🔧 **Server Management**

- **Reliable Process Control**: Proper PID tracking and process locking
- **Auto-configuration**: EULA acceptance and server.properties setup
- **Graceful Shutdown**: Smart stop commands with force-kill fallback
- **Memory Management**: Configurable min/max memory with validation

### 📊 **Live Monitoring**

- **Real-time Stats**: CPU, RAM, uptime, connections
- **Performance Trends**: 5-minute and 1-hour averages
- **Health Scoring**: Automated health assessment
- **Live Dashboard**: Continuously updating status display

### 💾 **Backup System**

- **Automatic Backups**: Scheduled with configurable intervals
- **Compression**: ZIP archives with integrity verification
- **Smart Cleanup**: Automatic old backup removal
- **Pre-restart Backups**: Automatic safety backups

### 🐕 **Intelligent Watchdog**

- **Crash Detection**: Port and process monitoring
- **Auto-restart**: Configurable restart limits and cooldowns
- **Restart History**: Detailed logging of all restart events
- **Health Checks**: Memory, CPU, and connection monitoring

### 🎨 **Rich Interface**

- **Beautiful Output**: Rich console with colors and formatting
- **Live Updates**: Real-time status with `--live` mode
- **Progress Bars**: Visual feedback for operations
- **Structured Display**: Tables, panels, and charts

## 🚀 Installation

### Prerequisites

```bash
# Python 3.7+ required
python3 --version

# Install dependencies
pip install psutil rich
```

### Quick Install

```bash
# Clone or download the modular Craft files
git clone <repository> craft-manager
cd craft-manager

# Make executable
chmod +x craft.py

# Initial setup
python3 craft.py setup
```

### Package Installation

```bash
# Install as a Python package (optional)
pip install -e .
```

## 📋 Quick Start

### 1. Initial Configuration

```bash
# Interactive setup wizard
python3 craft.py setup
```

### 2. Place Your Server JAR

```bash
# Put your server JAR file here:
mkdir -p server
cp minecraft_server.jar server/server.jar
```

### 3. Start Your Server

```bash
# Start server (detached mode)
python3 craft.py start

# Start with monitoring
python3 craft.py start && python3 craft.py watchdog start
```

### 4. Monitor Performance

```bash
# Static status
python3 craft.py status

# Live updating dashboard
python3 craft.py status --live
```

## 🎯 Core Commands

| Command    | Description               | Example                          |
|------------|---------------------------|----------------------------------|
| `setup`    | Interactive configuration | `craft.py setup`                 |
| `start`    | Start the server          | `craft.py start`                 |
| `stop`     | Stop the server           | `craft.py stop`                  |
| `restart`  | Restart the server        | `craft.py restart`               |
| `status`   | Show server status        | `craft.py status --live`         |
| `backup`   | Create manual backup      | `craft.py backup --name weekend` |
| `restore`  | Restore from backup       | `craft.py restore`               |
| `watchdog` | Manage monitoring         | `craft.py watchdog start`        |
| `command`  | Send server command       | `craft.py command say "Hello!"`  |

## 🔧 Advanced Usage

### Configuration Management

```python
from craft import ConfigManager

config = ConfigManager()
config.set("memory_max", "8G")
config.set("backup_interval", 1800)  # 30 minutes
```

### Programmatic Control

```python
from craft import MinecraftServer, BackupManager, Watchdog

# Initialize components
config = ConfigManager()
server = MinecraftServer(config)
backup_manager = BackupManager(config)
watchdog = Watchdog(server, backup_manager)

# Start server programmatically
if server.start():
    watchdog.start()

# Get status
status = server.get_status()
print(f"Server running: {status['running']}")
```

## 📊 Monitoring Dashboard

The live status dashboard shows:

```
┌─────────────────────────────────────────────────────────────┐
│                🎮 Craft Server Manager - 2024-01-15 14:30:25 │
└─────────────────────────────────────────────────────────────┘
┌─────────────────┬─────────────────┬─────────────────────────┐
│ 🖥️  Server Status│ 🐕 Monitoring   │ ⚙️  System              │
│                 │                 │                         │
│ Status: 🟢 Running │ Watchdog: 🟢 Active │ Port Status: 🟢 Open │
│ PID: 12345        │ Auto Backup: 🟢 Active │ World Size: 150.2 MB │
│ Uptime: 2h 15m    │ Restarts: 0     │ Peak Memory: 3.2 GB  │
│ Memory: 2.1 GB    │ Success Rate: 100% │ Peak CPU: 45.2%     │
│ CPU: 25.3%        │ Checks: 450     │                     │
└─────────────────┴─────────────────┴─────────────────────────┘
```

## 🔒 Security & Reliability

### Process Security

- **Exclusive Locking**: Prevents multiple server instances
- **PID Validation**: Ensures process tracking accuracy
- **Safe Shutdown**: Graceful stop with force-kill backup

### Data Protection

- **Backup Verification**: Validates backup integrity
- **Pre-operation Backups**: Automatic safety backups
- **Atomic Operations**: File operations are atomic where possible

### Error Handling

- **Graceful Degradation**: Continues operation despite errors
- **Retry Logic**: Automatic retry for transient failures
- **Comprehensive Logging**: Detailed error tracking

## 🛠️ Configuration Reference

### Server Settings

```json
{
  "server_dir": "server",
  "jar_name": "server.jar",
  "memory_min": "1G",
  "memory_max": "4G",
  "server_port": 25565,
  "java_args": "-XX:+UseG1GC"
}
```

### Backup Settings

```json
{
  "backup_dir": "backups",
  "auto_backup": true,
  "backup_interval": 3600,
  "max_backups": 10,
  "backup_on_stop": true
}
```

### Monitoring Settings

```json
{
  "watchdog_enabled": true,
  "watchdog_interval": 30,
  "restart_on_crash": true,
  "max_restarts": 5,
  "restart_cooldown": 300
}
```

## 🐛 Troubleshooting

### Server Won't Start

```bash
# Check Java installation
java -version

# Validate configuration
python3 craft.py setup

# Check permissions
ls -la server/server.jar

# View detailed errors
python3 craft.py start --verbose
```

### High Resource Usage

```bash
# Monitor performance
python3 craft.py status --live

# Check system resources
python3 -c "from craft.utils import check_system_resources; print(check_system_resources())"

# Adjust memory settings
python3 craft.py setup
```

### Backup Issues

```bash
# Check backup directory
ls -la backups/

# Test backup creation
python3 craft.py backup --name test

# Verify backups
python3 craft.py list-backups
```

## 🤝 Development

### Module Structure

Each module has a specific responsibility:

- **config.py**: Configuration management with validation
- **server.py**: Server lifecycle and command execution
- **backup.py**: Backup creation, restoration, and cleanup
- **watchdog.py**: Monitoring, health checks, and auto-restart
- **stats.py**: Performance data collection and analysis
- **process_manager.py**: Low-level process control
- **display.py**: User interface and status formatting
- **utils.py**: Common utilities and helper functions

### Adding Features

```python
# Example: Adding a new monitoring metric
from craft.stats import ServerStats


class CustomStats(ServerStats):
    def get_custom_metric(self):
        # Your custom monitoring logic
        return {"custom_value": 42}
```

### Testing

```bash
# Run basic validation
python3 -c "from craft.utils import validate_installation; validate_installation()"

# Test individual modules
python3 -c "from craft import ConfigManager; c = ConfigManager(); print('Config OK')"
```

## 📄 License

MIT License - see LICENSE file for details.

## 🆘 Support

1. **Check the troubleshooting section** above
2. **Validate your installation**: `python3 -c "from craft.utils import validate_installation; validate_installation()"`
3. **Review configuration**: `python3 craft.py setup`
4. **Check logs**: Look in the server/ directory for log files
5. **Use verbose mode**: Add `--verbose` to commands for detailed output

---

*Craft provides enterprise-grade reliability for your Minecraft server with a clean, modular architecture that's easy to
extend and maintain.*