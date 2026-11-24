"""把浅克隆的历史接成一条完整的线性历史（去掉 shallow 边界）。

本地 .git 是 shallow 仓：边界提交 d88ac7c 的父提交 cbb1e8d 不在本地，
push 时 thin pack 会引用它，服务器 unpack 时报
`fatal: did not receive expected object cbb1e8d...`。

旧仓库已被封（403），补不回那段历史，所以把边界提交改写成新的根提交，
其后的提交按原树、原信息、原作者/时间依次重建。文件内容一字不改。

用法：
    python scripts/unshallow-rewrite.py --dry      # 只看会做什么
    python scripts/unshallow-rewrite.py            # 真正重建

重建后原分支另存为 backup/pre-unshallow，原 tag 另存为 old-<tag>。
"""

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args, input_bytes=None):
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, input=input_bytes)
    if p.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} 失败：{p.stderr.decode('utf-8', 'replace')[:400]}")
    return p.stdout


def parse_commit(sha):
    raw = git("cat-file", "commit", sha).decode("utf-8", "replace")
    head, _, body = raw.partition("\n\n")
    tree = None
    parents = []
    author = committer = None
    for line in head.splitlines():
        if line.startswith("tree "):
            tree = line[5:].strip()
        elif line.startswith("parent "):
            parents.append(line[7:].strip())
        elif line.startswith("author "):
            author = line[7:]
        elif line.startswith("committer "):
            committer = line[10:]
    return {"tree": tree, "parents": parents, "author": author,
            "committer": committer, "message": body}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--branch", default="main")
    a = ap.parse_args()

    shallow = os.path.join(ROOT, ".git", "shallow")
    if not os.path.exists(shallow):
        print("不是 shallow 仓，什么都不用做。")
        return 0

    boundaries = {l.strip() for l in open(shallow) if l.strip()}
    print(f"shallow 边界 {len(boundaries)} 个：{', '.join(sorted(x[:8] for x in boundaries))}")

    order = git("rev-list", "--reverse", a.branch).decode().split()
    print(f"{a.branch} 上 {len(order)} 个提交")

    mapping = {}
    env = dict(os.environ)
    for sha in order:
        c = parse_commit(sha)
        real_parents = [p for p in c["parents"] if p in mapping]
        dropped = [p for p in c["parents"] if p not in mapping]
        # 用原 author/committer 的原样时间
        env["GIT_AUTHOR_NAME"] = c["author"].rsplit(" <", 1)[0]
        env["GIT_AUTHOR_EMAIL"] = c["author"].split("<", 1)[1].split(">", 1)[0]
        env["GIT_AUTHOR_DATE"] = c["author"].rsplit("> ", 1)[1]
        env["GIT_COMMITTER_NAME"] = c["committer"].rsplit(" <", 1)[0]
        env["GIT_COMMITTER_EMAIL"] = c["committer"].split("<", 1)[1].split(">", 1)[0]
        env["GIT_COMMITTER_DATE"] = c["committer"].rsplit("> ", 1)[1]
        args = ["commit-tree", c["tree"]]
        for p in real_parents:
            args += ["-p", mapping[p]]
        new = subprocess.run(["git", *args], cwd=ROOT, input=c["message"].encode(),
                             capture_output=True, env=env)
        if new.returncode != 0:
            raise SystemExit(f"commit-tree {sha[:8]} 失败：{new.stderr.decode('utf-8', 'replace')[:300]}")
        mapping[sha] = new.stdout.decode().strip()
        tag = "  [root]" if dropped else ""
        print(f"  {sha[:8]} -> {mapping[sha][:8]}{tag}"
              + (f"  丢掉父 {', '.join(p[:8] for p in dropped)}" if dropped else ""))

    tip_old = order[-1]
    tip_new = mapping[tip_old]
    print(f"\n新 HEAD：{tip_new[:8]}（原 {tip_old[:8]}）")

    if a.dry:
        print("--dry：未改动任何 ref。")
        return 0

    git("branch", "-f", "pre-unshallow-backup", a.branch)
    for t in git("tag", "--list").decode().split():
        sha = git("rev-parse", t).decode().strip()
        git("tag", "-f", "old-" + t, sha)

    git("update-ref", f"refs/heads/{a.branch}", tip_new)
    for t in git("tag", "--list").decode().split():
        if t.startswith("old-"):
            continue
        sha = git("rev-parse", t).decode().strip()
        # tag 可能指向 annotated tag 对象
        obj_type = git("cat-file", "-t", sha).decode().strip()
        if obj_type == "tag":
            target = git("rev-parse", t + "^{commit}").decode().strip()
            msg = git("cat-file", "tag", sha).decode("utf-8", "replace")
            body = msg.partition("\n\n")[2]
            if target in mapping:
                git("tag", "-f", "-a", t, "-m", body.strip() or t, mapping[target])
        elif sha in mapping:
            git("tag", "-f", t, mapping[sha])

    os.remove(shallow)
    git("checkout", "-f", a.branch)
    print("已重建，shallow 标记已删除。")
    print(git("log", "--oneline", "-5").decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
