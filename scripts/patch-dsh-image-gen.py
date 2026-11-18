"""让 dsh-image-gen 的 ComfyUI 生图永不被参数或残留状态卡住。

三个行为改动（幂等，可重复运行）：

1. 自动选对工作流 —— 显式传的 workflow 优先；做不了这次调用时（文生图撞上
   带 {{image}} 的、改图撞上不带 {{image}} 的、参考图张数不符）不再报错白跑，
   而是顺次往后退：显式请求 → 胶囊里那条 → 全部工作流，取第一条能干的。
   真的一个能干的都没有才报错。被替换时在结果里带一句提示。
2. 卡片显示真实底模 —— 从工作流 JSON 里读 CheckpointLoaderSimple / UnetLoaderGGUF
   的 ckpt_name / unet_name 写进 output，对话卡片标题旁边就能看到。
3. 尺寸读附件真实像素 —— 卡片上显示生成图的实际分辨率。

用法：
    python scripts/patch-dsh-image-gen.py            # 打补丁
    python scripts/patch-dsh-image-gen.py --check    # 只看会改什么
    python scripts/patch-dsh-image-gen.py --revert   # 从 .bak-comfypin 还原

插件目录按 --plugin-dir > DSH_IMAGE_GEN_DIR > ~/.dsh/profiles/desktop/node_modules 顺序找。
改完要重载插件才生效（plugin_manager 关再开），光改文件不够。
插件升级会覆盖补丁，升级后重跑一次即可。
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
// [comfyui-pin] 挑一条这次调用真能干的工作流。
// 顺序：显式请求 → 它的同底模兄弟 → 它的同族兄弟 → 胶囊 → 胶囊的兄弟 → 其余。
// 一律不因为「选错了」而失败 —— 只有一条能干的都没有时才报错。
function comfyUIResolveWorkflow(active, args, sourceImages) {
	const requested = typeof args.workflow === "string" ? args.workflow.trim() : "";
	const editing = sourceImages > 0;
	const fits = (entry) => {
		const slots = comfyUIWorkflowSlots(entry.json);
		return editing ? slots.images === sourceImages : slots.images === 0;
	};
	const baseOf = (entry) => comfyUIBaseModel(entry.json) ?? "";
	const familyOf = (name) => name.replace(/-(Edit|HiRes|FaceID|Inpaint)$/g, "");
	const find = (name) => active.workflows.find((entry) => entry.name === name);
	const explicit = requested.length > 0 ? find(requested) : void 0;
	const pinned = active.workflow;
	const anchor = explicit ?? pinned;
	const anchorBase = anchor === void 0 ? "" : baseOf(anchor);
	const anchorFamily = anchor === void 0 ? "" : familyOf(anchor.name);
	const candidates = [];
	const push = (entry) => {
		if (entry !== void 0 && candidates.indexOf(entry) < 0) candidates.push(entry);
	};
	push(explicit);
	for (const entry of active.workflows) if (anchorBase.length > 0 && baseOf(entry) === anchorBase) push(entry);
	for (const entry of active.workflows) if (anchorFamily.length > 0 && familyOf(entry.name) === anchorFamily) push(entry);
	push(pinned);
	for (const entry of active.workflows) push(entry);
	const chosen = candidates.find(fits);
	if (chosen === void 0) {
		const want = editing ? `需要恰好 ${String(sourceImages)} 个 ${COMFYUI_IMAGE_PLACEHOLDER} 输入的工作流` : `需要不含 ${COMFYUI_IMAGE_PLACEHOLDER} 的文生图工作流`;
		const names = active.workflows.map((entry) => `「${entry.name}」`);
		throw new Error(`没有能干这次调用的工作流：${want}。当前 ${String(active.workflows.length)} 条都不满足：${names.join("、")}。请先导入一条合适的工作流。`);
	}
	const notices = [];
	const why = (entry) => editing ? `${String(comfyUIWorkflowSlots(entry.json).images)} 个 ${COMFYUI_IMAGE_PLACEHOLDER} 输入` : `不含 ${COMFYUI_IMAGE_PLACEHOLDER}`;
	if (explicit !== void 0 && explicit !== chosen) notices.push(`请求的「${explicit.name}」${why(explicit)}，做不了这次调用，已自动改用「${chosen.name}」。`);
	if (explicit === void 0 && pinned !== void 0 && pinned !== chosen) notices.push(`胶囊里的「${pinned.name}」${why(pinned)}，做不了这次调用，已自动改用「${chosen.name}」。`);
	return {
		workflow: chosen,
		baseModel: comfyUIBaseModel(chosen.json),
		notice: notices.length === 0 ? void 0 : notices.join(" ")
	};
}
function selectComfyUIWorkflow(active, requested) {"""

PATCHES_INDEX = [
    # 1. 插入两个 helper（原文保持不动，只在前面加）
    (
        "function selectComfyUIWorkflow(active, requested) {",
        HELPERS,
        "function comfyUIResolveWorkflow(active, args, sourceImages) {",
    ),
    # 2. 文生图调用点
    (
        '\t\t\tconst workflow = selectComfyUIWorkflow(active, args.workflow);\n'
        "\t\t\tconst slots = comfyUIWorkflowSlots(workflow.json);\n"
        "\t\t\tassertImageCount(slots.images, 0);",
        "\t\t\tconst resolved = comfyUIResolveWorkflow(active, args, 0);\n"
        "\t\t\tconst workflow = resolved.workflow;\n"
        "\t\t\tconst slots = comfyUIWorkflowSlots(workflow.json);\n"
        "\t\t\tassertImageCount(slots.images, 0);",
        "const resolved = comfyUIResolveWorkflow(active, args, 0);",
    ),
    # 3. 改图调用点
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
    # 4. 两处 saveGenerated 的 output 换成真实底模
    (
        'active.provider, workflow.name, "API workflow", current(), exec, knownWorkspaceRoots)',
        'active.provider, workflow.name, resolved.baseModel ?? "API workflow", current(), exec, knownWorkspaceRoots)',
        'resolved.baseModel ?? "API workflow"',
    ),
    # 5. 文生图 notice 合并
    (
        "\t\t\treturn frame.notice === void 0 ? value : {\n\t\t\t\t...value,\n\t\t\t\tnotice: frame.notice\n\t\t\t};",
        "\t\t\tconst notice = [resolved.notice, frame.notice].filter((entry) => typeof entry === \"string\" && entry.length > 0).join(\" \");\n"
        "\t\t\treturn notice.length === 0 ? value : {\n\t\t\t\t...value,\n\t\t\t\tnotice\n\t\t\t};",
        "\t\t\tconst notice = [resolved.notice, frame.notice]",
    ),
    # 6. 改图 notice 合并
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
