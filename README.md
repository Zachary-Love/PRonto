# PRonto

<p align="center">
  <img src="https://raw.githubusercontent.com/Zachary-Love/PRonto/main/assets/pronto.png" width="128" alt="PRonto logo: a dog in profile with a green dot">
</p>

**Never look at an out-of-date pull request again.**

PRonto runs quietly on your computer and keeps every open GitHub pull request you've authored up to date with its base branch. Whenever GitHub would show the **Update branch** button on one of your PRs, PRonto presses it for you, using the default "merge commit" option. When you open your PRs, they're already current.

```
$ pronto
updated    acme/webapp#412
updated    acme/api#88
skipped    acme/api#85: There are no new commits on the base branch.
skipped    acme/infra#1205: merge conflict between base and head
```

---

## Quick start

**1. Install PRonto**

```sh
uv tool install pronto-pr
```

No `uv`? Use `pipx install pronto-pr`, or [install uv](https://docs.astral.sh/uv/getting-started/installation/) first.

**2. Turn it on**

```sh
export GITHUB_TOKEN=ghp_yourtokenhere
pronto install
```

You need a GitHub token with the `repo` scope. If you don't have one, see [Creating a GitHub token](#creating-a-github-token); it takes about a minute.

That's it. PRonto checks your PRs right away, then every 15 minutes, and keeps running after a reboot. A little dog appears in your menu bar or system tray: click it to turn PRonto off, change the settings, or run it now.

---

## Contents

- [Quick start](#quick-start)
- [Features](#features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Creating a GitHub token](#creating-a-github-token)
- [Usage](#usage)
  - [One-off runs](#one-off-runs)
  - [Running in the background](#running-in-the-background)
  - [The menu-bar / tray icon](#the-menu-bar--tray-icon)
- [Command reference](#command-reference)
- [Changing settings](#changing-settings)
- [Where PRonto keeps things](#where-pronto-keeps-things)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Development](#development)
- [License](#license)

---

## Features

- **Automatic "Update branch".** Merges the base branch into each of your open PRs that's behind, exactly as the GitHub button does.
- **Safe by design.** PRs that are already up to date, or that have merge conflicts, are left alone. PRonto never force-pushes, rebases, or resolves conflicts.
- **Runs in the background.** One command registers PRonto with your operating system's scheduler (launchd on macOS, Task Scheduler on Windows, cron on Linux). It keeps running across reboots, with no terminal window left open.
- **Menu-bar / system-tray icon.** Turn PRonto on or off, change how often it checks, limit it to recent PRs, run it on demand, and open the log, all from an icon.
- **Ignore old PRs.** Limit PRonto to PRs opened in the last *N* days, so that a forgotten PR from two years ago doesn't get a merge commit every 15 minutes.
- **Dry-run mode.** See which PRs PRonto would touch without changing anything.
- **Cross-platform.** macOS, Windows and Linux.
- **Small and auditable.** About 350 lines of Python. The only dependencies are for the tray icon.

## How it works

Each run, PRonto:

1. Searches GitHub for open pull requests authored by you (`is:pr is:open author:@me archived:false`). If you set a max age, it adds `created:>=<date>`.
2. Calls GitHub's [update-branch API](https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch) for each one. This is the same action as clicking **Update branch → Update with merge commit**.
3. GitHub decides the outcome:
   - **Branch is behind:** GitHub merges the base branch into it → `updated`
   - **Already up to date:** nothing happens → `skipped … no new commits`
   - **Has conflicts:** nothing happens → `skipped … merge conflict`

PRonto doesn't use git and never touches your local clones. Everything happens on GitHub's side.

## Requirements

- **Python 3.9 or newer**
- **A GitHub account** on github.com (GitHub Enterprise Server isn't supported yet)
- **A GitHub personal access token** ([see below](#creating-a-github-token)), or the [`gh` CLI](https://cli.github.com) logged in

## Installation

### Recommended: `uv` or `pipx`

These install PRonto as a standalone command, in its own isolated environment:

```sh
uv tool install pronto-pr
# or
pipx install pronto-pr
```

Don't have either? Install [uv](https://docs.astral.sh/uv/getting-started/installation/) with `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or `winget install astral-sh.uv` (Windows).

> The package is called **`pronto-pr`** because `pronto` was already taken on PyPI. The command you run is still `pronto`.

### Try it without installing

```sh
uvx --from pronto-pr pronto --dry-run
```

### From source

```sh
git clone https://github.com/Zachary-Love/PRonto.git
cd PRonto
uv tool install -e .
```

`-e` (editable) means code changes take effect immediately. If you change dependencies in `pyproject.toml`, re-run with `uv tool install -e . --reinstall`.

### Upgrading

```sh
uv tool upgrade pronto-pr     # or: pipx upgrade pronto-pr
```

If the background job is installed, it picks up the new version on its next run. To update the tray icon, quit it and run `pronto tray`.

## Creating a GitHub token

PRonto needs a token that can read your PRs and push merge commits to their branches. Create one at **https://github.com/settings/tokens**.

### Option A: Classic token (simplest)

1. Go to **Generate new token → Generate new token (classic)**.
2. Give it a name like `PRonto` and pick an expiration.
3. Check the **`repo`** scope.
4. Generate it and copy it (it starts with `ghp_`).

**Organizations with SAML SSO:** after creating the token, click **Configure SSO** next to it on the tokens page and **Authorize** each organization. Without this, PRonto can't see or update PRs in those orgs.

### Option B: Fine-grained token (tighter permissions)

1. Go to **Generate new token → Fine-grained token**.
2. Set **Resource owner** to the account or organization that owns the repos.
3. Under **Repository access**, choose the repos (or **All repositories**).
4. Under **Repository permissions**, set:
   - **Contents:** Read and write
   - **Pull requests:** Read and write
5. Generate it and copy it (it starts with `github_pat_`).

A fine-grained token only covers **one** resource owner. If your PRs are spread across several orgs, or across your personal account and an org, use a classic token. Some orgs also require an admin to approve fine-grained tokens.

### Giving the token to PRonto

PRonto looks for a token in this order:

1. The `GITHUB_TOKEN` environment variable
2. The `GH_TOKEN` environment variable
3. The token saved by `pronto install` (`~/.config/pronto/token`)
4. The `gh` CLI (`gh auth token`), if it's installed and logged in

For a first run, set the environment variable:

```sh
export GITHUB_TOKEN=ghp_yourtokenhere          # macOS / Linux
$env:GITHUB_TOKEN = "ghp_yourtokenhere"        # Windows PowerShell
```

`pronto install` checks the token with GitHub and saves it, so you only need to do this once.

## Usage

### One-off runs

```sh
pronto --dry-run               # list the open PRs PRonto would try; changes nothing
pronto                         # update all your out-of-date PRs once, then exit
pronto --max-age 30            # only PRs opened in the last 30 days
pronto --every 10              # keep running in this terminal, every 10 minutes (Ctrl+C to stop)
```

Each PR prints one line: `updated`, or `skipped` with GitHub's reason.

### Running in the background

```sh
pronto install                            # every 15 minutes, all PRs, with the tray icon
pronto install --every 30 --max-age 60    # every 30 minutes, only PRs opened in the last 60 days
pronto install --no-tray                  # background job only, no icon (good for servers)
```

`pronto install`:

1. Finds your token and checks it with GitHub (it fails right away if the token is bad).
2. Saves the token to `~/.config/pronto/token`, readable only by your user.
3. Registers a background job with your OS:

   | OS      | Mechanism                          | Runs while           |
   |---------|------------------------------------|----------------------|
   | macOS   | launchd user agent                 | you're logged in     |
   | Windows | Task Scheduler task named `pronto` | you're logged in     |
   | Linux   | a line in your crontab             | the machine is on    |

4. Starts the tray icon and sets it to open at login (unless you pass `--no-tray`).

Every run is logged to `~/.config/pronto/pronto.log`.

While your computer is asleep, nothing runs. PRonto catches up at the next scheduled run after it wakes.

### The menu-bar / tray icon

`pronto install` starts the icon for you. If you quit it, start it again with:

```sh
pronto tray
```

The icon is a black-and-white dog in profile with a **green dot** when PRonto is on, and no dot when it's off. On macOS it's a native template icon, so it turns white or black to match your menu bar. Its menu:

| Menu item       | What it does |
|-----------------|--------------|
| **Enabled**     | Turns the background job on or off. |
| **Max PR age**  | Only update PRs opened within: Any age, 7 days, 30 days, 90 days, or 1 year. |
| **Check every** | How often the background job runs: 5 min, 15 min, 30 min, or 1 hour. |
| **Run now**     | Runs immediately and shows a notification with how many PRs were updated. |
| **Open log**    | Opens `pronto.log` in your default text viewer. |
| **Quit**        | Closes the icon. Updates keep happening in the background. |

Notes:
- The icon is a **remote control** for the background job, not the job itself. Quitting the icon doesn't stop updates; use **Enabled** or `pronto uninstall` for that.
- The icon opens automatically at login, and only one copy runs at a time.
- The menu and the command line share the same settings, so you can switch between them freely.
- **Linux:** the icon needs a desktop with system-tray support. GNOME needs the *AppIndicator* extension.

## Command reference

```
pronto [command] [options]
```

| Command     | Description |
|-------------|-------------|
| `run`       | *(default)* Update your out-of-date PRs now. |
| `install`   | Save your token, set up the background job, and start the tray icon. Run it again to change settings. |
| `uninstall` | Remove the background job and the tray icon's login entry, and delete the saved token and settings. |
| `tray`      | Start the menu-bar / tray icon in the background. |

| Option            | Applies to       | Description |
|-------------------|------------------|-------------|
| `--dry-run`       | `run`            | List PRs without updating anything. |
| `--max-age DAYS`  | `run`, `install` | Ignore PRs opened more than `DAYS` days ago. |
| `--every MIN`     | `run`, `install` | Minutes between runs: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60, 120, 180, 240, 360, 480 or 720. These are the intervals every OS scheduler can run exactly. With `run`, PRonto keeps running in the terminal; without it, it runs once. With `install`, the default is 15. |
| `--no-tray`       | `install`        | Don't start the tray icon. |
| `-h`, `--help`    | all              | Show help. |

Exit codes: `0` on success. `1` if a one-off run can't reach GitHub, or no token is found.

## Changing settings

Use the tray menu, or re-run `install` with the options you want:

```sh
pronto install --every 60 --max-age 14
```

`install` **replaces** all settings with the ones you pass. Leaving out `--max-age` resets it to "any age", and leaving out `--every` resets it to 15 minutes.

To change your token, set `GITHUB_TOKEN` to the new one and run `pronto install` again.

## Where PRonto keeps things

All PRonto files live in `~/.config/pronto/` (on Windows: `C:\Users\<you>\.config\pronto\`):

| File            | Contents |
|-----------------|----------|
| `token`         | Your GitHub token (permissions `600`: only you can read it). |
| `settings.json` | Enabled, check interval, and max PR age. |
| `pronto.log`    | Output from every background run. Starts over once it passes 1 MB. |
| `tray.lock`     | Keeps a second tray icon from starting. |

Background job and login entries:

| OS      | Background job                           | Tray icon at login |
|---------|------------------------------------------|--------------------|
| macOS   | `~/Library/LaunchAgents/pronto.plist`    | `~/Library/LaunchAgents/pronto-tray.plist` |
| Windows | Task Scheduler → `pronto`                | Registry: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `pronto` |
| Linux   | crontab line ending in `# pronto`        | `~/.config/autostart/pronto.desktop` |

## Uninstalling

```sh
pronto uninstall               # remove the background job, login entry, saved token and settings
uv tool uninstall pronto-pr    # remove the program (or: pipx uninstall pronto-pr)
```

If the tray icon is running, choose **Quit** from its menu. To remove the log too, delete `~/.config/pronto/`.

You may also want to revoke the token at https://github.com/settings/tokens.

## Troubleshooting

**Start with the log:** `~/.config/pronto/pronto.log`, or **Open log** in the tray menu. Each run starts with a `--- YYYY-MM-DD HH:MM` line.

**`Set GITHUB_TOKEN (or log in with gh auth login)`**
No token was found. [Create one](#creating-a-github-token), `export GITHUB_TOKEN=...`, then run `pronto install`.

**`HTTP Error 401: Unauthorized`**
The token is wrong, expired, or revoked. Create a new one and run `pronto install` again.

**Some PRs (often in an org) never show up**
- *Classic token:* authorize it for the org via **Configure SSO** on the tokens page.
- *Fine-grained token:* make sure the **resource owner** is that org and the repos are included. The org may also need to approve the token.

**`skipped … Resource not accessible by personal access token`**
The token can see the PR but can't push to its branch. Give it **Contents: Read and write** and **Pull requests: Read and write**, or use a classic token with `repo`.

**`skipped … merge conflict between base and head`**
Expected: GitHub can't merge automatically. Resolve the conflict yourself; PRonto picks the PR up again afterwards.

**`skipped … There are no new commits on the base branch`**
Expected: the PR is already up to date.

**`Tray icon not available: No module named 'pystray'`**
Your install is missing its dependencies. This usually happens with an editable (`-e`) install made before dependencies changed. Reinstall:
```sh
uv tool install pronto-pr --reinstall          # from PyPI
uv tool install -e . --reinstall               # from a source checkout
```

**`Tray icon not available (…); the background job is still installed.`**
PRonto couldn't show an icon, usually because there's no desktop (for example a server or SSH session). Updates still run. Use `pronto install --no-tray` to skip the icon.

**The icon doesn't appear on Linux**
Your desktop needs tray support. On GNOME, install the *AppIndicator and KStatusNotifierItem Support* extension.

**No "Run now" notification on macOS**
Notifications are sent through macOS's built-in scripting tool, so they appear under **Script Editor**. Allow them in **System Settings → Notifications → Script Editor**.

**Windows laptop: nothing runs on battery**
Task Scheduler's defaults skip tasks while on battery. Open **Task Scheduler → pronto → Properties → Conditions** and uncheck **Start the task only if the computer is on AC power**.

**Check that the background job is registered**
```sh
launchctl list | grep pronto          # macOS
schtasks /Query /TN pronto            # Windows
crontab -l | grep pronto              # Linux
```

**Debug the tray icon**
Run it attached to your terminal so errors print directly:
```sh
pronto tray --foreground
```

## FAQ

**Does PRonto rebase my branches?**
No. It only uses the "merge commit" form of Update branch. It never rebases, force-pushes, or rewrites history.

**Will this trigger CI on every update?**
Yes. Each update is a new commit on your PR branch, so CI runs just as it would after clicking the button. Use `--max-age` or a longer `--every` if that's too much.

**Which PRs does it look at?**
Open PRs that **you** authored, in repositories that aren't archived, including drafts. It doesn't touch other people's PRs.

**What about PRs from two years ago that I forgot about?**
Use `--max-age`, or **Max PR age** in the tray menu. For example, `--max-age 30` only considers PRs opened in the last 30 days.

**Does it work when my laptop is closed?**
No. It runs on your machine, so it only works while the machine is awake (and, on macOS and Windows, while you're logged in). It catches up at the next scheduled run.

**Will it hit GitHub's rate limits?**
Unlikely. Each run makes one search request per 100 PRs, plus one request per PR. Even every 5 minutes, that's well within GitHub's limits for normal use.

**Is my token safe?**
It's stored in a file only your user can read, sent only to `api.github.com`, and never logged. `pronto uninstall` deletes it. A classic token with `repo` scope is powerful, so set an expiration, or use a fine-grained token if your PRs live under one owner.

**Does it work with GitHub Enterprise Server?**
Not yet: the API URL is fixed to `api.github.com`.

## Development

```sh
git clone https://github.com/Zachary-Love/PRonto.git
cd PRonto
uv tool install -e .       # installs the `pronto` command from your checkout
python3 test_pronto.py     # prints "ok"
```

Project layout:

| File              | Purpose |
|-------------------|---------|
| `pronto.py`       | CLI, GitHub API calls, background-job and login-item setup |
| `pronto_tray.py`  | Menu-bar / tray icon |
| `test_pronto.py`  | Scheduler and login-item tests (fakes OS calls; touches nothing real) |
| `pyproject.toml`  | Packaging metadata |

A safe way to try changes end to end: create a throwaway repo, open a PR, then push a commit to `main` so the PR falls behind. `pronto --max-age 1` should then report it as `updated`.

## License

[MIT](LICENSE) © 2026 Zachary Love
