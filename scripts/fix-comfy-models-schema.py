#!/usr/bin/env python3
"""修 dsh-comfy-models 三个工具的畸形 JSON Schema。

背景
----
`ctx.tools.register()` 只校验 `output.schema`，**不校验 `parameters`**
（见 `@deepseek-ai/dsh-tools/lib/index.js:433` 的 `register()`：
只对 `output.schema` 调 `assertSupportedJsonSchema`）。所以插件把
`parameters` 写成属性表时，DSH 一声不响地放行，这份畸形 schema 会被
原样塞进模型请求的 `input_schema` 字段。

严格校验的上游会直接拒掉整条请求：

    400: Trae refused the request · Trae code 4027 ·
    upstream: tool call failed: tools.6.function.parameters must be a JSON Schema of type object

注意这不是「某个工具调用失败」，是**整个请求 400** —— 那一轮直接死掉，
用户看到的现象是「发什么都失败，会话像是坏了」。

`dsh-connect-workbuddy` / `dsh-image-gen` / `dsh-purge` 的写法都带
`type: "object"`，只有 `dsh-comfy-models` 这三处漏了。

用法
----
    python scripts/fix-comfy-models-schema.py --check    # 只体检
    python scripts/fix-comfy-models-schema.py            # 修（幂等，自动备份）

修完要重载插件才会生效（`plugin_manager` 里关掉 `include:dsh-comfy-models` 再打开），
或者重启 DSH。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARK = "[comfy-models-schema]"

# 三个属性表的原样（修复前）与修复后。原样用作锚点，保证幂等。
BEFORE_LIST = """const listParameters = {
  refresh: {
    type: 'boolean',
    description: '重新扫一遍 ComfyUI（默认 true；给 false 只读上次结果）。',
  },
}"""

AFTER_LIST = """// ctx.tools.register() 不做 schema 编译，parameters 会原样变成模型请求里的
// `input_schema`。所以这里必须是完整的 JSON Schema（根节点 type: "object"），
// 不能只给属性表 —— 严格校验的上游（如 Trae code 4027）会直接 400 整条请求。
const listParameters = {
  type: 'object',
  properties: {
    refresh: {
      type: 'boolean',
      description: '重新扫一遍 ComfyUI（默认 true；给 false 只读上次结果）。',
    },
  },
}"""

BEFORE_SYNC = """const syncParameters = {
  only: {
    type: 'array',
    items: { type: 'string' },
    description: '只处理这些底模（按名字或文件名匹配，省略=全部）。',
  },
  activate: {
    type: 'string',
    description: '同步完成后把哪个工作流设为当前生图模型；省略则不改。',
  },
  overwrite: {
    type: 'boolean',
    description: '已存在同名工作流时是否覆盖（默认沿用插件配置）。',
  },
}"""

AFTER_SYNC = """const syncParameters = {
  type: 'object',
  properties: {
    only: {
      type: 'array',
      items: { type: 'string' },
      description: '只处理这些底模（按名字或文件名匹配，省略=全部）。',
    },
    activate: {
      type: 'string',
      description: '同步完成后把哪个工作流设为当前生图模型；省略则不改。',
    },
    overwrite: {
      type: 'boolean',
      description: '已存在同名工作流时是否覆盖（默认沿用插件配置）。',
    },
  },
}"""

BEFORE_SWITCH = """const switchParameters = {
  workflow: {
    type: 'string',
    required: true,
    description: '要切换到的目标：工作流名、底模名或文件名任一形式都接受。',
  },
}"""

AFTER_SWITCH = """const switchParameters = {
  type: 'object',
  properties: {
    workflow: {
      type: 'string',
      description: '要切换到的目标：工作流名、底模名或文件名任一形式都接受。',
    },
  },
  required: ['workflow'],
}"""

PATCHES = [
    ("listParameters", BEFORE_LIST, AFTER_LIST),
    ("syncParameters", BEFORE_SYNC, AFTER_SYNC),
    ("switchParameters", BEFORE_SWITCH, AFTER_SWITCH),
]


def default_profile() -> Path:
    home = Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    return home / "profiles" / "desktop"


def candidate_files(profile: Path) -> list[Path]:
    """三处都要看：
    - `.local-packages/` —— `file:` 依赖的源目录
    - `node_modules/`   —— 装好的那份（与源是硬链接，但 edit 会把链接断成两个 inode）
    - `plugin/`         —— 本仓库自带的插件源
    """
    out = []
    for rel in (
        Path(".local-packages") / "dsh-comfy-models" / "lib" / "index.js",
        Path("node_modules") / "dsh-comfy-models" / "lib" / "index.js",
        Path("plugin") / "lib" / "index.js",
    ):
        p = profile / rel
        if p.is_file() and p not in out:
            out.append(p)
    return out


def looks_broken(text: str) -> bool:
    """凡是 `const XxxParameters = {` 后面紧跟属性名（而不是 type:）就算畸形。"""
    bad = []
    for name in ("listParameters", "syncParameters", "switchParameters"):
        m = re.search(rf"const {name} = \{{\s*\n\s*(\S[^\n]*)", text)
        if m and not m.group(1).lstrip().startswith("type:"):
            bad.append(name)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", type=Path, default=None, help="DSH profile 目录，默认 ~/.dsh/profiles/desktop")
    ap.add_argument("--check", action="store_true", help="只体检，不改文件")
    args = ap.parse_args()

    profile = args.profile or default_profile()
    files = candidate_files(profile)
    if not files:
        print(f"{MARK} 没找到 dsh-comfy-models：{profile}", file=sys.stderr)
        return 2

    changed_any = False
    for path in files:
        text = path.read_text(encoding="utf-8")
        bad = looks_broken(text)
        applied = sum(1 for _, _, after in PATCHES if after in text)
        print(f"{MARK} {path}")
        print(f"  {len(bad)} 处畸形（{', '.join(bad) if bad else '无'}），{applied}/3 条补丁已应用")
        if args.check or not bad:
            continue

        backup = path.with_name(f"{path.name}.bak-schema-{int(time.time())}")
        shutil.copy2(path, backup)
        for name, before, after in PATCHES:
            if after in text:
                print(f"  · 已应用，跳过: {name}")
                continue
            if before not in text:
                print(f"  · 锚点不匹配，跳过: {name}", file=sys.stderr)
                continue
            text = text.replace(before, after, 1)
            print(f"  · 已修复: {name}")
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"  备份: {backup.name}")
        changed_any = True

    if changed_any:
        print(f"\n{MARK} 改完了。重载插件才生效：")
        print("  plugin_manager({ action: 'set_plugin', target: 'include:dsh-comfy-models', enabled: false })")
        print("  plugin_manager({ action: 'set_plugin', target: 'include:dsh-comfy-models', enabled: true })")
        print("  或者直接重启 DSH。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
