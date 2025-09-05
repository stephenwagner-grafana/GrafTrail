# =====================================================================
# GrafTrail - Mouse Trail Overlay Application
# =====================================================================
# A beautiful mouse trail overlay that creates smooth, colorful trails
# when holding the CTRL key. Features advanced curve rendering with
# Catmull-Rom splines converted to cubic Bézier curves.
#
# KEY FEATURES:
# • Smooth mouse trail with color gradients (Orange → Yellow fade)
# • Always-on-top, click-through overlay across all monitors
# • No administrator privileges required
# • System tray integration with pause/resume functionality
# • Automatic startup option
# • Exponential moving average (EMA) smoothing for fluid trails
# • Minimum distance filtering to prevent noise
#
# CONTROLS:
# • Hold CTRL (left or right) to draw trails
# • Right-click system tray icon for options
#
# BUILD:
# pyinstaller --noconsole --onefile --name "GrafTrail" overlay.py
#
# Requirements: Python 3.9+, PyQt5, pyautogui
# =====================================================================

# ===================================================================== 
# IMPORTS
# =====================================================================
import sys        # System-specific parameters and functions
import time       # Time-related functions for timestamps and timing
import ctypes     # Foreign function library for Windows API calls
import os         # Operating system interface functions
from dataclasses import dataclass  # Decorator for creating data classes
from typing import List, Optional, Tuple  # Type hints for better code documentation

# Third-party libraries
import pyautogui  # Cross-platform mouse and keyboard automation
from PyQt5 import QtCore, QtGui, QtWidgets  # Qt framework for GUI applications

# Platform-specific imports
import platform   # Platform detection

# Disable pyautogui's fail-safe (moving mouse to corner doesn't exit)
pyautogui.FAILSAFE = False

# =====================================================================
# CONFIGURATION CONSTANTS
# =====================================================================
# These values control the appearance and behavior of the mouse trail

# Trail timing and animation
FADE_SECONDS   = 1.5   # How long trails take to completely fade out
FRAME_MS       = 16    # Refresh rate (~60 FPS = 16.67ms per frame)

# Trail appearance
CORE_WIDTH     = 17    # Width of the solid center line (pixels)
GLOW_WIDTH     = 23    # Width of the outer glow effect (pixels)

# Trail quality and smoothing
MIN_DIST_PX    = 3.5   # Minimum distance between points (reduces noise)
EMA_ALPHA      = 0.35  # Exponential moving average factor (0-1, higher = more responsive)
CR_TENSION     = 1.0   # Catmull-Rom spline tension (1.0 = standard, higher = tighter curves)

# Color scheme: Orange to Yellow gradient as trail fades
COLOR_START_RGB = (240, 90, 40)   # Bright orange for fresh trail
COLOR_END_RGB   = (251, 202, 10)  # Golden yellow for faded trail

# Alpha transparency levels (0-255)
GLOW_ALPHA_MAX  = 110  # Maximum opacity for glow effect
CORE_ALPHA_MAX  = 230  # Maximum opacity for core trail

# Application identity
APP_NAME        = "GrafTrail"
# =====================================================================

# =====================================================================
# CROSS-PLATFORM SYSTEM HELPERS
# =====================================================================

def get_platform() -> str:
    """Get the current platform name in lowercase.
    
    Returns:
        str: 'windows', 'darwin' (macOS), or 'linux'
    """
    return platform.system().lower()

# Windows system metrics constants for multi-monitor setups
SM_XVIRTUALSCREEN  = 76  # Left edge of virtual screen
SM_YVIRTUALSCREEN  = 77  # Top edge of virtual screen  
SM_CXVIRTUALSCREEN = 78  # Width of virtual screen
SM_CYVIRTUALSCREEN = 79  # Height of virtual screen

# Platform-specific global state for CTRL key tracking
_ctrl_pressed = False
_key_monitor = None

def virtual_rect() -> QtCore.QRect:
    """Get the bounding rectangle that encompasses all monitors.
    
    This ensures the overlay covers the entire desktop area, including
    multiple monitors with different resolutions and arrangements.
    Works cross-platform using Qt's desktop widget on macOS/Linux and
    Windows API on Windows for optimal performance.
    
    Returns:
        QtCore.QRect: Rectangle covering all connected displays
    """
    current_platform = get_platform()
    
    if current_platform == "windows":
        # Use Windows API for precise multi-monitor support
        u32 = ctypes.windll.user32
        return QtCore.QRect(
            u32.GetSystemMetrics(SM_XVIRTUALSCREEN),   # X position of virtual screen
            u32.GetSystemMetrics(SM_YVIRTUALSCREEN),   # Y position of virtual screen
            u32.GetSystemMetrics(SM_CXVIRTUALSCREEN),  # Total width of all monitors
            u32.GetSystemMetrics(SM_CYVIRTUALSCREEN),  # Total height of all monitors
        )
    else:
        # Use Qt's cross-platform desktop widget for macOS/Linux
        app = QtWidgets.QApplication.instance()
        if app is None:
            # Fallback if no QApplication exists yet
            return QtCore.QRect(0, 0, 1920, 1080)
            
        desktop = app.desktop()
        
        # Calculate bounding rectangle for all screens
        screen_count = desktop.screenCount()
        if screen_count == 1:
            return desktop.screenGeometry(0)
        
        # Multi-monitor: find bounding rectangle
        left = min(desktop.screenGeometry(i).left() for i in range(screen_count))
        top = min(desktop.screenGeometry(i).top() for i in range(screen_count))
        right = max(desktop.screenGeometry(i).right() for i in range(screen_count))
        bottom = max(desktop.screenGeometry(i).bottom() for i in range(screen_count))
        
        return QtCore.QRect(left, top, right - left + 1, bottom - top + 1)

# Virtual key codes for CTRL keys (Windows)
VK_LCONTROL = 0xA2  # Left Control key
VK_RCONTROL = 0xA3  # Right Control key

class GlobalKeyMonitor(QtCore.QObject):
    """Cross-platform global key state monitor using Qt events.
    
    This class provides a fallback for platforms where low-level
    key monitoring is not easily available.
    """
    
    def __init__(self):
        super().__init__()
        self.ctrl_pressed = False
        
    def eventFilter(self, obj, event):
        """Qt event filter to track CTRL key state globally."""
        if event.type() == QtCore.QEvent.KeyPress:
            if event.key() == QtCore.Qt.Key_Control:
                self.ctrl_pressed = True
        elif event.type() == QtCore.QEvent.KeyRelease:
            if event.key() == QtCore.Qt.Key_Control:
                self.ctrl_pressed = False
        return False  # Don't consume the event

def _init_key_monitor():
    """Initialize platform-specific key monitoring."""
    global _key_monitor
    current_platform = get_platform()
    
    if current_platform != "windows":
        # Use Qt-based monitoring for non-Windows platforms
        _key_monitor = GlobalKeyMonitor()
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(_key_monitor)

def ctrl_down() -> bool:
    """Check if either CTRL key is currently pressed.
    
    Uses platform-appropriate method:
    - Windows: GetAsyncKeyState API (works without focus)
    - macOS/Linux: Qt event monitoring (requires app focus)
    
    Returns:
        bool: True if either left or right CTRL key is pressed
    """
    current_platform = get_platform()
    
    if current_platform == "windows":
        # Use Windows API for precise, focus-independent detection
        u32 = ctypes.windll.user32
        # Check high bit (0x8000) which indicates key is currently pressed
        return bool((u32.GetAsyncKeyState(VK_LCONTROL) & 0x8000) or
                    (u32.GetAsyncKeyState(VK_RCONTROL) & 0x8000))
    else:
        # Use Qt-based monitoring for macOS/Linux
        global _key_monitor
        if _key_monitor is None:
            _init_key_monitor()
        
        if _key_monitor:
            return _key_monitor.ctrl_pressed
        
        # Fallback: check current application key state
        app = QtWidgets.QApplication.instance()
        if app:
            modifiers = app.keyboardModifiers()
            return bool(modifiers & QtCore.Qt.ControlModifier)
        
        return False

# =====================================================================
# CROSS-PLATFORM STARTUP INTEGRATION
# =====================================================================

def exe_path_for_run():
    """Get the appropriate executable path for startup registration.
    
    When built with PyInstaller, sys.frozen is True and we use the .exe path.
    During development, we use the Python script path.
    
    Returns:
        str: Full path to executable or script file
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable
        return sys.executable
    # Running as Python script
    return os.path.abspath(sys.argv[0])

def set_run_at_startup(enable: bool):
    """Enable or disable automatic startup with the operating system.
    
    Uses platform-appropriate method:
    - Windows: Registry modification under HKEY_CURRENT_USER\...\Run
    - macOS: LaunchAgent plist creation/deletion
    - Linux: Desktop file in autostart directory
    
    Args:
        enable (bool): True to enable startup, False to disable
        
    Returns:
        bool: True if operation succeeded, False if failed
    """
    current_platform = get_platform()
    
    try:
        if current_platform == "windows":
            # Windows Registry method
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_ALL_ACCESS) as k:
                if enable:
                    winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, exe_path_for_run())
                else:
                    try:
                        winreg.DeleteValue(k, APP_NAME)
                    except FileNotFoundError:
                        pass  # Entry didn't exist, that's fine
            return True
            
        elif current_platform == "darwin":
            # macOS LaunchAgent method
            import plistlib
            
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_path = os.path.join(launch_agents_dir, f"com.{APP_NAME.lower()}.plist")
            
            if enable:
                # Create LaunchAgents directory if it doesn't exist
                os.makedirs(launch_agents_dir, exist_ok=True)
                
                # Create plist data
                plist_data = {
                    'Label': f'com.{APP_NAME.lower()}',
                    'ProgramArguments': [exe_path_for_run()],
                    'RunAtLoad': True,
                    'KeepAlive': False
                }
                
                # Write plist file
                with open(plist_path, 'wb') as f:
                    plistlib.dump(plist_data, f)
            else:
                # Remove plist file
                try:
                    os.remove(plist_path)
                except FileNotFoundError:
                    pass  # File didn't exist, that's fine
            return True
            
        else:  # Linux and other Unix-like systems
            # XDG autostart desktop file method
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_path = os.path.join(autostart_dir, f"{APP_NAME}.desktop")
            
            if enable:
                # Create autostart directory if it doesn't exist
                os.makedirs(autostart_dir, exist_ok=True)
                
                # Create desktop file content
                desktop_content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec={exe_path_for_run()}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""
                
                # Write desktop file
                with open(desktop_path, 'w') as f:
                    f.write(desktop_content)
            else:
                # Remove desktop file
                try:
                    os.remove(desktop_path)
                except FileNotFoundError:
                    pass  # File didn't exist, that's fine
            return True
            
    except Exception:
        # Any platform-specific operation failed
        return False

def is_run_at_startup():
    """Check if the application is set to run at system startup.
    
    Uses platform-appropriate method to check startup status:
    - Windows: Queries registry under HKEY_CURRENT_USER\...\Run
    - macOS: Checks for LaunchAgent plist file
    - Linux: Checks for autostart desktop file
    
    Returns:
        bool: True if startup is enabled, False otherwise
    """
    current_platform = get_platform()
    
    try:
        if current_platform == "windows":
            # Windows Registry method
            import winreg
            run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_READ) as k:
                val, _ = winreg.QueryValueEx(k, APP_NAME)
                return bool(val)  # Return True if entry exists and has a value
                
        elif current_platform == "darwin":
            # macOS LaunchAgent method
            plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.{APP_NAME.lower()}.plist")
            return os.path.exists(plist_path)
            
        else:  # Linux and other Unix-like systems
            # XDG autostart desktop file method
            desktop_path = os.path.expanduser(f"~/.config/autostart/{APP_NAME}.desktop")
            return os.path.exists(desktop_path)
            
    except Exception:
        # Any platform-specific operation failed or entry doesn't exist
        return False

# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass
class TrailPoint:
    """Represents a single point in the mouse trail.
    
    Attributes:
        x (int): Screen X coordinate
        y (int): Screen Y coordinate  
        t (float): Timestamp when point was created
        stroke (int): Stroke ID to group connected points
    """
    x: int      # Screen X coordinate
    y: int      # Screen Y coordinate
    t: float    # Timestamp (time.time())
    stroke: int # Stroke identifier for grouping points

# =====================================================================
# MAIN OVERLAY WIDGET
# =====================================================================

class Overlay(QtWidgets.QWidget):
    """Transparent overlay widget that captures mouse movement and draws trails.
    
    This widget covers the entire virtual desktop (all monitors) and remains
    always-on-top while being click-through. It continuously monitors for
    CTRL key presses and mouse movement to create smooth, animated trails.
    
    Signals:
        paused_changed (bool): Emitted when pause state changes
    """
    paused_changed = QtCore.pyqtSignal(bool)  # Signal for pause state changes

    def __init__(self):
        """Initialize the overlay widget with transparent, click-through properties."""
        super().__init__()
        
        # Configure window properties for overlay behavior
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)     # Enable transparency
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True) # Click-through
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)         # No title bar
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)        # Always on top
        self.setWindowFlag(QtCore.Qt.Tool, True)                        # Hide from taskbar

        # Set geometry to cover entire virtual desktop (all monitors)
        vr = virtual_rect()
        self.setGeometry(vr.left(), vr.top(), vr.width(), vr.height())
        self.vr = vr  # Store for coordinate conversion

        # Trail data storage
        self.points: List[TrailPoint] = []  # All trail points
        self.stroke_id = 0                  # Current stroke identifier
        self.prev_ctrl = False              # Previous CTRL key state
        self._ema_xy: Optional[Tuple[float, float]] = None  # EMA smoothing state
        self.paused = False                 # Pause state

        # Initialize drawing pens for the core trail
        self.core_pen = QtGui.QPen(QtGui.QColor(*COLOR_START_RGB))
        self.core_pen.setWidth(CORE_WIDTH)
        self.core_pen.setCapStyle(QtCore.Qt.FlatCap)    # Flat ends for seamless joins
        self.core_pen.setJoinStyle(QtCore.Qt.RoundJoin) # Smooth corners

        # Initialize drawing pens for the glow effect
        self.glow_pen = QtGui.QPen(QtGui.QColor(*COLOR_START_RGB))
        self.glow_pen.setWidth(GLOW_WIDTH)
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap)    # Flat ends for seamless joins
        self.glow_pen.setJoinStyle(QtCore.Qt.RoundJoin) # Smooth corners

        # Start the main update timer
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)  # Connect to update function
        self.timer.start(FRAME_MS)             # ~60 FPS refresh rate

    # ===================================================================
    # PUBLIC API
    # ===================================================================
    
    def set_paused(self, p: bool):
        """Set the pause state of the trail drawing.
        
        When paused, no new trail points are added, but existing trails
        continue to fade out naturally.
        
        Args:
            p (bool): True to pause, False to resume
        """
        self.paused = p
        if p:
            # Stop adding new points but let existing ones fade out
            pass
        self.paused_changed.emit(p)  # Notify listeners of state change

    # ===================================================================
    # MAIN UPDATE LOOP
    # ===================================================================
    
    def tick(self):
        """Main update function called every frame (~60 FPS).
        
        Handles:
        - CTRL key detection and stroke management
        - Mouse position sampling and smoothing
        - Point filtering and trail building
        - Automatic cleanup of old/faded points
        """
        now = time.time()
        
        if not self.paused:
            # Check if CTRL key is currently pressed
            pressed = ctrl_down()
            
            # Detect new stroke (CTRL just pressed)
            if pressed and not self.prev_ctrl:
                self.stroke_id += 1      # Start new stroke
                self._ema_xy = None      # Reset smoothing

            # Sample and smooth mouse position while CTRL is held
            if pressed:
                # Get raw mouse position
                rx, ry = pyautogui.position()
                
                # Apply exponential moving average (EMA) smoothing
                if self._ema_xy is None:
                    # First point - no smoothing needed
                    sx, sy = float(rx), float(ry)
                else:
                    # Smooth using EMA: new = α*raw + (1-α)*previous
                    sx = EMA_ALPHA * float(rx) + (1.0 - EMA_ALPHA) * self._ema_xy[0]
                    sy = EMA_ALPHA * float(ry) + (1.0 - EMA_ALPHA) * self._ema_xy[1]
                
                self._ema_xy = (sx, sy)  # Store for next frame

                # Apply minimum distance filter to reduce noise
                accept = True
                if self.points and self.points[-1].stroke == self.stroke_id:
                    # Calculate distance from last point in current stroke
                    dx = sx - self.points[-1].x
                    dy = sy - self.points[-1].y
                    distance_sq = dx*dx + dy*dy
                    
                    # Reject if too close to last point
                    if distance_sq < (MIN_DIST_PX * MIN_DIST_PX):
                        accept = False
                
                # Add point if it passes distance filter
                if accept:
                    self.points.append(TrailPoint(int(sx), int(sy), now, self.stroke_id))

            # Update previous CTRL state for next frame
            self.prev_ctrl = pressed

        # Remove old points that have completely faded out
        cutoff = now - FADE_SECONDS
        if self.points and self.points[0].t < cutoff:
            # Filter out points older than fade duration
            self.points = [p for p in self.points if p.t >= cutoff]

        # Trigger repaint
        self.update()

    # ===================================================================
    # COORDINATE AND CURVE UTILITIES  
    # ===================================================================
    
    def _to_local(self, x: float, y: float) -> Tuple[float, float]:
        """Convert global screen coordinates to widget-local coordinates.
        
        Args:
            x (float): Global screen X coordinate
            y (float): Global screen Y coordinate
            
        Returns:
            Tuple[float, float]: Local widget coordinates (x, y)
        """
        return x - self.vr.left(), y - self.vr.top()

    def _catmull_rom_to_bezier(self, p0, p1, p2, p3, tension=CR_TENSION):
        """Convert a Catmull-Rom spline segment to cubic Bézier control points.
        
        Catmull-Rom splines create smooth curves through points, but Qt only
        supports Bézier curves. This function calculates the equivalent Bézier
        control points for the segment from p1 to p2.
        
        Args:
            p0, p1, p2, p3 (QPointF): Four consecutive points
            tension (float): Curve tension (1.0 = standard Catmull-Rom)
            
        Returns:
            Tuple[QPointF, QPointF]: Control points (c1, c2) for Bézier curve
        """
        # Calculate control points using Catmull-Rom to Bézier conversion
        # c1 = p1 + (p2 - p0) * tension/6
        c1 = QtCore.QPointF(p1.x() + (p2.x() - p0.x()) * (tension / 6.0),
                            p1.y() + (p2.y() - p0.y()) * (tension / 6.0))
        
        # c2 = p2 - (p3 - p1) * tension/6  
        c2 = QtCore.QPointF(p2.x() - (p3.x() - p1.x()) * (tension / 6.0),
                            p2.y() - (p3.y() - p1.y()) * (tension / 6.0))
        
        return c1, c2

    def _age_to_fade_and_color(self, age: float):
        """Calculate fade amount and color based on trail point age.
        
        Converts point age to both opacity (fade) and color along the
        gradient from start color (orange) to end color (yellow).
        
        Args:
            age (float): Time since point was created (seconds)
            
        Returns:
            Tuple[float, QColor]: (fade_factor, interpolated_color)
                fade_factor: 0.0 (invisible) to 1.0 (fully opaque)
                interpolated_color: Color between start and end colors
        """
        # Calculate normalized lifetime (0.0 = new, 1.0 = fully aged)
        life = max(0.0, min(1.0, age / FADE_SECONDS))
        
        # Fade factor decreases as point ages
        fade = 1.0 - life
        
        # Interpolate color components from start to end
        r0, g0, b0 = COLOR_START_RGB  # Orange (new)
        r1, g1, b1 = COLOR_END_RGB    # Yellow (old)
        
        r = int(r0 + (r1 - r0) * life)  # Red component
        g = int(g0 + (g1 - g0) * life)  # Green component  
        b = int(b0 + (b1 - b0) * life)  # Blue component
        
        return fade, QtGui.QColor(r, g, b)

    def _set_pens_for_age(self, painter: QtGui.QPainter, age: float):
        """Configure drawing pens based on trail point age.
        
        Sets up both glow and core pens with appropriate colors and transparency
        based on how old the trail point is. Older points are more transparent.
        
        Args:
            painter (QPainter): Painter to configure
            age (float): Age of the trail point in seconds
        """
        # Get fade amount and interpolated color
        fade, col = self._age_to_fade_and_color(age)
        
        # Create glow pen with reduced opacity
        glow_col = QtGui.QColor(col)
        glow_col.setAlpha(int(fade * GLOW_ALPHA_MAX))
        
        # Create core pen with higher opacity
        core_col = QtGui.QColor(col)
        core_col.setAlpha(int(fade * CORE_ALPHA_MAX))
        
        # Apply colors to pens
        self.glow_pen.setColor(glow_col)
        self.core_pen.setColor(core_col)
        
        # Ensure flat caps for seamless joining
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.core_pen.setCapStyle(QtCore.Qt.FlatCap)
        
        # Set glow pen as default (core pen applied separately)
        painter.setPen(self.glow_pen)

    def _draw_round_cap(self, painter: QtGui.QPainter, x: int, y: int, age: float):
        """Draw a rounded end cap for a trail stroke.
        
        Creates circular caps at the beginning and end of each stroke to
        give trails a more polished, rounded appearance.
        
        Args:
            painter (QPainter): Painter to draw with
            x, y (int): Global screen coordinates of the cap center
            age (float): Age of the trail point for fade/color calculation
        """
        # Calculate fade and color based on age
        fade, col = self._age_to_fade_and_color(age)
        
        # Skip if completely faded out
        if fade <= 0.0:
            return
            
        # Convert to local widget coordinates
        lx, ly = self._to_local(x, y)
        center = QtCore.QPointF(lx, ly)

        # Draw glow circle (outer, softer)
        glow = QtGui.QColor(col)
        glow.setAlpha(int(fade * GLOW_ALPHA_MAX))
        painter.setPen(QtCore.Qt.NoPen)              # No outline
        painter.setBrush(QtGui.QBrush(glow))         # Solid fill
        painter.drawEllipse(center, self.glow_pen.width()/2, self.glow_pen.width()/2)

        # Draw core circle (inner, more opaque)
        core = QtGui.QColor(col)
        core.setAlpha(int(fade * CORE_ALPHA_MAX))
        painter.setBrush(QtGui.QBrush(core))         # Solid fill
        painter.drawEllipse(center, self.core_pen.width()/2, self.core_pen.width()/2)

    # ===================================================================
    # RENDERING
    # ===================================================================
    
    def paintEvent(self, ev: QtGui.QPaintEvent):
        """Main rendering function called whenever the widget needs repainting.
        
        Renders all trail segments using smooth Catmull-Rom curves converted
        to cubic Bézier paths. Each segment is drawn twice (glow + core) with
        age-based color and transparency.
        
        Args:
            ev (QPaintEvent): Paint event (unused but required by Qt)
        """
        # Skip rendering if no trail points exist
        if not self.points:
            return
            
        # Initialize painter with antialiasing for smooth curves
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        now = time.time()

        # Group points by stroke and render each stroke as a continuous curve
        pts = self.points
        n = len(pts)
        i = 0
        
        while i < n:
            # Find all points belonging to the current stroke
            j = i + 1
            sid = pts[i].stroke  # Current stroke ID
            
            # Advance j until we find a different stroke or reach the end
            while j < n and pts[j].stroke == sid:
                j += 1
                
            # Extract segment (all points with same stroke ID)
            segment = pts[i:j]
            
            # Only render segments with at least 2 points
            if len(segment) >= 2:
                # Render smooth curves between consecutive points
                for k in range(0, len(segment) - 1):
                    # Get 4 points for Catmull-Rom curve calculation
                    # Use duplicate points at ends if necessary
                    p0 = segment[k-1] if k-1 >= 0 else segment[k]        # Previous point
                    p1 = segment[k]                                       # Start point
                    p2 = segment[k+1]                                     # End point  
                    p3 = segment[k+2] if (k+2) < len(segment) else segment[k+1]  # Next point
                    
                    # Convert to local coordinates
                    P0 = QtCore.QPointF(*self._to_local(p0.x, p0.y))
                    P1 = QtCore.QPointF(*self._to_local(p1.x, p1.y))
                    P2 = QtCore.QPointF(*self._to_local(p2.x, p2.y))
                    P3 = QtCore.QPointF(*self._to_local(p3.x, p3.y))
                    
                    # Calculate Bézier control points from Catmull-Rom
                    C1, C2 = self._catmull_rom_to_bezier(P0, P1, P2, P3)
                    
                    # Create cubic Bézier path from P1 to P2
                    path = QtGui.QPainterPath(P1)
                    path.cubicTo(C1, C2, P2)

                    # Calculate age and skip if completely faded
                    age = now - p2.t
                    fade, _ = self._age_to_fade_and_color(age)
                    if fade <= 0.0:
                        continue
                    
                    # Configure pens for this age and draw the path
                    self._set_pens_for_age(painter, age)
                    
                    # Draw glow effect (wider, more transparent)
                    painter.setPen(self.glow_pen)
                    painter.drawPath(path)
                    
                    # Draw core trail (narrower, more opaque)
                    painter.setPen(self.core_pen)
                    painter.drawPath(path)

                # Add rounded end caps for a polished look
                tail, head = segment[0], segment[-1]
                self._draw_round_cap(painter, tail.x, tail.y, now - tail.t)
                self._draw_round_cap(painter, head.x, head.y, now - head.t)
                
            # Move to next stroke
            i = j

# =====================================================================
# SYSTEM TRAY INTEGRATION
# =====================================================================

class Tray(QtWidgets.QSystemTrayIcon):
    """System tray icon providing user control over the trail overlay.
    
    Creates a system tray icon with a context menu for pausing/resuming
    trail drawing, enabling/disabling startup, and quitting the application.
    """
    
    def __init__(self, overlay: Overlay, parent=None):
        """Initialize system tray icon with context menu.
        
        Args:
            overlay (Overlay): The overlay widget to control
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.overlay = overlay

        # Set tray icon (default Qt icon - replace with custom .ico if desired)
        self.setIcon(self._default_icon())

        # Create context menu
        menu = QtWidgets.QMenu()
        
        # Pause/Resume toggle
        self.action_pause = menu.addAction("Pause drawing")
        self.action_pause.setCheckable(True)  # Checkbox style
        self.action_pause.triggered.connect(self.toggle_pause)

        # Auto-startup toggle  
        self.action_autorun = menu.addAction("Run at startup")
        self.action_autorun.setCheckable(True)  # Checkbox style
        self.action_autorun.setChecked(is_run_at_startup())  # Set current state
        self.action_autorun.triggered.connect(self.toggle_autorun)

        # Separator and quit option
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)

        # Configure tray icon
        self.setContextMenu(menu)
        self.setToolTip(APP_NAME)  # Hover tooltip
        self.show()                # Make tray icon visible

    def _default_icon(self):
        """Create a simple default tray icon if no custom icon is available.
        
        Returns:
            QIcon: A cyan circle icon for the system tray
        """
        # Create transparent 64x64 pixmap
        pm = QtGui.QPixmap(64, 64)
        pm.fill(QtCore.Qt.transparent)
        
        # Draw a simple cyan circle
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)  # Smooth edges
        
        pen = QtGui.QPen(QtGui.QColor(0, 200, 255))  # Cyan color
        pen.setWidth(8)                              # Thick line
        p.setPen(pen)
        p.drawEllipse(8, 8, 48, 48)                  # Circle with 8px margin
        p.end()
        
        return QtGui.QIcon(pm)

    def toggle_pause(self, checked):
        """Handle pause/resume toggle from tray menu.
        
        Args:
            checked (bool): True if pause is checked, False if unchecked
        """
        self.overlay.set_paused(checked)

    def toggle_autorun(self, checked):
        """Handle auto-startup toggle from tray menu.
        
        Attempts to modify Windows registry to enable/disable startup.
        Shows error message and reverts checkbox if operation fails.
        
        Args:
            checked (bool): True to enable startup, False to disable
        """
        ok = set_run_at_startup(checked)
        
        if not ok:
            # Registry modification failed - show error and revert
            QtWidgets.QMessageBox.warning(
                None, APP_NAME, 
                "Couldn't update startup setting. Check permissions."
            )
            # Revert checkbox to actual registry state
            self.action_autorun.setChecked(is_run_at_startup())

# =====================================================================
# APPLICATION ENTRY POINT
# =====================================================================

def main():
    """Main application entry point.
    
    Initializes Qt application, creates overlay and tray icon,
    then starts the main event loop.
    """
    # Create Qt application
    app = QtWidgets.QApplication(sys.argv)
    
    # Enable high-DPI pixmap support for crisp icons on high-DPI displays
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    # Initialize cross-platform key monitoring
    _init_key_monitor()

    # Create and show the transparent overlay
    overlay = Overlay()
    overlay.show()
    
    # Create system tray icon for user interaction
    tray = Tray(overlay)

    # Start the Qt event loop (runs until application quits)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
