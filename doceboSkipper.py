# Python 3.9
# Always-on-top desktop overlay (red box) + top-2 color watcher + conditional click with cooldown.

import sys
import time
import threading
import ctypes
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import mss
import pyautogui
import keyboard

from PyQt5 import QtCore, QtGui, QtWidgets

# ===== CONFIG =====
SAMPLE_PERIOD = 3.0               # seconds between reports
QUANTIZE_STEPS = [0, 8, 16]       # 0=exact; 8/16 bucket similar shades
SECOND_COLOR_DARK_THRESHOLD = 90  # 2nd color considered "dark" if R,G,B < 90
CLICK_COOLDOWN = 5.0              # seconds after a click before another allowed
MAX_ROWS_PRINT = 2                # print only top 2 colors
OVERLAY_REFRESH_MS = 250          # redraw overlay box every 250ms
# ===================

HK_SET_TOPLEFT  = "ctrl+alt+1"
HK_SET_BOTRIGHT = "ctrl+alt+2"
HK_START        = "ctrl+alt+s"
HK_STOP         = "ctrl+alt+d"
HK_QUIT         = "ctrl+alt+q"
HK_TOGGLE_QTZ   = "ctrl+alt+g"

pyautogui.FAILSAFE = False

# ---- Virtual desktop geometry (handles multi-monitor) ----
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

def get_virtual_screen_rect() -> QtCore.QRect:
    vx = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return QtCore.QRect(vx, vy, vw, vh)

@dataclass
class Region:
    left: int
    top: int
    width: int
    height: int
    def mss_dict(self):
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}
    def center(self) -> Tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

# Globals shared between worker & overlay
region: Optional[Region] = None
running = False
quantize_idx = 0
last_click_ts = 0.0

# ------------- Overlay Window (always-on-top, transparent, click-through) -------------
class OverlayWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)  # click-through
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowFlag(QtCore.Qt.Tool, True)  # avoid taskbar entry

        # Expand to the whole virtual desktop
        vr = get_virtual_screen_rect()
        # On Windows, Qt uses a (0,0) origin; we position the window at the virtual origin
        # and size it to cover all monitors
        self.move(vr.left(), vr.top())
        self.resize(vr.width(), vr.height())

        # Pen for rectangle
        self.pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
        self.pen.setWidth(3)

        # Timer to refresh overlay
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(OVERLAY_REFRESH_MS)

    def paintEvent(self, event: QtGui.QPaintEvent):
        if region is None:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.setPen(self.pen)

        # Convert absolute screen coords to this window's coords
        vr = get_virtual_screen_rect()
        x = region.left - vr.left()
        y = region.top - vr.top()
        w = region.width
        h = region.height
        painter.drawRect(x, y, w, h)

# --------------------- Color counting + click worker ---------------------
def grab_region_rgb(sct: mss.mss, r: Region) -> np.ndarray:
    bgra = np.array(sct.grab(r.mss_dict()))  # BGRA
    rgb = bgra[:, :, :3][:, :, ::-1]        # to RGB
    return rgb

def quantize_rgb(rgb: np.ndarray, step: int) -> np.ndarray:
    if step <= 0:
        return rgb
    return (rgb // step) * step

def count_colors(rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    flat = rgb.reshape(-1, 3)
    uniques, counts = np.unique(flat, axis=0, return_counts=True)
    order = np.argsort(-counts)
    return uniques[order], counts[order]

def fmt_color(c: np.ndarray) -> str:
    return f"({int(c[0])},{int(c[1])},{int(c[2])})"

def second_color_is_dark(c: np.ndarray) -> bool:
    thr = SECOND_COLOR_DARK_THRESHOLD
    return int(c[0]) < thr and int(c[1]) < thr and int(c[2]) < thr

def click_at(x: int, y: int) -> None:
    # Save/restore cursor so user keeps control
    orig_x, orig_y = pyautogui.position()
    screen_w, screen_h = pyautogui.size()
    nx = int(x * 65535 / max(1, screen_w - 1))
    ny = int(y * 65535 / max(1, screen_h - 1))
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_MOVE     = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP   = 0x0004
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE, nx, ny, 0, 0)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, nx, ny, 0, 0)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP,   nx, ny, 0, 0)
    pyautogui.moveTo(orig_x, orig_y)

def report_loop():
    global running, last_click_ts
    print("[INFO] Reporting started. Press", HK_STOP, "to stop.")
    with mss.mss() as sct:
        while running:
            if region is None:
                time.sleep(0.2)
                continue
            try:
                img = grab_region_rgb(sct, region)
            except Exception as e:
                print(f"[ERR] capture failed: {e}")
                time.sleep(SAMPLE_PERIOD)
                continue

            step = QUANTIZE_STEPS[quantize_idx]
            img_proc = quantize_rgb(img, step) if step > 0 else img

            uniques, counts = count_colors(img_proc)
            total = int(counts.sum())
            top_n = min(MAX_ROWS_PRINT, uniques.shape[0])

            print(f"\n=== Top {top_n} colors — region [{region.left},{region.top},{region.width},{region.height}] "
                  f"— total_pixels={total} — quantization={'exact' if step==0 else f'bucket={step}'} ===")
            to_print = []
            for i in range(top_n):
                color = uniques[i]
                cnt = int(counts[i])
                pct = (cnt / total) * 100 if total else 0.0
                to_print.append((color, cnt, pct))
                print(f"{fmt_color(color):>16} = {cnt:7d}  ({pct:5.1f}%)")

            # Decision: second-most-common color dark? Click center (with cooldown)
            if top_n >= 2:
                second_color = to_print[1][0]
                dark = second_color_is_dark(second_color)
                now = time.time()
                can_click = (now - last_click_ts) >= CLICK_COOLDOWN
                print(f"[DEBUG] second_color={fmt_color(second_color)} dark={dark} cooldown_ok={can_click}")
                if dark and can_click:
                    cx, cy = region.center()
                    print(f"[CLICK] Clicking center at ({cx},{cy}) due to dark second color {fmt_color(second_color)}")
                    click_at(cx, cy)
                    last_click_ts = now
                elif dark and not can_click:
                    print("[INFO] Dark second color detected but cooling down…")

            time.sleep(SAMPLE_PERIOD)
    print("[INFO] Reporting stopped.")

# --------------------- Hotkeys & App wiring ---------------------
def set_region_from_corners(tl: Tuple[int, int], br: Tuple[int, int]) -> None:
    global region
    left = min(tl[0], br[0]); top = min(tl[1], br[1])
    width = max(1, abs(br[0] - tl[0])); height = max(1, abs(br[1] - tl[1]))
    region = Region(left, top, width, height)
    print(f"[INFO] Region set: left={left}, top={top}, width={width}, height={height}")

def main():
    app = QtWidgets.QApplication(sys.argv)
    overlay = OverlayWindow()
    overlay.show()

    def on_tl():
        keyboard._corner_tl = pyautogui.position()
        print(f"[SET] Top-left: {keyboard._corner_tl}")

    def on_br():
        if not hasattr(keyboard, "_corner_tl"):
            print("[WARN] Set top-left first with", HK_SET_TOPLEFT); return
        tl = keyboard._corner_tl
        br = pyautogui.position()
        set_region_from_corners(tl, br)
        overlay.update()

    def on_start():
        global running
        if region is None:
            print("[ERR] Region not set."); return
        if running:
            print("[INFO] Already running."); return
        running = True
        threading.Thread(target=report_loop, daemon=True).start()

    def on_stop():
        global running
        running = False

    def on_quit():
        on_stop()
        print("[INFO] Quitting…")
        QtCore.QTimer.singleShot(100, app.quit)

    def on_toggle_qtz():
        global quantize_idx
        quantize_idx = (quantize_idx + 1) % len(QUANTIZE_STEPS)
        step = QUANTIZE_STEPS[quantize_idx]
        label = "exact" if step == 0 else f"bucket={step}"
        print(f"[INFO] Quantization mode -> {label}")

    keyboard.add_hotkey(HK_SET_TOPLEFT, on_tl)
    keyboard.add_hotkey(HK_SET_BOTRIGHT, on_br)
    keyboard.add_hotkey(HK_START, on_start)
    keyboard.add_hotkey(HK_STOP, on_stop)
    keyboard.add_hotkey(HK_QUIT, on_quit)
    keyboard.add_hotkey(HK_TOGGLE_QTZ, on_toggle_qtz)

    print("\n== Color Top-2 Watcher (desktop overlay) ==")
    print("  Set region:     ", HK_SET_TOPLEFT, "(top-left),", HK_SET_BOTRIGHT, "(bottom-right)")
    print("  Start:          ", HK_START)
    print("  Stop:           ", HK_STOP)
    print("  Quit:           ", HK_QUIT)
    print("  Toggle quantize:", HK_TOGGLE_QTZ, f"(modes: {QUANTIZE_STEPS})")
    print("  Overlay: red rectangle is always on top & click-through.\n")

    # Run Qt event loop
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
