// Denoise slider for local ComfyUI (Illustrious-XL)
// Zero dependencies. Node >= 18.
import http from "node:http";
import fsp from "node:fs/promises";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMFY_ROOT = process.env.COMFY_ROOT || "D:/ComfyUI/ComfyUI-0.45.0";
const COMFY_INPUT = path.join(COMFY_ROOT, "input");
const UPLOAD_DIR = path.join(HERE, "uploads");
const COMFY_API = (process.env.COMFY_API || "http://127.0.0.1:8188").replace(/\/+$/, "");
const PORT = Number(process.env.PORT || 8189);
const CKPT = process.env.CKPT || "Illustrious-XL-v1.1.safetensors";
const HOST = "127.0.0.1";

const NEG_DEFAULT =
  "lowres, bad anatomy, bad hands, extra digits, fewer digits, missing fingers, " +
  "watermark, text, signature, username, jpeg artifacts, worst quality, low quality, " +
  "normal quality, monochrome, grayscale";

await fsp.mkdir(UPLOAD_DIR, { recursive: true });
await fsp.mkdir(COMFY_INPUT, { recursive: true });

/** prompt_id -> job record */
const JOBS = new Map();
/** newest first */
const HISTORY = [];

const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

function json(res, code, obj) {
  const body = Buffer.from(JSON.stringify(obj), "utf8");
  res.writeHead(code, {
    "content-type": "application/json; charset=utf-8",
    "content-length": body.length,
    "cache-control": "no-store",
  });
  res.end(body);
}

function sendFile(res, code, file, type) {
  fs.stat(file, (err, st) => {
    if (err) return json(res, 404, { error: "not found" });
    res.writeHead(code, {
      "content-type": type,
      "content-length": st.size,
      "cache-control": "no-store",
    });
    fs.createReadStream(file).pipe(res);
  });
}

function readBody(req, limit = 64 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on("data", (c) => {
      total += c.length;
      if (total > limit) {
        reject(new Error("body too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

async function comfy(pathname, init) {
  const r = await fetch(COMFY_API + pathname, init);
  const text = await r.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  return { status: r.status, data };
}

function buildWorkflow(p) {
  const wf = {
    "1": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: p.ckpt } },
    "2": { class_type: "CLIPTextEncode", inputs: { text: p.prompt, clip: ["1", 1] } },
    "3": { class_type: "CLIPTextEncode", inputs: { text: p.negative, clip: ["1", 1] } },
    "4": {
      class_type: "KSampler",
      inputs: {
        seed: p.seed,
        steps: p.steps,
        cfg: p.cfg,
        sampler_name: p.sampler,
        scheduler: p.scheduler,
        denoise: p.mode === "create" ? 1 : p.denoise,
        model: ["1", 0],
        positive: ["2", 0],
        negative: ["3", 0],
        latent_image: ["6", 0],
      },
    },
    "5": { class_type: "VAEDecode", inputs: { samples: ["4", 0], vae: ["1", 2] } },
    "9": { class_type: "SaveImage", inputs: { filename_prefix: "slider", images: ["5", 0] } },
  };
  if (p.mode === "edit") {
    wf["10"] = { class_type: "LoadImage", inputs: { image: p.sourceImage, upload: "image" } };
    wf["6"] = { class_type: "VAEEncode", inputs: { pixels: ["10", 0], vae: ["1", 2] } };
  } else {
    wf["6"] = {
      class_type: "EmptyLatentImage",
      inputs: { width: p.width, height: p.height, batch_size: 1 },
    };
  }
  return wf;
}

function clampNum(v, lo, hi, dflt) {
  const n = Number(v);
  if (!Number.isFinite(n)) return dflt;
  return Math.min(hi, Math.max(lo, n));
}

const ROUTES = {
  async "GET /api/health"() {
    const t0 = Date.now();
    try {
      const { status, data } = await comfy("/system_stats");
      if (status !== 200) return { code: 200, body: { comfyui: false, detail: data } };
      const dev = (data.devices || [])[0] || {};
      const q = await comfy("/queue");
      const ck = await comfy("/object_info/CheckpointLoaderSimple");
      return {
        code: 200,
        body: {
          comfyui: true,
          version: data.system?.comfyui_version,
          python: data.system?.python_version,
          vramTotal: dev.vram_total,
          vramFree: dev.vram_free,
          device: dev.name,
          queue: {
            running: q.data?.queue_running?.length || 0,
            pending: q.data?.queue_pending?.length || 0,
          },
          checkpoints: ck.data?.CheckpointLoaderSimple?.input?.required?.ckpt_name?.[0] || [],
          latencyMs: Date.now() - t0,
        },
      };
    } catch (e) {
      return {
        code: 200,
        body: { comfyui: false, error: String(e.message || e), latencyMs: Date.now() - t0 },
      };
    }
  },

  async "POST /api/upload"(req) {
    const raw = await readBody(req);
    let parsed;
    try {
      parsed = JSON.parse(raw.toString("utf8"));
    } catch {
      return { code: 400, body: { error: "invalid json" } };
    }
    const m = /^data:(image\/[a-z0-9.+-]+);base64,(.*)$/is.exec(parsed.dataUrl || "");
    if (!m) return { code: 400, body: { error: "expected dataUrl image" } };
    const buf = Buffer.from(m[2], "base64");
    if (buf.length < 64) return { code: 400, body: { error: "image too small" } };
    const ext = m[1].includes("jpeg") || m[1].includes("jpg") ? "jpg"
      : m[1].includes("webp") ? "webp" : "png";
    const hash = crypto.createHash("sha1").update(buf).digest("hex").slice(0, 12);
    const name = `slider_src_${hash}.${ext}`;
    await fsp.writeFile(path.join(COMFY_INPUT, name), buf);
    await fsp.writeFile(path.join(UPLOAD_DIR, name), buf);
    log("upload", name, buf.length, "bytes");
    return { code: 200, body: { image: name, bytes: buf.length } };
  },

  async "POST /api/edit"(req) {
    const raw = await readBody(req);
    let p;
    try {
      p = JSON.parse(raw.toString("utf8"));
    } catch {
      return { code: 400, body: { error: "invalid json" } };
    }
    const mode = p.mode === "create" ? "create" : "edit";
    if (mode === "edit" && !p.sourceImage) {
      return { code: 400, body: { error: "\u7f3a\u5c11\u6e90\u56fe" } };
    }
    const params = {
      mode,
      ckpt: p.ckpt || CKPT,
      prompt: String(p.prompt || "").trim() || "best quality, masterpiece, highly detailed",
      negative: String(p.negative ?? NEG_DEFAULT),
      denoise: clampNum(p.denoise, 0.01, 1, mode === "create" ? 1 : 0.55),
      steps: Math.round(clampNum(p.steps, 1, 80, 24)),
      cfg: clampNum(p.cfg, 0.5, 20, 6.5),
      sampler: p.sampler || "dpmpp_2m",
      scheduler: p.scheduler || "karras",
      seed:
        p.seed === -1 || p.seed === undefined || p.seed === null || p.seed === ""
          ? Math.floor(Math.random() * 1e9)
          : Math.round(clampNum(p.seed, 0, 4294967295, 0)),
      sourceImage: mode === "edit" ? p.sourceImage : null,
      width: Math.round(clampNum(p.width, 256, 2048, 1024)),
      height: Math.round(clampNum(p.height, 256, 2048, 1024)),
    };
    const wf = buildWorkflow(params);
    const { status, data } = await comfy("/prompt", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: wf, client_id: "dsh-slider" }),
    });
    if (status !== 200 || !data?.prompt_id) {
      return { code: 502, body: { error: "ComfyUI \u63d0\u4ea4\u5931\u8d25", detail: data } };
    }
    const job = {
      id: data.prompt_id,
      params,
      startedAt: Date.now(),
      state: "queued",
      files: [],
      error: null,
    };
    JOBS.set(job.id, job);
    log("queued", job.id.slice(0, 8), "denoise=" + params.denoise, "seed=" + params.seed);
    return { code: 200, body: { id: job.id, params } };
  },

  async "GET /api/job"(req, url) {
    const id = url.searchParams.get("id") || "";
    const job = JOBS.get(id);
    if (!job) return { code: 404, body: { error: "unknown job" } };
    if (job.state === "done" || job.state === "error") return { code: 200, body: job };
    const { status, data } = await comfy("/history/" + encodeURIComponent(id));
    if (status === 200 && data && data[id]) {
      const rec = data[id];
      const imgs = Object.values(rec.outputs || {})
        .flatMap((o) => o.images || [])
        .map((x) => ({ filename: x.filename, subfolder: x.subfolder || "", type: x.type || "output" }));
      if (rec.status?.status_str === "error") {
        job.state = "error";
        job.error = JSON.stringify(rec.status).slice(0, 600);
        job.elapsedMs = Date.now() - job.startedAt;
      } else if (imgs.length) {
        job.state = "done";
        job.files = imgs;
        job.elapsedMs = Date.now() - job.startedAt;
        HISTORY.unshift({
          id: job.id,
          file: imgs[0].filename,
          subfolder: imgs[0].subfolder,
          params: job.params,
          elapsedMs: job.elapsedMs,
          at: Date.now(),
        });
        if (HISTORY.length > 60) HISTORY.length = 60;
        log("done", job.id.slice(0, 8), (job.elapsedMs / 1000).toFixed(1) + "s", imgs[0].filename);
      }
    } else {
      const q = await comfy("/queue");
      const running = (q.data?.queue_running || []).some((x) => x[1] === id);
      job.state = running ? "running" : "queued";
    }
    return { code: 200, body: job };
  },

  async "GET /api/history"() {
    return { code: 200, body: { items: HISTORY } };
  },

  async "DELETE /api/history"() {
    HISTORY.length = 0;
    return { code: 200, body: { ok: true } };
  },

  async "GET /api/view"(req, url) {
    return { proxyView: url };
  },

  async "GET /api/samplers"() {
    const { data } = await comfy("/object_info/KSampler");
    const req = data?.KSampler?.input?.required || {};
    return {
      code: 200,
      body: {
        samplers: req.sampler_name?.[0] || [],
        schedulers: req.scheduler?.[0] || [],
      },
    };
  },
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://" + (req.headers.host || "127.0.0.1"));
  const key = `${req.method} ${url.pathname}`;

  try {
    if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) {
      return sendFile(res, 200, path.join(HERE, "index.html"), "text/html; charset=utf-8");
    }

    const handler = ROUTES[key];
    if (handler) {
      const out = await handler(req, url);
      if (out?.proxyView) {
        const u = out.proxyView;
        const q = new URLSearchParams({
          filename: u.searchParams.get("filename") || "",
          subfolder: u.searchParams.get("subfolder") || "",
          type: u.searchParams.get("type") || "output",
        });
        const r = await fetch(COMFY_API + "/view?" + q.toString());
        if (r.status !== 200) return json(res, r.status, { error: "view failed" });
        const buf = Buffer.from(await r.arrayBuffer());
        res.writeHead(200, {
          "content-type": r.headers.get("content-type") || "image/png",
          "content-length": buf.length,
          "cache-control": "max-age=31536000, immutable",
        });
        return res.end(buf);
      }
      return json(res, out.code, out.body);
    }

    if (url.pathname.startsWith("/uploads/")) {
      const name = path.basename(decodeURIComponent(url.pathname.slice(9)));
      const ext = path.extname(name).toLowerCase();
      const type = ext === ".jpg" || ext === ".jpeg" ? "image/jpeg"
        : ext === ".webp" ? "image/webp" : "image/png";
      return sendFile(res, 200, path.join(UPLOAD_DIR, name), type);
    }

    json(res, 404, { error: "not found" });
  } catch (e) {
    log("ERR", key, e.message);
    if (!res.headersSent) json(res, 500, { error: String(e.message || e) });
    else res.end();
  }
});

server.listen(PORT, HOST, () => {
  log(`denoise slider  ->  http://${HOST}:${PORT}`);
  log(`comfyui api     ->  ${COMFY_API}`);
  log(`comfyui input   ->  ${COMFY_INPUT}`);
});
