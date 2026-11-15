// Wires the ComfyUI workflows into the DSH profile config.
//
//   node dsh/apply-workflows.mjs             # write (backs up first)
//   node dsh/apply-workflows.mjs --dry-run    # print the block, change nothing
//   node dsh/apply-workflows.mjs --revert     # restore the newest backup
//
// Target file:  ~/.dsh/profiles/desktop/cordis.patch.yml
//
// cordis.patch.yml is a top-level YAML **array** of loader patch entries. Each
// entry looks like:
//
//     - id: image-gen
//       name: dsh-image-gen
//       config:
//         provider: comfyui
//         ...
//
// This script edits that file as text so comments, ordering and DSH's `!!js`
// tags survive untouched. It only ever rewrites the `config` keys it owns
// (provider / comfyui*), leaving every other key in that entry alone.

import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WF_DIR = path.join(HERE, "workflows");

const dryRun = process.argv.includes("--dry-run");
const revert = process.argv.includes("--revert");

/** The id used by the image generation plugin in the patch layer. */
const ENTRY_IDS = ["image-gen", "dsh-image-gen"];

function dshHome() {
  const fromEnv = process.env.DSH_HOME;
  if (fromEnv && fs.existsSync(fromEnv)) return fromEnv;
  const guess = path.join(os.homedir(), ".dsh");
  if (fs.existsSync(guess)) return guess;
  console.error("cannot find DSH home (~/.dsh). Set DSH_HOME and try again.");
  process.exit(1);
}

const DSH_HOME = dshHome();
const PROFILE_DIR = path.join(DSH_HOME, "profiles", "desktop");
const CONFIG = path.join(PROFILE_DIR, "cordis.patch.yml");

if (!fs.existsSync(CONFIG)) {
  console.error("not found:", CONFIG);
  console.error("Open DeepSeek Harness Desktop once so it creates the desktop profile.");
  process.exit(1);
}

// ------------------------------------------------------------------ revert
if (revert) {
  const backups = fs
    .readdirSync(PROFILE_DIR)
    .filter((f) => f.startsWith("cordis.patch.yml.bak-workflows-"))
    .sort();
  if (!backups.length) {
    console.error("no backup found in", PROFILE_DIR);
    process.exit(1);
  }
  const newest = path.join(PROFILE_DIR, backups[backups.length - 1]);
  fs.copyFileSync(newest, CONFIG);
  console.log("restored from", newest);
  process.exit(0);
}

// ------------------------------------------------------------------ workflows
if (!fs.existsSync(WF_DIR)) {
  console.error("workflows folder missing:", WF_DIR);
  process.exit(1);
}

const workflows = fs
  .readdirSync(WF_DIR)
  .filter((f) => f.endsWith(".json"))
  .sort()
  .map((f) => {
    const name = f.replace(/\.json$/, "");
    let json;
    try {
      json = JSON.parse(fs.readFileSync(path.join(WF_DIR, f), "utf8"));
    } catch (e) {
      console.error(`${f}: invalid JSON - ${e.message}`);
      process.exit(1);
    }
    if (!json || typeof json !== "object" || Array.isArray(json)) {
      console.error(`${f}: an API workflow must be a JSON object keyed by node id`);
      process.exit(1);
    }
    const flat = JSON.stringify(json);
    const images = (flat.match(/\{\{image\}\}/g) || []).length;
    const hasSize = /\{\{(width|height)\}\}/.test(flat);
    console.log(
      `  ${name.padEnd(24)} image=${images} size=${hasSize ? "yes" : "no "} nodes=${Object.keys(json).length}`,
    );
    return { name, json: flat };
  });

if (!workflows.length) {
  console.error("no *.json workflows found in", WF_DIR);
  process.exit(1);
}

// Text-to-image first, image-to-image after: the first entry is what the panel
// shows as the default generation workflow.
workflows.sort((a, b) => {
  const ai = a.json.includes("{{image}}") ? 1 : 0;
  const bi = b.json.includes("{{image}}") ? 1 : 0;
  return ai - bi || a.name.localeCompare(b.name);
});

// Optional: per-workflow presetPrompt, so the panel's prompt box is pre-filled
// with something useful instead of an empty textarea.
const MANIFEST = path.join(HERE, "workflows.manifest.json");
let preset = {};
if (fs.existsSync(MANIFEST)) {
  try {
    for (const item of JSON.parse(fs.readFileSync(MANIFEST, "utf8"))) {
      if (item && item.name) preset[item.name] = item.presetPrompt || "";
    }
  } catch (e) {
    console.warn("workflows.manifest.json ignored -", e.message);
  }
}

// text-to-image workflow is the one without an {{image}} placeholder
const activeName =
  (workflows.find((w) => !w.json.includes("{{image}}")) || workflows[0]).name;

// ------------------------------------------------------------------ read config
const text = fs.readFileSync(CONFIG, "utf8");
const lines = text.split(/\r?\n/);

/** Top-level array item starts at indentation 0 with "- ". */
function isTopItem(line) {
  return /^-\s/.test(line) && !/^\s/.test(line);
}

function findEntry() {
  for (let i = 0; i < lines.length; i++) {
    const m = /^-\s+id:\s*(\S+)\s*$/.exec(lines[i]);
    if (!m) continue;
    if (!ENTRY_IDS.includes(m[1])) continue;
    let end = lines.length;
    for (let j = i + 1; j < lines.length; j++) {
      if (isTopItem(lines[j])) { end = j; break; }
    }
    return { start: i, end };
  }
  return null;
}

const ownedKeys = [
  "provider",
  "comfyuiBaseURL",
  "comfyuiTimeoutMs",
  "comfyuiActiveWorkflow",
  "comfyuiWorkflows",
];
const ownedRe = new RegExp(`^\\s*(?:${ownedKeys.join("|")})\\s*:`);

const entry = findEntry();

function buildKeys(indent) {
  return [
    `${indent}provider: comfyui`,
    `${indent}comfyuiBaseURL: http://127.0.0.1:8188`,
    `${indent}comfyuiTimeoutMs: 900000`,
    `${indent}comfyuiActiveWorkflow: ${activeName}`,
    `${indent}comfyuiWorkflows:`,
    ...workflows.flatMap((w) => {
      const lines = [`${indent}  - name: ${w.name}`];
      const p = preset[w.name];
      if (p) lines.push(`${indent}    presetPrompt: ${JSON.stringify(p)}`);
      lines.push(`${indent}    json: ${JSON.stringify(w.json)}`);
      return lines;
    }),
  ];
}

let outLines;

if (!entry) {
  // No image-gen entry yet: append a fresh one at the end of the array.
  const indent = "    ";
  const block = ["- id: image-gen", "  name: dsh-image-gen", "  config:", ...buildKeys(indent)];
  outLines = [...lines];
  while (outLines.length && outLines[outLines.length - 1].trim() === "") outLines.pop();
  outLines.push(...block);
  console.log("\nappending a new entry (none existed).");
} else {
  const head = lines.slice(entry.start, entry.end);

  // split head into: item line, then everything up to the config block
  const cfgLineIdx = head.findIndex((l) => /^\s{2}config\s*:\s*$/.test(l));
  const keyIndent = "    ";

  const kept = [];
  for (let i = 0; i < head.length; i++) {
    const line = head[i];
    if (i > 0 && ownedRe.test(line)) {
      // comfyuiWorkflows spans deeper-indented list items: skip them too
      if (/^\s*(?:comfyuiWorkflows)\s*:/.test(line)) {
        const ind = (line.match(/^\s*/) || [""])[0].length;
        let j = i + 1;
        while (j < head.length) {
          const l = head[j];
          if (!l.trim()) { j++; continue; }
          const li = (l.match(/^\s*/) || [""])[0].length;
          if (li > ind) { j++; continue; }
          break;
        }
        i = j - 1;
      }
      continue;
    }
    kept.push(line);
  }

  const insertAt = kept.findIndex((l) => /^\s{2}config\s*:\s*$/.test(l));
  if (insertAt >= 0) {
    outLines = [
      ...lines.slice(0, entry.start),
      ...kept.slice(0, insertAt + 1),
      ...buildKeys(keyIndent),
      ...kept.slice(insertAt + 1),
      ...lines.slice(entry.end),
    ];
  } else {
    outLines = [
      ...lines.slice(0, entry.start),
      ...kept,
      `  config:`,
      ...buildKeys(keyIndent),
      ...lines.slice(entry.end),
    ];
  }
}

const newText = outLines.join("\n");

if (newText === text) {
  console.log("\nnothing to change - config already up to date.");
  process.exit(0);
}

if (dryRun) {
  console.log("\n[dry-run] would write this dsh-image-gen entry:");
  const e = (() => {
    const tmp = newText.split(/\r?\n/);
    for (let i = 0; i < tmp.length; i++) {
      if (/^-\s+id:\s*(image-gen|dsh-image-gen)\s*$/.test(tmp[i])) {
        let end = tmp.length;
        for (let j = i + 1; j < tmp.length; j++) if (/^-\s/.test(tmp[j])) { end = j; break; }
        return tmp.slice(i, end);
      }
    }
    return [];
  })();
  console.log(e.map((l) => (l.length > 120 ? l.slice(0, 118) + " …" : l)).join("\n"));
  process.exit(0);
}

const backup = `${CONFIG}.bak-workflows-${Date.now()}`;
fs.copyFileSync(CONFIG, backup);
fs.writeFileSync(CONFIG, newText, "utf8");

console.log("\nupdated :", CONFIG);
console.log("backup  :", backup);
console.log("\nRestart DeepSeek Harness, then Settings > Plugins > Image generation:");
console.log("  provider             comfyui");
console.log("  base URL             http://127.0.0.1:8188");
console.log("  active workflow      " + activeName);
console.log("  workflows            " + workflows.map((w) => w.name).join(", "));
console.log("\nNote: the Studio (图像生成工作台) panel does not support ComfyUI - it");
console.log("falls back to a cloud provider. Only the agent tools route to local:");
console.log("generate_image / generate_images / edit_image.");
