# GrafTrail Changelog

## [1.5.3] - 2024-12-XX

### ⌨️ Keyboard Shortcuts
- **Alt+1**: Switch to Freehand drawing mode
- **Alt+2**: Switch to Rectangle drawing mode  
- **Alt+3**: Switch to Circle drawing mode
- **Alt+4**: Switch to Arrow drawing mode

### 🛠️ User Experience
- **Quick Mode Switching**: Instantly change drawing modes without opening settings
- **Persistent Settings**: Mode changes via shortcuts are automatically saved
- **Cross-Platform**: Full Windows support, framework ready for macOS/Linux

---

## [1.5.1] - 2024-12-XX

### ✨ New Features
- **Fat Rounded Caps**: Added beautiful rounded caps at trail start and end (5% smaller than stroke width)
- **Advanced UI Section**: Reorganized settings with basic/advanced toggle for cleaner interface
- **Multi-Color Gradients**: Support for 1, 2, 3, or Rainbow color schemes
- **Enhanced Particle System**: Configurable explosion frequency (1-60/sec) and intensity

### 🎨 Visual Improvements
- **Clean Trail Rendering**: Single-pass stroke rendering eliminates overlapping on sharp curves
- **Improved Glow System**: Optional glow effects with percentage-based sizing
- **Start Cap Layering**: Start caps now render underneath trail for natural appearance
- **No-Fill Rendering**: Prevents unwanted filling on self-intersecting curves

### 🛠️ User Experience
- **Simplified Settings**: Essential settings visible by default, advanced options hidden
- **Better Organization**: Moved complex settings to collapsible advanced section
- **Reduced Particle Limit**: Lowered max explosion frequency from 500 to 60/sec for better performance

### 🔧 Technical Improvements
- **Continuous Path Rendering**: Eliminates segment overlapping on sharp turns
- **Per-Segment Color Gradients**: Proper fade transitions restored while maintaining clean rendering
- **Optimized Drawing Pipeline**: Separate glow and core stroke rendering for better control

### 🏗️ Build System
- **Updated Build Scripts**: New platform-specific build scripts for v1.5.1
- **Cross-Platform Packages**: Standardized release packaging for Windows, macOS, and Linux
- **Improved Documentation**: Updated README with latest features and build instructions

---

## [1.5.0] - Previous Release
- Smooth gradient particles with randomness
- Cross-platform support
- System tray integration
- Basic glow effects

---

## Version Notes

### What's New in 1.5.1
This release focuses on visual polish and user experience improvements:

1. **Professional Appearance**: Fat rounded caps give trails a polished, professional look
2. **Cleaner Interface**: Advanced settings are now hidden by default, making the app more approachable
3. **Better Rendering**: Solved the overlapping stroke issue on sharp curves
4. **Enhanced Customization**: More flexible color schemes and particle effects

### Upgrade Notes
- Settings will be preserved from previous versions
- New advanced section may need to be enabled to access all previous settings
- Particle frequency may be reduced if previously set above 60/sec

### Compatibility
- Windows 10/11
- macOS 10.14+
- Linux (X11-based desktop environments)
- Python 3.9+ (for building from source)

