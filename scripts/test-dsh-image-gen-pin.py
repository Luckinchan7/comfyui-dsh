"""直接对打补丁后的 dsh-image-gen 做单元验证，不依赖 DSH 运行时。

    python scripts/test-dsh-image-gen-pin.py

插件目录按 DSH_IMAGE_GEN_DIR > ~/.dsh/profiles/desktop/node_modules 顺序找；
node 找不到时退回 PATH 里的 node。
"""
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


def find_plugin():
    env = os.environ.get("DSH_IMAGE_GEN_DIR")
    if env:
        return env
    home = os.path.expanduser("~")
    for name in ("desktop", "default"):
        cand = os.path.join(home, ".dsh", "profiles", name, "node_modules", "dsh-image-gen")
        if os.path.isdir(cand):
            return cand
    return os.path.join(home, ".dsh", "profiles", "desktop", "node_modules", "dsh-image-gen")


def find_node():
    home = os.path.expanduser("~")
    hits = sorted(glob.glob(os.path.join(home, ".dsh", "dsh-runtimes", "*", "dependencies", "node", "bin", "node.exe")))
    if hits:
        return hits[0]
    found = shutil.which("node")
    return found or "node"


PLUGIN = find_plugin()
LIB = os.path.join(PLUGIN, "lib", "index.js")
NODE = find_node()
WORK = tempfile.mkdtemp(prefix="dsh_pin_")

HARNESS = r"""
import fs from "node:fs";

const src = fs.readFileSync(process.argv[2], "utf8");

// 从打包文件里抠出需要的函数体，塞进一个独立作用域跑。
const grab = (name) => {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error("missing " + name);
  let depth = 0, i = src.indexOf("{", start);
  const begin = i;
  for (; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") { depth--; if (depth === 0) break; }
  }
  return src.slice(start, i + 1);
};

const prelude = `
const COMFYUI_IMAGE_PLACEHOLDER = "{{image}}";
const parseWorkflow = (json) => typeof json === "string" ? JSON.parse(json) : json;
const record$7 = (v) => (v !== null && typeof v === "object" && !Array.isArray(v)) ? v : void 0;
const countImagePlaceholders = (wf) => Object.values(wf).filter((n) => n && n.inputs && n.inputs.image === "{{image}}").length;
const containsSizePlaceholder = (wf) => JSON.stringify(wf).includes("{{width}}");
function comfyUIWorkflowSlots(workflowJson) {
  const workflow = parseWorkflow(workflowJson);
  return { images: countImagePlaceholders(workflow), size: containsSizePlaceholder(workflow) };
}
`;

const code = prelude
  + grab("comfyUIBaseModel") + "\n"
  + grab("comfyUIResolveWorkflow") + "\n"
  + grab("selectComfyUIWorkflow") + "\n"
  + "export { comfyUIBaseModel, comfyUIResolveWorkflow, selectComfyUIWorkflow };";

fs.writeFileSync(process.argv[3], code, "utf8");
"""


def main():
    tmp_harness = os.path.join(WORK, "_mk_harness.mjs")
    tmp_mod = os.path.join(WORK, "_pin_under_test.mjs")
    with open(tmp_harness, "w", encoding="utf-8") as f:
        f.write(HARNESS)
    r = subprocess.run([NODE, tmp_harness, LIB, tmp_mod], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("harness 失败:", r.stdout, r.stderr)
        return 1
    print(f"抽出被测模块: {tmp_mod} ({os.path.getsize(tmp_mod)} B)")

    mod_url = pathlib.Path(tmp_mod).as_uri()
    runner = r"""
import { comfyUIBaseModel, comfyUIResolveWorkflow } from "__MOD_URL__";

const text = { class_type: "CLIPTextEncode", inputs: { text: "{{prompt}}" } };
const mk = (name, ckpt, images) => {
  const wf = { "1": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: ckpt } }, "2": text, "3": { class_type: "KSampler", inputs: {} } };
  if (images > 0) wf["4"] = { class_type: "LoadImage", inputs: { image: "{{image}}" } };
  return { name, json: JSON.stringify(wf) };
};

const t2i = mk("RealVisXL-V5", "RealVisXL_V5.0_fp16.safetensors", 0);
const edit = mk("RealVisXL-V5-Edit", "RealVisXL_V5.0_fp16.safetensors", 1);
const faceid = mk("Juggernaut-XI-FaceID", "Juggernaut-XI-v11_fp16.safetensors", 1);
const gguf = { name: "FLUX-Krea", json: JSON.stringify({ "1": { class_type: "UnetLoaderGGUF", inputs: { unet_name: "flux1-krea-dev-Q2_K.gguf" } } }) };
const ggufEdit = { name: "FLUX-Krea-Edit", json: JSON.stringify({ "1": { class_type: "UnetLoaderGGUF", inputs: { unet_name: "flux1-krea-dev-Q2_K.gguf" } }, "4": { class_type: "LoadImage", inputs: { image: "{{image}}" } } }) };

const mkActive = (activeName) => ({
  workflow: [t2i, edit, faceid, gguf].find((w) => w.name === activeName),
  workflows: [gguf, ggufEdit, faceid, t2i, edit],
});

let pass = 0, fail = 0;
const ok = (label, cond, extra = "") => { cond ? pass++ : fail++; console.log(`${cond ? "PASS" : "FAIL"}  ${label}${cond ? "" : "  << " + extra}`); };
const run = (active, args, n) => { try { return { value: comfyUIResolveWorkflow(active, args, n) }; } catch (e) { return { error: e.message }; } };

// 1. 显式请求可行 → 直接用，不提示
{
  const r = run(mkActive("RealVisXL-V5"), { workflow: "RealVisXL-V5-Edit" }, 1);
  ok("显式请求可行直接用", r.value && r.value.workflow.name === "RealVisXL-V5-Edit", JSON.stringify(r));
  ok("无多余 notice", r.value && r.value.notice === void 0, String(r.value && r.value.notice));
}
// 2. 显式请求不可行（t2i 做改图）→ 自动退到 edit，不报错
{
  const r = run(mkActive("RealVisXL-V5"), { workflow: "RealVisXL-V5" }, 1);
  ok("t2i 请求做改图自动改道", r.value && r.value.workflow.name === "RealVisXL-V5-Edit", JSON.stringify(r));
  ok("改道给 notice", r.value && typeof r.value.notice === "string" && r.value.notice.includes("RealVisXL-V5"), String(r.value && r.value.notice));
}
// 3. 胶囊是 -Edit 但做文生图 → 自动退到 t2i，不报错
{
  const r = run(mkActive("RealVisXL-V5-Edit"), {}, 0);
  ok("胶囊 -Edit 做文生图自动改道", r.value && r.value.workflow.name === "RealVisXL-V5", JSON.stringify(r));
  ok("提示胶囊不适用", r.value && typeof r.value.notice === "string" && r.value.notice.includes("胶囊"), String(r.value && r.value.notice));
}
// 4. 胶囊 t2i 但传参考图 → 自动退到 edit
{
  const r = run(mkActive("RealVisXL-V5"), {}, 1);
  ok("胶囊 t2i 做改图自动改道", r.value && r.value.workflow.name === "RealVisXL-V5-Edit", JSON.stringify(r));
}
// 4b. 同底模优先：RealVisXL 的 t2i 请求做改图 → 必须出 RealVisXL-V5-Edit，不能跳去 FLUX/Juggernaut
{
  const r = run(mkActive("FLUX-Krea"), { workflow: "RealVisXL-V5" }, 1);
  ok("同底模兄弟优先", r.value && r.value.workflow.name === "RealVisXL-V5-Edit", JSON.stringify(r));
  ok("不跳到异底模", r.value && r.value.baseModel !== "flux1-krea-dev-Q2_K.gguf", String(r.value && r.value.baseModel));
}
// 5. 胶囊 = Undress 型（1 image）传 2 张图 → 退到能吃的（这里全不行 → 报错）
{
  const r = run({ ...mkActive("RealVisXL-V5-Edit"), workflows: [t2i, edit, faceid] }, {}, 2);
  ok("无可用工作流才报错", !!r.error && r.error.includes("没有能干这次调用的工作流"), r.error);
}
// 6. 显式请求不存在 → 退到胶囊可用的
{
  const r = run(mkActive("RealVisXL-V5"), { workflow: "不存在的工作流" }, 0);
  ok("请求不存在时退回胶囊", r.value && r.value.workflow.name === "RealVisXL-V5", JSON.stringify(r));
}
// 7. 底模提取
{
  ok("底模=RealVisXL", comfyUIBaseModel(t2i.json) === "RealVisXL_V5.0_fp16.safetensors", String(comfyUIBaseModel(t2i.json)));
  ok("底模=Juggernaut", comfyUIBaseModel(faceid.json) === "Juggernaut-XI-v11_fp16.safetensors", String(comfyUIBaseModel(faceid.json)));
  ok("底模=GGUF", comfyUIBaseModel(gguf.json) === "flux1-krea-dev-Q2_K.gguf", String(comfyUIBaseModel(gguf.json)));
  ok("非法 JSON 不抛", comfyUIBaseModel("{不是 json") === void 0, "should be undefined");
}

console.log(`${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
"""
    tmp_run = os.path.join(WORK, "_pin_test.mjs")
    with open(tmp_run, "w", encoding="utf-8") as f:
        f.write(runner.replace("__MOD_URL__", mod_url))
    r = subprocess.run([NODE, tmp_run], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout)
    if r.stderr.strip():
        print("STDERR:", r.stderr[:2000])
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
