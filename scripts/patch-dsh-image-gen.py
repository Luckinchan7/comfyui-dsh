"""让 dsh-image-gen 的 ComfyUI 生图严格按「输入栏胶囊里选的工作流」执行。

三个行为改动（幂等，可重复运行）：

1. 胶囊优先 —— 工具调用里传的 workflow 参数不再能覆盖胶囊里的选择；
   真被忽略时，结果里带一句提示。
2. 模式不匹配直接报错 —— 胶囊选了 -Edit 却要文生图（或反过来）、
   参考图张数不符，抛带工作流名字的中文错误，而不是让 ComfyUI 那边莫名失败。
3. 卡片显示真实底模 —— 从工作流 JSON 里读 CheckpointLoaderSimple / UnetLoaderGGUF
   的 ckpt_name / unet_name 写进 output，对话卡片标题旁边就能看到。

用法：
    python scripts/patch-dsh-image-gen.py            # 打补丁
    python scripts/patch-dsh-image-gen.py --check    # 只看会改什么
    python scripts/patch-dsh-image-gen.py --revert   # 从 .bak-comfypin 还原

插件目录按 --plugin-dir > DSH_IMAGE_GEN_DIR > ~/.dsh/profiles/desktop/node_modules 顺序找。
改完要重载插件才生效（plugin_manager 关再开），光改文件不够。
"""

import argparse
import os
import shutil
import sys


def find_plugin_dir():
    """定位 dsh-image-gen 插件目录。

    优先级：--plugin-dir 参数 > DSH_IMAGE_GEN_DIR 环境变量 > 常见 profile 路径。
    """
    env = os.environ.get("DSH_IMAGE_GEN_DIR")
    if env:
        return env
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, ".dsh", "profiles", "desktop", "node_modules"),
        os.path.join(home, ".dsh", "profiles", "default", "node_modules"),
    ]
    for root in roots:
        cand = os.path.join(root, "dsh-image-gen")
        if os.path.isdir(cand):
            return cand
    return os.path.join(roots[0], "dsh-image-gen")


PLUGIN_DIR = find_plugin_dir()

T = "\t"

HELPERS = """// [comfyui-pin] 从工作流 JSON 里取出真实加载的底模文件名。
function comfyUIBaseModel(workflowJson) {
\tlet gguf;
\ttry {
\t\tconst workflow = parseWorkflow(workflowJson);
\t\tfor (const value of Object.values(workflow)) {
\t\t\tconst node = record$7(value);
\t\t\tconst inputs = node === void 0 ? void 0 : record$7(node.inputs);
\t\t\tif (inputs === void 0) continue;
\t\t\tif (node.class_type === "CheckpointLoaderSimple" && typeof inputs.ckpt_name === "string") return inputs.ckpt_name;
\t\t\tif ((node.class_type === "UnetLoaderGGUF" || node.class_type === "UNETLoader") && typeof inputs.unet_name === "string") gguf = inputs.unet_name;
\t\t}
\t} catch {
\t\treturn void 0;
\t}
\treturn gguf;
}
// [comfyui-pin] 解析这次调用该用哪条工作流，并在与请求不匹配时给出可操作的提示。
function comfyUIResolveWorkflow(active, args, sourceImages) {
\tconst requested = typeof args.workflow === "string" ? args.workflow.trim() : "";
\tconst workflow = selectComfyUIWorkflow(active, args.workflow);
\tconst slots = comfyUIWorkflowSlots(workflow.json);
\tconst editing = sourceImages > 0;
\tconst sibling = (name, drop, add) => {
\t\tconst guess = drop.length > 0 && name.endsWith(drop) ? name.slice(0, -drop.length) + add : name + add;
\t\tconst found = active.workflows.find((entry) => entry.name === guess);
\t\treturn found === void 0 ? "" : `最接近的是「${found.name}」。`;
\t};
\tif (!editing && slots.images > 0) throw new Error(`胶囊里选的工作流「${workflow.name}」含 ${String(slots.images)} 个 ${COMFYUI_IMAGE_PLACEHOLDER} 输入，是给 edit_image 用的，做不了文生图。${sibling(workflow.name, "-Edit", "")}请在输入栏胶囊里换成文生图工作流（RealVisXL-V5 / Juggernaut-XI / 带 -HiRes 的那几条）。`);
\tif (editing && slots.images === 0) throw new Error(`胶囊里选的工作流「${workflow.name}」是文生图工作流，没有 ${COMFYUI_IMAGE_PLACEHOLDER} 输入，做不了 edit_image。${sibling(workflow.name, "", "-Edit")}请在输入栏胶囊里换成带 -Edit / -FaceID 的工作流。`);
\tif (editing && slots.images !== sourceImages) throw new Error(`胶囊里选的工作流「${workflow.name}」有 ${String(slots.images)} 个 ${COMFYUI_IMAGE_PLACEHOLDER} 输入，这次传了 ${String(sourceImages)} 张参考图；数量必须一致。`);
\tconst ignored = requested.length > 0 && requested !== workflow.name;
\treturn {
\t\tworkflow,
\t\tbaseModel: comfyUIBaseModel(workflow.json),
\t\tnotice: ignored ? `已按输入栏胶囊里的「${workflow.name}」出图，忽略了调用方请求的「${requested}」。要换工作流请直接在胶囊里改。` : void 0
\t};
}
function selectComfyUIWorkflow(active, requested) {"""

PATCHES_INDEX = [
    # 1. 胶囊优先：pinActiveWorkflow 打开时忽略调用方传的 workflow
    (
        '\tif (typeof requested !== "string" || requested.trim().length === 0) return active.workflow;',
        '\tif (active.pinActiveWorkflow === true) return active.workflow;\n'
        '\tif (typeof requested !== "string" || requested.trim().length === 0) return active.workflow;',
        "if (active.pinActiveWorkflow === true) return active.workflow;",
    ),
    # 2. 把开关读进 comfyui provider 描述
    (
        "\t\t\t\tworkflows,\n\t\t\t\t...workflow === void 0 ? {} : { workflow },\n\t\t\t\ttimeoutMs: config.comfyuiTimeoutMs ?? 3e5",
        "\t\t\t\tworkflows,\n\t\t\t\t...workflow === void 0 ? {} : { workflow },\n"
        "\t\t\t\tpinActiveWorkflow: config.comfyuiPinActiveWorkflow !== false,\n"
        "\t\t\t\ttimeoutMs: config.comfyuiTimeoutMs ?? 3e5",
        "pinActiveWorkflow: config.comfyuiPinActiveWorkflow !== false,",
    ),
    # 3. 插入两个 helper（原文保持不动，只在前面加）
    (
        "function selectComfyUIWorkflow(active, requested) {",
        HELPERS,
        "function comfyUIResolveWorkflow(active, args, sourceImages) {",
    ),
    # 4. 文生图调用点
    (
        "\t\t\tconst workflow = selectComfyUIWorkflow(active, args.workflow);\n"
        "\t\t\tconst slots = comfyUIWorkflowSlots(workflow.json);\n"
        "\t\t\tassertImageCount(slots.images, 0);",
        "\t\t\tconst resolved = comfyUIResolveWorkflow(active, args, 0);\n"
        "\t\t\tconst workflow = resolved.workflow;\n"
        "\t\t\tconst slots = comfyUIWorkflowSlots(workflow.json);\n"
        "\t\t\tassertImageCount(slots.images, 0);",
        "const resolved = comfyUIResolveWorkflow(active, args, 0);",
    ),
    # 5. 改图调用点
    (
        "\t\t\t\tconst workflow = selectComfyUIWorkflow(active, args.workflow);\n"
        "\t\t\t\tconst slots = comfyUIWorkflowSlots(workflow.json);\n"
        "\t\t\t\tassertImageCount(slots.images, sourceImages.length);",
        "\t\t\t\tconst resolved = comfyUIResolveWorkflow(active, args, sourceImages.length);\n"
        "\t\t\t\tconst workflow = resolved.workflow;\n"
        "\t\t\t\tconst slots = comfyUIWorkflowSlots(workflow.json);\n"
        "\t\t\t\tassertImageCount(slots.images, sourceImages.length);",
        "const resolved = comfyUIResolveWorkflow(active, args, sourceImages.length);",
    ),
    # 6. 两处 saveGenerated 的 output 换成真实底模
    (
        'active.provider, workflow.name, "API workflow", current(), exec, knownWorkspaceRoots)',
        'active.provider, workflow.name, resolved.baseModel ?? "API workflow", current(), exec, knownWorkspaceRoots)',
        'resolved.baseModel ?? "API workflow"',
    ),
    # 7. 文生图 notice 合并
    (
        "\t\t\treturn frame.notice === void 0 ? value : {\n\t\t\t\t...value,\n\t\t\t\tnotice: frame.notice\n\t\t\t};",
        "\t\t\tconst notice = [resolved.notice, frame.notice].filter((entry) => typeof entry === \"string\" && entry.length > 0).join(\" \");\n"
        "\t\t\treturn notice.length === 0 ? value : {\n\t\t\t\t...value,\n\t\t\t\tnotice\n\t\t\t};",
        "\t\t\tconst notice = [resolved.notice, frame.notice]",
    ),
    # 8. 改图 notice 合并
    (
        "\t\t\t\treturn frame.notice === void 0 ? value : {\n\t\t\t\t\t...value,\n\t\t\t\t\tnotice: frame.notice\n\t\t\t\t};",
        "\t\t\t\tconst notice = [resolved.notice, frame.notice].filter((entry) => typeof entry === \"string\" && entry.length > 0).join(\" \");\n"
        "\t\t\t\treturn notice.length === 0 ? value : {\n\t\t\t\t\t...value,\n\t\t\t\t\tnotice\n\t\t\t\t};",
        "\t\t\t\tconst notice = [resolved.notice, frame.notice]",
    ),
]

SOURCE_TAG = """\t\t\tconst sourceTag = activeResult !== void 0 && activeResult.model.trim().length > 0 ? (0, react_jsx_runtime.jsx)("span", {
\t\t\t\tclassName: "dsh-ig-tag dsh-ig-tag-source",
\t\t\t\ttitle: activeResult.provider === "comfyui" ? `工作流 ${activeResult.model} · 底模 ${activeResult.output.trim().length > 0 ? activeResult.output : "未记录"}` : `${activeResult.provider} · ${activeResult.model}`,
\t\t\t\tchildren: activeResult.provider === "comfyui" ? activeResult.model : `${activeResult.provider} · ${activeResult.model}`
\t\t\t}) : null;
\t\t\tconst versionTotal = revisionChain.revisions.length + 1;"""

PATCHES_CLIENT = [
    # 1. 尺寸读附件真实像素
    (
        '\t\t\tif (item.provider === "import" && hasImageDimensions(item)) return `${item.attachment.width}×${item.attachment.height}`;',
        '\t\t\tif (hasImageDimensions(item)) return `${item.attachment.width}×${item.attachment.height}`;',
        'if (hasImageDimensions(item)) return `${item.attachment.width}×${item.attachment.height}`;',
    ),
    # 2. 在卡片里定义 sourceTag
    (
        "\t\t\tconst versionTotal = revisionChain.revisions.length + 1;",
        SOURCE_TAG,
        "dsh-ig-tag-source",
    ),
    # 3. 标题行插入 sourceTag
    (
        '\t\t\t\t\t\tchildren: [t("generatedTitle"), gif.animated ? (0, react_jsx_runtime.jsx)("span", {',
        '\t\t\t\t\t\tchildren: [t("generatedTitle"), sourceTag, gif.animated ? (0, react_jsx_runtime.jsx)("span", {',
        'children: [t("generatedTitle"), sourceTag,',
    ),
    # 4. 新 tag 的样式
    (
        ".dsh-ig-result-title{font-size:14px;font-weight:600}",
        ".dsh-ig-result-title{font-size:14px;font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap}"
        "\n.dsh-ig-tag-source{font-size:11px;font-weight:500;padding:2px 7px;border-radius:5px;background:var(--dsw-alias-bg-layer-3,#f1f5f9);color:var(--dsw-alias-label-secondary,#475569);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
        ".dsh-ig-tag-source{font-size:11px;font-weight:500;",
    ),
]


def apply_patches(path, patches, dry):
    text = open(path, encoding="utf-8").read()
    before = text
    applied, skipped = [], []
    for entry in patches:
        old, new = entry[0], entry[1]
        guard = entry[2] if len(entry) > 2 else None
        if guard is not None and guard in text:
            skipped.append("已应用，跳过: " + old.splitlines()[0].strip()[:70])
            continue
        n = text.count(old)
        if n == 0:
            skipped.append("锚点不存在: " + old.splitlines()[0].strip()[:78])
            continue
        multi_ok = "resolved.baseModel" in new
        if n > 2 or (n == 2 and not multi_ok):
            skipped.append(f"锚点出现 {n} 次，跳过: " + old.splitlines()[0].strip()[:60])
            continue
        text = text.replace(old, new)
        applied.append(old.splitlines()[0].strip()[:78])
    changed = text != before
    if changed and not dry:
        bak = path + ".bak-comfypin"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
        open(path, "w", encoding="utf-8", newline="").write(text)
    return applied, skipped, changed


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--plugin-dir", default=PLUGIN_DIR)
    args = ap.parse_args()

    plugin_dir = args.plugin_dir
    if not os.path.isdir(plugin_dir):
        print(f"找不到插件目录: {plugin_dir}\n用 --plugin-dir 指定，或设 DSH_IMAGE_GEN_DIR。")
        return 2

    idx = os.path.join(plugin_dir, "lib", "index.js")
    cli = os.path.join(plugin_dir, "lib", "client.js")

    if args.revert:
        for f in (idx, cli):
            bak = f + ".bak-comfypin"
            if os.path.exists(bak):
                shutil.copy2(bak, f)
                print(f"还原 {f}")
            else:
                print(f"无备份 {f}")
        return 0

    for f, patches in ((idx, PATCHES_INDEX), (cli, PATCHES_CLIENT)):
        applied, skipped, changed = apply_patches(f, patches, args.check)
        print(f"{os.path.basename(f)}: {len(applied)} 条已应用, changed={changed}")
        for a in applied:
            print(f"  + {a}")
        for s in skipped:
            print(f"  · {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
