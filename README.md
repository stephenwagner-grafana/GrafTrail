# 🎨 GrafTrail

**A beautiful, cross-platform mouse trail overlay that transforms your cursor into art.**

Create stunning mouse trails with smooth curves, customizable colors, and precise time control. Perfect for presentations, screen recordings, digital art, or just adding some visual flair to your desktop!

![GrafTrail Demo](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![Version](https://img.shields.io/badge/Version-v1.1.0-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

### 🎯 **Core Functionality**
- **CTRL + Drag**: Create beautiful mouse trails that follow your cursor
- **SHIFT + Hold**: Pause trail aging to freeze the current visual state
- **Cross-Platform**: Works seamlessly on Windows, macOS, and Linux
- **Always-on-Top**: Overlay that doesn't interfere with your workflow

### 🎨 **Visual Excellence**
- **Smooth Catmull-Rom Curves**: Mathematically perfect, silky-smooth trail paths
- **Dual-Layer Rendering**: Glow + core stroke with anti-aliasing
- **Rounded End Caps**: Professional, polished appearance
- **Bead-Free Joins**: Seamless connections between trail segments

### ⚙️ **Customization**
- **Color Control**: Customizable start and end colors with smooth gradients
- **Fade Control**: Adjustable fade duration (0.1-20 seconds)
- **Fade Slowdown**: Control fade curve behavior (1.0-3.0) for dramatic effects
- **Thickness Settings**: Separate core and glow thickness controls
- **Advanced Smoothing**: EMA smoothing, minimum spacing, and curve tension

### 🛠️ **User Experience**
- **System Tray Integration**: Easy access to pause, settings, and auto-startup
- **Live Settings**: Real-time preview of all changes
- **Auto-Startup**: Optional launch on system boot
- **Click-Through**: Never interferes with your normal computer use

## 🚀 Quick Start

### Download & Run
1. **Download** the latest release for your platform:
   - **Windows**: `GrafTrail-Main.exe`
   - **Linux**: `GrafTrail-Linux.tar.gz`
   - **macOS**: `GrafTrail.app` (coming soon)

2. **Run** the executable - no installation required!

3. **Create trails**:
   - Hold **CTRL** and move your mouse to create trails
   - Hold **SHIFT** to pause/freeze the current trail
   - Right-click the system tray icon for settings

### 🎮 Controls
| Key/Action | Effect |
|------------|--------|
| **CTRL + Mouse Move** | Create beautiful mouse trail |
| **SHIFT + Hold** | Pause trail aging (freeze in time) |
| **System Tray → Settings** | Open customization panel |
| **System Tray → Pause** | Pause/resume trail creation |

## 🛠️ Build from Source

### Prerequisites
- Python 3.8+ 
- PyQt5
- pyautogui
- pyinstaller (for building executables)

### Setup
```bash
# Clone the repository
git clone https://github.com/stephenwagner-grafana/GrafTrail.git
cd GrafTrail/GrafTrail

# Install dependencies
pip install -r requirements.txt

# Run from source
python GrafTrail/app.py
```

### Building Executables

#### Windows
```batch
# Run the automated build script
.\build_scripts\build_windows.bat

# Or build manually
pyinstaller --onefile --noconsole --name "GrafTrail" --icon "Resources/graftrail.ico" "GrafTrail/app.py"
```

#### macOS
```bash
# Run the automated build script
./build_scripts/build_macos.sh

# Or build manually
pyinstaller --onefile --windowed --name "GrafTrail" --icon "Resources/graftrail.ico" "GrafTrail/app.py"
```

#### Linux
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3-venv python3-pip python3-tk python3-dev python3-pyqt5

# Run the automated build script
./build_scripts/build_linux.sh

# Or build manually
pyinstaller --onefile --noconsole --name "GrafTrail" "GrafTrail/app.py"
```

## 🎨 Customization Guide

### Color Themes
- **Start Color**: The initial color of new trail segments
- **End Color**: The color trails fade to before disappearing
- **Gradients**: Smooth color transitions create beautiful effects

### Performance Tuning
- **EMA Alpha**: Controls smoothing responsiveness (0.0-1.0)
- **Min Spacing**: Minimum distance between trail points (prevents overcrowding)
- **Curve Tension**: Adjusts curve tightness for different artistic effects

### Timing Control
- **Fade Duration**: How long trails remain visible (0.1-20 seconds)
- **Fade Slowdown**: Makes trails fade slower for dramatic effect (1.0-3.0)
- **SHIFT Pause**: Hold SHIFT to freeze aging and study your creation

## 🌟 Use Cases

- **📊 Presentations**: Highlight important areas or guide audience attention
- **🎬 Screen Recording**: Add visual interest to tutorials and demos  
- **🎨 Digital Art**: Create flowing, organic shapes and patterns
- **🎮 Streaming**: Add visual flair to live streams and gaming content
- **📚 Education**: Demonstrate concepts with smooth, flowing gestures
- **✨ Fun**: Just enjoy the beautiful trails during everyday computer use!

## 🤝 Contributing

We welcome contributions! Please feel free to:
- 🐛 Report bugs via GitHub Issues
- 💡 Suggest new features or improvements  
- 🔧 Submit pull requests with enhancements
- 📖 Improve documentation

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Links

- **GitHub Repository**: https://github.com/stephenwagner-grafana/GrafTrail
- **Latest Releases**: https://github.com/stephenwagner-grafana/GrafTrail/releases
- **Issue Tracker**: https://github.com/stephenwagner-grafana/GrafTrail/issues

---

**Made with ❤️ for the joy of beautiful mouse trails**
