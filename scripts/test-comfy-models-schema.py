#!/usr/bin/env python3
"""`fix-comfy-models-schema.py` 的单元测试。

不需要 DSH 运行时：把插件 `apply()` 跑在假 ctx 上收 `tools.register()` 的
definition，再直接断言 `parameters` 的形状。断言的是「模型请求里会变成什么」，
不是「源码里写了什么」—— 所以它测的是行为，不是文本。

    python scripts/test-comfy-models-schema.py                 # 测 profile 里装好的那份
    python scripts/test-comfy-models-schema.py --repo          # 测仓库里的 plugin/
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARK = "[test-comfy-models-schema]"

PROBE = r"""
import { pathToFileURL } from 'node:url'
const entry = process.argv[2]
const noop = () => {}
const reg = []
const ctx = {
  tools: { register: (d) => { reg.push(d); return noop }, restrict: noop, define: noop },
  logger: { info: noop, debug: noop, warn: noop, error: noop },
  effect: noop, on: noop, emit: noop, set: noop, get: noop,
  inject: (_d, fn) => { try { return fn({ profileContext: { dir: process.env.PROBE_PROFILE || '' } }) } catch { return noop } },
}
const mod = await import(pathToFileURL(entry).href + '?t=' + Date.now())
await mod.apply(ctx, { autoSyncOnStart: false })
console.log(JSON.stringify(reg.map((d) => ({ name: d.name, parameters: d.parameters }))))
process.exit(0)
"""


def find_node() -> str:
    home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    for pat in ("*/dependencies/node/bin/node.exe", "*/dependencies/node/bin/node"):
        for cand in sorted((home / "dsh-runtimes").glob(pat), reverse=True):
            if cand.is_file():
                return str(cand)
    return "node"


def run_probe(entry: Path, profile: Path) -> list[dict]:
    """`entry` 必须在能解析 `@deepseek-ai/schemastery` 的位置。
    profile 里装好的那份天然能；仓库那份（`plugin/lib/index.js`）不能 ——
    所以要把它临时复制进包目录，跑完删掉。"""
    staged = None
    try:
        with tempfile.TemporaryDirectory(prefix="dsh_schema_test_") as tmp:
            probe = Path(tmp) / "probe.mjs"
            probe.write_text(PROBE, encoding="utf-8")
            target = entry
            if "node_modules" not in entry.parts:
                pkg_lib = profile / "node_modules" / "dsh-comfy-models" / "lib"
                if pkg_lib.is_dir():
                    staged = pkg_lib / "_repo_probe.mjs"
                    staged.write_text(entry.read_text(encoding="utf-8"), encoding="utf-8")
                    target = staged
            env = {**os.environ, "PROBE_PROFILE": str(profile)}
            proc = subprocess.run(
                [find_node(), str(probe), str(target)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120,
            )
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("["):
            return json.loads(line)
    raise RuntimeError(f"探测没返回结果\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")


PASSED = 0
FAILED = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED += 1
        print(f"  FAIL  {label}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", action="store_true", help="测仓库里的 plugin/lib/index.js，而不是 profile 里装好的那份")
    args = ap.parse_args()

    home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    profile = home / "profiles" / "desktop"
    if args.repo:
        entry = Path(__file__).resolve().parent.parent / "plugin" / "lib" / "index.js"
    else:
        entry = profile / "node_modules" / "dsh-comfy-models" / "lib" / "index.js"

    if not entry.is_file():
        print(f"{MARK} 找不到 {entry}", file=sys.stderr)
        return 2

    print(f"{MARK} {entry}")
    tools = run_probe(entry, profile)

    # —— 基础 ——
    check("注册了三个工具", len(tools) == 3, f"实际 {len(tools)}")
    names = [t["name"] for t in tools]
    for expected in ("comfy_models_list", "comfy_models_sync", "comfy_models_switch"):
        check(f"含 {expected}", expected in names, ", ".join(names))

    by_name = {t["name"]: t for t in tools}

    # —— 根 schema（4027 的直接成因）——
    for t in tools:
        p = t["parameters"]
        check(f"{t['name']}: parameters 是对象", isinstance(p, dict) and not isinstance(p, list))
        check(f"{t['name']}: type == 'object'", p.get("type") == "object", f"type={p.get('type')!r}")
        check(f"{t['name']}: properties 是对象", isinstance(p.get("properties"), dict))

    # —— 属性没丢 ——
    check(
        "list 有 refresh",
        isinstance(by_name["comfy_models_list"]["parameters"]["properties"].get("refresh"), dict),
    )
    sync_props = by_name["comfy_models_sync"]["parameters"]["properties"]
    for key in ("only", "activate", "overwrite"):
        check(f"sync 有 {key}", isinstance(sync_props.get(key), dict), ", ".join(sync_props))
    sw = by_name["comfy_models_switch"]["parameters"]
    check("switch 有 workflow", isinstance(sw["properties"].get("workflow"), dict))

    # —— required 是数组，不是属性级布尔 ——
    check("switch: required 是数组", isinstance(sw.get("required"), list), f"required={sw.get('required')!r}")
    check("switch: required 含 workflow", "workflow" in (sw.get("required") or []))
    check(
        "switch: workflow 上不再有属性级 required",
        "required" not in sw["properties"]["workflow"],
        json.dumps(sw["properties"]["workflow"], ensure_ascii=False)[:80],
    )

    # —— 每个属性自己要有 type ——
    for t in tools:
        for key, prop in (t["parameters"].get("properties") or {}).items():
            check(f"{t['name']}.{key}: 有 type", isinstance(prop, dict) and "type" in prop)

    print(f"\n{MARK} {PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
