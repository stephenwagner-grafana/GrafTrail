#!/bin/bash
# =====================================================================
# GrafTrail Linux Build Script (including WSL)
# =====================================================================
# This script builds Linux executables for both GrafTrail versions
# Works on Ubuntu, Debian, WSL, and other Linux distributions

set -e  # Exit on any error

echo "====================================================================="
echo "Building GrafTrail for Linux"
echo "====================================================================="

# Check if running in WSL
if grep -qEi "(Microsoft|WSL)" /proc/version &> /dev/null; then
    echo "Detected WSL environment"
    IS_WSL=true
else
    echo "Detected native Linux environment"
    IS_WSL=false
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build_linux"
DIST_DIR="$PROJECT_ROOT/dist_linux"

# Install system dependencies
echo "Checking system dependencies..."
if command -v apt &> /dev/null; then
    echo "Installing required packages with apt..."
    sudo apt update
    sudo apt install -y python3-venv python3-pip python3-tk python3-dev
elif command -v yum &> /dev/null; then
    echo "Installing required packages with yum..."
    sudo yum install -y python3-venv python3-pip python3-tkinter python3-devel
elif command -v pacman &> /dev/null; then
    echo "Installing required packages with pacman..."
    sudo pacman -S --noconfirm python-virtualenv python-pip tk python
else
    echo "Warning: Could not detect package manager. Please install:"
    echo "  - python3-venv"
    echo "  - python3-pip" 
    echo "  - python3-tk"
    echo "  - python3-dev"
fi

# Create and activate virtual environment
echo "Creating virtual environment..."
python3 -m venv "$BUILD_DIR/venv"
source "$BUILD_DIR/venv/bin/activate"

# Upgrade pip and install dependencies
echo "Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r "$PROJECT_ROOT/requirements.txt"

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf "$DIST_DIR"
rm -rf "$BUILD_DIR/build"
mkdir -p "$DIST_DIR"

# Build main application
echo "Building GrafTrail main application..."
pyinstaller --clean --noconfirm \
    --specpath "$BUILD_DIR" \
    --workpath "$BUILD_DIR/build" \
    --distpath "$DIST_DIR" \
    "$PROJECT_ROOT/build_configs/graftrail_app.spec"

# Build overlay application
echo "Building GrafTrail overlay application..."
pyinstaller --clean --noconfirm \
    --specpath "$BUILD_DIR" \
    --workpath "$BUILD_DIR/build" \
    --distpath "$DIST_DIR" \
    "$PROJECT_ROOT/build_configs/graftrail_overlay.spec"

# Create application package
echo "Creating application package..."
PACKAGE_DIR="$DIST_DIR/GrafTrail-Linux"
mkdir -p "$PACKAGE_DIR"

# Copy executables
cp "$DIST_DIR/GrafTrail" "$PACKAGE_DIR/"
cp "$DIST_DIR/GrafTrail-Overlay" "$PACKAGE_DIR/"
cp "$PROJECT_ROOT/README.md" "$PACKAGE_DIR/"

# Create desktop files
echo "Creating desktop files..."
cat > "$PACKAGE_DIR/GrafTrail.desktop" << EOF
[Desktop Entry]
Type=Application
Name=GrafTrail
Comment=Beautiful mouse trail overlay application
Exec=$PACKAGE_DIR/GrafTrail
Icon=$PACKAGE_DIR/graftrail.png
Terminal=false
Categories=Graphics;Utility;
StartupNotify=true
EOF

cat > "$PACKAGE_DIR/GrafTrail-Overlay.desktop" << EOF
[Desktop Entry]
Type=Application
Name=GrafTrail Overlay
Comment=Minimal mouse trail overlay
Exec=$PACKAGE_DIR/GrafTrail-Overlay
Icon=$PACKAGE_DIR/graftrail.png
Terminal=false
Categories=Graphics;Utility;
StartupNotify=true
NoDisplay=true
EOF

# Make desktop files executable
chmod +x "$PACKAGE_DIR"/*.desktop

# Create installation script
cat > "$PACKAGE_DIR/install.sh" << 'EOF'
#!/bin/bash
# GrafTrail Installation Script for Linux

echo "Installing GrafTrail..."

# Create application directory
sudo mkdir -p /opt/graftrail
sudo cp -r * /opt/graftrail/
sudo chmod +x /opt/graftrail/GrafTrail
sudo chmod +x /opt/graftrail/GrafTrail-Overlay

# Create symbolic links in /usr/local/bin
sudo ln -sf /opt/graftrail/GrafTrail /usr/local/bin/graftrail
sudo ln -sf /opt/graftrail/GrafTrail-Overlay /usr/local/bin/graftrail-overlay

# Install desktop files
mkdir -p ~/.local/share/applications
cp GrafTrail.desktop ~/.local/share/applications/
cp GrafTrail-Overlay.desktop ~/.local/share/applications/

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications
fi

echo "Installation complete!"
echo "You can now run 'graftrail' from the command line"
echo "Or find GrafTrail in your applications menu"
EOF

chmod +x "$PACKAGE_DIR/install.sh"

# Create installation instructions
cat > "$PACKAGE_DIR/Installation Instructions.txt" << EOF
GrafTrail for Linux - Installation Instructions
===============================================

Option 1: Quick Install (Recommended)
-------------------------------------
Run the installation script:
    ./install.sh

This will install GrafTrail system-wide and add it to your applications menu.

Option 2: Manual Install
------------------------
1. Copy the GrafTrail and GrafTrail-Overlay executables to your preferred location
2. Make them executable: chmod +x GrafTrail GrafTrail-Overlay
3. Run directly: ./GrafTrail

Option 3: Run Portable
---------------------
Simply run the executables directly from this folder:
    ./GrafTrail          # Full version with settings
    ./GrafTrail-Overlay  # Minimal overlay version

Requirements:
- PyQt5 libraries (usually installed with python3-pyqt5)
- X11 display server
- For Wayland: may need XWayland compatibility

Troubleshooting:
- If you get library errors, install: python3-pyqt5 python3-pyqt5-dev
- For Ubuntu/Debian: sudo apt install python3-pyqt5
- For Fedora: sudo dnf install python3-qt5
- For Arch: sudo pacman -S python-pyqt5
EOF

# Create tarball
echo "Creating tarball..."
cd "$DIST_DIR"
tar -czf "GrafTrail-Linux.tar.gz" "GrafTrail-Linux/"
cd - > /dev/null

# Deactivate virtual environment
deactivate

echo "====================================================================="
echo "Build completed successfully!"
echo "====================================================================="
echo "Executables location: $DIST_DIR"
echo "Package: $DIST_DIR/GrafTrail-Linux.tar.gz"
echo ""
echo "To install:"
echo "  cd $DIST_DIR/GrafTrail-Linux"
echo "  ./install.sh"
echo ""
echo "To run portable:"
echo "  cd $DIST_DIR/GrafTrail-Linux"
echo "  ./GrafTrail"
echo "====================================================================="

