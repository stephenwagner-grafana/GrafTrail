#!/bin/bash
# =====================================================================
# GrafTrail macOS Build Script
# =====================================================================
# This script builds macOS applications for both GrafTrail versions
# Requirements: Python 3.9+, pip, Xcode Command Line Tools

set -e  # Exit on any error

echo "====================================================================="
echo "Building GrafTrail for macOS"
echo "====================================================================="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build_macos"
DIST_DIR="$PROJECT_ROOT/dist_macos"

# Create and activate virtual environment
echo "Creating virtual environment..."
python3 -m venv "$BUILD_DIR/venv"
source "$BUILD_DIR/venv/bin/activate"

# Upgrade pip and install dependencies
echo "Installing dependencies..."
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

# Create application bundle structure
echo "Creating application package..."
PACKAGE_DIR="$DIST_DIR/GrafTrail-macOS"
mkdir -p "$PACKAGE_DIR"

# Copy applications
cp -R "$DIST_DIR/GrafTrail.app" "$PACKAGE_DIR/"
cp -R "$DIST_DIR/GrafTrail-Overlay.app" "$PACKAGE_DIR/"
cp "$PROJECT_ROOT/README.md" "$PACKAGE_DIR/"

# Create installation instructions for macOS
cat > "$PACKAGE_DIR/Installation Instructions.txt" << EOF
GrafTrail for macOS - Installation Instructions
===============================================

1. Copy both .app files to your Applications folder
2. Run GrafTrail.app for the full-featured version with settings
3. Run GrafTrail-Overlay.app for the minimal overlay version

Note: You may need to allow the application in System Preferences > 
Security & Privacy if you see a warning about unsigned applications.

To enable startup at login:
- Open the application
- Right-click the system tray icon
- Check "Run at startup"
EOF

# Create DMG (requires create-dmg or hdiutil)
echo "Creating DMG package..."
if command -v create-dmg &> /dev/null; then
    create-dmg \
        --volname "GrafTrail" \
        --window-pos 200 120 \
        --window-size 800 400 \
        --icon-size 100 \
        --app-drop-link 600 185 \
        "$DIST_DIR/GrafTrail-macOS.dmg" \
        "$PACKAGE_DIR"
else
    # Fallback to simple DMG creation
    hdiutil create -volname "GrafTrail" -srcfolder "$PACKAGE_DIR" -ov -format UDZO "$DIST_DIR/GrafTrail-macOS.dmg"
fi

# Deactivate virtual environment
deactivate

echo "====================================================================="
echo "Build completed successfully!"
echo "====================================================================="
echo "Applications location: $DIST_DIR"
echo "DMG package: $DIST_DIR/GrafTrail-macOS.dmg"
echo "====================================================================="
