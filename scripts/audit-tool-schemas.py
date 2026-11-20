#!/usr/bin/env python3
"""扫 DSH profile 里每个插件的工具 schema，找出会让严格上游 400 的那类畸形。

为什么需要
----------
`ctx.tools.register()` 只校验 `output.schema`，**完全不看 `parameters`**
（`@deepseek-ai/dsh-tools/lib/index.js:433`）。参数 schema 会被原样塞进
模型请求的 `input_schema`，本地不报错，一到严格校验的上游就整个请求 400：

    400: Trae refused the request · Trae code 4027 ·
    upstream: tool call failed: tools.6.function.parameters must be a JSON Schema of type object

症状是「这个会话发什么都失败」，看起来像会话坏了，其实是插件注册时埋的雷。
`dsh-comfy-models` 就是这种 —— 三个工具的 `parameters` 直接写成属性表，
没有外层 `{ type: 'object', properties: {...} }`。

做法
----
真的把每个插件 `apply(ctx, config)` 跑一遍，用假 ctx 收集
`tools.register(definition)` 拿到的 definition，然后对 `parameters`
做两层判断：

1. **根必须是 object**（`type === 'object'` + `properties` 是对象）—— 这是
   4027 的直接成因。
2. **整份 schema 要通过 DSH 自己的 `assertSupportedJsonSchema`** —— DSH 支持的
   是 JSON Schema 子集（`type/oneOf/properties/required/additionalProperties/
   items/enum/const` + 注解）。`minLength` / `pattern` / `minItems` 这类
   关键字不在子集里，且 `type` 不允许写数组（`["string","array"]`）。
   这类畸形不会 400，但会在别的严格上游上炸 —— 顺手一起报出来。

用法
----
    python scripts/audit-tool-schemas.py
    python scripts/audit-tool-schemas.py --profile D:/other/profile

退出码：有根畸形 → 1；只有子集关键字问题 → 0（只是警告）。
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

MARK = "[audit-tool-schemas]"

# 用假 ctx 跑插件、收集 tools.register 的 definition，再交给 DSH 自己的校验器。
PROBE = r"""
import { pathToFileURL } from 'node:url'
import fs from 'node:fs'
import path from 'node:path'

const profile = process.argv[2]
const shared = process.argv[3]
const { m: assertSupported } = await import(pathToFileURL(shared).href)

const NM = path.join(profile, 'node_modules')
const noop = () => {}

function makeCtx(reg) {
  const rec = (def) => { reg.push(def); return noop }
  const base = {
    tools: { register: rec, restrict: noop, define: rec },
    logger: { info: noop, debug: noop, warn: noop, error: noop, trace: noop },
    effect: noop, on: noop, off: noop, emit: noop, set: noop, get: noop, inject: noop,
    plugin: noop, command: noop, middleware: noop, server: noop, api: noop, config: {},
    schema: { object: (o) => o, dict: (o) => o, union: () => ({}), array: (o) => o },
    systemPrompt: { section: () => noop, text: () => noop },
    host: { systemPrompt: { section: () => noop } },
  }
  return new Proxy(base, { get: (t, k) => (k in t ? t[k] : noop), has: () => true })
}

const out = []
if (!fs.existsSync(NM)) { console.log(JSON.stringify({ error: 'no node_modules: ' + NM })); process.exit(0) }

for (const pkg of fs.readdirSync(NM)) {
  if (pkg.startsWith('.')) continue
  const entry = path.join(NM, pkg, 'lib', 'index.js')
  if (!fs.existsSync(entry)) continue
  const reg = []
  try {
    const mod = await import(pathToFileURL(entry).href)
    const apply = mod.apply ?? mod.default?.apply ?? mod.default
    if (typeof apply !== 'function') continue
    const r = apply(makeCtx(reg), {})
    if (r && typeof r.then === 'function') await Promise.race([r, new Promise((res) => setTimeout(res, 1200))])
  } catch { continue }
  const named = reg.filter((d) => d && typeof d.name === 'string')
  if (named.length === 0) continue
  for (const d of named) {
    const p = d.parameters
    const row = { pkg, tool: d.name, rootOk: false, problems: [] }
    if (p === undefined || p === null || typeof p !== 'object' || Array.isArray(p)) {
      row.problems.push('parameters 不是对象')
    } else if (p.type !== 'object' || typeof p.properties !== 'object' || p.properties === null) {
      row.problems.push('根缺 type:"object" / properties（严格上游会 400 整条请求）')
    } else {
      row.rootOk = true
      try { assertSupported(p) } catch (e) { row.problems.push('不在 DSH 支持的子集: ' + e.message) }
    }
    out.push(row)
  }
}
console.log(JSON.stringify({ rows: out }))
process.exit(0)
"""


def find_node(profile: Path) -> Path:
    home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    for cand in sorted((home / "dsh-runtimes").glob("*/dependencies/node/bin/node.exe"), reverse=True):
        if cand.is_file():
            return cand
    for cand in sorted((home / "dsh-runtimes").glob("*/dependencies/node/bin/node"), reverse=True):
        if cand.is_file():
            return cand
    return Path("node")


def find_dsh_tools(profile: Path) -> Path | None:
    """找 DSH 自己的 dsh-tools/shared-*.js，那是 schema 子集校验器的权威来源。"""
    roots = [
        profile / "node_modules" / "@deepseek-ai" / "dsh-tools" / "lib",
        Path(os.environ.get("DSH_CHECKOUT", "")) / "node_modules" / "@deepseek-ai" / "dsh-tools" / "lib",
        Path(r"D:\DSH_DESKTOP\resources\app\dsh\node_modules\@deepseek-ai\dsh-tools\lib"),
        Path(r"D:\DSH_DESKTOP\resources\app.asar.unpacked\node_modules\@deepseek-ai\dsh-tools\lib"),
    ]
    for root in roots:
        if not root or not root.is_dir():
            continue
        hits = sorted(root.glob("shared-*.js"))
        for hit in hits:
            if "assertSupportedJsonSchema" in hit.read_text(encoding="utf-8", errors="replace")[:200000]:
                return hit
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", type=Path, default=None)
    args = ap.parse_args()

    profile = args.profile or (Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh")) / "profiles" / "desktop")
    if not profile.is_dir():
        print(f"{MARK} 没有这个 profile：{profile}", file=sys.stderr)
        return 2

    node = find_node(profile)
    shared = find_dsh_tools(profile)
    if shared is None:
        print(f"{MARK} 找不到 dsh-tools 的 schema 校验器，只做根 type 检查", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="dsh_schema_audit_") as tmp:
        probe = Path(tmp) / "probe.mjs"
        probe.write_text(PROBE, encoding="utf-8")
        cmd = [str(node), str(probe), str(profile), str(shared) if shared else str(profile / "missing.js")]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            print(f"{MARK} 探测超时（某个插件 apply 挂住了）", file=sys.stderr)
            return 2

    payload = None
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if payload is None:
        print(f"{MARK} 探测没返回结果\nstdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}", file=sys.stderr)
        return 2
    if "error" in payload:
        print(f"{MARK} {payload['error']}", file=sys.stderr)
        return 2

    rows = payload["rows"]
    root_bad = [r for r in rows if not r["rootOk"]]
    subset_bad = [r for r in rows if r["rootOk"] and r["problems"]]
    by_pkg: dict[str, list[dict]] = {}
    for r in rows:
        by_pkg.setdefault(r["pkg"], []).append(r)

    print(f"{MARK} {profile}")
    print(f"  扫了 {len(by_pkg)} 个注册了工具的插件，共 {len(rows)} 个工具\n")
    for pkg, items in sorted(by_pkg.items()):
        bad = [i for i in items if i["problems"]]
        flag = "✗" if bad else "✓"
        print(f"  {flag} {pkg}  ({len(items)} 个工具)")
        for i in bad:
            print(f"      · {i['tool']}: {'; '.join(i['problems'])}")

    print()
    if root_bad:
        print(f"{MARK} {len(root_bad)} 个工具的根 schema 畸形 —— 在严格校验的上游上会让整个请求 400（Trae 4027）")
        if any(r["pkg"] == "dsh-comfy-models" for r in root_bad):
            print("  修 dsh-comfy-models：python scripts/fix-comfy-models-schema.py")
        return 1
    if subset_bad:
        print(f"{MARK} 根 schema 都合规；{len(subset_bad)} 个工具用了 DSH 子集之外的 JSON Schema 关键字（本地能跑，换严格上游可能炸）")
        return 0
    print(f"{MARK} 全部合规")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
