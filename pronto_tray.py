"""Menu-bar (macOS) / system-tray (Windows, Linux) icon for PRonto."""
import io
import os
import subprocess
import sys
import threading

import pystray
from PIL import Image, ImageDraw

import pronto

AGES = {"Any age": None, "7 days": 7, "30 days": 30, "90 days": 90, "1 year": 365}
EVERY = {"5 min": 5, "15 min": 15, "30 min": 30, "1 hour": 60}
MAC = sys.platform == "darwin"
GREEN = (52, 199, 89)

# Dog's head in side profile, facing right, on a 256x256 grid.
HEAD = [(40, 252), (38, 190), (50, 128), (76, 78), (116, 48), (158, 46), (186, 70), (204, 88),
        (228, 96), (246, 104), (254, 118), (248, 134), (226, 142), (200, 154), (176, 168), (150, 182),
        (130, 204), (124, 252)]
EAR = [(80, 92), (126, 66), (150, 98), (150, 146), (122, 170), (92, 152), (82, 124)]


def smooth(pts, steps=12):
    """Points along a closed Catmull-Rom curve through pts (`steps` per segment)."""
    out, n = [], len(pts)
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        for k in range(steps):
            t = k / steps
            out.append(tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t
                                    + (3 * b - a - 3 * c + d) * t ** 3) for a, b, c, d in zip(p0, p1, p2, p3)))
    return out


def image(enabled, size=64):
    """Black dog silhouette. Elsewhere than macOS it gets a white outline (visible on any
    taskbar) and a green dot when on; on macOS the Icon class below handles both."""
    img = Image.new("RGBA", (256, 256))
    d = ImageDraw.Draw(img)
    cut = (0, 0, 0, 0) if MAC else "white"  # details: see-through on macOS, white elsewhere
    head = smooth(HEAD)
    if not MAC:
        d.polygon(head, fill="white", outline="white", width=22)
    d.polygon(head, fill="black")
    d.line(smooth(EAR)[12:70], fill=cut, width=10, joint="curve")  # ear: front + bottom edge
    d.ellipse((160, 76, 177, 93), fill=cut)                         # eye
    d.line([(240, 139), (206, 149), (188, 151)], fill=cut, width=8, joint="curve")  # mouth
    for x, y in ((212, 120), (224, 117), (219, 128)):               # whisker dots
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=cut)
    if enabled and not MAC:
        d.ellipse((168, 168, 254, 254), fill="white")
        d.ellipse((178, 178, 244, 244), fill=GREEN)
    return img.resize((size, size), Image.LANCZOS)


if MAC:
    import AppKit
    import Foundation
    import Quartz
    from PyObjCTools import AppHelper

    class Icon(pystray.Icon):
        """Makes the dog a template image, so macOS colors it to match the menu bar like
        native icons, and lays a green dot over it when on (template images can't hold color).
        """
        # ponytail: overrides pystray 0.19's private _assert_image; pystray is pinned <0.20
        enabled = False

        def _assert_image(self):
            if self._icon_image:
                return
            pt = self._status_bar.thickness()
            png = io.BytesIO()
            image(self.enabled, int(pt * 2)).save(png, "png")  # 2x so it's sharp on Retina
            self._icon_image = AppKit.NSImage.alloc().initWithData_(Foundation.NSData(png.getvalue()))
            self._icon_image.setSize_((pt, pt))
            self._icon_image.setTemplate_(True)
            # pystray calls this from a background thread; AppKit views must be touched on the main one
            AppHelper.callAfter(self._show_image)

        def _show_image(self):
            button = self._status_item.button()
            button.setImage_(self._icon_image)
            pt = self._status_bar.thickness()
            if not hasattr(self, "_dot"):
                d = round(pt * 0.3)
                w, h = button.bounds().size
                x = (w + pt) / 2 - d  # bottom-right corner of the dog, which is centered in the button
                y = h - d if button.isFlipped() else 0
                self._dot = AppKit.NSView.alloc().initWithFrame_(((x, y), (d, d)))
                self._dot.setWantsLayer_(True)
                self._dot.layer().setBackgroundColor_(Quartz.CGColorCreateGenericRGB(*(c / 255 for c in GREEN), 1))
                self._dot.layer().setCornerRadius_(d / 2)
                button.addSubview_(self._dot)
            self._dot.setHidden_(not self.enabled)
else:
    Icon = pystray.Icon


def open_file(path):
    path.touch()
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", path])


def build_icon():
    s = pronto.load_settings()

    def say(icon, message):
        if icon.HAS_NOTIFICATION:  # not every Linux backend has notifications
            try:
                icon.notify(message, "PRonto")
            except Exception:
                pass

    def change(icon, **new):
        s.update(pronto.load_settings())  # pick up anything `pronto install` changed meanwhile
        s.update(new)
        try:
            pronto.apply_settings(**s)
        except Exception as e:
            s.update(pronto.load_settings())  # roll back to what's actually saved
            say(icon, f"Couldn't save settings: {e}")
        icon.enabled = s["enabled"]
        icon.icon = image(s["enabled"])  # also redraws the macOS dot
        icon.update_menu()

    def run_now(icon):
        def work():
            try:
                n = pronto.update_all(pronto.get_token(), max_age_days=s["max_age"])
                say(icon, f"Updated {n} PR{'' if n == 1 else 's'}")
            except (Exception, SystemExit) as e:  # get_token() exits when there's no token
                say(icon, f"Run failed: {e}")
        threading.Thread(target=work, daemon=True).start()

    def choice(key, label, value):
        return pystray.MenuItem(label, lambda icon: change(icon, **{key: value}),
                                checked=lambda _: s[key] == value, radio=True)

    menu = pystray.Menu(
        pystray.MenuItem("Enabled", lambda icon: change(icon, enabled=not s["enabled"]),
                         checked=lambda _: s["enabled"]),
        pystray.MenuItem("Max PR age", pystray.Menu(*(choice("max_age", k, v) for k, v in AGES.items()))),
        pystray.MenuItem("Check every", pystray.Menu(*(choice("every", k, v) for k, v in EVERY.items()))),
        pystray.MenuItem("Run now", run_now),
        pystray.MenuItem("Open log", lambda: open_file(pronto.LOG_FILE)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda icon: icon.stop()),
    )
    if MAC:  # menu-bar only, no Dock icon
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    icon = Icon("pronto", image(s["enabled"]), "PRonto", menu)
    icon.enabled = s["enabled"]
    return icon


def single_instance():
    """Lock held for the life of the process. Returns None if another tray already holds it."""
    pronto.CONFIG.mkdir(parents=True, exist_ok=True)
    f = open(pronto.CONFIG / "tray.lock", "a")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def main(foreground=False):
    if foreground:
        lock = single_instance()
        if lock:  # otherwise a tray is already running; quietly do nothing
            build_icon().run()
        return
    if not pronto.TOKEN_FILE.exists():
        pronto.save_token(pronto.get_token())
    cmd = [pronto.python_exe(), os.path.abspath(pronto.__file__), "tray", "--foreground", "--log", str(pronto.LOG_FILE)]
    pronto.set_login_item(cmd)
    detach = {"creationflags": subprocess.DETACHED_PROCESS} if sys.platform == "win32" else {"start_new_session": True}
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detach)
    print("PRonto is in your menu bar / system tray, and will start when you log in.")
