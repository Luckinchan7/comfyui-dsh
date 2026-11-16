/**
 * 直接读写 profile 的 cordis.patch.yml。
 *
 * 为什么不走 settings / configEditor 服务：这两个服务在不同 DSH 版本上的行为不一致
 * （0.1.2–0.1.6 有 installSection，0.2.x 换成 schema 派生表单，插件拿到的服务实例
 * 可能取不到自己的值）。而 profile patch 文件本身是**被 HMR 监听的** —— 改它就会
 * 触发 Loader 热重载，这正是设置面板背后做的事。
 *
 * 读用 js-yaml（拿到结构化的值），写用纯文本外科手术（只替换 image-gen 段的
 * comfyuiWorkflows 块 + 几个标量），其它字节一个不动 —— 注释、`!!js` 表达式、
 * 别的插件配置全部原样保留。
 */
import { readFile, writeFile, rename } from 'node:fs/promises'
import { join } from 'node:path'
import yaml from 'js-yaml'

const IMAGE_GEN_ID = '- id: image-gen'

/** 单引号包裹 YAML 标量：把内部的 ' 转义成 ''。 */
function quote(value) {
  return `'${String(value).replace(/'/g, "''")}'`
}

/** 把一条工作流渲染成 YAML 列表项文本。 */
function renderWorkflow(row, indent) {
  const pad = ' '.repeat(indent)
  return [
    `${pad}- name: ${quote(row.name)}`,
    `${pad}  presetPrompt: ${quote(row.presetPrompt ?? '')}`,
    `${pad}  json: ${quote(row.json)}`,
  ].join('\n')
}

/** 找到 image-gen 段的起止行号 [start, end)。 */
function findImageGenBlock(lines) {
  const start = lines.findIndex((line) => line.trim() === IMAGE_GEN_ID)
  if (start < 0) throw new Error('cordis.patch.yml has no `- id: image-gen`')
  let end = start + 1
  while (end < lines.length) {
    const line = lines[end]
    if (/^- /.test(line)) break
    end += 1
  }
  return [start, end]
}

/** 在 image-gen 段内定位 `comfyuiWorkflows:` 及其块结束位置。 */
function findWorkflowsKey(lines, from, to) {
  const keyIndex = lines.findIndex((line, index) => index >= from && index < to && /^ {4}comfyuiWorkflows:\s*$/.test(line))
  if (keyIndex < 0) throw new Error('image-gen block has no `comfyuiWorkflows:`')
  let end = keyIndex + 1
  while (end < to) {
    const line = lines[end]
    if (line.trim().length > 0 && /^ {0,4}\S/.test(line)) break
    end += 1
  }
  while (end > keyIndex + 1 && lines[end - 1].trim().length === 0) end -= 1
  return { keyIndex, end }
}

/** 设置 image-gen 段内的某个标量键（存在则替换，不存在则插在段首）。 */
function setScalar(lines, from, to, key, value) {
  const pattern = new RegExp(`^ {4}${key}:`)
  const index = lines.findIndex((line, position) => position >= from && position < to && pattern.test(line))
  if (index >= 0) {
    lines[index] = `    ${key}: ${value}`
    return
  }
  lines.splice(from + 1, 0, `    ${key}: ${value}`)
}

/**
 * 读 profile patch 里 image-gen 的完整配置。
 * @param {string} profileDir profile 根目录
 */
export async function readImageGenConfig(profileDir) {
  const path = join(profileDir, 'cordis.patch.yml')
  const text = await readFile(path, 'utf8')
  const rows = yaml.load(text)
  const entry = Array.isArray(rows) ? rows.find((row) => row !== null && typeof row === 'object' && row.id === 'image-gen') : undefined
  if (entry === undefined) throw new Error('cordis.patch.yml has no image-gen entry')
  const config = entry.config ?? {}
  const workflows = Array.isArray(config.comfyuiWorkflows) ? config.comfyuiWorkflows : []
  return {
    path,
    provider: config.provider,
    activeWorkflow: config.comfyuiActiveWorkflow,
    pillVisible: config.showProviderPill === true,
    workflows: workflows
      .filter((row) => typeof row?.name === 'string' && typeof row?.json === 'string')
      .map((row) => ({ name: row.name, json: row.json, presetPrompt: row.presetPrompt ?? '' })),
  }
}

/**
 * 把工作流列表写回 profile patch，并按需改 activeWorkflow / showProviderPill。
 * 保留其余所有字节；写之前先落一份 .bak。
 */
export async function writeImageGenConfig(profileDir, { workflows, activeWorkflow, showProviderPill = true, provider = 'comfyui' }) {
  const path = join(profileDir, 'cordis.patch.yml')
  const original = await readFile(path, 'utf8')
  const backup = `${path}.bak-comfymodels-${Date.now()}`
  await writeFile(backup, original, 'utf8')

  const lines = original.split('\n')
  let [start, end] = findImageGenBlock(lines)

  const { keyIndex, end: blockEnd } = findWorkflowsKey(lines, start, end)
  const rendered = ['    comfyuiWorkflows:', ...workflows.map((row) => renderWorkflow(row, 6))]
  lines.splice(keyIndex, blockEnd - keyIndex, ...rendered)

  ;[start, end] = findImageGenBlock(lines)
  setScalar(lines, start, end, 'provider', provider)
  if (activeWorkflow !== undefined) setScalar(lines, start, end, 'comfyuiActiveWorkflow', activeWorkflow)
  if (showProviderPill) setScalar(lines, start, end, 'showProviderPill', 'true')

  const next = lines.join('\n')
  const tmp = `${path}.tmp-comfymodels`
  await writeFile(tmp, next, 'utf8')
  await rename(tmp, path)
  return { path, backup, count: workflows.length }
}
