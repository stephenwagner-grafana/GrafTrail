# 🎨 GrafTrail

**A beautiful, cross-platform mouse trail overlay that transforms your cursor into art.**

Create stunning mouse trails with smooth curves, customizable colors, and precise time control. Perfect for presentations, screen recordings, digital art, or just adding some visual flair to your desktop!

![GrafTrail Demo](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![graftrail](https://github.com/user-attachments/assets/011d48ee-241a-44ab-aa67-3e60a436109f)

![Version](https://img.shields.io/badge/Version-v1.5.1-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## ✨ Features

### 🎯 **Core Functionality**
- **CTRL + Drag**: Create beautiful mouse trails that follow your cursor
- **SHIFT + Hold**: Pause trail aging to freeze the current visual state
- **CAPS LOCK Toggle**: Pause aging when CAPS LOCK is enabled (hands-free!)
- **Cross-Platform**: Works seamlessly on Windows, macOS, and Linux
- **Always-on-Top**: Overlay that doesn't interfere with your workflow

### 🎨 **Visual Excellence**
- **Multi-Color Gradients**: 1, 2, 3, or Rainbow color schemes with full customization
- **Smooth Catmull-Rom Curves**: Mathematically perfect, silky-smooth trail paths
- **Advanced Glow System**: Configurable glow effects with gradient layers
- **Particle Effects**: Optional sparks and ice crystal trails

### ⚙️ **Customization**
- **Multi-Color System**: 1, 2, 3, or Rainbow color gradients with full customization
- **Flexible Glow**: Optional glow effects with percentage-based sizing
- **Fade Control**: Adjustable fade duration (0.1-20 seconds) and slowdown curves
- **Particle System**: Configurable explosion frequency (1-60/sec) and intensity
- **Advanced Smoothing**: EMA smoothing, minimum spacing, and curve tension
- **Ice Crystal Trails**: Optional perpendicular ice crystal particle effects

### 🛠️ **User Experience**
- **Clean Settings UI**: Simplified interface with advanced options hidden by default
- **System Tray Integration**: Easy access to pause, settings, and auto-startup
- **Live Settings**: Real-time preview of all changes with instant feedback
- **Auto-Startup**: Optional launch on system boot
- **Click-Through**: Never interferes with your normal computer use
- **Professional Rendering**: Optimized drawing system for smooth performance

## 🚀 Quick Start

### Download & Run
1. **Download** the latest release for your platform:
   - **Windows**: `GrafTrail-v1.5.3.exe`

2. **Run** the executable - no installation required!

3. **Create trails**:
   - Hold **CTRL** and move your mouse to create trails
   - Hold **SHIFT** to pause/freeze the current trail (temporary)
   - Toggle **CAPS LOCK** to pause/freeze trails (hands-free!)
   - Right-click the system tray icon for settings

### 🎮 Controls
| Key/Action | Effect |
|------------|--------|
| **CTRL + Mouse Move** | Create beautiful mouse trail |
| **SHIFT + Hold** | Pause trail aging (temporary freeze) |
| **CAPS LOCK On** | Pause trail aging (toggle freeze) |
| **ALT+1 (2, 3, or 4)** | Change Stroke to Freehand, Box, Circle, or Arrow |
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
pyinstaller --onefile --noconsole --name "GrafTrail-v1.5.1" --icon "Resources/graftrail.ico" "GrafTrail/app.py"
```

#### macOS
```bash
# Run the automated build script
./build_scripts/build_macos.sh

# Or build manually
pyinstaller --onefile --windowed --name "GrafTrail-v1.5.1" --icon "Resources/graftrail.ico" "GrafTrail/app.py"
```

#### Linux
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3-venv python3-pip python3-tk python3-dev python3-pyqt5

# Run the automated build script
./build_scripts/build_linux.sh

# Or build manually
pyinstaller --onefile --noconsole --name "GrafTrail-v1.5.1" "GrafTrail/app.py"
```

## 🎨 Customization Guide

### Color Themes
- **3-Color System**: Start (Purple), Middle (Burnt Orange), End (Yellow) by default
- **Flexible Combinations**: Enable any 1, 2, or 3 colors with checkboxes
- **Smart Gradients**: Automatic color blending based on enabled colors
- **Examples**:
  - ☑️☑️☑️ = Purple → Orange → Yellow (full gradient)
  - ☑️☐☑️ = Purple → Yellow (skip orange)
  - ☐☑️☑️ = Orange → Yellow (no purple)
  - ☑️☐☐ = Solid purple trail

### Performance Tuning
- **EMA Alpha**: Controls smoothing responsiveness (0.0-1.0)
- **Min Spacing**: Minimum distance between trail points (prevents overcrowding)
- **Curve Tension**: Adjusts curve tightness for different artistic effects

### Timing Control
- **Fade Duration**: How long trails remain visible (0.1-20 seconds)
- **Fade Slowdown**: Makes trails fade slower for dramatic effect (1.0-3.0)
- **SHIFT Pause**: Hold SHIFT to temporarily freeze aging
- **CAPS LOCK Pause**: Toggle CAPS LOCK for hands-free freeze control
- **Age-Based System**: Trails age independently, not based on real time

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
