"""把 comfyui-dsh 发布到新账号：建仓库 → 推 main + tag → 建 release 传资产。

用法（token 只在本进程内存里，不落盘、不写日志）：

    GH_TOKEN=ghp_xxx python scripts/publish-new-account.py
    python scripts/publish-new-account.py --token ghp_xxx
    python scripts/publish-new-account.py            # 交互输入，不显示回显

可选：
    --owner Luckinchan7   账号名，默认 Luckinchan7
    --repo comfyui-dsh    仓库名，默认 comfyui-dsh
    --version 1.4.5       要发布的版本，默认取最新 tag
    --skip-push           只建仓库和 release（分支已经推过时）
    --dry                 只校验 token 与远端状态，不改任何东西

前置：本地已有 dist/comfyui-dsh.zip 与 dist/SHA256SUMS-v<version>
（由 scripts/pack-release.ps1 生成）。
"""

import argparse
import getpass
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
API = "https://api.github.com"


def out(msg):
    print(msg, flush=True)


def api(method, path, token, data=None, raw=None, ctype=None):
    """打 GitHub API；raw 非空时直接发字节（上传资产用）。"""
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "comfyui-dsh-publish",
    }
    if body is not None:
        headers["Content-Type"] = ctype or "application/json"
    req = urllib.request.Request(f"{API}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload.strip()[:1] in b"{[" else payload)
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"body": payload[:400]}


def run(cmd, cwd=ROOT, env_extra=None):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def latest_tag():
    rc, so, _ = run(["git", "tag", "--sort=-v:refname"])
    tags = [t.strip() for t in so.splitlines() if t.strip()]
    return tags[0] if tags else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--owner", default="Luckinchan7")
    ap.add_argument("--repo", default="comfyui-dsh")
    ap.add_argument("--version", default=None)
    ap.add_argument("--skip-push", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    token = (a.token or "").strip()
    if not token:
        try:
            token = getpass.getpass("GitHub PAT（输入不回显）: ").strip()
        except (KeyboardInterrupt, EOFError):
            return 2
    if not token:
        out("没有拿到 token。")
        return 2

    full = f"{a.owner}/{a.repo}"
    version = a.version or (latest_tag() or "").lstrip("v")
    if not version:
        out("找不到版本号：本地没有 tag，也没传 --version。")
        return 2
    tag = "v" + version

    # 1. 校验 token 是谁
    code, user = api("GET", "/user", token)
    if code != 200:
        out(f"token 无效或被限：HTTP {code} {user}")
        return 1
    login = user.get("login")
    out(f"token 归属：{login}")
    if login.lower() != a.owner.lower():
        out(f"token 属于 {login}，不是 {a.owner} —— 换一个该账号的 PAT。")
        return 1

    # 2. 仓库在不在
    code, repo = api("GET", f"/repos/{full}", token)
    exists = code == 200
    out(f"仓库 {full}：" + ("已存在" if exists else f"不存在（HTTP {code}）"))

    if a.dry:
        out("--dry：到此为止，什么都没改。")
        return 0

    if not exists:
        code, repo = api("POST", "/user/repos", token, data={
            "name": a.repo,
            "description": "本地生图：ComfyUI + DeepSeek Harness，一份能跑的工作流与实测数据",
            "private": False,
            "has_issues": True,
            "has_wiki": False,
            "auto_init": False,
        })
        if code not in (200, 201):
            out(f"建仓库失败：HTTP {code} {repo}")
            return 1
        out(f"已建仓库：{repo.get('html_url')}")

    # 3. 记为推送凭据（只在本机 Windows 凭证管理器，用户要求时也可跳过）
    run(["git", "remote", "set-url", "origin", f"https://github.com/{full}.git"])
    if not a.skip_push:
        auth = f"https://x-access-token:{token}@github.com/{full}.git"
        out("推送 main ...")
        rc, so, se = run(["git", "push", auth, "HEAD:refs/heads/main"])
        out((so + se).strip()[-400:] or f"rc={rc}")
        if rc != 0:
            out("main 推送失败，停止。")
            return 1
        out(f"推送 {tag} ...")
        rc, so, se = run(["git", "push", auth, f"refs/tags/{tag}:refs/tags/{tag}"])
        out((so + se).strip()[-400:] or f"rc={rc}")
        if rc != 0:
            out("tag 推送失败（可能已存在）。继续发 release。")

    # 4. release
    zip_path = os.path.join(DIST, "comfyui-dsh.zip")
    sums_path = os.path.join(DIST, f"SHA256SUMS-{tag}")
    notes_path = os.path.join(DIST, f"notes-{tag}.md")
    for p in (zip_path, sums_path):
        if not os.path.exists(p):
            out(f"缺文件：{p}（先跑 scripts/pack-release.ps1 -Version {version}）")
            return 2
    notes = ""
    if os.path.exists(notes_path):
        notes = open(notes_path, encoding="utf-8").read()

    code, rel = api("GET", f"/repos/{full}/releases/tags/{tag}", token)
    if code == 200:
        out(f"release {tag} 已存在：{rel.get('html_url')}")
        rel_id = rel["id"]
    else:
        code, rel = api("POST", f"/repos/{full}/releases", token, data={
            "tag_name": tag,
            "name": tag,
            "body": notes,
            "draft": False,
            "prerelease": False,
        })
        if code not in (200, 201):
            out(f"建 release 失败：HTTP {code} {rel}")
            return 1
        rel_id = rel["id"]
        out(f"已建 release {tag} (id {rel_id})")

    # 资产走 uploads.github.com，和 api.github.com 是不同域名；
    # urllib 在这条线上会碰到 TLS EOF，改用 curl（Windows 自带）。
    for path, ctype in ((zip_path, "application/octet-stream"),
                        (sums_path, "application/octet-stream")):
        name = os.path.basename(path)
        url = (f"https://uploads.github.com/repos/{full}/releases/{rel_id}"
               f"/assets?name={name}")
        rc, so, se = run(["curl", "-sS", "--retry", "4", "--retry-delay", "3",
                          "-m", "600", "-X", "POST",
                          "-H", f"Authorization: Bearer {token}",
                          "-H", f"Content-Type: {ctype}",
                          "-H", "User-Agent: comfyui-dsh-publish",
                          "--data-binary", f"@{path}", url])
        if rc != 0:
            out(f"  {name} 上传失败：{(se or so).strip()[:300]}")
            return 1
        try:
            res = json.loads(so)
        except Exception:
            res = {"state": so[:200]}
        out(f"  {name} ({os.path.getsize(path)} B) -> {res.get('state')}")

    code, final = api("GET", f"/repos/{full}/releases/{rel_id}", token)
    if code == 200:
        out("")
        out(f"完成：{final.get('html_url')}")
        for asset in final.get("assets", []):
            out(f"  {asset['name']}  {asset['size']} B  {asset['state']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
