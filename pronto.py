#!/usr/bin/env python3
"""Press GitHub's "Update branch" (merge commit) button on all your open PRs."""
import argparse
import datetime
import http.client
import json
import os
import plistlib
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.github.com"
CONFIG = Path.home() / ".config" / "pronto"
TOKEN_FILE = CONFIG / "token"
LOG_FILE = CONFIG / "pronto.log"
SETTINGS_FILE = CONFIG / "settings.json"
LABEL = "pronto"  # launchd label / Windows task name / crontab marker
# Intervals every scheduler can do exactly (cron needs a divisor of an hour, or of a day in hours)
VALID_EVERY = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60, 120, 180, 240, 360, 480, 720]
# Network-ish failures worth retrying next round rather than crashing on
NETWORK_ERRORS = (OSError, ValueError, http.client.HTTPException)  # OSError covers URLError


def get_token():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    if TOKEN_FILE.exists():  # saved by `pronto install`
        return TOKEN_FILE.read_text().strip()
    try:  # fall back to the gh CLI if it's installed and logged in
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("Set GITHUB_TOKEN (or log in with `gh auth login`).")


def api(token, method, path, body=None):
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def my_open_prs(token, max_age_days=None):
    q = "is:pr is:open author:@me archived:false"
    if max_age_days:
        since = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=max_age_days)
        q += f" created:>={since.isoformat()}"
    q = urllib.parse.quote(q)
    page = 1
    while True:
        items = api(token, "GET", f"/search/issues?q={q}&per_page=100&page={page}")["items"]
        for item in items:
            # repository_url looks like https://api.github.com/repos/OWNER/REPO
            yield item["repository_url"].removeprefix(API + "/repos/"), item["number"]
        if len(items) < 100:
            return
        page += 1


def update_all(token, dry_run=False, max_age_days=None):
    """Returns how many PRs were updated."""
    updated = 0
    for repo, number in my_open_prs(token, max_age_days):
        name = f"{repo}#{number}"
        if dry_run:
            print(f"would try  {name}")
            continue
        # ponytail: no "is it behind?" pre-check. The endpoint is exactly the button:
        # it merges base in if behind, and returns 422 if up to date or conflicting.
        try:
            api(token, "PUT", f"/repos/{repo}/pulls/{number}/update-branch", {})
            print(f"updated    {name}")
            updated += 1
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("message", e.reason)
            except NETWORK_ERRORS:  # e.g. an HTML error page
                msg = f"HTTP {e.code} {e.reason}"
            print(f"skipped    {name}: {msg}")
    return updated


def set_schedule(cmd, every):
    """Remove pronto from the OS scheduler, then (if cmd) add it to run every `every` minutes."""
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink(missing_ok=True)
        if cmd:
            plist.parent.mkdir(parents=True, exist_ok=True)
            plist.write_bytes(plistlib.dumps(
                {"Label": LABEL, "ProgramArguments": cmd, "StartInterval": every * 60, "RunAtLoad": True}))
            subprocess.run(["launchctl", "load", str(plist)], check=True)
    elif sys.platform == "win32":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", LABEL], capture_output=True)
        if cmd:
            # ponytail: schtasks caps /TR at 261 chars; fine for normal install paths
            subprocess.run(["schtasks", "/Create", "/F", "/TN", LABEL, "/SC", "MINUTE", "/MO", str(every),
                            "/TR", subprocess.list2cmdline(cmd)], check=True, capture_output=True)
    else:  # Linux and friends: cron
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines()
        lines = [line for line in current if not line.endswith(f"# {LABEL}")]
        if cmd:
            when = f"*/{every} * * * *" if every < 60 else f"0 */{every // 60} * * *"
            lines.append(f"{when} {shlex.join(cmd)} # {LABEL}")
        subprocess.run(["crontab", "-"], input="".join(line + "\n" for line in lines), text=True, check=True)


def set_login_item(cmd):
    """Start `cmd` whenever the user logs in (or stop doing so, if cmd is None)."""
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}-tray.plist"
        plist.unlink(missing_ok=True)
        if cmd:
            plist.parent.mkdir(parents=True, exist_ok=True)
            plist.write_bytes(plistlib.dumps({"Label": f"{LABEL}-tray", "ProgramArguments": cmd, "RunAtLoad": True}))
    elif sys.platform == "win32":
        import winreg
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
            if cmd:
                winreg.SetValueEx(key, LABEL, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(key, LABEL)
                except FileNotFoundError:
                    pass
    else:  # XDG autostart, which Linux desktops follow
        desktop = Path.home() / ".config" / "autostart" / f"{LABEL}.desktop"
        desktop.unlink(missing_ok=True)
        if cmd:
            desktop.parent.mkdir(parents=True, exist_ok=True)
            desktop.write_text(f"[Desktop Entry]\nType=Application\nName=PRonto\nExec={shlex.join(cmd)}\n")


def python_exe():
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")  # no console window popping up
    return str(exe)


def save_token(token):
    login = api(token, "GET", "/user")["login"]  # fail now on a bad token, not silently later
    CONFIG.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(token)
    return login


def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (OSError, ValueError):
        return {"enabled": False, "every": 15, "max_age": None}


def apply_settings(enabled, every, max_age):
    """Save settings and make the OS scheduler match them."""
    cmd = None
    if enabled:
        cmd = [python_exe(), os.path.abspath(__file__), "--log", str(LOG_FILE)]
        if max_age:
            cmd += ["--max-age", str(max_age)]
    set_schedule(cmd, every)
    CONFIG.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps({"enabled": enabled, "every": every, "max_age": max_age}))


def install(every, max_age):
    login = save_token(get_token())
    apply_settings(True, every, max_age)
    print(f"Installed: updating @{login}'s PRs every {every} min. Log: {LOG_FILE}")


def uninstall():
    set_schedule(None, 0)
    set_login_item(None)
    for f in (TOKEN_FILE, SETTINGS_FILE):
        f.unlink(missing_ok=True)
    print("Uninstalled. (If the tray icon is running, quit it from its menu.)")


def start_tray(foreground=False, required=True):
    try:
        import pronto_tray  # pystray can fail to import with no desktop (e.g. a headless server)
    except Exception as e:
        if required:
            sys.exit(f"Tray icon not available: {e}")
        return print(f"Tray icon not available ({e}); the background job is still installed.")
    pronto_tray.main(foreground)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", nargs="?", default="run", choices=["run", "install", "uninstall", "tray"],
                   help="run now (default), install/uninstall as a background job, or start the tray icon")
    p.add_argument("--every", type=int, metavar="MIN",
                   help="minutes between runs (install default: 15; run default: once)")
    p.add_argument("--max-age", type=int, metavar="DAYS", help="ignore PRs opened more than DAYS ago")
    p.add_argument("--dry-run", action="store_true", help="list PRs without updating them")
    p.add_argument("--no-tray", action="store_true", help="install: don't start the menu-bar/tray icon")
    p.add_argument("--log", help=argparse.SUPPRESS)  # used by the background job
    p.add_argument("--foreground", action="store_true", help=argparse.SUPPRESS)  # tray: don't detach
    args = p.parse_args()
    if args.every is not None and args.every not in VALID_EVERY:
        p.error(f"--every must be one of: {', '.join(map(str, VALID_EVERY))}")
    if args.max_age is not None and args.max_age < 1:
        p.error("--max-age must be at least 1")

    if args.log:
        log = Path(args.log)
        # ponytail: crude rotation, start over past 1 MB
        sys.stdout = sys.stderr = open(log, "a" if log.exists() and log.stat().st_size < 1_000_000 else "w", buffering=1)
        print(f"--- {datetime.datetime.now():%Y-%m-%d %H:%M}")

    if args.command == "install":
        install(args.every or 15, args.max_age)
        if not args.no_tray:
            start_tray(required=False)
        return
    if args.command == "uninstall":
        return uninstall()
    if args.command == "tray":
        return start_tray(foreground=args.foreground)

    token = get_token()
    while True:
        try:
            update_all(token, args.dry_run, args.max_age)
        except NETWORK_ERRORS as e:  # network blip / rate limit / GitHub hiccup: try again next round
            print(f"error: {e}", file=sys.stderr)
            if not args.every:
                sys.exit(1)
        if not args.every:
            return
        time.sleep(args.every * 60)


if __name__ == "__main__":
    main()
