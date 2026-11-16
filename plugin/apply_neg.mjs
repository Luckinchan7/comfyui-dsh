import { readImageGenConfig, writeImageGenConfig } from './lib/yaml-store.js';

const PROFILE = 'C:\\Users\\devin\\.dsh\\profiles\\desktop';

const NEG_CLEAN = [
  'freckles', 'moles', 'birthmark', 'beauty mark', 'blemishes', 'skin spots', 'dark spots',
  'age spots', 'sun spots', 'liver spots', 'acne', 'pimples', 'acne scars', 'blackheads',
  'rosacea', 'redness on cheeks', 'blotchy skin', 'uneven skin tone', 'patchy skin',
  'textured skin', 'rough skin', 'oily skin', 'greasy skin', 'shiny forehead', 'large pores',
  'visible pores', 'wrinkles', 'skin imperfection', 'dirty skin',
  'cartoon', 'anime', 'illustration', 'painting', 'drawing', 'sketch', '3d render', 'cgi',
  'octane render', 'unreal engine', 'plastic skin', 'airbrushed', 'waxy', 'doll', 'mannequin',
  'oversmooth', 'oversaturated',
  'deformed', 'bad anatomy', 'bad hands', 'extra fingers', 'blurry', 'lowres',
  'jpeg artifacts', 'watermark', 'text', 'signature', 'logo',
].join(', ');

const cfg = await readImageGenConfig(PROFILE);
console.log('path', cfg.path, '| workflows', Array.isArray(cfg.workflows) ? cfg.workflows.length : cfg.workflows);

const list = cfg.workflows;
const updated = list.map((wf) => {
  const isFlux = /^FLUX-/.test(wf.name);
  let g;
  try { g = JSON.parse(wf.json); } catch { console.log('skip(parse)', wf.name); return wf; }

  let hits = 0;
  for (const id of Object.keys(g)) {
    const n = g[id];
    if (n.class_type !== 'CLIPTextEncode') continue;
    const t = n.inputs && n.inputs.text;
    if (typeof t !== 'string') continue;
    if (t.includes('{{prompt}}')) continue;
    n.inputs.text = isFlux ? t : NEG_CLEAN;
    hits++;
  }
  console.log((isFlux ? 'flux-keep ' : 'patched   ') + wf.name + ' | neg nodes ' + hits);
  return { ...wf, json: JSON.stringify(g) };
});

const changed = updated.filter((w, i) => w.json !== list[i].json).map((w) => w.name);
console.log('changedWorkflows', changed);

if (changed.length) {
  await writeImageGenConfig(PROFILE, {
    workflows: updated,
    activeWorkflow: cfg.activeWorkflow,
    showProviderPill: cfg.pillVisible,
    provider: cfg.provider,
  });
  console.log('written');
} else {
  console.log('no-op');
}
