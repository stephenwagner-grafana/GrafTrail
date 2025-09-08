# trail_app_gui.py  (Python 3.9+)
# Windows overlay app with a Settings GUI:
# - Hold CTRL to draw a silky trail (Catmull–Rom -> cubic Bézier)
# - Start/Finish colors (color pickers)
# - Fade duration (seconds)
# - Core & Glow thickness sliders
# - Optional smoothness controls (EMA, min spacing)
# - Rounded end caps; bead-free joins (FlatCap on segments)
# - System tray: Settings…, Pause, Run at startup, Quit
#
# Build: pyinstaller --noconsole --onefile --name "GrafTrail-v1.5.3" app.py

import sys, time, os, ctypes, math, threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path
from enum import Enum

import pyautogui
from PyQt5 import QtCore, QtGui, QtWidgets
import platform   # Platform detection for cross-platform compatibility

pyautogui.FAILSAFE = False

APP_NAME    = "GrafTrail"
APP_VERSION = "1.5.3"      # Keyboard shortcuts (Alt+1-4) for draw modes
ORG_NAME    = "GrafTrail"   # for QSettings
ORG_DOMAIN  = "graftrail.local"

class DrawMode(Enum):
    FREEHAND = "freehand"
    RECTANGLE = "rectangle"
    CIRCLE = "circle"
    ARROW = "arrow"

# ------------------------- Cross-platform helpers -------------------------
def get_platform() -> str:
    """Get the current platform name in lowercase."""
    return platform.system().lower()

# Windows system metrics constants for multi-monitor setups
SM_XVIRTUALSCREEN  = 76
SM_YVIRTUALSCREEN  = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_CAPITAL = 0x14  # CAPS LOCK key
VK_LALT = 0xA4     # Left Alt key
VK_RALT = 0xA5     # Right Alt key
VK_1 = 0x31        # Number 1 key
VK_2 = 0x32        # Number 2 key
VK_3 = 0x33        # Number 3 key
VK_4 = 0x34        # Number 4 key

# Platform-specific global state for CTRL and SHIFT key tracking
_ctrl_pressed = False
_shift_pressed = False
_key_monitor = None

class GlobalKeyMonitor(QtCore.QObject):
    """Cross-platform global key state monitor using Qt events."""
    draw_mode_changed = QtCore.pyqtSignal(DrawMode)  # Signal for draw mode changes
    
    def __init__(self):
        super().__init__()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.check_keys)
        self.timer.start(16)  # Check every 16ms (~60 FPS) for more responsive key detection
        
        # Track previous key states to detect key press events (not just held keys)
        self._prev_alt_1 = False
        self._prev_alt_2 = False
        self._prev_alt_3 = False
        self._prev_alt_4 = False

    def check_keys(self):
        global _ctrl_pressed, _shift_pressed
        current_platform = get_platform()
        
        if current_platform == "windows":
            try:
                _ctrl_pressed = (ctypes.windll.user32.GetAsyncKeyState(VK_LCONTROL) & 0x8000) or \
                               (ctypes.windll.user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000)
                _shift_pressed = (ctypes.windll.user32.GetAsyncKeyState(VK_LSHIFT) & 0x8000) or \
                                (ctypes.windll.user32.GetAsyncKeyState(VK_RSHIFT) & 0x8000)
            except:
                pass
        elif current_platform == "darwin":  # macOS
            try:
                # Try to use pyobjc for global key detection
                import objc
                from Cocoa import NSEvent
                # Get current event modifier flags - this works globally without focus
                flags = NSEvent.modifierFlags()
                # Check for CMD key (⌘) and Shift key using proper constants
                _ctrl_pressed = bool(flags & 0x100000)  # NSEventModifierFlagCommand
                _shift_pressed = bool(flags & 0x020000)  # NSEventModifierFlagShift
            except (ImportError, AttributeError):
                # Fallback: Use Qt with a more robust approach
                try:
                    app = QtWidgets.QApplication.instance()
                    if app:
                        modifiers = app.queryKeyboardModifiers()  # Use queryKeyboardModifiers for global state
                        _ctrl_pressed = bool(modifiers & QtCore.Qt.MetaModifier)  # CMD key on Mac
                        _shift_pressed = bool(modifiers & QtCore.Qt.ShiftModifier)
                except:
                    # Last resort: check if any windows have focus and use their modifiers
                    try:
                        app = QtWidgets.QApplication.instance()
                        if app:
                            # Check if we can get global modifier state
                            modifiers = QtWidgets.QApplication.keyboardModifiers()
                            _ctrl_pressed = bool(modifiers & QtCore.Qt.MetaModifier)  # CMD key
                            _shift_pressed = bool(modifiers & QtCore.Qt.ShiftModifier)
                    except:
                        pass
        else:  # Linux
            try:
                # Use Qt to check for CTRL key on Linux
                app = QtWidgets.QApplication.instance()
                if app:
                    modifiers = app.keyboardModifiers()
                    _ctrl_pressed = bool(modifiers & QtCore.Qt.ControlModifier)
                    _shift_pressed = bool(modifiers & QtCore.Qt.ShiftModifier)
            except:
                pass
        
        # Check for Alt+1-4 key combinations to change draw modes
        self._check_draw_mode_shortcuts(current_platform)
    
    def _check_draw_mode_shortcuts(self, current_platform: str):
        """Check for Alt+1-4 shortcuts and emit draw mode changes."""
        if current_platform == "windows":
            try:
                # Check if Alt is pressed
                alt_pressed = (ctypes.windll.user32.GetAsyncKeyState(VK_LALT) & 0x8000) or \
                             (ctypes.windll.user32.GetAsyncKeyState(VK_RALT) & 0x8000)
                
                if alt_pressed:
                    # Check for number keys 1-4
                    alt_1 = bool(ctypes.windll.user32.GetAsyncKeyState(VK_1) & 0x8000)
                    alt_2 = bool(ctypes.windll.user32.GetAsyncKeyState(VK_2) & 0x8000)
                    alt_3 = bool(ctypes.windll.user32.GetAsyncKeyState(VK_3) & 0x8000)
                    alt_4 = bool(ctypes.windll.user32.GetAsyncKeyState(VK_4) & 0x8000)
                    
                    # Detect key press events (not just held keys)
                    if alt_1 and not self._prev_alt_1:
                        self.draw_mode_changed.emit(DrawMode.FREEHAND)
                    elif alt_2 and not self._prev_alt_2:
                        self.draw_mode_changed.emit(DrawMode.RECTANGLE)
                    elif alt_3 and not self._prev_alt_3:
                        self.draw_mode_changed.emit(DrawMode.CIRCLE)
                    elif alt_4 and not self._prev_alt_4:
                        self.draw_mode_changed.emit(DrawMode.ARROW)
                    
                    # Update previous states
                    self._prev_alt_1 = alt_1
                    self._prev_alt_2 = alt_2
                    self._prev_alt_3 = alt_3
                    self._prev_alt_4 = alt_4
                else:
                    # Reset previous states when Alt is not pressed
                    self._prev_alt_1 = False
                    self._prev_alt_2 = False
                    self._prev_alt_3 = False
                    self._prev_alt_4 = False
            except:
                pass
        else:
            # For macOS and Linux, use Qt key detection
            try:
                app = QtWidgets.QApplication.instance()
                if app:
                    modifiers = app.keyboardModifiers()
                    alt_pressed = bool(modifiers & QtCore.Qt.AltModifier)
                    
                    if alt_pressed:
                        # Note: Global number key detection on macOS/Linux is more complex
                        # For now, this provides the framework - full implementation would
                        # require platform-specific low-level key hooks
                        pass
            except:
                pass

def _init_key_monitor():
    global _key_monitor
    if _key_monitor is None:
        _key_monitor = GlobalKeyMonitor()

def ctrl_down() -> bool:
    """Check if the appropriate modifier key is pressed.
    
    Returns True when:
    - Windows/Linux: CTRL key is pressed
    - macOS: CMD key (⌘) is pressed - more natural for Mac users
    """
    return _ctrl_pressed

def shift_down() -> bool:
    return _shift_pressed

def caps_lock_on() -> bool:
    current_platform = get_platform()
    if current_platform == "windows":
        try:
            return bool(ctypes.windll.user32.GetKeyState(VK_CAPITAL) & 1)
        except:
            return False
    return False

def virtual_rect() -> QtCore.QRect:
    current_platform = get_platform()
    if current_platform == "windows":
        try:
            left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
            top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
            width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
            height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
            return QtCore.QRect(left, top, width, height)
        except:
            pass
    return QtWidgets.QApplication.desktop().screenGeometry()

def asset_path(*parts):
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = Path(__file__).parent
    return os.path.join(base_dir, *parts)

def set_run_at_startup(enable: bool) -> bool:
    current_platform = get_platform()
    app_path = sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{__file__}"'
    
    try:
        if current_platform == "windows":
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as k:
                if enable:
                    winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, app_path)
                else:
                    try:
                        winreg.DeleteValue(k, APP_NAME)
                    except FileNotFoundError:
                        pass
            return True
        elif current_platform == "darwin":
            plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.{APP_NAME.lower()}.plist")
            if enable:
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{APP_NAME.lower()}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{app_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
                with open(plist_path, 'w') as f:
                    f.write(plist_content)
            else:
                if os.path.exists(plist_path):
                    os.remove(plist_path)
            return True
        else:  # Linux
            desktop_path = os.path.expanduser(f"~/.config/autostart/{APP_NAME}.desktop")
            if enable:
                desktop_content = f"""[Desktop Entry]
Type=Application
Exec={app_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name={APP_NAME}
Comment=Beautiful mouse trails
"""
                os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
                with open(desktop_path, 'w') as f:
                    f.write(desktop_content)
            else:
                if os.path.exists(desktop_path):
                    os.remove(desktop_path)
            return True
    except Exception:
        return False

def is_run_at_startup():
    current_platform = get_platform()
    
    try:
        if current_platform == "windows":
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_READ) as k:
                val, _ = winreg.QueryValueEx(k, APP_NAME)
                return bool(val)
        elif current_platform == "darwin":
            plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.{APP_NAME.lower()}.plist")
            return os.path.exists(plist_path)
        else:  # Linux
            desktop_path = os.path.expanduser(f"~/.config/autostart/{APP_NAME}.desktop")
            return os.path.exists(desktop_path)
    except Exception:
        return False

# ------------------------- Config model -------------------------
@dataclass
class Config:
    color_start: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(170, 0, 255))    # Purple
    color_mid:   QtGui.QColor = field(default_factory=lambda: QtGui.QColor(255, 140, 0))   # Burnt Orange  
    color_end:   QtGui.QColor = field(default_factory=lambda: QtGui.QColor(255, 255, 0))   # Yellow
    # Rainbow colors (7 colors with blended transitions for smoother flow)
    rainbow_1: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(255, 0, 0))      # Red
    rainbow_2: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(255, 165, 0))    # Orange
    rainbow_3: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(255, 255, 0))    # Yellow
    rainbow_4: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(0, 200, 55))     # Green with a little blue
    rainbow_5: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(75, 0, 180))     # Blue with a little purple
    rainbow_6: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(128, 0, 128))    # Purple
    rainbow_7: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(139, 69, 19))    # Brown
    fade_seconds: float = 1.5
    stroke_thickness: int = 16    # Core thickness (stroke thickness) - 16 pixel diameter
    glow_percent: int = 0         # Glow percentage (0% = no glow by default)
    gradient_layers: int = 6      # Number of gradient layers (2-25) for smooth glow
    ema_alpha:    float = 0.35
    min_dist_px:  float = 3.5
    tension:      float = 1.0  # Catmull–Rom tension
    fade_slowdown: float = 2.5  # Controls fade curve (1.0=linear, higher=slower fade)
    num_colors: int = 3  # Number of colors in gradient (1, 2, 3, or 4=rainbow)
    particles_enabled: bool = True  # Enable/disable particle explosions
    explosion_frequency: float = 15.0  # Explosions per second (increased for better fast movement coverage)
    explosion_intensity: float = 1.0  # Explosion intensity multiplier (0.1 = light, 3.0 = massive)
    comet_enabled: bool = True  # Enable/disable comet tails
    draw_mode: DrawMode = DrawMode.FREEHAND  # Drawing mode (freehand, rectangle, circle)

    @staticmethod
    def _qcolor_to_hex(c: QtGui.QColor) -> str:
        return "#{:02X}{:02X}{:02X}".format(c.red(), c.green(), c.blue())

    @staticmethod
    def _hex_to_qcolor(txt: str, fallback: QtGui.QColor) -> QtGui.QColor:
        c = QtGui.QColor(txt)
        return c if c.isValid() else fallback
    
    @property
    def core_width(self) -> int:
        """Get core width (same as stroke thickness)."""
        return self.stroke_thickness
    
    @property 
    def glow_width(self) -> int:
        """Calculate glow width using formula: stroke_thickness + (stroke_thickness * glow_percent/100)."""
        return int(self.stroke_thickness + (self.stroke_thickness * self.glow_percent / 100))

    def update_colors_for_scheme(self):
        """Update colors based on the selected number of colors scheme"""
        if self.num_colors == 1:
            # 1 color: Cyan
            self.color_start = QtGui.QColor(0, 255, 255)  # Cyan
            self.color_mid = QtGui.QColor(0, 255, 255)    # Same
            self.color_end = QtGui.QColor(0, 255, 255)    # Same
        elif self.num_colors == 2:
            # 2 colors: Burnt Orange -> Yellow
            self.color_start = QtGui.QColor(255, 140, 0)  # Burnt Orange
            self.color_mid = QtGui.QColor(255, 200, 0)    # Interpolated
            self.color_end = QtGui.QColor(255, 255, 0)    # Yellow
        elif self.num_colors == 3:
            # 3 colors: Purple -> Burnt Orange -> Yellow
            self.color_start = QtGui.QColor(170, 0, 255)  # Purple
            self.color_mid = QtGui.QColor(255, 140, 0)    # Burnt Orange
            self.color_end = QtGui.QColor(255, 255, 0)    # Yellow
        else:  # 4 colors (rainbow)
            # Rainbow: no color scheme updates needed - uses rainbow_1 through rainbow_6
            pass

    def save(self, s: QtCore.QSettings):
        s.setValue("color_start", self._qcolor_to_hex(self.color_start))
        s.setValue("color_mid",   self._qcolor_to_hex(self.color_mid))
        s.setValue("color_end",   self._qcolor_to_hex(self.color_end))
        s.setValue("rainbow_1", self._qcolor_to_hex(self.rainbow_1))
        s.setValue("rainbow_2", self._qcolor_to_hex(self.rainbow_2))
        s.setValue("rainbow_3", self._qcolor_to_hex(self.rainbow_3))
        s.setValue("rainbow_4", self._qcolor_to_hex(self.rainbow_4))
        s.setValue("rainbow_5", self._qcolor_to_hex(self.rainbow_5))
        s.setValue("rainbow_6", self._qcolor_to_hex(self.rainbow_6))
        s.setValue("rainbow_7", self._qcolor_to_hex(self.rainbow_7))
        s.setValue("fade_seconds", self.fade_seconds)
        s.setValue("stroke_thickness", self.stroke_thickness)
        s.setValue("glow_percent", self.glow_percent)
        s.setValue("gradient_layers", self.gradient_layers)
        s.setValue("ema_alpha",    self.ema_alpha)
        s.setValue("min_dist_px",  self.min_dist_px)
        s.setValue("tension",      self.tension)
        s.setValue("fade_slowdown", self.fade_slowdown)
        s.setValue("num_colors", self.num_colors)
        s.setValue("particles_enabled", self.particles_enabled)
        s.setValue("explosion_frequency", self.explosion_frequency)
        s.setValue("explosion_intensity", self.explosion_intensity)
        s.setValue("comet_enabled", self.comet_enabled)
        s.setValue("draw_mode", self.draw_mode.value)

    @staticmethod
    def load(s: QtCore.QSettings) -> "Config":
        cfg = Config()
        cfg.color_start = Config._hex_to_qcolor(s.value("color_start", "#AA00FF"), QtGui.QColor(170, 0, 255))
        cfg.color_mid   = Config._hex_to_qcolor(s.value("color_mid",   "#FF8C00"), QtGui.QColor(255, 140, 0))
        cfg.color_end   = Config._hex_to_qcolor(s.value("color_end",   "#FFFF00"), QtGui.QColor(255, 255, 0))
        cfg.rainbow_1   = Config._hex_to_qcolor(s.value("rainbow_1",   "#FF0000"), QtGui.QColor(255, 0, 0))
        cfg.rainbow_2   = Config._hex_to_qcolor(s.value("rainbow_2",   "#FFA500"), QtGui.QColor(255, 165, 0))
        cfg.rainbow_3   = Config._hex_to_qcolor(s.value("rainbow_3",   "#FFFF00"), QtGui.QColor(255, 255, 0))
        cfg.rainbow_4   = Config._hex_to_qcolor(s.value("rainbow_4",   "#00C837"), QtGui.QColor(0, 200, 55))
        cfg.rainbow_5   = Config._hex_to_qcolor(s.value("rainbow_5",   "#4B00B4"), QtGui.QColor(75, 0, 180))
        cfg.rainbow_6   = Config._hex_to_qcolor(s.value("rainbow_6",   "#800080"), QtGui.QColor(128, 0, 128))
        cfg.rainbow_7   = Config._hex_to_qcolor(s.value("rainbow_7",   "#8B4513"), QtGui.QColor(139, 69, 19))
        cfg.fade_seconds = float(s.value("fade_seconds", cfg.fade_seconds))
        cfg.stroke_thickness = int(s.value("stroke_thickness", cfg.stroke_thickness))
        cfg.glow_percent = int(s.value("glow_percent", cfg.glow_percent))
        cfg.gradient_layers = int(s.value("gradient_layers", cfg.gradient_layers))
        cfg.ema_alpha    = float(s.value("ema_alpha",  cfg.ema_alpha))
        cfg.min_dist_px  = float(s.value("min_dist_px", cfg.min_dist_px))
        cfg.tension      = float(s.value("tension",     cfg.tension))
        cfg.fade_slowdown = float(s.value("fade_slowdown", cfg.fade_slowdown))
        cfg.num_colors = int(s.value("num_colors", cfg.num_colors))
        cfg.particles_enabled = s.value("particles_enabled", cfg.particles_enabled, type=bool)
        cfg.explosion_frequency = float(s.value("explosion_frequency", cfg.explosion_frequency))
        cfg.explosion_intensity = float(s.value("explosion_intensity", cfg.explosion_intensity))
        cfg.comet_enabled = s.value("comet_enabled", cfg.comet_enabled, type=bool)
        draw_mode_str = s.value("draw_mode", cfg.draw_mode.value)
        try:
            cfg.draw_mode = DrawMode(draw_mode_str)
        except ValueError:
            cfg.draw_mode = DrawMode.FREEHAND
        return cfg

# ------------------------- Overlay window -------------------------
@dataclass
class TrailPoint:
    x: int; y: int; t: float; stroke: int; age: float = 0.0

@dataclass
class Spark:
    x: float; y: float; vx: float; vy: float; t: float; life: float; is_trail: bool = False

@dataclass
class Comet:
    x: float; y: float; vx: float; vy: float; t: float; life: float; size: float

class ParticleUpdateThread(QtCore.QThread):
    """Background thread for updating particle physics to improve performance."""
    
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.running = True
        self.daemon = True
    
    def run(self):
        """Main thread loop - updates particles at ~60 FPS in background."""
        while self.running:
            start_time = time.time()
            
            # Only update if not paused
            if not self.overlay.paused:
                now = time.time()
                
                # Check if position updates should be paused
                position_paused = shift_down() or caps_lock_on()
                
                # Thread-safe particle updates
                with self.overlay.particle_lock:
                    if position_paused:
                        # Don't update positions, but do check for cleanup (aging still works)
                        self.overlay._cleanup_particles_only(now)
                    else:
                        # Update positions normally
                        self.overlay._update_sparks_threaded(now)
                        self.overlay._update_comets_threaded(now)
            
            # Maintain ~60 FPS (16ms per frame)
            elapsed = time.time() - start_time
            sleep_time = max(0, 0.016 - elapsed)
            time.sleep(sleep_time)
    
    def stop(self):
        """Stop the thread gracefully."""
        self.running = False
        self.wait()

class Overlay(QtWidgets.QWidget):
    paused_changed = QtCore.pyqtSignal(bool)

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(QtCore.Qt.Tool, True)

        vr = virtual_rect()
        self.setGeometry(vr.left(), vr.top(), vr.width(), vr.height())
        self.vr = vr

        self.points: List[TrailPoint] = []
        self.sparks: List[Spark] = []
        self.comets: List[Comet] = []
        self.stroke_id = 0
        self.prev_ctrl = False
        self._ema_xy: Optional[Tuple[float, float]] = None
        self._last_explosion_time: float = 0.0  # Track time for explosion intervals
        self._last_explosion_pos: Optional[Tuple[float, float]] = None  # Track last explosion position
        self._last_explosion_stroke: int = -1  # Track which stroke the last explosion belonged to
        self._last_comet_time: float = 0.0  # Track time for comet generation
        self._last_comet_pos: Optional[Tuple[float, float]] = None  # Track last position where comets were generated
        self._prev_mouse_pos: Optional[Tuple[float, float]] = None  # Track previous mouse position for direction
        self.paused = False
        
        # Shape mode tracking
        self._shape_start: Optional[Tuple[float, float]] = None  # Shape start position
        self._shape_active: bool = False  # Currently drawing shape
        self._temp_points: List[TrailPoint] = []  # Temporary points for current shape (cleared each frame)
        
        # Frozen time system for Shift/Caps Lock pause
        self._frozen_time: Optional[float] = None
        self._time_when_frozen: Optional[float] = None
        self._total_pause_time: float = 0.0  # Total time spent paused
        
        # Thread-safe particle updates
        self.particle_lock = threading.Lock()
        self.particle_thread = ParticleUpdateThread(self)
        self.particle_thread.start()

        self.core_pen = QtGui.QPen(self.cfg.color_start)
        self.core_pen.setWidth(self.cfg.core_width)
        self.core_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.core_pen.setJoinStyle(QtCore.Qt.RoundJoin)

        self.glow_pen = QtGui.QPen(self.cfg.color_start)
        self.glow_pen.setWidth(self.cfg.glow_width)
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.glow_pen.setJoinStyle(QtCore.Qt.RoundJoin)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)  # ~60 FPS
    
    def closeEvent(self, event):
        """Clean up the particle update thread when closing."""
        if hasattr(self, 'particle_thread'):
            self.particle_thread.stop()
        super().closeEvent(event)

    # ----- config updates -----
    def apply_config(self, cfg: Config):
        self.cfg = cfg
        self.core_pen.setWidth(self.cfg.core_width)
        self.glow_pen.setWidth(self.cfg.glow_width)
        # color is per-segment based on age; pen colors are set each draw
        self.update()

    def set_paused(self, p: bool):
        self.paused = p
        self.paused_changed.emit(p)
    
    def change_draw_mode(self, mode: DrawMode, settings: QtCore.QSettings):
        """Change the drawing mode via keyboard shortcut and save to settings."""
        self.cfg.draw_mode = mode
        self.cfg.save(settings)  # Persist the change
    
    def get_effective_time(self) -> float:
        """Get current time, but frozen during Shift/Caps Lock pause."""
        now = time.time()
        
        # Check if we should be frozen
        should_be_frozen = shift_down() or caps_lock_on()
        
        if should_be_frozen:
            if self._frozen_time is None:
                # Just started freezing - capture current time
                self._frozen_time = now
                self._time_when_frozen = now
            # Return the frozen time
            return self._frozen_time
        else:
            if self._frozen_time is not None:
                # Just unfroze - track total pause time
                frozen_duration = now - self._time_when_frozen
                self._total_pause_time += frozen_duration
                self._frozen_time = None
                self._time_when_frozen = None
            # Return normal time minus total pause time
            return now - self._total_pause_time
    
    def get_adjusted_age(self, creation_time: float, current_time: float) -> float:
        """Calculate age accounting for pause time."""
        # If we're currently paused, use the time when we started pausing
        if self._frozen_time is not None:
            return self._frozen_time - creation_time - self._total_pause_time
        else:
            return current_time - creation_time - self._total_pause_time
    
    def _create_rectangle(self, start: Tuple[float, float], end: Tuple[float, float], now: float, temporary: bool = False):
        """Create rectangle trail points from start corner to end corner."""
        start_x, start_y = start
        end_x, end_y = end
        
        # Create rectangle corners
        corners = [
            (start_x, start_y),  # Top-left (start)
            (end_x, start_y),    # Top-right
            (end_x, end_y),      # Bottom-right (end)
            (start_x, end_y),    # Bottom-left
            (start_x, start_y)   # Back to start to close rectangle
        ]
        
        # Create trail points along rectangle edges
        points_per_edge = 10  # Number of points per edge for smooth rendering
        points = []
        
        for i in range(len(corners) - 1):
            corner1 = corners[i]
            corner2 = corners[i + 1]
            
            # Interpolate points along this edge
            for j in range(points_per_edge + (1 if i == len(corners) - 2 else 0)):  # Add extra point for final edge
                t = j / points_per_edge
                x = corner1[0] + (corner2[0] - corner1[0]) * t
                y = corner1[1] + (corner2[1] - corner1[1]) * t
                point = TrailPoint(int(x), int(y), now, self.stroke_id)
                points.append(point)
        
        if temporary:
            self._temp_points = points
        else:
            self.points.extend(points)
    
    def _create_circle(self, center: Tuple[float, float], end: Tuple[float, float], now: float, temporary: bool = False):
        """Create circle trail points with center and radius from center to end."""
        center_x, center_y = center
        end_x, end_y = end
        
        # Calculate radius
        radius = math.sqrt((end_x - center_x)**2 + (end_y - center_y)**2)
        
        # Create circle points
        num_points = max(20, int(radius * 0.5))  # More points for larger circles
        points = []
        
        for i in range(num_points):
            angle = (2 * math.pi * i) / num_points
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            point = TrailPoint(int(x), int(y), now, self.stroke_id)
            points.append(point)
        
        if temporary:
            self._temp_points = points
        else:
            self.points.extend(points)
    
    def _create_arrow(self, tip: Tuple[float, float], tail: Tuple[float, float], now: float, temporary: bool = False):
        """Create arrow trail points with tip at start and tail at end."""
        tip_x, tip_y = tip
        tail_x, tail_y = tail
        
        # Calculate main arrow shaft vector
        shaft_dx = tip_x - tail_x
        shaft_dy = tip_y - tail_y
        shaft_length = math.sqrt(shaft_dx**2 + shaft_dy**2)
        
        if shaft_length == 0:
            return  # No arrow if no distance
        
        # Normalize shaft vector
        shaft_unit_x = shaft_dx / shaft_length
        shaft_unit_y = shaft_dy / shaft_length
        
        # Calculate arrowhead length: min(half shaft length, 10x stroke thickness)
        arrowhead_length = min(shaft_length / 2, self.cfg.stroke_thickness * 10)
        
        # Calculate 45-degree angles from the shaft direction (going backwards from tip)
        cos_45 = math.cos(math.radians(45))
        sin_45 = math.sin(math.radians(45))
        
        # Reverse shaft direction (pointing backwards from tip)
        reverse_shaft_x = -shaft_unit_x
        reverse_shaft_y = -shaft_unit_y
        
        # Rotate reverse shaft direction by +45 degrees for first barb
        barb1_unit_x = reverse_shaft_x * cos_45 + reverse_shaft_y * sin_45
        barb1_unit_y = -reverse_shaft_x * sin_45 + reverse_shaft_y * cos_45
        barb1_x = tip_x + arrowhead_length * barb1_unit_x
        barb1_y = tip_y + arrowhead_length * barb1_unit_y
        
        # Rotate reverse shaft direction by -45 degrees for second barb
        barb2_unit_x = reverse_shaft_x * cos_45 - reverse_shaft_y * sin_45
        barb2_unit_y = reverse_shaft_x * sin_45 + reverse_shaft_y * cos_45
        barb2_x = tip_x + arrowhead_length * barb2_unit_x
        barb2_y = tip_y + arrowhead_length * barb2_unit_y
        
        # Create three separate strokes: main shaft, and two barbs
        points = []
        points_per_stroke = 10
        
        # Use consistent stroke IDs for both temporary and permanent arrows
        if temporary:
            # For temporary arrows, use negative IDs to completely avoid conflicts
            base_stroke_id = -1000
        else:
            # For permanent arrows, use current stroke_id and increment it
            base_stroke_id = self.stroke_id
            self.stroke_id += 3  # Reserve 3 stroke IDs
        
        # Stroke 1: Main shaft from tail to tip
        shaft_stroke_id = base_stroke_id
        for i in range(points_per_stroke + 1):
            t = i / points_per_stroke
            x = tail_x + (tip_x - tail_x) * t
            y = tail_y + (tip_y - tail_y) * t
            points.append(TrailPoint(int(x), int(y), now, shaft_stroke_id))
        
        # Stroke 2: First barb from tip to barb1 (separate stroke ID)
        barb1_stroke_id = base_stroke_id + 1
        for i in range(points_per_stroke + 1):  
            t = i / points_per_stroke
            x = tip_x + (barb1_x - tip_x) * t
            y = tip_y + (barb1_y - tip_y) * t
            points.append(TrailPoint(int(x), int(y), now, barb1_stroke_id))
        
        # Stroke 3: Second barb from tip to barb2 (separate stroke ID)
        barb2_stroke_id = base_stroke_id + 2
        for i in range(points_per_stroke + 1):  
            t = i / points_per_stroke
            x = tip_x + (barb2_x - tip_x) * t
            y = tip_y + (barb2_y - tip_y) * t
            points.append(TrailPoint(int(x), int(y), now, barb2_stroke_id))
        
        if temporary:
            self._temp_points = points
        else:
            self.points.extend(points)

    # ----- sampling / smoothing -----
    def tick(self):
        # Use effective time (frozen during Shift/Caps Lock)
        now = self.get_effective_time()
        real_now = time.time()  # Keep real time for frame timing
        
        # Increment age for all trail points (only when not frozen by Shift/Caps Lock)
        if not shift_down() and not caps_lock_on():
            for point in self.points:
                point.age += 0.016  # 16ms increment
        
        if not self.paused:
            pressed = ctrl_down()
            if pressed and not self.prev_ctrl:
                # CTRL just pressed
                self.stroke_id += 1
                self._ema_xy = None
                self._last_explosion_time = now  # Reset explosion timer
                self._last_explosion_pos = None  # Reset explosion position tracking (no curve particles between strokes)
                self._last_comet_time = now  # Reset comet timer
                self._last_comet_pos = None  # Reset comet position tracking
                self._prev_mouse_pos = None  # Reset mouse direction tracking
                
                # Handle shape modes
                if self.cfg.draw_mode != DrawMode.FREEHAND:
                    rx, ry = pyautogui.position()
                    self._shape_start = (float(rx), float(ry))
                    self._shape_active = True
                    # Clear any existing trail points from current stroke to avoid interference
                    self.points = [p for p in self.points if p.stroke != self.stroke_id]
                    
            if not pressed and self.prev_ctrl:
                # CTRL just released
                if self.cfg.draw_mode != DrawMode.FREEHAND and self._shape_active:
                    # Complete shape
                    rx, ry = pyautogui.position()
                    if self._shape_start:
                        if self.cfg.draw_mode == DrawMode.RECTANGLE:
                            self._create_rectangle(self._shape_start, (float(rx), float(ry)), now)
                        elif self.cfg.draw_mode == DrawMode.CIRCLE:
                            self._create_circle(self._shape_start, (float(rx), float(ry)), now)
                        elif self.cfg.draw_mode == DrawMode.ARROW:
                            self._create_arrow(self._shape_start, (float(rx), float(ry)), now)
                    self._shape_active = False
                    self._shape_start = None
                    
            if pressed and self.cfg.draw_mode == DrawMode.FREEHAND:
                rx, ry = pyautogui.position()
                if self._ema_xy is None:
                    sx, sy = float(rx), float(ry)
                else:
                    a = self.cfg.ema_alpha
                    sx = a * float(rx) + (1.0 - a) * self._ema_xy[0]
                    sy = a * float(ry) + (1.0 - a) * self._ema_xy[1]
                self._ema_xy = (sx, sy)

                accept = True
                if self.points and self.points[-1].stroke == self.stroke_id:
                    dx = sx - self.points[-1].x; dy = sy - self.points[-1].y
                    if (dx*dx + dy*dy) < (self.cfg.min_dist_px * self.cfg.min_dist_px):
                        accept = False
                if accept:
                    self.points.append(TrailPoint(int(sx), int(sy), now, self.stroke_id))
                
                # Generate explosions at regular time intervals while CTRL is held (if enabled)
                # Only generate when SHIFT is not held AND CAPS LOCK is off
                if not shift_down() and not caps_lock_on():
                    # Explosions happen based on frequency setting (explosions per second) OR distance moved
                    explosion_interval = 1.0 / self.cfg.explosion_frequency  # Convert frequency to interval
                    time_triggered = now - self._last_explosion_time >= explosion_interval
                    
                    # Also trigger based on distance for fast movement coverage
                    distance_triggered = False
                    if self._last_explosion_pos is not None:
                        dx = sx - self._last_explosion_pos[0]
                        dy = sy - self._last_explosion_pos[1]
                        distance_moved = (dx*dx + dy*dy) ** 0.5
                        # Trigger explosion if moved more than 40 pixels since last explosion
                        distance_triggered = distance_moved > 40
                    
                    if self.cfg.particles_enabled and (time_triggered or distance_triggered):
                        import random
                        # Generate explosion at current mouse position (thread-safe)
                        if random.random() < 1:  # 100% chance to generate explosion
                            intensity = random.choice([1, 1, 1, 2, 3])  # Vary intensity
                            with self.particle_lock:
                                # Generate main explosion
                                for _ in range(intensity):
                                    self._generate_sparks(sx, sy, now)
                                
                                # Generate intermediate particles along the curve if we have a previous explosion IN THE SAME STROKE
                                if self._last_explosion_pos is not None and self._last_explosion_stroke == self.stroke_id:
                                    self._generate_curve_particles(self._last_explosion_pos, (sx, sy), now)
                        
                        # Update last explosion position, time, and stroke
                        self._last_explosion_pos = (sx, sy)
                        self._last_explosion_stroke = self.stroke_id
                        self._last_explosion_time = now
                    
                    # Generate ice crystal tails continuously while CTRL is held (if enabled)
                    if self.cfg.comet_enabled and now - self._last_comet_time >= 0.001:  # 1000 generations per second
                        import random
                        import math
                        
                        # Generate comets with thread-safe access
                        with self.particle_lock:
                            # If we have a previous comet position, backfill the space between
                            if self._last_comet_pos is not None:
                                last_x, last_y = self._last_comet_pos
                                # Calculate distance between last position and current position
                                dx = sx - last_x
                                dy = sy - last_y
                                distance = math.sqrt(dx*dx + dy*dy)
                                
                                # Generate ice crystals along the path to fill the gap
                                if distance > 0:
                                    # Number of steps to fill the gap (every 2 pixels)
                                    steps = max(1, int(distance / 2))
                                    for step in range(steps + 1):
                                        # Interpolate position along the path
                                        t = step / max(1, steps)
                                        fill_x = last_x + dx * t
                                        fill_y = last_y + dy * t
                                        
                                        # Generate dense ice crystals at each fill position
                                        for _ in range(random.randint(0, 7)):  # Reduced crystals at each point
                                            self._generate_comet(fill_x, fill_y, now)
                            else:
                                # First generation - just generate at current position
                                for _ in range(random.randint(100, 300)):  # 100-300 ice crystals per generation
                                    self._generate_comet(sx, sy, now)
                        
                        # Update last comet position and time
                        self._last_comet_pos = (sx, sy)
                        self._last_comet_time = now
                
                # Update previous mouse position for direction calculation
                self._prev_mouse_pos = (sx, sy)
            
            # Clear temporary points from previous frame
            self._temp_points = []
            
            # Create temporary shape for current frame while CTRL is held
            if pressed and self.cfg.draw_mode != DrawMode.FREEHAND and self._shape_active and self._shape_start:
                rx, ry = pyautogui.position()
                # Only create temporary shape if mouse has moved significantly from start
                distance = ((rx - self._shape_start[0])**2 + (ry - self._shape_start[1])**2)**0.5
                if distance > 5:  # Minimum distance to avoid tiny shapes
                    if self.cfg.draw_mode == DrawMode.RECTANGLE:
                        self._create_rectangle(self._shape_start, (float(rx), float(ry)), now, temporary=True)
                    elif self.cfg.draw_mode == DrawMode.CIRCLE:
                        self._create_circle(self._shape_start, (float(rx), float(ry)), now, temporary=True)
                    elif self.cfg.draw_mode == DrawMode.ARROW:
                        self._create_arrow(self._shape_start, (float(rx), float(ry)), now, temporary=True)
                
            self.prev_ctrl = pressed

        # Remove trail points based on age instead of time
        if self.points:
            self.points = [p for p in self.points if p.age < self.cfg.fade_seconds]
        
        # Particle updates are now handled by background thread for better performance
        # No need to update sparks/comets here anymore
        
        self.update()

    # ----- utils -----
    def _to_local(self, x: float, y: float) -> Tuple[float, float]:
        return x - self.vr.left(), y - self.vr.top()

    def _catmull_rom_to_bezier(self, p0, p1, p2, p3, tension: float):
        c1 = QtCore.QPointF(p1.x() + (p2.x() - p0.x()) * (tension / 6.0),
                            p1.y() + (p2.y() - p0.y()) * (tension / 6.0))
        c2 = QtCore.QPointF(p2.x() - (p3.x() - p1.x()) * (tension / 6.0),
                            p2.y() - (p3.y() - p1.y()) * (tension / 6.0))
        return c1, c2

    # ----- sparks -----
    def _generate_sparks(self, x: float, y: float, now: float):
        """Generate massive asteroid-like explosion with particles flying everywhere."""
        import random
        import math
        
        # Mathematical formula for particle count based on intensity
        # Formula: base_particles * intensity^1.2 + random_variance
        # This creates exponential scaling for more dramatic effect at higher intensities
        base_particles = 20  # Base particle count
        intensity_factor = math.pow(self.cfg.explosion_intensity, 1.2)  # Exponential scaling
        calculated_particles = int(base_particles * intensity_factor)
        
        # Add random variance (±25% of calculated amount)
        variance = int(calculated_particles * 0.25)
        min_particles = max(1, calculated_particles - variance)
        max_particles = max(2, calculated_particles + variance)
        
        num_sparks = random.randint(min_particles, max_particles)
        
        for _ in range(num_sparks):
            # Generate explosion angle with upward bias
            angle = random.uniform(0, 2 * math.pi)
            # Bias particles to shoot upward initially (add upward velocity component)
            upward_bias = random.uniform(-80, -20)  # Strong upward initial velocity
            
            # Varied speeds for more chaotic, realistic asteroid explosion (2.5x bigger)
            speed = random.uniform(25, 200)  # 2.5x bigger explosion velocities (halved from 5x)
            
            # Add some randomness to the angle for more natural spread
            angle_variation = random.uniform(-0.3, 0.3)  # Small random variation
            final_angle = angle + angle_variation
            
            vx = math.cos(final_angle) * speed
            vy = math.sin(final_angle) * speed + upward_bias  # Add upward bias
            
            # Add some random "chaos" to make it less perfect
            chaos_factor = random.uniform(0.8, 1.2)
            vx *= chaos_factor
            vy *= chaos_factor
            
            # Longer lifetimes for bigger explosions
            life = random.uniform(1.5, 3.0)  # 2x longer life for bigger particles
            
            self.sparks.append(Spark(x, y, vx, vy, now, life, is_trail=False))
    
    def _generate_curve_particles(self, start_pos: Tuple[float, float], end_pos: Tuple[float, float], now: float):
        """Generate particles along the straight line between two explosion points."""
        import random
        import math
        
        start_x, start_y = start_pos
        end_x, end_y = end_pos
        
        # Calculate distance between explosions
        dx = end_x - start_x
        dy = end_y - start_y
        distance = math.sqrt(dx*dx + dy*dy)
        
        # Only generate intermediate particles if explosions are reasonably far apart
        if distance < 20:  # Too close, skip
            return
            
        # Number of intermediate particles based on distance (more particles for longer lines)
        num_particles = max(2, min(15, int(distance / 30)))  # 2-15 particles
        
        # Generate particles along a straight line between the two points
        for i in range(num_particles):
            # Calculate interpolation factor (0.0 to 1.0)
            t = (i + 1) / (num_particles + 1)  # Skip start and end points
            
            # Simple linear interpolation for straight line
            line_x = start_x + t * (end_x - start_x)
            line_y = start_y + t * (end_y - start_y)
            
            # Generate smaller, more subtle particles along the line
            for _ in range(random.randint(1, 3)):  # 1-3 particles per point
                # Small random offset from line point
                px = line_x + random.uniform(-5, 5)
                py = line_y + random.uniform(-5, 5)
                
                # Gentle upward velocity with some randomness
                vx = random.uniform(-20, 20)  # Gentle horizontal spread
                vy = random.uniform(-40, -10)  # Gentle upward motion
                
                # Shorter lifetime for intermediate particles
                life = random.uniform(0.8, 1.5)
                
                # Create spark with trail flag to distinguish from main explosions
                self.sparks.append(Spark(px, py, vx, vy, now, life, is_trail=True))
    
    def _update_sparks(self, now: float):
        """Update spark positions and remove expired ones with realistic physics."""
        dt = 0.016  # 16ms frame time
        
        # Update existing sparks
        for spark in self.sparks[:]:  # Copy list to avoid modification during iteration
            age = now - spark.t
            if age > spark.life:
                self.sparks.remove(spark)
                continue
            
            # Update position based on velocity
            spark.x += spark.vx * dt
            spark.y += spark.vy * dt
            
            # Cursor sparks: apply realistic firework physics
            # Gravity pulls down
            gravity = 200  # pixels per second squared
            spark.vy += gravity * dt
            
            # Air resistance/drag - slows down sparks over time
            drag_factor = 0.98  # Slight air resistance
            spark.vx *= drag_factor
            spark.vy *= drag_factor

    # ----- comets -----
    def _generate_comet(self, x: float, y: float, now: float):
        """Generate ice particles flying perpendicular to mouse movement direction."""
        import random
        import math
        
        # Start at cursor position with slight random offset
        comet_x = x + random.uniform(-3, 3)
        comet_y = y + random.uniform(-3, 3)
        
        # Calculate perpendicular direction based on mouse movement
        if self._prev_mouse_pos is not None:
            # Calculate mouse movement direction
            dx = x - self._prev_mouse_pos[0]
            dy = y - self._prev_mouse_pos[1]
            movement_magnitude = math.sqrt(dx*dx + dy*dy)
            
            if movement_magnitude > 0.5:  # Only if mouse is actually moving
                # Normalize movement direction
                move_dir_x = dx / movement_magnitude
                move_dir_y = dy / movement_magnitude
                
                # Calculate perpendicular directions (90 degrees left and right)
                perp_left_x = -move_dir_y
                perp_left_y = move_dir_x
                perp_right_x = move_dir_y
                perp_right_y = -move_dir_x
                
                # Randomly choose left or right perpendicular direction
                if random.random() < 0.5:
                    perp_x, perp_y = perp_left_x, perp_left_y
                else:
                    perp_x, perp_y = perp_right_x, perp_right_y
                
                # Add some angle variation (±30 degrees) for natural spread
                angle_variation = random.uniform(-0.52, 0.52)  # ±30 degrees in radians
                cos_var = math.cos(angle_variation)
                sin_var = math.sin(angle_variation)
                
                # Apply rotation to perpendicular direction
                final_x = perp_x * cos_var - perp_y * sin_var
                final_y = perp_x * sin_var + perp_y * cos_var
                
                # Set velocity with random speed (3x faster for 3x distance)
                speed = random.uniform(75, 180)  # 3x the original speed
                vx = final_x * speed
                vy = final_y * speed
            else:
                # If mouse isn't moving, use random radial direction
                angle = random.uniform(0, 2 * math.pi)
                speed = random.uniform(45, 105)  # 3x the original speed
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed
        else:
            # No previous position, use random direction
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(45, 105)  # 3x the original speed
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
        
        # Random size and lifetime for ice crystals (halved from previous)
        size = random.uniform(0.8, 2.5)
        life = random.uniform(0.75, 1.875)  # Halved again for better performance
        
        self.comets.append(Comet(comet_x, comet_y, vx, vy, now, life, size))
    
    def _update_comets(self, now: float):
        """Update ice crystal positions and remove expired ones."""
        dt = 0.016  # 16ms frame time
        
        # Update existing ice crystals
        for comet in self.comets[:]:  # Copy list to avoid modification during iteration
            age = now - comet.t
            if age > comet.life:
                self.comets.remove(comet)
                continue
            
            # Update position based on velocity
            comet.x += comet.vx * dt
            comet.y += comet.vy * dt
            
            # Ice crystal physics - very light and floaty
            drag_factor = 0.94  # High drag - ice crystals slow down quickly
            comet.vx *= drag_factor
            comet.vy *= drag_factor
            
            # Very light gravity - ice crystals float more than fall
            comet.vy += 15 * dt  # Very light gravity
            
            # Add slight random drift for natural ice crystal movement
            import random
            comet.vx += random.uniform(-2, 2) * dt
            comet.vy += random.uniform(-1, 1) * dt
    
    def _update_sparks_threaded(self, now: float):
        """Thread-safe version of _update_sparks for background processing."""
        dt = 0.016  # 16ms frame time
        
        # Update existing sparks (thread-safe)
        sparks_to_remove = []
        for i, spark in enumerate(self.sparks):
            age = self.get_adjusted_age(spark.t, now)
            if age > spark.life:
                sparks_to_remove.append(i)
                continue
            
            # Update position based on velocity
            spark.x += spark.vx * dt
            spark.y += spark.vy * dt
            
            # Cursor sparks: apply realistic firework physics
            # Gravity pulls down
            gravity = 200  # pixels per second squared
            spark.vy += gravity * dt
            
            # Air resistance/drag - slows down sparks over time
            drag_factor = 0.98  # Slight air resistance
            spark.vx *= drag_factor
            spark.vy *= drag_factor
        
        # Remove expired sparks (in reverse order to maintain indices)
        for i in reversed(sparks_to_remove):
            del self.sparks[i]
    
    def _cleanup_particles_only(self, now: float):
        """Remove expired particles without updating positions (for pause mode)."""
        # Clean up expired sparks
        sparks_to_remove = []
        for i, spark in enumerate(self.sparks):
            age = self.get_adjusted_age(spark.t, now)
            if age > spark.life:
                sparks_to_remove.append(i)
        
        for i in reversed(sparks_to_remove):
            del self.sparks[i]
        
        # Clean up expired comets
        comets_to_remove = []
        for i, comet in enumerate(self.comets):
            age = self.get_adjusted_age(comet.t, now)
            if age > comet.life:
                comets_to_remove.append(i)
        
        for i in reversed(comets_to_remove):
            del self.comets[i]
    
    def _update_comets_threaded(self, now: float):
        """Thread-safe version of _update_comets for background processing."""
        dt = 0.016  # 16ms frame time
        
        # Update existing ice crystals (thread-safe)
        comets_to_remove = []
        for i, comet in enumerate(self.comets):
            age = self.get_adjusted_age(comet.t, now)
            if age > comet.life:
                comets_to_remove.append(i)
                continue
            
            # Update position based on velocity
            comet.x += comet.vx * dt
            comet.y += comet.vy * dt
            
            # Ice crystal physics - very light and floaty
            drag_factor = 0.94  # High drag - ice crystals slow down quickly
            comet.vx *= drag_factor
            comet.vy *= drag_factor
            
            # Very light gravity - ice crystals float more than fall
            comet.vy += 15 * dt  # Very light gravity
            
            # Add slight random drift for natural ice crystal movement
            import random
            comet.vx += random.uniform(-2, 2) * dt
            comet.vy += random.uniform(-1, 1) * dt
        
        # Remove expired comets (in reverse order to maintain indices)
        for i in reversed(comets_to_remove):
            del self.comets[i]

    def _age_to_fade_and_color(self, age: float):
        life = max(0.0, min(1.0, age / self.cfg.fade_seconds))
        fade = 1.0 - life
        fade = math.pow(fade, 1/self.cfg.fade_slowdown)
        
        # Handle different numbers of colors based on the dropdown selection
        if self.cfg.num_colors == 1:
            # Single color: no gradient
            color = self.cfg.color_start
        elif self.cfg.num_colors == 2:
            # Two colors: simple gradient from start to end
            start_color = self.cfg.color_start
            end_color = self.cfg.color_end
            r = int(start_color.red()   + (end_color.red()   - start_color.red())   * life)
            g = int(start_color.green() + (end_color.green() - start_color.green()) * life)
            b = int(start_color.blue()  + (end_color.blue()  - start_color.blue())  * life)
            color = QtGui.QColor(r, g, b)
        elif self.cfg.num_colors == 3:
            # Three colors: gradient with middle transition at 50%
            start_color = self.cfg.color_start
            mid_color = self.cfg.color_mid
            end_color = self.cfg.color_end
            
            if life <= 0.5:
                # First half: start -> mid
                t = life * 2.0  # 0.0 to 1.0
                r = int(start_color.red()   + (mid_color.red()   - start_color.red())   * t)
                g = int(start_color.green() + (mid_color.green() - start_color.green()) * t)
                b = int(start_color.blue()  + (mid_color.blue()  - start_color.blue())  * t)
            else:
                # Second half: mid -> end
                t = (life - 0.5) * 2.0  # 0.0 to 1.0
                r = int(mid_color.red()   + (end_color.red()   - mid_color.red())   * t)
                g = int(mid_color.green() + (end_color.green() - mid_color.green()) * t)
                b = int(mid_color.blue()  + (end_color.blue()  - mid_color.blue())  * t)
            color = QtGui.QColor(r, g, b)
        else:  # 4 colors (rainbow)
            # Seven-color rainbow: Red -> Orange -> Yellow -> Green -> Blue -> Purple -> Brown
            colors = [
                self.cfg.rainbow_1,  # Red
                self.cfg.rainbow_2,  # Orange
                self.cfg.rainbow_3,  # Yellow
                self.cfg.rainbow_4,  # Green
                self.cfg.rainbow_5,  # Blue
                self.cfg.rainbow_6,  # Purple
                self.cfg.rainbow_7   # Brown
            ]
            
            # Determine which segment we're in (0-5 for 6 segments)
            segment_index = int(life * 6)
            segment_index = min(segment_index, 5)  # Clamp to valid range
            
            # Calculate t within the current segment
            t = (life * 6) - segment_index
            t = max(0.0, min(1.0, t))  # Clamp t to [0,1]
            
            # Get the two colors to interpolate between
            color1 = colors[segment_index]
            color2 = colors[min(segment_index + 1, 6)]  # Don't go beyond last color
            
            # Linear interpolation between the two colors
            r = int(color1.red()   + (color2.red()   - color1.red())   * t)
            g = int(color1.green() + (color2.green() - color1.green()) * t)
            b = int(color1.blue()  + (color2.blue()  - color1.blue())  * t)
            color = QtGui.QColor(r, g, b)
        
        return fade, color

    def _set_pens_for_age(self, painter: QtGui.QPainter, age: float):
        fade, col = self._age_to_fade_and_color(age)
        
        # Store the base color for gradient drawing
        self._current_color = col
        self._current_fade = fade
        
        # Keep old pens for fallback
        glow_col = QtGui.QColor(col); glow_col.setAlpha(int(fade * 110))
        core_col = QtGui.QColor(col); core_col.setAlpha(int(fade * 230))
        self.glow_pen.setColor(glow_col); self.core_pen.setColor(core_col)
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.core_pen.setCapStyle(QtCore.Qt.FlatCap)
    
    def _draw_gradient_path(self, painter: QtGui.QPainter, path: QtGui.QPainterPath):
        """Draw path with solid core stroke and gradient glow layers."""
        col = self._current_color
        fade = self._current_fade
        
        # First, draw glow layers if glow is enabled
        if self.cfg.glow_percent > 0:
            num_layers = self.cfg.gradient_layers
            
            # Draw glow layers from outside to inside (only beyond the core stroke)
            for i in range(num_layers):
                # Calculate thickness for this glow layer (from glow_width down to just above core_width)
                layer_ratio = (num_layers - i) / num_layers  # 1.0 to 1/num_layers
                # Glow layers range from full glow_width down to slightly above core_width (don't affect base stroke)
                min_glow_thickness = self.cfg.core_width + 1  # Start glow just outside core stroke
                thickness = int(min_glow_thickness + (self.cfg.glow_width - min_glow_thickness) * layer_ratio)
                
                # Calculate alpha for smooth glow falloff (much more visible glow)
                # Make glow more visible: fade from 80 to 10 for better visibility
                alpha = int(fade * (80 - (layer_ratio * 70)))  # Fade from 80 to 10
                
                # Create pen for this glow layer
                glow_color = QtGui.QColor(col)
                glow_color.setAlpha(alpha)
                glow_pen = QtGui.QPen(glow_color, thickness)
                glow_pen.setCapStyle(QtCore.Qt.FlatCap)
                glow_pen.setJoinStyle(QtCore.Qt.MiterJoin)
                
                painter.setPen(glow_pen)
                painter.setBrush(QtCore.Qt.NoBrush)  # Ensure no fill for glow
                painter.drawPath(path)
        
        # Draw the solid core stroke on top (single pass only)
        core_color = QtGui.QColor(col)
        core_color.setAlpha(int(fade * 255))  # Full opacity for core
        core_pen = QtGui.QPen(core_color, self.cfg.core_width)
        core_pen.setCapStyle(QtCore.Qt.FlatCap)
        core_pen.setJoinStyle(QtCore.Qt.MiterJoin)
        
        painter.setPen(core_pen)
        painter.setBrush(QtCore.Qt.NoBrush)  # Ensure no fill
        painter.drawPath(path)  # Single draw call for main stroke

    def _draw_rounded_start(self, painter: QtGui.QPainter, start_point: QtCore.QPointF, age: float):
        """Draw a small rounded start at the very beginning of the trail."""
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        
        # Draw a small circle at the start point with core stroke radius
        core_radius = self.cfg.core_width / 4  # Make it smaller than full stroke width
        core_color = QtGui.QColor(col)
        core_color.setAlpha(int(fade * 255))  # Full opacity for core
        
        painter.setBrush(QtGui.QBrush(core_color))
        painter.setPen(QtCore.Qt.NoPen)
        
        # Draw small circle at the start
        painter.drawEllipse(start_point, core_radius, core_radius)

    def _draw_fat_start_cap(self, painter: QtGui.QPainter, start_point: QtCore.QPointF, age: float):
        """Draw a fat rounded cap at the very start of the trail."""
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        
        # Draw glow layers first if glow is enabled (same as trail)
        if self.cfg.glow_percent > 0:
            num_layers = self.cfg.gradient_layers
            
            # Draw gradient circles from outside to inside (glow)
            for i in range(num_layers):
                # Calculate radius for this glow layer (matches trail glow system)
                layer_ratio = (num_layers - i) / num_layers  # 1.0 to 1/num_layers
                min_glow_radius = (self.cfg.core_width + 1) / 2  # Start glow just outside core
                radius = min_glow_radius + ((self.cfg.glow_width / 2) - min_glow_radius) * layer_ratio
                
                # Calculate alpha for glow (same as trail glow)
                alpha = int(fade * (80 - (layer_ratio * 70)))  # Fade from 80 to 10
                
                # Create color for this glow layer
                glow_color = QtGui.QColor(col)
                glow_color.setAlpha(alpha)
                
                painter.setBrush(QtGui.QBrush(glow_color))
                painter.setPen(QtCore.Qt.NoPen)
                
                # Draw full circle for glow
                painter.drawEllipse(start_point, radius, radius)
        
        # Draw fat core cap on top (5% smaller)
        core_radius = (self.cfg.core_width / 2) * 0.95  # 5% smaller than full core width
        core_color = QtGui.QColor(col)
        core_color.setAlpha(int(fade * 255))  # Full opacity for core
        
        painter.setBrush(QtGui.QBrush(core_color))
        painter.setPen(QtCore.Qt.NoPen)
        
        # Draw fat core circle
        painter.drawEllipse(start_point, core_radius, core_radius)

    def _draw_fat_end_cap(self, painter: QtGui.QPainter, end_point: QtCore.QPointF, age: float):
        """Draw a fat rounded cap at the very end of the trail."""
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        
        # Draw glow layers first if glow is enabled (same as trail)
        if self.cfg.glow_percent > 0:
            num_layers = self.cfg.gradient_layers
            
            # Draw gradient circles from outside to inside (glow)
            for i in range(num_layers):
                # Calculate radius for this glow layer (matches trail glow system)
                layer_ratio = (num_layers - i) / num_layers  # 1.0 to 1/num_layers
                min_glow_radius = (self.cfg.core_width + 1) / 2  # Start glow just outside core
                radius = min_glow_radius + ((self.cfg.glow_width / 2) - min_glow_radius) * layer_ratio
                
                # Calculate alpha for glow (same as trail glow)
                alpha = int(fade * (80 - (layer_ratio * 70)))  # Fade from 80 to 10
                
                # Create color for this glow layer
                glow_color = QtGui.QColor(col)
                glow_color.setAlpha(alpha)
                
                painter.setBrush(QtGui.QBrush(glow_color))
                painter.setPen(QtCore.Qt.NoPen)
                
                # Draw full circle for glow
                painter.drawEllipse(end_point, radius, radius)
        
        # Draw fat core cap on top (5% smaller)
        core_radius = (self.cfg.core_width / 2) * 0.95  # 5% smaller than full core width
        core_color = QtGui.QColor(col)
        core_color.setAlpha(int(fade * 255))  # Full opacity for core
        
        painter.setBrush(QtGui.QBrush(core_color))
        painter.setPen(QtCore.Qt.NoPen)
        
        # Draw fat core circle
        painter.drawEllipse(end_point, core_radius, core_radius)

    def _draw_gradient_path_with_caps(self, painter: QtGui.QPainter, path: QtGui.QPainterPath, round_start: bool, round_end: bool):
        """Draw path with solid core stroke and gradient glow layers, with configurable cap styles."""
        col = self._current_color
        fade = self._current_fade
        
        # First, draw glow layers if glow is enabled
        if self.cfg.glow_percent > 0:
            num_layers = self.cfg.gradient_layers
            
            # Draw glow layers from outside to inside (only beyond the core stroke)
            for i in range(num_layers):
                # Calculate thickness for this glow layer (from glow_width down to just above core_width)
                layer_ratio = (num_layers - i) / num_layers  # 1.0 to 1/num_layers
                # Glow layers range from full glow_width down to slightly above core_width (don't affect base stroke)
                min_glow_thickness = self.cfg.core_width + 1  # Start glow just outside core stroke
                thickness = int(min_glow_thickness + (self.cfg.glow_width - min_glow_thickness) * layer_ratio)
                
                # Calculate alpha for smooth glow falloff (much more visible glow)
                alpha = int(fade * (80 - (layer_ratio * 70)))  # Fade from 80 to 10
                
                # Create pen for this glow layer with appropriate cap style
                glow_color = QtGui.QColor(col)
                glow_color.setAlpha(alpha)
                glow_pen = QtGui.QPen(glow_color, thickness)
                # Use rounded caps for first segment start, flat caps otherwise
                if round_start:
                    glow_pen.setCapStyle(QtCore.Qt.RoundCap)
                else:
                    glow_pen.setCapStyle(QtCore.Qt.FlatCap)
                glow_pen.setJoinStyle(QtCore.Qt.MiterJoin)
                
                painter.setPen(glow_pen)
                painter.drawPath(path)
        
        # Then draw the solid core stroke on top
        core_color = QtGui.QColor(col)
        core_color.setAlpha(int(fade * 255))  # Full opacity for core
        core_pen = QtGui.QPen(core_color, self.cfg.core_width)
        # Use rounded caps for first segment start, flat caps otherwise
        if round_start:
            core_pen.setCapStyle(QtCore.Qt.RoundCap)
        else:
            core_pen.setCapStyle(QtCore.Qt.FlatCap)
        core_pen.setJoinStyle(QtCore.Qt.MiterJoin)
        
        painter.setPen(core_pen)
        painter.drawPath(path)

    def _draw_half_cap(self, painter: QtGui.QPainter, x: int, y: int, direction_x: float, direction_y: float, age: float):
        """Draw a full circle cap with only core stroke thickness (no glow)"""
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        lx, ly = self._to_local(x, y)
        
        # Draw only a full circle with core stroke thickness (ignore glow)
        core_radius = self.cfg.core_width / 2
        core_color = QtGui.QColor(col)
        core_color.setAlpha(int(fade * 255))  # Full opacity for core
        
        painter.setBrush(QtGui.QBrush(core_color))
        painter.setPen(QtCore.Qt.NoPen)
        
        # Draw full circle (360 degrees) with core stroke size only
        painter.drawEllipse(QtCore.QPointF(lx, ly), core_radius, core_radius)

    def _draw_round_cap(self, painter: QtGui.QPainter, x: int, y: int, age: float):
        """Draw a round cap with smooth gradient matching the trail style"""
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        lx, ly = self._to_local(x, y)
        painter.setPen(QtCore.Qt.NoPen)

        # Use same number of gradient layers as the trail
        num_layers = self.cfg.gradient_layers
        
        # Draw gradient circles from outside to inside
        for i in range(num_layers):
            # Calculate radius for this layer
            layer_ratio = (num_layers - i) / num_layers  # 1.0 to 1/num_layers
            radius = (self.cfg.glow_width / 2) * layer_ratio
            
            # Calculate alpha for smooth falloff (same formula as trail)
            if i == 0:  # Outermost layer
                alpha = int(fade * 20)  # Very faint
            elif i == num_layers - 1:  # Center layer
                alpha = int(fade * 255)  # Full opacity
            else:
                # Smooth curve between outer and center
                t = i / (num_layers - 1)
                alpha = int(fade * (20 + (235 * t * t)))  # Quadratic curve for smooth falloff
            
            # Create color for this layer
            layer_color = QtGui.QColor(col)
            layer_color.setAlpha(alpha)
            
            painter.setBrush(QtGui.QBrush(layer_color))
            painter.drawEllipse(QtCore.QPointF(lx, ly), radius, radius)

    def _draw_sparks(self, painter: QtGui.QPainter, now: float):
        """Draw all active sparks with realistic cooling color transition."""
        painter.setPen(QtCore.Qt.NoPen)
        
        for spark in self.sparks:
            age = self.get_adjusted_age(spark.t, now)
            life_ratio = age / spark.life
            
            # Skip if spark is dead
            if life_ratio >= 1.0:
                continue
            
            # Convert to local coordinates
            lx, ly = self._to_local(spark.x, spark.y)
            
            # Smooth gradient fire colors with randomness: White -> Orange -> Red -> Brown -> Black
            import random
            
            # Add slight randomness to life_ratio for natural variation
            random_offset = random.uniform(-0.05, 0.05)  # ±5% variation
            varied_life = max(0.0, min(1.0, life_ratio + random_offset))

            # Add color randomness for natural variation
            color_variation = 15  # ±15 RGB units of variation
            
            
            # Define color keyframes for smooth interpolation
            if varied_life <= 0.1:  # 0-10%: White to bright orange
                t = varied_life / 0.1  # 0.0 to 1.0
                r = int(255)  # Keep white/orange red high
                g = int(255)
                b = int(255)
                color_variation = 0
                alpha = 255
            elif varied_life <= 0.25:  # 10-45%: Orange to red
                t = (varied_life - 0.1) / 0.35  # 0.0 to 1.0
                r = int(255)  # Keep red maxed
                g = int(165 - (165 - 50) * t)  # 165 to 50
                b = int(50 * (1 - t))  # 50 to 0
                alpha = 255
            elif varied_life <= 0.5:  # 45-70%: Red to brown
                t = (varied_life - 0.45) / 0.25  # 0.0 to 1.0
                r = int(255 - (255 - 120) * t)  # 255 to 120
                g = int(50 - (50 - 40) * t)  # 50 to 40
                b = int(20 * t)  # 0 to 20
                alpha = int(255 - 35 * t)  # 255 to 220
            else:  # 70-100%: Brown to black
                t = (varied_life - 0.7) / 0.3  # 0.0 to 1.0
                r = int(120 - (120 - 10) * t)  # 120 to 10
                g = int(40 - (40 - 10) * t)  # 40 to 10
                b = int(20 - 10 * t)  # 20 to 10
                alpha = int(220 - 100 * t)  # 220 to 120, then fade
            
            
            r = max(0, min(255, r + random.randint(-color_variation, color_variation)))
            g = max(0, min(255, g + random.randint(-color_variation, color_variation)))
            b = max(0, min(255, b + random.randint(-color_variation, color_variation)))
            
            spark_color = QtGui.QColor(r, g, b)
            
            spark_color.setAlpha(min(alpha, 255))

            # Main explosion particles: 2.5x bigger sizes (halved from 5x)
            if life_ratio < 0.083:  # Hot white phase - bigger and brighter (33% shorter)
                spark_size = max(1, int(6.25 * (1.0 - life_ratio * 0.5)))  # 2.5x bigger
                glow_size = int(3.75)  # 2.5x bigger
            elif life_ratio < 0.65:  # Cooling phase - medium size
                spark_size = max(1, int(3.75 * (1.0 - life_ratio * 0.8)))  # 2.5x bigger
                glow_size = int(2.5)  # 2.5x bigger
            else:  # Ember phase - small and dim
                spark_size = max(1, int(2.5 * (1.0 - life_ratio)))  # 2.5x bigger
                glow_size = int(1.25)  # 2.5x bigger
            
            # Outer glow (only for hot phases)
            if life_ratio < 0.65:
                glow_color = QtGui.QColor(spark_color)
                glow_color.setAlpha(int(alpha * 0.3))
                painter.setBrush(QtGui.QBrush(glow_color))
                painter.drawEllipse(QtCore.QPointF(lx, ly), spark_size + glow_size, spark_size + glow_size)
            
            # Draw spark as streak/explosion rather than just a dot
            # Calculate velocity-based streak direction and length
            velocity_magnitude = math.sqrt(spark.vx * spark.vx + spark.vy * spark.vy)
            if velocity_magnitude > 0.5:  # Only draw streaks for moving sparks
                # Calculate streak length based on velocity
                streak_length = min(velocity_magnitude * 0.5, spark_size * 3)
                
                # Calculate streak end position (opposite to velocity direction)
                streak_end_x = lx - (spark.vx / velocity_magnitude) * streak_length
                streak_end_y = ly - (spark.vy / velocity_magnitude) * streak_length
                
                # Draw streak line with gradient effect
                pen = QtGui.QPen(spark_color)
                pen.setWidth(max(1, spark_size // 2))
                pen.setCapStyle(QtCore.Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QtCore.QPointF(lx, ly), QtCore.QPointF(streak_end_x, streak_end_y))
                
                # Draw bright head of spark
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QBrush(spark_color))
                painter.drawEllipse(QtCore.QPointF(lx, ly), spark_size, spark_size)
            else:
                # For slow/stationary sparks, draw as circle
                painter.setBrush(QtGui.QBrush(spark_color))
                painter.drawEllipse(QtCore.QPointF(lx, ly), spark_size, spark_size)

    def _draw_comets(self, painter: QtGui.QPainter, now: float):
        """Draw ice crystal particles trailing behind the cursor."""
        painter.setPen(QtCore.Qt.NoPen)
        
        for comet in self.comets:
            age = self.get_adjusted_age(comet.t, now)
            life_ratio = age / comet.life
            
            # Skip if ice crystal is dead
            if life_ratio >= 1.0:
                continue
            
            # Convert to local coordinates
            lx, ly = self._to_local(comet.x, comet.y)
            
            # Create icy crystal colors (bright white/cyan to transparent)
            if life_ratio < 0.2:  # 0-20%: Bright icy white
                ice_color = QtGui.QColor(240, 250, 255)  # Very light blue-white
                alpha = 255
            elif life_ratio < 0.4:  # 20-40%: Light cyan
                ice_color = QtGui.QColor(200, 240, 255)  # Light cyan
                alpha = 220
            elif life_ratio < 0.7:  # 40-70%: Pale blue
                ice_color = QtGui.QColor(180, 220, 255)  # Pale blue
                alpha = 180
            else:  # 70-100%: Fade to transparent
                blend = (life_ratio - 0.7) / 0.3
                ice_color = QtGui.QColor(160, 200, 255)  # Light blue
                alpha = int(140 * (1.0 - blend))
            
            ice_color.setAlpha(alpha)
            
            # Size stays more consistent (ice crystals don't shrink as much)
            current_size = comet.size * (1.0 - life_ratio * 0.2)
            
            # Draw ice crystal with sparkle effect
            # Outer sparkle glow
            if life_ratio < 0.6:
                sparkle_color = QtGui.QColor(255, 255, 255)  # Pure white sparkle
                sparkle_color.setAlpha(int(alpha * 0.4))
                painter.setBrush(QtGui.QBrush(sparkle_color))
                painter.drawEllipse(QtCore.QPointF(lx, ly), current_size * 1.8, current_size * 1.8)
            
            # Main ice crystal body
            painter.setBrush(QtGui.QBrush(ice_color))
            painter.drawEllipse(QtCore.QPointF(lx, ly), current_size, current_size)
            
            # Add tiny bright center for ice crystal sparkle
            if life_ratio < 0.5:
                center_color = QtGui.QColor(255, 255, 255)
                center_color.setAlpha(int(alpha * 0.8))
                painter.setBrush(QtGui.QBrush(center_color))
                painter.drawEllipse(QtCore.QPointF(lx, ly), current_size * 0.3, current_size * 0.3)

    # ----- paint -----
    def paintEvent(self, ev: QtGui.QPaintEvent):
        if not self.points and not self.sparks and not self.comets and not self._temp_points: return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Draw trail
        if self.points:
            pts = self.points; n = len(pts); i = 0
            while i < n:
                j = i + 1; sid = pts[i].stroke
                while j < n and pts[j].stroke == sid: j += 1
                segment = pts[i:j]

                if len(segment) >= 2:
                    # Draw segments individually for proper color/alpha gradients
                    # but use a stroke-only approach to avoid filling on self-intersecting paths
                    start_point = None
                    end_point = None
                    
                    # Draw start cap first (underneath the trail)
                    if len(segment) > 0:
                        start_point = QtCore.QPointF(*self._to_local(segment[0].x, segment[0].y))
                        self._draw_fat_start_cap(painter, start_point, segment[0].age)
                    
                    for k in range(0, len(segment)-1):
                        p0 = segment[k-1] if k-1 >= 0 else segment[k]
                        p1 = segment[k]; p2 = segment[k+1]
                        p3 = segment[k+2] if (k+2) < len(segment) else segment[k+1]
                        P0 = QtCore.QPointF(*self._to_local(p0.x, p0.y))
                        P1 = QtCore.QPointF(*self._to_local(p1.x, p1.y))
                        P2 = QtCore.QPointF(*self._to_local(p2.x, p2.y))
                        P3 = QtCore.QPointF(*self._to_local(p3.x, p3.y))
                        C1, C2 = self._catmull_rom_to_bezier(P0, P1, P2, P3, self.cfg.tension)
                        path = QtGui.QPainterPath(P1); path.cubicTo(C1, C2, P2)

                        age = p2.age
                        fade, _ = self._age_to_fade_and_color(age)
                        if fade <= 0.0: continue
                        
                        # Draw segments with proper color/alpha gradients
                        self._set_pens_for_age(painter, age)
                        self._draw_gradient_path(painter, path)
                        
                        # Track end point for end cap
                        if k == len(segment) - 2:
                            end_point = P2
                    
                    # Add end cap on top of the trail
                    if end_point and len(segment) > 1:
                        self._draw_fat_end_cap(painter, end_point, segment[-1].age)

                    # No caps - using rounded corners for the start of first segment instead

                i = j
        
        # Draw temporary shape (rectangle/circle) with full trail styling
        if self._temp_points:
            temp_pts = self._temp_points
            if len(temp_pts) >= 2:
                # Treat temporary points as a single stroke segment
                segment = temp_pts
                
                # Draw start cap first (underneath the trail)
                if len(segment) > 0:
                    start_point = QtCore.QPointF(*self._to_local(segment[0].x, segment[0].y))
                    self._draw_fat_start_cap(painter, start_point, 0.0)  # Age 0 for full opacity
                
                # Draw segments with full trail styling (age 0 for full opacity)
                for k in range(0, len(segment)-1):
                    p0 = segment[k-1] if k-1 >= 0 else segment[k]
                    p1 = segment[k]; p2 = segment[k+1]
                    p3 = segment[k+2] if (k+2) < len(segment) else segment[k+1]
                    P0 = QtCore.QPointF(*self._to_local(p0.x, p0.y))
                    P1 = QtCore.QPointF(*self._to_local(p1.x, p1.y))
                    P2 = QtCore.QPointF(*self._to_local(p2.x, p2.y))
                    P3 = QtCore.QPointF(*self._to_local(p3.x, p3.y))
                    C1, C2 = self._catmull_rom_to_bezier(P0, P1, P2, P3, self.cfg.tension)
                    path = QtGui.QPainterPath(P1); path.cubicTo(C1, C2, P2)

                    # Draw with age 0 for full opacity and color
                    self._set_pens_for_age(painter, 0.0)
                    self._draw_gradient_path(painter, path)
                
                # Add end cap on top of the trail
                if len(segment) > 1:
                    end_point = QtCore.QPointF(*self._to_local(segment[-1].x, segment[-1].y))
                    self._draw_fat_end_cap(painter, end_point, 0.0)  # Age 0 for full opacity
        
        # Draw sparks (thread-safe)
        with self.particle_lock:
            self._draw_sparks(painter, time.time())
        
        # Draw comets (thread-safe)
        with self.particle_lock:
            self._draw_comets(painter, time.time())

# ------------------------- Settings dialog -------------------------
class SettingsDialog(QtWidgets.QDialog):
    config_changed = QtCore.pyqtSignal(Config)

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} Settings")
        self.setModal(False)
        self.setMinimumWidth(420)
        
        # Set window icon for taskbar
        self.setWindowIcon(self._create_settings_icon())
        
        self.cfg = cfg  # live reference

        def color_button(initial: QtGui.QColor):
            btn = QtWidgets.QPushButton()
            btn.setFixedWidth(60)
            btn.setStyleSheet(f"background-color: {initial.name()}; border: 1px solid #444;")
            return btn
        
        def rainbow_button():
            btn = QtWidgets.QPushButton()
            btn.setFixedWidth(60)
            btn.setFixedHeight(btn.sizeHint().height())
            
            # Create rainbow gradient pixmap
            pixmap = QtGui.QPixmap(60, btn.sizeHint().height())
            painter = QtGui.QPainter(pixmap)
            
            # Create rainbow gradient with 7 colors
            gradient = QtGui.QLinearGradient(0, 0, 60, 0)
            gradient.setColorAt(0.0, QtGui.QColor(255, 0, 0))    # Red
            gradient.setColorAt(0.167, QtGui.QColor(255, 165, 0)) # Orange
            gradient.setColorAt(0.333, QtGui.QColor(255, 255, 0)) # Yellow
            gradient.setColorAt(0.5, QtGui.QColor(0, 200, 55))   # Green
            gradient.setColorAt(0.667, QtGui.QColor(75, 0, 180)) # Blue
            gradient.setColorAt(0.833, QtGui.QColor(128, 0, 128)) # Purple
            gradient.setColorAt(1.0, QtGui.QColor(139, 69, 19))  # Brown
            
            painter.fillRect(pixmap.rect(), gradient)
            painter.end()
            
            btn.setIcon(QtGui.QIcon(pixmap))
            btn.setStyleSheet("border: 1px solid #444;")
            return btn

        # Widgets
        self.btn_start = color_button(self.cfg.color_start)
        self.btn_mid   = color_button(self.cfg.color_mid)
        self.btn_end   = color_button(self.cfg.color_end)
        self.btn_rainbow = rainbow_button()
        
        # Number of colors dropdown
        self.combo_num_colors = QtWidgets.QComboBox()
        self.combo_num_colors.addItems(["1 Color", "2 Colors", "3 Colors", "Rainbow"])
        self.combo_num_colors.setCurrentIndex(self.cfg.num_colors - 1)  # Convert 1,2,3,4 to 0,1,2,3
        
        # Fade slider (0.1-10 seconds with 0.1 intervals)
        self.slider_fade = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_fade.setRange(1, 100)  # 0.1 to 10.0 seconds (multiply by 0.1)
        self.slider_fade.setValue(int(self.cfg.fade_seconds * 10))
        
        self.spin_fade = QtWidgets.QDoubleSpinBox()
        self.spin_fade.setRange(0.1, 10.0); self.spin_fade.setSingleStep(0.1)
        self.spin_fade.setValue(self.cfg.fade_seconds)
        
        self.spin_fade_slowdown = QtWidgets.QDoubleSpinBox()
        self.spin_fade_slowdown.setRange(1.0, 3.0); self.spin_fade_slowdown.setSingleStep(0.1)
        self.spin_fade_slowdown.setValue(self.cfg.fade_slowdown)

        self.spin_stroke = QtWidgets.QSpinBox(); self.spin_stroke.setRange(1, 100); self.spin_stroke.setValue(self.cfg.stroke_thickness)
        self.spin_glow_percent = QtWidgets.QSpinBox(); self.spin_glow_percent.setRange(0, 200); self.spin_glow_percent.setValue(self.cfg.glow_percent); self.spin_glow_percent.setSuffix("%")
        self.spin_gradient_layers = QtWidgets.QSpinBox(); self.spin_gradient_layers.setRange(2, 25); self.spin_gradient_layers.setValue(self.cfg.gradient_layers)

        self.slider_stroke = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.slider_stroke.setRange(1, 100); self.slider_stroke.setValue(self.cfg.stroke_thickness)
        self.slider_glow_percent = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.slider_glow_percent.setRange(0, 200); self.slider_glow_percent.setValue(self.cfg.glow_percent)
        self.slider_gradient_layers = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.slider_gradient_layers.setRange(2, 25); self.slider_gradient_layers.setValue(self.cfg.gradient_layers)

        self.spin_ema  = QtWidgets.QDoubleSpinBox(); self.spin_ema.setRange(0.0, 1.0); self.spin_ema.setSingleStep(0.05); self.spin_ema.setValue(self.cfg.ema_alpha)
        self.spin_min  = QtWidgets.QDoubleSpinBox(); self.spin_min.setRange(0.0, 20.0); self.spin_min.setSingleStep(0.1); self.spin_min.setValue(self.cfg.min_dist_px)
        self.spin_tens = QtWidgets.QDoubleSpinBox(); self.spin_tens.setRange(0.2, 2.0); self.spin_tens.setSingleStep(0.1); self.spin_tens.setValue(self.cfg.tension)
        
        self.check_particles = QtWidgets.QCheckBox("Enable particle explosions"); self.check_particles.setChecked(self.cfg.particles_enabled)
        self.check_comets = QtWidgets.QCheckBox("Enable ice crystal trail"); self.check_comets.setChecked(self.cfg.comet_enabled)
        
        # Draw mode buttons
        self.draw_mode_group = QtWidgets.QButtonGroup()
        
        self.btn_freehand = QtWidgets.QPushButton("—◉")  # Straight line leading to spiral
        self.btn_freehand.setFixedSize(40, 30)
        self.btn_freehand.setCheckable(True)
        self.btn_freehand.setToolTip("Freehand Mode: Draw flowing trails")
        
        self.btn_rectangle = QtWidgets.QPushButton("□")  # Square for rectangle
        self.btn_rectangle.setFixedSize(40, 30)
        self.btn_rectangle.setCheckable(True)
        self.btn_rectangle.setToolTip("Rectangle Mode: Hold CTRL and drag to create rectangles")
        
        self.btn_circle = QtWidgets.QPushButton("○")  # Circle for circle
        self.btn_circle.setFixedSize(40, 30)
        self.btn_circle.setCheckable(True)
        self.btn_circle.setToolTip("Circle Mode: Hold CTRL from center to radius")
        
        self.btn_arrow = QtWidgets.QPushButton("↗")  # Arrow for arrow
        self.btn_arrow.setFixedSize(40, 30)
        self.btn_arrow.setCheckable(True)
        self.btn_arrow.setToolTip("Arrow Mode: Hold CTRL from tip to tail")
        
        # Add buttons to group for exclusive selection
        self.draw_mode_group.addButton(self.btn_freehand, 0)
        self.draw_mode_group.addButton(self.btn_rectangle, 1)
        self.draw_mode_group.addButton(self.btn_circle, 2)
        self.draw_mode_group.addButton(self.btn_arrow, 3)
        
        # Set initial selection
        if self.cfg.draw_mode == DrawMode.FREEHAND:
            self.btn_freehand.setChecked(True)
        elif self.cfg.draw_mode == DrawMode.RECTANGLE:
            self.btn_rectangle.setChecked(True)
        elif self.cfg.draw_mode == DrawMode.CIRCLE:
            self.btn_circle.setChecked(True)
        elif self.cfg.draw_mode == DrawMode.ARROW:
            self.btn_arrow.setChecked(True)
        
        # Explosion frequency slider and spinbox
        self.slider_explosion_freq = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_explosion_freq.setRange(1, 60)  # 1-60 explosions per second
        self.slider_explosion_freq.setValue(int(self.cfg.explosion_frequency))
        
        self.spin_explosion_freq = QtWidgets.QDoubleSpinBox()
        self.spin_explosion_freq.setRange(1.0, 60.0)
        self.spin_explosion_freq.setSingleStep(0.5)
        self.spin_explosion_freq.setValue(self.cfg.explosion_frequency)
        self.spin_explosion_freq.setSuffix(" /sec")
        
        # Explosion intensity slider and spinbox (Mathematical Formula: 20 * intensity^1.2)
        self.slider_explosion_intensity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_explosion_intensity.setRange(1, 50)  # 0.1x to 5.0x intensity (stored as 1-50, divided by 10)
        self.slider_explosion_intensity.setValue(int(self.cfg.explosion_intensity * 10))
        
        self.spin_explosion_intensity = QtWidgets.QDoubleSpinBox()
        self.spin_explosion_intensity.setRange(0.1, 5.0)
        self.spin_explosion_intensity.setSingleStep(0.1)
        self.spin_explosion_intensity.setValue(self.cfg.explosion_intensity)
        self.spin_explosion_intensity.setSuffix("x particles")

        # Main Layout - Basic Settings
        form = QtWidgets.QFormLayout()
        self.form = form  # Store reference for dynamic updates
        form.addRow("Color scheme:", self.combo_num_colors)
        
        # Color picker rows with labels (we'll show/hide these dynamically)
        self.label_start = QtWidgets.QLabel("Start color:")
        self.label_mid = QtWidgets.QLabel("Middle color:")
        self.label_end = QtWidgets.QLabel("End color:")
        self.label_rainbow = QtWidgets.QLabel("Rainbow:")
        
        form.addRow(self.label_start, self.btn_start)
        form.addRow(self.label_mid, self.btn_mid)  
        form.addRow(self.label_end, self.btn_end)
        form.addRow(self.label_rainbow, self.btn_rainbow)
        
        # Basic settings (always visible)
        strokeBox = QtWidgets.QHBoxLayout(); strokeBox.addWidget(self.slider_stroke); strokeBox.addWidget(self.spin_stroke)
        form.addRow("Stroke thickness:", strokeBox)        
        glowBox = QtWidgets.QHBoxLayout(); glowBox.addWidget(self.slider_glow_percent); glowBox.addWidget(self.spin_glow_percent)
        form.addRow("Glow %:", glowBox)
        fadeBox = QtWidgets.QHBoxLayout(); fadeBox.addWidget(self.slider_fade); fadeBox.addWidget(self.spin_fade)
        form.addRow("Fade (seconds):", fadeBox)
        
        # Draw mode buttons in horizontal layout
        draw_mode_layout = QtWidgets.QHBoxLayout()
        draw_mode_layout.addWidget(self.btn_freehand)
        draw_mode_layout.addWidget(self.btn_rectangle)
        draw_mode_layout.addWidget(self.btn_circle)
        draw_mode_layout.addWidget(self.btn_arrow)
        draw_mode_layout.addStretch()  # Push buttons to left
        draw_mode_widget = QtWidgets.QWidget()
        draw_mode_widget.setLayout(draw_mode_layout)
        form.addRow("Draw mode:", draw_mode_widget)

        # Advanced settings checkbox
        self.check_advanced = QtWidgets.QCheckBox("Show advanced settings")
        self.check_advanced.setChecked(False)  # Hidden by default
        form.addRow("", self.check_advanced)
        
        # Advanced settings group (initially hidden)
        self.adv_group = QtWidgets.QGroupBox("Advanced Settings")
        self.adv_group.setVisible(False)  # Hidden by default
        advForm = QtWidgets.QFormLayout(self.adv_group)
        
        # Move advanced settings into the group
        advForm.addRow("Fade slowdown:", self.spin_fade_slowdown)
        layersBox = QtWidgets.QHBoxLayout(); layersBox.addWidget(self.slider_gradient_layers); layersBox.addWidget(self.spin_gradient_layers)
        advForm.addRow("Gradient layers:", layersBox)
        advForm.addRow("", self.check_particles)  # Particle toggle
        advForm.addRow("", self.check_comets)  # Comet toggle
        
        # Explosion frequency with slider + spinbox
        explosionBox = QtWidgets.QHBoxLayout(); explosionBox.addWidget(self.slider_explosion_freq); explosionBox.addWidget(self.spin_explosion_freq)
        advForm.addRow("Explosion frequency:", explosionBox)
        
        # Explosion intensity with slider + spinbox
        intensityBox = QtWidgets.QHBoxLayout(); intensityBox.addWidget(self.slider_explosion_intensity); intensityBox.addWidget(self.spin_explosion_intensity)
        advForm.addRow("Particle count (20×i^1.2):", intensityBox)
        
        # Smoothing settings
        advForm.addRow("EMA α (smoothing):", self.spin_ema)
        advForm.addRow("Min spacing (px):", self.spin_min)
        advForm.addRow("Curve tension:", self.spin_tens)

        btn_close = QtWidgets.QPushButton("Close")
        btn_reset = QtWidgets.QPushButton("Reset defaults")

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1); buttons.addWidget(btn_reset); buttons.addWidget(btn_close)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(self.adv_group)  # Add the advanced group
        outer.addLayout(buttons)

        # Signals: color pickers
        self.btn_start.clicked.connect(lambda: self.pick_color("start"))
        self.btn_mid.clicked.connect(lambda: self.pick_color("mid"))
        self.btn_end.clicked.connect(lambda: self.pick_color("end"))
        
        # Signals: color scheme dropdown
        self.combo_num_colors.currentIndexChanged.connect(self.update_color_scheme)
        
        # Signals: advanced settings toggle
        self.check_advanced.toggled.connect(self.toggle_advanced_settings)
        
        # Initialize color picker visibility
        self.update_color_picker_visibility()

        # link sliders & spins
        self.slider_stroke.valueChanged.connect(self.spin_stroke.setValue)
        self.spin_stroke.valueChanged.connect(self.slider_stroke.setValue)
        self.slider_glow_percent.valueChanged.connect(self.spin_glow_percent.setValue)
        self.spin_glow_percent.valueChanged.connect(self.slider_glow_percent.setValue)
        self.slider_gradient_layers.valueChanged.connect(self.spin_gradient_layers.setValue)
        self.spin_gradient_layers.valueChanged.connect(self.slider_gradient_layers.setValue)
        
        # Link fade slider & spinbox (convert between 1-100 and 0.1-10.0)
        self.slider_fade.valueChanged.connect(lambda v: self.spin_fade.setValue(v / 10.0))
        self.spin_fade.valueChanged.connect(lambda v: self.slider_fade.setValue(int(v * 10)))
        
        # Link explosion frequency slider & spinbox
        self.slider_explosion_freq.valueChanged.connect(self.spin_explosion_freq.setValue)
        self.spin_explosion_freq.valueChanged.connect(lambda v: self.slider_explosion_freq.setValue(int(v)))
        
        # Link explosion intensity slider & spinbox (convert between 0.1-3.0 and 1-30)
        self.slider_explosion_intensity.valueChanged.connect(lambda v: self.spin_explosion_intensity.setValue(v / 10.0))
        self.spin_explosion_intensity.valueChanged.connect(lambda v: self.slider_explosion_intensity.setValue(int(v * 10)))

        # live-apply on any change
        for w, attr in [
            (self.spin_fade, "fade_seconds"),
            (self.spin_fade_slowdown, "fade_slowdown"),
            (self.spin_stroke, "stroke_thickness"),
            (self.spin_glow_percent, "glow_percent"),
            (self.spin_gradient_layers, "gradient_layers"),
            (self.spin_ema,  "ema_alpha"),
            (self.spin_min,  "min_dist_px"),
            (self.spin_tens, "tension"),
            (self.spin_explosion_freq, "explosion_frequency"),
            (self.spin_explosion_intensity, "explosion_intensity"),
        ]:
            w.valueChanged.connect(lambda _=None, a=attr, ww=w: self.update_cfg(a, ww.value()))
        
        # Connect checkboxes
        self.check_particles.toggled.connect(lambda checked: self.update_cfg("particles_enabled", checked))
        self.check_comets.toggled.connect(lambda checked: self.update_cfg("comet_enabled", checked))
        
        # Connect draw mode buttons
        self.draw_mode_group.buttonClicked.connect(self.on_draw_mode_changed)

        btn_reset.clicked.connect(self.reset_defaults)
        btn_close.clicked.connect(self.hide)

    def pick_color(self, which: str):
        if which == "start":
            initial = self.cfg.color_start
        elif which == "mid":
            initial = self.cfg.color_mid
        else:
            initial = self.cfg.color_end
            
        chosen = QtWidgets.QColorDialog.getColor(initial, self, f"Pick {which} color",
                                                 QtWidgets.QColorDialog.ShowAlphaChannel | QtWidgets.QColorDialog.DontUseNativeDialog)
        if chosen.isValid():
            if which == "start":
                self.cfg.color_start = chosen
                self.btn_start.setStyleSheet(f"background-color: {chosen.name()}; border:1px solid #444;")
            elif which == "mid":
                self.cfg.color_mid = chosen
                self.btn_mid.setStyleSheet(f"background-color: {chosen.name()}; border:1px solid #444;")
            else:
                self.cfg.color_end = chosen
                self.btn_end.setStyleSheet(f"background-color: {chosen.name()}; border:1px solid #444;")
            self.emit_change()

    def update_cfg(self, attr: str, value):
        # Coerce to right type
        if attr in ("fade_seconds", "ema_alpha", "min_dist_px", "tension", "fade_slowdown", "explosion_frequency", "explosion_intensity"):
            setattr(self.cfg, attr, float(value))
        elif attr in ("particles_enabled", "comet_enabled"):
            setattr(self.cfg, attr, bool(value))
        else:
            setattr(self.cfg, attr, int(value))
        self.emit_change()

    def reset_defaults(self):
        self.cfg = Config()  # reset
        # reflect defaults in UI
        self.btn_start.setStyleSheet(f"background-color: {self.cfg.color_start.name()}; border:1px solid #444;")
        self.btn_mid.setStyleSheet(f"background-color: {self.cfg.color_mid.name()}; border:1px solid #444;")
        self.btn_end.setStyleSheet(f"background-color: {self.cfg.color_end.name()}; border:1px solid #444;")
        self.combo_num_colors.setCurrentIndex(self.cfg.num_colors - 1)
        self.update_color_picker_visibility()  # Update visibility after reset
        self.spin_fade.setValue(self.cfg.fade_seconds)
        self.slider_fade.setValue(int(self.cfg.fade_seconds * 10))
        self.spin_fade_slowdown.setValue(self.cfg.fade_slowdown)
        self.spin_stroke.setValue(self.cfg.stroke_thickness)
        self.spin_glow_percent.setValue(self.cfg.glow_percent)
        self.spin_gradient_layers.setValue(self.cfg.gradient_layers)
        self.spin_ema.setValue(self.cfg.ema_alpha)
        self.spin_min.setValue(self.cfg.min_dist_px)
        self.spin_tens.setValue(self.cfg.tension)
        self.check_particles.setChecked(self.cfg.particles_enabled)
        self.check_comets.setChecked(self.cfg.comet_enabled)
        
        # Update draw mode buttons
        if self.cfg.draw_mode == DrawMode.FREEHAND:
            self.btn_freehand.setChecked(True)
        elif self.cfg.draw_mode == DrawMode.RECTANGLE:
            self.btn_rectangle.setChecked(True)
        elif self.cfg.draw_mode == DrawMode.CIRCLE:
            self.btn_circle.setChecked(True)
        elif self.cfg.draw_mode == DrawMode.ARROW:
            self.btn_arrow.setChecked(True)
        self.spin_explosion_freq.setValue(self.cfg.explosion_frequency)
        self.slider_explosion_freq.setValue(int(self.cfg.explosion_frequency))
        self.spin_explosion_intensity.setValue(self.cfg.explosion_intensity)
        self.slider_explosion_intensity.setValue(int(self.cfg.explosion_intensity * 10))
        self.slider_stroke.setValue(self.cfg.stroke_thickness)
        self.slider_glow_percent.setValue(self.cfg.glow_percent)
        self.slider_gradient_layers.setValue(self.cfg.gradient_layers)
        self.slider_fade.setValue(int(self.cfg.fade_seconds * 10))
        self.emit_change()

    def on_draw_mode_changed(self, button):
        """Handle draw mode button selection"""
        button_id = self.draw_mode_group.id(button)
        if button_id == 0:
            self.cfg.draw_mode = DrawMode.FREEHAND
        elif button_id == 1:
            self.cfg.draw_mode = DrawMode.RECTANGLE
        elif button_id == 2:
            self.cfg.draw_mode = DrawMode.CIRCLE
        elif button_id == 3:
            self.cfg.draw_mode = DrawMode.ARROW
        self.emit_change()

    def toggle_advanced_settings(self, checked: bool):
        """Show/hide advanced settings group"""
        self.adv_group.setVisible(checked)
        # Resize dialog to fit content
        self.adjustSize()

    def update_color_picker_visibility(self):
        """Show/hide color pickers based on the number of colors selected"""
        num_colors = self.cfg.num_colors
        
        if num_colors == 4:  # Rainbow mode
            # Hide all color pickers, show only rainbow
            self.label_start.setVisible(False)
            self.btn_start.setVisible(False)
            self.label_mid.setVisible(False)
            self.btn_mid.setVisible(False)
            self.label_end.setVisible(False)
            self.btn_end.setVisible(False)
            self.label_rainbow.setVisible(True)
            self.btn_rainbow.setVisible(True)
        else:
            # Hide rainbow, show appropriate color pickers
            self.label_rainbow.setVisible(False)
            self.btn_rainbow.setVisible(False)
            
            # Always show start color
            self.label_start.setVisible(True)
            self.btn_start.setVisible(True)
            
            # Show middle color only for 3+ colors
            self.label_mid.setVisible(num_colors >= 3)
            self.btn_mid.setVisible(num_colors >= 3)
            
            # Show end color only for 2+ colors
            self.label_end.setVisible(num_colors >= 2)
            self.btn_end.setVisible(num_colors >= 2)

    def update_color_scheme(self, index: int):
        """Update the color scheme based on dropdown selection"""
        # Convert dropdown index (0,1,2,3) to num_colors (1,2,3,4)
        self.cfg.num_colors = index + 1
        
        # Update colors to match the selected scheme
        self.cfg.update_colors_for_scheme()
        
        # Update the color button displays
        self.btn_start.setStyleSheet(f"background-color: {self.cfg.color_start.name()}; border: 1px solid #444;")
        self.btn_mid.setStyleSheet(f"background-color: {self.cfg.color_mid.name()}; border: 1px solid #444;")
        self.btn_end.setStyleSheet(f"background-color: {self.cfg.color_end.name()}; border: 1px solid #444;")
        
        # Update visibility of color pickers
        self.update_color_picker_visibility()
        
        self.emit_change()

    def emit_change(self):
        self.config_changed.emit(self.cfg)

    def _create_settings_icon(self):
        """Create the GrafTrail icon for the settings window"""
        pm = QtGui.QPixmap(64, 64)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Simple spiral with GrafTrail colors
        center_x, center_y = 32, 32
        spiral_points = []
        
        for i in range(40):
            angle = i * 0.4
            radius = 2 + i * 0.6
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            spiral_points.append((x, y))

        # Draw spiral with gradient colors (New Purple -> Burnt Orange -> Yellow)
        for i in range(len(spiral_points) - 1):
            t = i / (len(spiral_points) - 1)
            if t < 0.5:
                # New Purple (170, 0, 255) to burnt orange
                blend = t * 2
                color = QtGui.QColor(
                    int(170 + (255-170) * blend),
                    int(0 + (140-0) * blend),
                    int(255 + (0-255) * blend)
                )
            else:
                # Burnt orange to yellow
                blend = (t - 0.5) * 2
                color = QtGui.QColor(
                    255,
                    int(140 + (255-140) * blend),
                    int(0 + (0-0) * blend)
                )
            
            pen = QtGui.QPen(color, 3)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            
            current = spiral_points[i]
            next_point = spiral_points[i + 1]
            p.drawLine(int(current[0]), int(current[1]), int(next_point[0]), int(next_point[1]))

        p.end()
        return QtGui.QIcon(pm)

# ------------------------- Tray icon -------------------------
class Tray(QtWidgets.QSystemTrayIcon):
    def __init__(self, overlay: Overlay, settings: QtCore.QSettings, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.settings = settings
        
        # Use custom generated icon
        self.setIcon(self._graftrail_icon())

        menu = QtWidgets.QMenu()
        self.action_settings = menu.addAction("Settings…")
        self.action_settings.triggered.connect(self.open_settings)

        self.action_pause = menu.addAction("Pause")
        self.action_pause.setCheckable(True)
        self.action_pause.triggered.connect(lambda c: self.overlay.set_paused(c))

        self.action_autorun = menu.addAction("Run at startup")
        self.action_autorun.setCheckable(True)
        self.action_autorun.setChecked(is_run_at_startup())
        self.action_autorun.triggered.connect(self.toggle_autorun)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)

        self.setContextMenu(menu)
        # Platform-specific tooltip
        platform = get_platform()
        if platform == "darwin":  # macOS
            controls_text = "• CMD (⌘) + Drag: Create trail\n• SHIFT: Pause fading (hold)\n• CAPS LOCK: Pause fading (toggle)"
        else:  # Windows/Linux
            controls_text = "• CTRL + Drag: Create trail\n• SHIFT: Pause fading (hold)\n• CAPS LOCK: Pause fading (toggle)"
        
        self.setToolTip(f"{APP_NAME}\n\nControls:\n{controls_text}")
        self.show()

        self.dlg: Optional[SettingsDialog] = None

    def _graftrail_icon(self):
        """Create a simple spiral icon"""
        pm = QtGui.QPixmap(64, 64)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Simple spiral
        center_x, center_y = 32, 32
        spiral_points = []
        
        for i in range(40):
            angle = i * 0.4
            radius = 2 + i * 0.6
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            spiral_points.append((x, y))

        # Draw spiral with gradient colors
        for i in range(len(spiral_points) - 1):
            t = i / (len(spiral_points) - 1)
            if t < 0.5:
                # Purple to orange
                blend = t * 2
                color = QtGui.QColor(
                    int(128 + (255-128) * blend),
                    int(0 + (140-0) * blend),
                    int(128 + (0-128) * blend)
                )
            else:
                # Orange to yellow
                blend = (t - 0.5) * 2
                color = QtGui.QColor(
                    255,
                    int(140 + (255-140) * blend),
                    int(0 + (0-0) * blend)
                )
            
            pen = QtGui.QPen(color, 3)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            
            current = spiral_points[i]
            next_point = spiral_points[i + 1]
            p.drawLine(int(current[0]), int(current[1]), int(next_point[0]), int(next_point[1]))

        p.end()
        return QtGui.QIcon(pm)

    def open_settings(self):
        if self.dlg is None:
            self.dlg = SettingsDialog(self.overlay.cfg)
            self.dlg.config_changed.connect(self.on_config_changed)
        self.dlg.show()
        self.dlg.raise_(); self.dlg.activateWindow()

    def on_config_changed(self, cfg: Config):
        # Persist and apply
        cfg.save(self.settings)
        self.overlay.apply_config(cfg)

    def toggle_autorun(self, checked):
        ok = set_run_at_startup(checked)
        if not ok:
            QtWidgets.QMessageBox.warning(None, APP_NAME, "Couldn't update startup setting.")
            self.action_autorun.setChecked(is_run_at_startup())

# ------------------------- main -------------------------
def main():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setOrganizationName(ORG_NAME); app.setOrganizationDomain(ORG_DOMAIN); app.setApplicationName(APP_NAME)

    # Initialize components
    _init_key_monitor()
    settings = QtCore.QSettings(QtCore.QSettings.UserScope, ORG_NAME, APP_NAME)
    cfg = Config.load(settings)
    overlay = Overlay(cfg); overlay.show()
    tray = Tray(overlay, settings)
    
    # Connect keyboard shortcuts to draw mode changes
    global _key_monitor
    if _key_monitor:
        _key_monitor.draw_mode_changed.connect(lambda mode: overlay.change_draw_mode(mode, settings))

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()