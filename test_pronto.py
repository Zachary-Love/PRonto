"""Run: python3 test_pronto.py  (fakes the OS scheduler commands; touches nothing real)"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pronto


def fake_run(calls, crontab=""):
    def run(args, input=None, **kw):
        calls.append((args, input))
        return SimpleNamespace(stdout=crontab)
    return run


def test_cron_keeps_other_jobs():
    calls = []
    sys.platform = "linux"
    subprocess.run = fake_run(calls, "0 * * * * backup.sh\n*/5 * * * * old pronto # pronto\n")
    pronto.set_schedule(["/py", "/x/pronto.py", "--max-age", "30"], 15)
    assert calls[-1][1] == "0 * * * * backup.sh\n*/15 * * * * /py /x/pronto.py --max-age 30 # pronto\n", calls[-1][1]

    pronto.set_schedule(["/py"], 120)
    assert "0 */2 * * * /py # pronto" in calls[-1][1]

    pronto.set_schedule(None, 0)
    assert calls[-1][1] == "0 * * * * backup.sh\n"


def test_windows_task():
    calls = []
    sys.platform = "win32"
    subprocess.run = fake_run(calls)
    pronto.set_schedule([r"C:\Program Files\py\pythonw.exe", r"C:\x\pronto.py"], 15)
    assert calls[0][0][:2] == ["schtasks", "/Delete"]
    create = calls[1][0]
    assert create[create.index("/MO") + 1] == "15"
    assert create[create.index("/TR") + 1] == r'"C:\Program Files\py\pythonw.exe" C:\x\pronto.py'


def test_login_item(tmp):
    os.environ["HOME"] = tmp
    sys.platform = "linux"
    pronto.set_login_item(["/py", "/x/pronto.py", "tray"])
    desktop = Path(tmp, ".config", "autostart", "pronto.desktop")
    assert "Exec=/py /x/pronto.py tray\n" in desktop.read_text()
    pronto.set_login_item(None)
    assert not desktop.exists()

    reg = {}
    sys.modules["winreg"] = SimpleNamespace(
        HKEY_CURRENT_USER=0, KEY_SET_VALUE=0, REG_SZ=1,
        OpenKey=lambda *a: contextlib.nullcontext(),
        SetValueEx=lambda key, name, _, kind, value: reg.update({name: value}),
        DeleteValue=lambda key, name: reg.pop(name))
    sys.platform = "win32"
    pronto.set_login_item([r"C:\py\pythonw.exe", "tray"])
    assert reg == {"pronto": r"C:\py\pythonw.exe tray"}
    pronto.set_login_item(None)
    assert reg == {}


def test_html_error_page_is_skipped_not_fatal():
    def api(token, method, path, body=None):
        if method == "GET":
            n = len(api.calls)
            api.calls.append(path)
            return {"items": [{"repository_url": pronto.API + "/repos/o/r", "number": 1},
                              {"repository_url": pronto.API + "/repos/o/r", "number": 2}] if n == 0 else []}
        if path.endswith("/1/update-branch"):
            raise urllib.error.HTTPError(path, 502, "Bad Gateway", {}, io.BytesIO(b"<html>oops</html>"))
        return {}
    api.calls = []
    real, pronto.api = pronto.api, api
    try:
        assert pronto.update_all("t") == 1  # PR 1 skipped, PR 2 still updated
    finally:
        pronto.api = real


if __name__ == "__main__":
    real = sys.platform, subprocess.run
    try:
        test_cron_keeps_other_jobs()
        test_windows_task()
        test_html_error_page_is_skipped_not_fatal()
        with tempfile.TemporaryDirectory() as tmp:
            test_login_item(tmp)
    finally:
        sys.platform, subprocess.run = real
    print("ok")
