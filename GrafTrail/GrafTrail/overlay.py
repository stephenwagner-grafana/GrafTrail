# trail_app.py  (Python 3.9+)
# Windows overlay app: hold CTRL to draw a silky trail (Orange -> Yellow as it fades).
# - Always-on-top, click-through overlay across all monitors
# - No admin required (uses GetAsyncKeyState for CTRL)
# - System tray: Pause/Resume, Run at startup, Quit
#
# Build (after testing):  pyinstaller --noconsole --onefile --name "CyanTrail" trail_app.py

import sys, time, ctypes, os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pyautogui
from PyQt5 import QtCore, QtGui, QtWidgets

pyautogui.FAILSAFE = False

# ================== Tunables ==================
FADE_SECONDS   = 1.5
FRAME_MS       = 16
CORE_WIDTH     = 17
GLOW_WIDTH     = 23
MIN_DIST_PX    = 3.5
EMA_ALPHA      = 0.35
CR_TENSION     = 1.0
# Color ramp (Orange -> Yellow as it fades)
COLOR_START_RGB = (240, 90, 40)
COLOR_END_RGB   = (251, 202, 10)
GLOW_ALPHA_MAX  = 110
CORE_ALPHA_MAX  = 230
APP_NAME        = "GrafTrail"
# ==============================================

# ---- Windows virtual desktop metrics ----
SM_XVIRTUALSCREEN  = 76
SM_YVIRTUALSCREEN  = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
def virtual_rect() -> QtCore.QRect:
    u32 = ctypes.windll.user32
    return QtCore.QRect(
        u32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )

# ---- CTRL detection (no admin) ----
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
def ctrl_down() -> bool:
    u32 = ctypes.windll.user32
    return bool((u32.GetAsyncKeyState(VK_LCONTROL) & 0x8000) or
                (u32.GetAsyncKeyState(VK_RCONTROL) & 0x8000))

# ---- Autostart (HKCU\...\Run) ----
def exe_path_for_run():
    # If frozen (pyinstaller), use exe; else use current python file.
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])

def set_run_at_startup(enable: bool):
    try:
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_ALL_ACCESS) as k:
            if enable:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, exe_path_for_run())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False

def is_run_at_startup():
    try:
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, APP_NAME)
            return bool(val)
    except Exception:
        return False

# ---- Data ----
@dataclass
class TrailPoint:
    x: int; y: int; t: float; stroke: int

# ================= Overlay =================
class Overlay(QtWidgets.QWidget):
    paused_changed = QtCore.pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        # Window: transparent, always on top, click-through
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(QtCore.Qt.Tool, True)

        vr = virtual_rect()
        self.setGeometry(vr.left(), vr.top(), vr.width(), vr.height())
        self.vr = vr

        self.points: List[TrailPoint] = []
        self.stroke_id = 0
        self.prev_ctrl = False
        self._ema_xy: Optional[Tuple[float, float]] = None
        self.paused = False

        self.core_pen = QtGui.QPen(QtGui.QColor(*COLOR_START_RGB))
        self.core_pen.setWidth(CORE_WIDTH)
        self.core_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.core_pen.setJoinStyle(QtCore.Qt.RoundJoin)

        self.glow_pen = QtGui.QPen(QtGui.QColor(*COLOR_START_RGB))
        self.glow_pen.setWidth(GLOW_WIDTH)
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.glow_pen.setJoinStyle(QtCore.Qt.RoundJoin)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(FRAME_MS)

    # ---- public API ----
    def set_paused(self, p: bool):
        self.paused = p
        if p:
            # stop adding points but let existing ones fade out
            pass
        self.paused_changed.emit(p)

    # ---- smoothing + sampling ----
    def tick(self):
        now = time.time()
        if not self.paused:
            pressed = ctrl_down()
            if pressed and not self.prev_ctrl:
                self.stroke_id += 1
                self._ema_xy = None

            if pressed:
                rx, ry = pyautogui.position()
                if self._ema_xy is None:
                    sx, sy = float(rx), float(ry)
                else:
                    sx = EMA_ALPHA * float(rx) + (1.0 - EMA_ALPHA) * self._ema_xy[0]
                    sy = EMA_ALPHA * float(ry) + (1.0 - EMA_ALPHA) * self._ema_xy[1]
                self._ema_xy = (sx, sy)

                accept = True
                if self.points and self.points[-1].stroke == self.stroke_id:
                    dx = sx - self.points[-1].x; dy = sy - self.points[-1].y
                    if (dx*dx + dy*dy) < (MIN_DIST_PX * MIN_DIST_PX):
                        accept = False
                if accept:
                    self.points.append(TrailPoint(int(sx), int(sy), now, self.stroke_id))

            self.prev_ctrl = pressed

        # prune faded points
        cutoff = now - FADE_SECONDS
        if self.points and self.points[0].t < cutoff:
            self.points = [p for p in self.points if p.t >= cutoff]

        self.update()

    # ---- utilities ----
    def _to_local(self, x: float, y: float) -> Tuple[float, float]:
        return x - self.vr.left(), y - self.vr.top()

    def _catmull_rom_to_bezier(self, p0, p1, p2, p3, tension=CR_TENSION):
        c1 = QtCore.QPointF(p1.x() + (p2.x() - p0.x()) * (tension / 6.0),
                            p1.y() + (p2.y() - p0.y()) * (tension / 6.0))
        c2 = QtCore.QPointF(p2.x() - (p3.x() - p1.x()) * (tension / 6.0),
                            p2.y() - (p3.y() - p1.y()) * (tension / 6.0))
        return c1, c2

    def _age_to_fade_and_color(self, age: float):
        life = max(0.0, min(1.0, age / FADE_SECONDS))
        fade = 1.0 - life
        r0,g0,b0 = COLOR_START_RGB; r1,g1,b1 = COLOR_END_RGB
        r = int(r0 + (r1 - r0) * life)
        g = int(g0 + (g1 - g0) * life)
        b = int(b0 + (b1 - b0) * life)
        return fade, QtGui.QColor(r,g,b)

    def _set_pens_for_age(self, painter: QtGui.QPainter, age: float):
        fade, col = self._age_to_fade_and_color(age)
        glow_col = QtGui.QColor(col); glow_col.setAlpha(int(fade * GLOW_ALPHA_MAX))
        core_col = QtGui.QColor(col); core_col.setAlpha(int(fade * CORE_ALPHA_MAX))
        self.glow_pen.setColor(glow_col); self.core_pen.setColor(core_col)
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap); self.core_pen.setCapStyle(QtCore.Qt.FlatCap)
        painter.setPen(self.glow_pen)

    def _draw_round_cap(self, painter: QtGui.QPainter, x: int, y: int, age: float):
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        lx, ly = self._to_local(x, y)

        glow = QtGui.QColor(col); glow.setAlpha(int(fade * GLOW_ALPHA_MAX))
        painter.setPen(QtCore.Qt.NoPen); painter.setBrush(QtGui.QBrush(glow))
        painter.drawEllipse(QtCore.QPointF(lx, ly), self.glow_pen.width()/2, self.glow_pen.width()/2)

        core = QtGui.QColor(col); core.setAlpha(int(fade * CORE_ALPHA_MAX))
        painter.setBrush(QtGui.QBrush(core))
        painter.drawEllipse(QtCore.QPointF(lx, ly), self.core_pen.width()/2, self.core_pen.width()/2)

    # ---- paint ----
    def paintEvent(self, ev: QtGui.QPaintEvent):
        if not self.points: return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        now = time.time()

        pts = self.points; n = len(pts); i = 0
        while i < n:
            j = i + 1; sid = pts[i].stroke
            while j < n and pts[j].stroke == sid: j += 1
            segment = pts[i:j]
            if len(segment) >= 2:
                for k in range(0, len(segment)-1):
                    p0 = segment[k-1] if k-1 >= 0 else segment[k]
                    p1 = segment[k]; p2 = segment[k+1]
                    p3 = segment[k+2] if (k+2) < len(segment) else segment[k+1]
                    P0 = QtCore.QPointF(*self._to_local(p0.x, p0.y))
                    P1 = QtCore.QPointF(*self._to_local(p1.x, p1.y))
                    P2 = QtCore.QPointF(*self._to_local(p2.x, p2.y))
                    P3 = QtCore.QPointF(*self._to_local(p3.x, p3.y))
                    C1, C2 = self._catmull_rom_to_bezier(P0, P1, P2, P3)
                    path = QtGui.QPainterPath(P1); path.cubicTo(C1, C2, P2)

                    age = now - p2.t
                    fade, _ = self._age_to_fade_and_color(age)
                    if fade <= 0.0: continue
                    self._set_pens_for_age(painter, age)
                    painter.setPen(self.glow_pen); painter.drawPath(path)
                    painter.setPen(self.core_pen); painter.drawPath(path)

                # rounded end caps
                tail, head = segment[0], segment[-1]
                self._draw_round_cap(painter, tail.x, tail.y, now - tail.t)
                self._draw_round_cap(painter, head.x, head.y, now - head.t)
            i = j

# ================= Tray =================
class Tray(QtWidgets.QSystemTrayIcon):
    def __init__(self, overlay: Overlay, parent=None):
        super().__init__(parent)
        self.overlay = overlay

        # default icon (Qt generic) – replace with your .ico via setIcon(QIcon('icon.ico'))
        self.setIcon(self._default_icon())

        menu = QtWidgets.QMenu()
        self.action_pause = menu.addAction("Pause drawing")
        self.action_pause.setCheckable(True)
        self.action_pause.triggered.connect(self.toggle_pause)

        self.action_autorun = menu.addAction("Run at startup")
        self.action_autorun.setCheckable(True)
        self.action_autorun.setChecked(is_run_at_startup())
        self.action_autorun.triggered.connect(self.toggle_autorun)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QtWidgets.QApplication.quit)

        self.setContextMenu(menu)
        self.setToolTip(APP_NAME)
        self.show()

    def _default_icon(self):
        pm = QtGui.QPixmap(64,64); pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(0,200,255)); pen.setWidth(8)
        p.setPen(pen); p.drawEllipse(8,8,48,48); p.end()
        return QtGui.QIcon(pm)

    def toggle_pause(self, checked):
        self.overlay.set_paused(checked)

    def toggle_autorun(self, checked):
        ok = set_run_at_startup(checked)
        if not ok:
            QtWidgets.QMessageBox.warning(None, APP_NAME, "Couldn't update startup setting.")
            # revert checkbox
            self.action_autorun.setChecked(is_run_at_startup())

# =============== main ===============
def main():
    app = QtWidgets.QApplication(sys.argv)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    overlay = Overlay(); overlay.show()
    tray = Tray(overlay)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
