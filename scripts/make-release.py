"""Create the v1.2.1 GitHub release and upload its assets.

Token comes from the Windows credential manager entry that git already uses
(see README "推送凭据"). Reading it through subprocess with binary pipes avoids
the gbk decode error that text=True triggers on this console.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import argparse

REPO = "devin667/comfyui-dsh"
DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist")

_ap = argparse.ArgumentParser(description="Create a GitHub release and upload its assets.")
_ap.add_argument("version", help="version without the v prefix, e.g. 1.2.1")
_ap.add_argument("--name", default=None, help="release title; defaults to the tag")
_ap.add_argument("--notes", default=None, help="notes file; defaults to dist/notes-v<version>.md")
_args = _ap.parse_args()
TAG = "v" + _args.version.lstrip("v")

def token():
    """Read the stored https://github.com credential straight from git.

    `bash -lc` does not work here: the login shell in this environment is not
    bash on PATH, so it exits 1 and prints a WSL install message in UTF-16.
    Feeding the credential protocol on stdin keeps everything ASCII.
    """
    p = subprocess.run(["git", "-c", "credential.helper=wincred",
                        "credential", "fill"],
                       input=b"protocol=https\nhost=github.com\n\n",
                       capture_output=True)
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("password="):
            return line[len("password="):].strip()
    raise SystemExit(f"no password in credential output: {p.stdout[:200]!r}")

TOK = token()
assert TOK.startswith("gh") or len(TOK) >= 20, f"bad token: {TOK[:6]!r}"

def api(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"https://api.github.com{path}", data=body, method=method,
        headers={"Authorization": f"token {TOK}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json",
                 "User-Agent": "comfyui-dsh-release"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "body": e.read().decode("utf-8", "replace")[:500]}

def upload(rel_id, name, path):
    url = f"https://uploads.github.com/repos/{REPO}/releases/{rel_id}/assets?name={name}"
    size = os.path.getsize(path)
    req = urllib.request.Request(url, data=open(path, "rb").read(), method="POST",
        headers={"Authorization": f"token {TOK}",
                 "Content-Type": "application/octet-stream",
                 "Content-Length": str(size),
                 "User-Agent": "comfyui-dsh-release"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
            return d.get("name"), d.get("size"), d.get("browser_download_url")
    except urllib.error.HTTPError as e:
        return ("ERR", e.code, e.read().decode("utf-8", "replace")[:300])

# 已有同名 release 就复用
existing = api("GET", f"/repos/{REPO}/releases/tags/{TAG}")
if existing.get("id"):
    rel = existing
    print("reusing release", rel["id"])
else:
    notes_path = _args.notes or os.path.join(DIST, f"notes-v{_args.version}.md")
    notes = open(notes_path, encoding="utf-8").read()
    rel = api("POST", f"/repos/{REPO}/releases", {
        "tag_name": TAG, "name": _args.name or TAG,
        "body": notes, "draft": False, "prerelease": False})
    if rel.get("__err"):
        sys.exit(f"create failed: {rel}")
    print("created release", rel["id"])

for f in ["comfyui-dsh.zip", f"SHA256SUMS-v{_args.version}"]:
    print(upload(rel["id"], f, os.path.join(DIST, f)))

final = api("GET", f"/repos/{REPO}/releases/tags/{TAG}")
print("url:", final.get("html_url"))
print("assets:", [(a["name"], a["size"]) for a in final.get("assets", [])])
