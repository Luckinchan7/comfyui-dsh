// Restore the two Illustrious-XL workflows to their original anime-tuned
// negative prompt.
//
// Why: apply_neg.mjs replaced the negative prompt of all 8 SDXL workflows with
// NEG_CLEAN, whose tail is an anti-CG string (cartoon, anime, illustration,
// painting, drawing, sketch...). That is correct for RealVisXL / Juggernaut,
// where the whole point is to stop the model drifting toward illustration.
// Applied to an anime checkpoint it does the opposite: it fights the model's
// native style and pushes Illustrious toward photoreal output.
//
// Run:  node plugin/restore_anime_neg.mjs [--dry-run]

import path from "node:path";
import os from "node:os";
import { readImageGenConfig, writeImageGenConfig } from "./lib/yaml-store.js";

const DRY = process.argv.includes("--dry-run");
const PROFILE = process.env.DSH_PROFILE_DIR
  || path.join(os.homedir(), ".dsh", "profiles", "desktop");

// The original Illustrious-XL negative, as shipped before the bulk replace.
const ANIME_NEG = "lowres, bad anatomy, bad hands, extra digit, fewer digits, watermark, text, signature, username, jpeg artifacts, worst quality, low quality, normal quality, monochrome, grayscale";

const TARGETS = ["Illustrious-XL", "Illustrious-XL-Edit"];

function patchWorkflow(json) {
  const wf = JSON.parse(json);
  let hits = 0;
  for (const node of Object.values(wf)) {
    if (node?.class_type !== "CLIPTextEncode") continue;
    const text = node.inputs?.text;
    if (typeof text !== "string") continue;
    // Only touch the negative node: the positive one never starts with freckles.
    if (text.startsWith("freckles,")) {
      node.inputs.text = ANIME_NEG;
      hits++;
    }
  }
  return hits ? JSON.stringify(wf) : null;
}

const cfg = await readImageGenConfig(PROFILE);
console.log(`profile : ${cfg.path}`);
console.log(`mode    : ${DRY ? "dry run" : "write"}\n`);

const next = [];
let changed = 0;
for (const w of cfg.workflows) {
  if (!TARGETS.includes(w.name)) {
    next.push(w);
    continue;
  }
  const patched = patchWorkflow(w.json);
  if (patched) {
    changed++;
    console.log(`  patched  ${w.name}`);
    next.push({ ...w, json: patched });
  } else {
    console.log(`  keep     ${w.name} (already anime negative)`);
    next.push(w);
  }
}

if (!changed) {
  console.log("\nnothing to do.");
  process.exit(0);
}

if (DRY) {
  console.log(`\n[dry-run] would rewrite ${changed} workflow(s)`);
  process.exit(0);
}

await writeImageGenConfig(PROFILE, {
  workflows: next,
  activeWorkflow: cfg.activeWorkflow,
  showProviderPill: cfg.pillVisible,
  provider: cfg.provider,
});
console.log(`\nwritten: ${changed} workflow(s) restored to the anime negative`);
// Note: cordis.patch.yml is watched by HMR, so the running DSH picks this up
// in about 10-15 s without a restart.
