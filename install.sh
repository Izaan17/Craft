#!/bin/bash
# Craft Minecraft Server Manager - Automated Installer
# This script sets up Craft with all dependencies and initial configuration

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${CYAN}🎮 Craft Minecraft Server Manager Installer${NC}"
    echo -e "${CYAN}===========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Main installation function
main() {
    print_header

    # Check if running as root (not recommended)
    if [[ $EUID -eq 0 ]]; then
        print_warning "Running as root is not recommended. Consider using a regular user account."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Check system requirements
    print_info "Checking system requirements..."

    # Check Python 3
    if check_command python3; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        print_success "Python 3 found: $PYTHON_VERSION"
    else
        print_error "Python 3 is required but not found"
        print_info "Please install Python 3.7+ and try again"
        exit 1
    fi

    # Check pip
    if check_command pip3; then
        print_success "pip3 found"
    else
        print_error "pip3 is required but not found"
        print_info "Please install pip3 and try again"
        exit 1
    fi

    # Check Java
    if check_command java; then
        JAVA_VERSION=$(java -version 2>&1 | head -n 1)
        print_success "Java found: $JAVA_VERSION"
    else
        print_warning "Java not found. You'll need Java to run Minecraft servers."
        print_info "Install Java 8, 11, 17, or 21 from: https://adoptium.net/"
    fi

    # Install Python dependencies
    print_info "Installing Python dependencies..."
    if pip3 install psutil rich; then
        print_success "Dependencies installed successfully"
    else
        print_error "Failed to install dependencies"
        exit 1
    fi

    # Create directory structure
    print_info "Creating directory structure..."
    mkdir -p server
    mkdir -p backups
    mkdir -p logs
    print_success "Directories created"

    # Make craft.py executable
    if [[ -f "craft.py" ]]; then
        chmod +x craft.py
        print_success "Made craft.py executable"
    else
        print_warning "craft.py not found in current directory"
    fi

    # Check for existing server JAR
    if [[ -f "server/server.jar" ]]; then
        print_success "Server JAR found at server/server.jar"
    else
        print_warning "No server JAR found"
        echo -e "${CYAN}📥 To complete setup:${NC}"
        echo "  1. Download your Minecraft server JAR"
        echo "  2. Place it at: server/server.jar"
        echo ""
        echo -e "${CYAN}Popular server types:${NC}"
        echo "  • Vanilla: https://www.minecraft.net/en-us/download/server"
        echo "  • Paper: https://papermc.io/downloads"
        echo "  • Spigot: https://www.spigotmc.org/"
        echo "  • Fabric: https://fabricmc.net/use/server/"
        echo ""
    fi

    # Run initial configuration
    print_info "Starting interactive configuration..."
    if [[ -f "craft.py" ]]; then
        echo -e "${CYAN}You can reconfigure anytime with: ./craft.py setup${NC}"
        echo ""

        # Ask if user wants to configure now
        read -p "Run configuration setup now? (Y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            print_info "Skipping configuration. Run './craft.py setup' when ready."
        else
            python3 craft.py setup
        fi
    fi

    # Create helpful scripts
    print_info "Creating helper scripts..."

    # Create start script
    cat > start-server.sh << 'EOF'
#!/bin/bash
# Quick start script for Craft server
echo "🎮 Starting Craft Minecraft Server..."
python3 craft.py start
if [ $? -eq 0 ]; then
    echo "🐕 Starting watchdog monitoring..."
    python3 craft.py watchdog start
fi
EOF
    chmod +x start-server.sh

    # Create status script
    cat > server-status.sh << 'EOF'
#!/bin/bash
# Quick status check script
python3 craft.py status --live
EOF
    chmod +x server-status.sh

    print_success "Helper scripts created (start-server.sh, server-status.sh)"

    # Create desktop shortcut (if desktop environment detected)
    if [[ -n "$DISPLAY" ]] && [[ -d "$HOME/Desktop" ]]; then
        cat > "$HOME/Desktop/Craft Server Manager.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Craft Server Manager
Comment=Minecraft Server Manager
Exec=gnome-terminal --working-directory="$(pwd)" --title="Craft Server Manager" -- python3 craft.py status --live
Icon=applications-games
Terminal=false
Categories=Game;
EOF
        chmod +x "$HOME/Desktop/Craft Server Manager.desktop"
        print_success "Desktop shortcut created"
    fi

    # Installation complete
    echo ""
    echo -e "${GREEN}🎉 Installation Complete!${NC}"
    echo ""
    echo -e "${CYAN}Quick start commands:${NC}"
    echo "  ./craft.py setup          # Configure server settings"
    echo "  ./craft.py start          # Start the server"
    echo "  ./craft.py status --live  # Live monitoring dashboard"
    echo "  ./craft.py backup         # Create backup"
    echo "  ./craft.py --help         # Show all commands"
    echo ""
    echo -e "${CYAN}Helper scripts:${NC}"
    echo "  ./start-server.sh         # Quick start with monitoring"
    echo "  ./server-status.sh        # Live status dashboard"
    echo ""

    if [[ ! -f "server/server.jar" ]]; then
        echo -e "${YELLOW}⚠️  Remember to place your server JAR at: server/server.jar${NC}"
        echo ""
    fi

    # Offer to start configuration
    if [[ -f "server/server.jar" ]] && [[ -f "craft.py" ]]; then
        read -p "Start the server now? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${CYAN}🚀 Starting server...${NC}"
            python3 craft.py start
            if [ $? -eq 0 ]; then
                echo -e "${CYAN}🐕 Starting monitoring...${NC}"
                python3 craft.py watchdog start
                echo -e "${GREEN}✅ Server and monitoring started!${NC}"
                echo "Run './craft.py status --live' to see live stats"
            fi
        fi
    fi

    print_success "Installation completed successfully!"
}

# Error handling
trap 'print_error "Installation failed at line $LINENO. Please check the error above."' ERR

# Check if script is being run from the correct directory
if [[ ! -f "craft.py" ]] && [[ ! -f "__init__.py" ]]; then
    print_error "Please run this installer from the Craft directory (where craft.py is located)"
    exit 1
fi

# Run main installation
main "$@"