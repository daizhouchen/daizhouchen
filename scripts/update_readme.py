#!/usr/bin/env python3
"""Refresh 'recently-pushed' block in README from GitHub events.

Runs daily via .github/workflows/refresh.yml.
- Pulls last 100 events from /users/<user>/events
- Filters to PushEvents on public repos (skips private + archived + the profile repo itself)
- Picks 5 most-recent unique repos
- Atomically replaces content between BEGIN/END markers in README.md
- If anything fails, exits without writing — keeps existing README intact
"""
import os
import re
import sys
from pathlib import Path

import requests

USER = "daizhouchen"
PROFILE_REPO = f"{USER}/{USER}"
TOKEN = os.environ["GITHUB_TOKEN"]
README = Path("README.md")
BEGIN = "<!-- BEGIN recently-pushed -->"
END = "<!-- END recently-pushed -->"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def fetch_events():
    """Last 100 user events (3 pages of 30 max via per_page; events API capped)."""
    r = requests.get(
        f"https://api.github.com/users/{USER}/events?per_page=100",
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_repo(full_name):
    r = requests.get(
        f"https://api.github.com/repos/{full_name}",
        headers=HEADERS, timeout=30,
    )
    if r.status_code != 200:
        return None
    return r.json()


def main():
    events = fetch_events()
    seen = {}  # repo_full_name -> created_at
    for ev in events:
        if ev.get("type") != "PushEvent":
            continue
        repo = ev["repo"]["name"]
        if repo == PROFILE_REPO:
            continue  # don't show pushes to profile itself
        if repo in seen:
            continue
        seen[repo] = ev["created_at"]

    rows = []
    for repo, created_at in seen.items():
        meta = fetch_repo(repo)
        if meta is None:
            continue
        if meta.get("private"):
            continue
        if meta.get("archived"):
            continue  # archived = "old", skip from "recently shipped"
        desc = (meta.get("description") or "").strip()
        if not desc:
            continue  # skip repos without a description (looks bad in list)
        # truncate long descriptions
        if len(desc) > 100:
            desc = desc[:97] + "…"
        date = created_at[:10]
        name = repo.split("/")[-1]
        rows.append(f"- [{name}](https://github.com/{repo}) — {desc} · `{date}`")
        if len(rows) >= 5:
            break

    if not rows:
        print("No qualifying push events; skipping update.", file=sys.stderr)
        return

    new_block = "\n".join(rows)
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    replacement = f"{BEGIN}\n\n{new_block}\n\n{END}"
    new_text = pattern.sub(replacement, text)

    if new_text == text:
        print("No change.")
        return

    README.write_text(new_text, encoding="utf-8")
    print(f"README updated with {len(rows)} entries.")


if __name__ == "__main__":
    main()
