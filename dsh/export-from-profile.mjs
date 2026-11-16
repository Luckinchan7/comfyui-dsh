import yaml from 'js-yaml';
import fs from 'node:fs';
import path from 'node:path';

const CONFIG = 'C:\\Users\\devin\\.dsh\\profiles\\desktop\\cordis.patch.yml';
const OUT = 'D:\\ComfyUI\\comfyui-dsh\\dsh\\workflows';

function findImageGen(node) {
  if (!node || typeof node !== 'object') return null;
  if (Array.isArray(node)) {
    for (const v of node) {
      const r = findImageGen(v);
      if (r) return r;
    }
    return null;
  }
  if (node.id === 'image-gen') return node;
  for (const k of Object.keys(node)) {
    const r = findImageGen(node[k]);
    if (r) return r;
  }
  return null;
}

const doc = yaml.load(fs.readFileSync(CONFIG, 'utf8'));
const entry = findImageGen(doc);
if (!entry) throw new Error('image-gen entry not found');

fs.mkdirSync(OUT, { recursive: true });

const manifest = [];
for (const wf of entry.config.comfyuiWorkflows) {
  const pretty = JSON.parse(wf.json);
  const file = path.join(OUT, wf.name + '.json');
  fs.writeFileSync(file, JSON.stringify(pretty, null, 2) + '\n', 'utf8');
  const flat = JSON.stringify(pretty);
  manifest.push({
    name: wf.name,
    presetPrompt: wf.presetPrompt || '',
    file: 'workflows/' + wf.name + '.json',
  });
  console.log(
    wf.name.padEnd(24),
    'nodes=' + String(Object.keys(pretty).length).padEnd(3),
    'size=' + (/\{\{(width|height)\}\}/.test(flat) ? 'yes' : 'no ').padEnd(3),
    'image=' + (flat.match(/\{\{image\}\}/g) || []).length,
  );
}

fs.writeFileSync(
  path.join(path.dirname(OUT), 'workflows.manifest.json'),
  JSON.stringify(manifest, null, 2) + '\n',
  'utf8',
);
console.log('\nmanifest entries:', manifest.length);
console.log('active in profile:', entry.config.comfyuiActiveWorkflow);
