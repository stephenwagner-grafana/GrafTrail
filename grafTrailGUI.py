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
# Build: pyinstaller --noconsole --onefile --name "CyanTrail" trail_app_gui.py

import sys, time, os, ctypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pyautogui
from PyQt5 import QtCore, QtGui, QtWidgets

pyautogui.FAILSAFE = False

APP_NAME    = "GrafTrail"
ORG_NAME    = "GrafTrail"   # for QSettings
ORG_DOMAIN  = "graftrail.local"

# ------------------------- Windows helpers -------------------------
SM_XVIRTUALSCREEN  = 76
SM_YVIRTUALSCREEN  = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3

def virtual_rect() -> QtCore.QRect:
    u32 = ctypes.windll.user32
    return QtCore.QRect(
        u32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )

def ctrl_down() -> bool:
    u32 = ctypes.windll.user32
    return bool((u32.GetAsyncKeyState(VK_LCONTROL) & 0x8000) or
                (u32.GetAsyncKeyState(VK_RCONTROL) & 0x8000))

def exe_path_for_run():
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
                try: winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError: pass
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

# ------------------------- Config model -------------------------
@dataclass
class Config:
    color_start: QtGui.QColor = QtGui.QColor(240, 90, 40)
    color_end:   QtGui.QColor = QtGui.QColor(251, 202, 10)
    fade_seconds: float = 1.5
    core_width:   int   = 17
    glow_width:   int   = 23
    ema_alpha:    float = 0.35
    min_dist_px:  float = 3.5
    tension:      float = 1.0  # Catmull–Rom tension

    @staticmethod
    def _qcolor_to_hex(c: QtGui.QColor) -> str:
        return "#{:02X}{:02X}{:02X}".format(c.red(), c.green(), c.blue())

    @staticmethod
    def _hex_to_qcolor(txt: str, fallback: QtGui.QColor) -> QtGui.QColor:
        c = QtGui.QColor(txt)
        return c if c.isValid() else fallback

    def save(self, s: QtCore.QSettings):
        s.setValue("color_start", self._qcolor_to_hex(self.color_start))
        s.setValue("color_end",   self._qcolor_to_hex(self.color_end))
        s.setValue("fade_seconds", self.fade_seconds)
        s.setValue("core_width",   self.core_width)
        s.setValue("glow_width",   self.glow_width)
        s.setValue("ema_alpha",    self.ema_alpha)
        s.setValue("min_dist_px",  self.min_dist_px)
        s.setValue("tension",      self.tension)

    @staticmethod
    def load(s: QtCore.QSettings) -> "Config":
        cfg = Config()
        cfg.color_start = Config._hex_to_qcolor(s.value("color_start", "#00FFFF"), QtGui.QColor(0,255,255))
        cfg.color_end   = Config._hex_to_qcolor(s.value("color_end",   "#00FFFF"), QtGui.QColor(0,255,255))
        cfg.fade_seconds = float(s.value("fade_seconds", cfg.fade_seconds))
        cfg.core_width   = int(s.value("core_width",   cfg.core_width))
        cfg.glow_width   = int(s.value("glow_width",   cfg.glow_width))
        cfg.ema_alpha    = float(s.value("ema_alpha",  cfg.ema_alpha))
        cfg.min_dist_px  = float(s.value("min_dist_px", cfg.min_dist_px))
        cfg.tension      = float(s.value("tension",     cfg.tension))
        return cfg

# ------------------------- Overlay window -------------------------
@dataclass
class TrailPoint:
    x: int; y: int; t: float; stroke: int

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
        self.stroke_id = 0
        self.prev_ctrl = False
        self._ema_xy: Optional[Tuple[float, float]] = None
        self.paused = False

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

    # ----- sampling / smoothing -----
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
            self.prev_ctrl = pressed

        cutoff = now - self.cfg.fade_seconds
        if self.points and self.points[0].t < cutoff:
            self.points = [p for p in self.points if p.t >= cutoff]
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

    def _age_to_fade_and_color(self, age: float):
        life = max(0.0, min(1.0, age / self.cfg.fade_seconds))
        fade = 1.0 - life
        s = self.cfg.color_start; e = self.cfg.color_end
        r = int(s.red()   + (e.red()   - s.red())   * life)
        g = int(s.green() + (e.green() - s.green()) * life)
        b = int(s.blue()  + (e.blue()  - s.blue())  * life)
        return fade, QtGui.QColor(r, g, b)

    def _set_pens_for_age(self, painter: QtGui.QPainter, age: float):
        fade, col = self._age_to_fade_and_color(age)
        glow_col = QtGui.QColor(col); glow_col.setAlpha(int(fade * 110))
        core_col = QtGui.QColor(col); core_col.setAlpha(int(fade * 230))
        self.glow_pen.setColor(glow_col); self.core_pen.setColor(core_col)
        self.glow_pen.setCapStyle(QtCore.Qt.FlatCap)
        self.core_pen.setCapStyle(QtCore.Qt.FlatCap)
        painter.setPen(self.glow_pen)

    def _draw_round_cap(self, painter: QtGui.QPainter, x: int, y: int, age: float):
        fade, col = self._age_to_fade_and_color(age)
        if fade <= 0.0: return
        lx, ly = self._to_local(x, y)
        painter.setPen(QtCore.Qt.NoPen)

        glow = QtGui.QColor(col); glow.setAlpha(int(fade * 110))
        painter.setBrush(QtGui.QBrush(glow))
        painter.drawEllipse(QtCore.QPointF(lx, ly), self.cfg.glow_width/2, self.cfg.glow_width/2)

        core = QtGui.QColor(col); core.setAlpha(int(fade * 230))
        painter.setBrush(QtGui.QBrush(core))
        painter.drawEllipse(QtCore.QPointF(lx, ly), self.cfg.core_width/2, self.cfg.core_width/2)

    # ----- paint -----
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
                    C1, C2 = self._catmull_rom_to_bezier(P0, P1, P2, P3, self.cfg.tension)
                    path = QtGui.QPainterPath(P1); path.cubicTo(C1, C2, P2)

                    age = now - p2.t
                    fade, _ = self._age_to_fade_and_color(age)
                    if fade <= 0.0: continue
                    self._set_pens_for_age(painter, age)
                    painter.setPen(self.glow_pen); painter.drawPath(path)
                    painter.setPen(self.core_pen); painter.drawPath(path)

                tail, head = segment[0], segment[-1]
                self._draw_round_cap(painter, tail.x, tail.y, now - tail.t)
                self._draw_round_cap(painter, head.x, head.y, now - head.t)

            i = j

# ------------------------- Settings dialog -------------------------
class SettingsDialog(QtWidgets.QDialog):
    config_changed = QtCore.pyqtSignal(Config)

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setModal(False)
        self.setMinimumWidth(420)
        self.cfg = cfg  # live reference

        def color_button(initial: QtGui.QColor):
            btn = QtWidgets.QPushButton()
            btn.setFixedWidth(60)
            btn.setStyleSheet(f"background-color: {initial.name()}; border: 1px solid #444;")
            return btn

        # Widgets
        self.btn_start = color_button(self.cfg.color_start)
        self.btn_end   = color_button(self.cfg.color_end)
        self.spin_fade = QtWidgets.QDoubleSpinBox()
        self.spin_fade.setRange(0.1, 20.0); self.spin_fade.setSingleStep(0.1)
        self.spin_fade.setValue(self.cfg.fade_seconds)

        self.spin_core = QtWidgets.QSpinBox(); self.spin_core.setRange(1, 100); self.spin_core.setValue(self.cfg.core_width)
        self.spin_glow = QtWidgets.QSpinBox(); self.spin_glow.setRange(0, 200); self.spin_glow.setValue(self.cfg.glow_width)

        self.slider_core = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.slider_core.setRange(1, 100); self.slider_core.setValue(self.cfg.core_width)
        self.slider_glow = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.slider_glow.setRange(0, 200); self.slider_glow.setValue(self.cfg.glow_width)

        self.spin_ema  = QtWidgets.QDoubleSpinBox(); self.spin_ema.setRange(0.0, 1.0); self.spin_ema.setSingleStep(0.05); self.spin_ema.setValue(self.cfg.ema_alpha)
        self.spin_min  = QtWidgets.QDoubleSpinBox(); self.spin_min.setRange(0.0, 20.0); self.spin_min.setSingleStep(0.1); self.spin_min.setValue(self.cfg.min_dist_px)
        self.spin_tens = QtWidgets.QDoubleSpinBox(); self.spin_tens.setRange(0.2, 2.0); self.spin_tens.setSingleStep(0.1); self.spin_tens.setValue(self.cfg.tension)

        # Layout
        form = QtWidgets.QFormLayout()
        cstart = QtWidgets.QHBoxLayout(); cstart.addWidget(self.btn_start); cstart.addStretch(1)
        cend   = QtWidgets.QHBoxLayout(); cend.addWidget(self.btn_end);   cend.addStretch(1)
        form.addRow("Start color:", cstart)
        form.addRow("Finish color:", cend)
        form.addRow("Fade (seconds):", self.spin_fade)

        # Core/glow with sliders + spinboxes linked
        coreBox = QtWidgets.QHBoxLayout(); coreBox.addWidget(self.slider_core); coreBox.addWidget(self.spin_core)
        glowBox = QtWidgets.QHBoxLayout(); glowBox.addWidget(self.slider_glow); glowBox.addWidget(self.spin_glow)
        form.addRow("Core thickness:", coreBox)
        form.addRow("Glow thickness:", glowBox)

        # Advanced
        adv = QtWidgets.QGroupBox("Advanced smoothing")
        advForm = QtWidgets.QFormLayout(adv)
        advForm.addRow("EMA α (smoothing):", self.spin_ema)
        advForm.addRow("Min spacing (px):", self.spin_min)
        advForm.addRow("Curve tension:", self.spin_tens)

        btn_close = QtWidgets.QPushButton("Close")
        btn_reset = QtWidgets.QPushButton("Reset defaults")

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1); buttons.addWidget(btn_reset); buttons.addWidget(btn_close)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(adv)
        outer.addLayout(buttons)

        # Signals: color pickers
        self.btn_start.clicked.connect(lambda: self.pick_color("start"))
        self.btn_end.clicked.connect(lambda: self.pick_color("end"))

        # link sliders & spins
        self.slider_core.valueChanged.connect(self.spin_core.setValue)
        self.spin_core.valueChanged.connect(self.slider_core.setValue)
        self.slider_glow.valueChanged.connect(self.spin_glow.setValue)
        self.spin_glow.valueChanged.connect(self.slider_glow.setValue)

        # live-apply on any change
        for w, attr in [
            (self.spin_fade, "fade_seconds"),
            (self.spin_core, "core_width"),
            (self.spin_glow, "glow_width"),
            (self.spin_ema,  "ema_alpha"),
            (self.spin_min,  "min_dist_px"),
            (self.spin_tens, "tension"),
        ]:
            w.valueChanged.connect(lambda _=None, a=attr, ww=w: self.update_cfg(a, ww.value()))

        btn_reset.clicked.connect(self.reset_defaults)
        btn_close.clicked.connect(self.close)

    def pick_color(self, which: str):
        initial = self.cfg.color_start if which == "start" else self.cfg.color_end
        chosen = QtWidgets.QColorDialog.getColor(initial, self, f"Pick {which} color",
                                                 QtWidgets.QColorDialog.ShowAlphaChannel | QtWidgets.QColorDialog.DontUseNativeDialog)
        if chosen.isValid():
            if which == "start":
                self.cfg.color_start = chosen
                self.btn_start.setStyleSheet(f"background-color: {chosen.name()}; border:1px solid #444;")
            else:
                self.cfg.color_end = chosen
                self.btn_end.setStyleSheet(f"background-color: {chosen.name()}; border:1px solid #444;")
            self.emit_change()

    def update_cfg(self, attr: str, value):
        # Coerce to right type
        if attr in ("fade_seconds", "ema_alpha", "min_dist_px", "tension"):
            setattr(self.cfg, attr, float(value))
        else:
            setattr(self.cfg, attr, int(value))
        self.emit_change()

    def reset_defaults(self):
        self.cfg = Config()  # reset
        # reflect defaults in UI
        self.btn_start.setStyleSheet(f"background-color: {self.cfg.color_start.name()}; border:1px solid #444;")
        self.btn_end.setStyleSheet(f"background-color: {self.cfg.color_end.name()}; border:1px solid #444;")
        self.spin_fade.setValue(self.cfg.fade_seconds)
        self.spin_core.setValue(self.cfg.core_width)
        self.spin_glow.setValue(self.cfg.glow_width)
        self.spin_ema.setValue(self.cfg.ema_alpha)
        self.spin_min.setValue(self.cfg.min_dist_px)
        self.spin_tens.setValue(self.cfg.tension)
        self.emit_change()

    def emit_change(self):
        self.config_changed.emit(self.cfg)

# ------------------------- Tray icon -------------------------
class Tray(QtWidgets.QSystemTrayIcon):
    def __init__(self, overlay: Overlay, settings: QtCore.QSettings, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.settings = settings
        self.setIcon(self._default_icon())

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
        self.setToolTip(APP_NAME)
        self.show()

        self.dlg: Optional[SettingsDialog] = None

    def _default_icon(self):
        pm = QtGui.QPixmap(64,64); pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(0,200,255)); pen.setWidth(8)
        p.setPen(pen); p.drawEllipse(8,8,48,48); p.end()
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
    app.setOrganizationName(ORG_NAME); app.setOrganizationDomain(ORG_DOMAIN); app.setApplicationName(APP_NAME)

    settings = QtCore.QSettings(QtCore.QSettings.UserScope, ORG_NAME, APP_NAME)
    cfg = Config.load(settings)

    overlay = Overlay(cfg); overlay.show()
    tray = Tray(overlay, settings)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
