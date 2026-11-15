// 命令行入口：让 DSH / 终端直接驱动滑杆服务，任意 denoise。
// 用法：
//   node cli.mjs --src "D:\path\a.jpg" --denoise 0.85 --prompt "..." [--steps 24] [--cfg 6.5]
//                [--size 1024x1024] [--seed -1] [--negative "..."] [--sampler dpmpp_2m] [--scheduler karras]
//   纯文生图去掉 --src，加 --create
// 输出最后一行是 RESULT <json>，供脚本解析。

import fsp from "node:fs/promises";
import path from "node:path";

const SRV = (process.env.SLIDER_API || "http://127.0.0.1:8189").replace(/\/+$/, "");
const COMFY_ROOT = process.env.COMFY_ROOT || "D:/ComfyUI/ComfyUI-0.45.0";

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) continue;
    const k = a.slice(2);
    if (k === "create") { out.create = true; continue; }
    const v = argv[i + 1];
    if (v === undefined || v.startsWith("--")) { out[k] = true; continue; }
    out[k] = v;
    i++;
  }
  return out;
}

const arg = parseArgs(process.argv);

if (!arg.prompt) {
  console.error("缺少 --prompt");
  process.exit(2);
}

let sourceImage = null;
if (!arg.create) {
  if (!arg.src) {
    console.error("缺少 --src（或加 --create 走纯文生图）");
    process.exit(2);
  }
  const abs = path.resolve(arg.src);
  const buf = await fsp.readFile(abs);
  const dataUrl = "data:image/jpeg;base64," + buf.toString("base64");
  const up = await fetch(SRV + "/api/upload", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ dataUrl, name: path.basename(abs) }),
  });
  const uj = await up.json();
  if (!uj.image) {
    console.error("上传失败:", JSON.stringify(uj).slice(0, 300));
    process.exit(1);
  }
  sourceImage = uj.image;
}

let width = 1024, height = 1024;
if (arg.size) {
  const m = String(arg.size).match(/^(\d+)\s*[xX×]\s*(\d+)$/);
  if (m) { width = Number(m[1]); height = Number(m[2]); }
}

const body = {
  mode: arg.create ? "create" : "edit",
  prompt: arg.prompt,
  denoise: arg.denoise !== undefined ? Number(arg.denoise) : 0.55,
  steps: arg.steps ? Number(arg.steps) : 24,
  cfg: arg.cfg ? Number(arg.cfg) : 6.5,
  sampler: arg.sampler || "dpmpp_2m",
  scheduler: arg.scheduler || "karras",
  seed: arg.seed !== undefined ? Number(arg.seed) : -1,
  width, height,
  sourceImage,
};
if (arg.negative) body.negative = arg.negative;

const r = await fetch(SRV + "/api/edit", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});
const j = await r.json();
if (!j.id) {
  console.error("提交失败:", JSON.stringify(j).slice(0, 400));
  process.exit(1);
}
console.log("已提交 " + j.id.slice(0, 8) + " denoise=" + j.params.denoise + " seed=" + j.params.seed);

const t0 = Date.now();
for (let i = 0; i < 600; i++) {
  await new Promise((s) => setTimeout(s, 1000));
  const jr = await fetch(SRV + "/api/job?id=" + encodeURIComponent(j.id));
  if (!jr.ok) continue;
  const job = await jr.json();
  if (job.state === "done") {
    const files = job.files || [];
    const secs = ((Date.now() - t0) / 1000).toFixed(1);
    const abs = files.map((f) => {
      const name = typeof f === "string" ? f : f.filename;
      const sub = typeof f === "string" ? "" : f.subfolder || "";
      return path.join(COMFY_ROOT, "output", sub, name);
    });
    for (const p of abs) {
      try { const st = await fsp.stat(p); console.log("文件 " + p + " " + st.size + " bytes"); } catch {}
    }
    console.log("完成 " + secs + "s");
    console.log("RESULT " + JSON.stringify({ ok: true, seconds: Number(secs), files: abs, params: job.params }));
    process.exit(0);
  }
  if (job.state === "error") {
    console.error("执行出错:", JSON.stringify(job.error || job).slice(0, 400));
    process.exit(1);
  }
}
console.error("超时");
process.exit(1);
