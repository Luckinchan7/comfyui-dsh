/**
 * dsh-comfy-models
 *
 * 把本机 ComfyUI 里"已经下载好的底模"变成 DSH 里可自由切换的生图模型。
 *
 * 做三件事：
 *   1. 扫描 ComfyUI 的 /object_info，列出 checkpoints 与 diffusion_models(GGUF) 里的底模；
 *   2. 为每个底模生成标准工作流（文生图 / 改图 / hires），写进 dsh-image-gen 的配置；
 *   3. 提供一个"切换当前生图模型"的工具，以及一个状态查询工具。
 *
 * 写配置直接改 profile 的 cordis.patch.yml —— 那份文件被 HMR 监听，改它等价于
 * 从设置面板改了一次，Loader 会自己热重载。设置面板、输入框药丸、本插件三个入口
 * 因此永远读的是同一份数据。
 */
import z from '@deepseek-ai/schemastery'
import { workflowsFor, kindOf, displayNameOf, NEG_CLEAN } from './catalog.js'
import { readImageGenConfig, writeImageGenConfig } from './yaml-store.js'

export const name = 'dsh-comfy-models'

/** tools 用于注册；profileContext 提供 profile 目录，缺了就只能读不能写。 */
export const inject = ['tools']

export const Config = z.object({
  comfyuiBaseURL: z.string().default('http://127.0.0.1:8188'),
  /** 启动后自动把 ComfyUI 里的新底模补进工作流列表。 */
  autoSyncOnStart: z.boolean().default(true),
  /** 生成的模型是否附带改图工作流。 */
  includeEdit: z.boolean().default(true),
  /** 生成的 SDXL 模型是否附带 hires 工作流。 */
  includeHires: z.boolean().default(false),
  /** 已存在同名工作流时是否覆盖（默认保留用户手改过的那份）。 */
  overwriteExisting: z.boolean().default(false),
})

// ── ComfyUI 探针 ────────────────────────────────────────────────────────────

async function getJson(base, path, timeoutMs = 15000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(new URL(path, base), { signal: controller.signal })
    if (!response.ok) throw new Error(`${path} → HTTP ${response.status}`)
    return await response.json()
  } finally {
    clearTimeout(timer)
  }
}

/** 读一个节点的某项 enum 候选列表；节点或字段不存在时返回空数组。 */
async function enumOf(base, node, field) {
  try {
    const info = await getJson(base, `/object_info/${node}`)
    const row = info?.[node]
    const spec = row?.input?.required?.[field] ?? row?.input?.optional?.[field]
    const list = Array.isArray(spec) ? spec[0] : undefined
    return Array.isArray(list) ? list.filter((value) => typeof value === 'string') : []
  } catch {
    return []
  }
}

/** 扫出 ComfyUI 现有底模，并归好类（sdxl / flux）。 */
async function scanModels(base) {
  const [ckpts, unets, clipsA, clipsB, vaeNames] = await Promise.all([
    enumOf(base, 'CheckpointLoaderSimple', 'ckpt_name'),
    enumOf(base, 'UnetLoaderGGUF', 'unet_name'),
    enumOf(base, 'DualCLIPLoaderGGUF', 'clip_name1'),
    enumOf(base, 'DualCLIPLoaderGGUF', 'clip_name2'),
    enumOf(base, 'VAELoader', 'vae_name'),
  ])
  const clips = [...new Set([...clipsA, ...clipsB])]

  const models = []
  for (const file of ckpts) {
    models.push({ file, folder: 'checkpoints', kind: 'sdxl', display: displayNameOf(file) })
  }
  for (const file of unets) {
    models.push({ file, folder: 'diffusion_models', kind: kindOf('diffusion_models', file), display: displayNameOf(file) })
  }

  const pick = (list, needle) => list.find((value) => value.toLowerCase().includes(needle))
  const clipL = pick(clips, 'clip_l') ?? pick(clips, 'clip-l')
  const t5 = pick(clips, 't5')
  const fluxVae = pick(vaeNames, 'flux') ?? vaeNames[0]

  return {
    models,
    aux: { clipL, t5, vae: fluxVae },
    counts: { ckpts: ckpts.length, unets: unets.length, clips: clips.length, vaes: vaeNames.length },
  }
}

// ── 配置读写 ───────────────────────────────────────────────────────────────

/**
 * profile patch 就是设置面板落盘的那份，而且被 HMR 监听 —— 写它等于
 * "从设置面板改了一次"。这里直接读写它，绕开 service API 的版本差异。
 */
function makeStore(ctx) {
  let profileDir
  ctx.inject(['profileContext'], (profileCtx) => {
    profileDir = profileCtx?.profileContext?.dir
    return () => { profileDir = undefined }
  })

  return {
    get dir() {
      return profileDir
    },
    async read() {
      if (profileDir === undefined) return undefined
      try {
        return await readImageGenConfig(profileDir)
      } catch {
        return undefined
      }
    },
    async write(patch) {
      if (profileDir === undefined) {
        throw new Error('profileContext is unavailable; this plugin must run inside a DSH profile')
      }
      return await writeImageGenConfig(profileDir, patch)
    },
    get ready() {
      return profileDir !== undefined
    },
  }
}

// ── 工具参数 ───────────────────────────────────────────────────────────────

const listParameters = {
  refresh: {
    type: 'boolean',
    description: '重新扫一遍 ComfyUI（默认 true；给 false 只读上次结果）。',
  },
}

const syncParameters = {
  only: {
    type: 'array',
    items: { type: 'string' },
    description: '只处理这些底模（按名字或文件名匹配，省略=全部）。',
  },
  activate: {
    type: 'string',
    description: '同步完成后把哪个工作流设为当前生图模型；省略则不改。',
  },
  overwrite: {
    type: 'boolean',
    description: '已存在同名工作流时是否覆盖（默认沿用插件配置）。',
  },
}

const switchParameters = {
  workflow: {
    type: 'string',
    required: true,
    description: '要切换到的目标：工作流名、底模名或文件名任一形式都接受。',
  },
}

const text = (value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }]

function tool(name, description, parameters, execute) {
  return {
    name,
    description,
    parameters,
    output: { schema: { type: 'string' }, render: (_args, value) => text(value) },
    async execute(args) {
      try {
        return await execute(args ?? {})
      } catch (error) {
        return JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) }, null, 2)
      }
    },
  }
}

// ── 插件本体 ───────────────────────────────────────────────────────────────

export function apply(ctx, config = {}) {
  const site = {
    comfyuiBaseURL: config.comfyuiBaseURL ?? 'http://127.0.0.1:8188',
    includeEdit: config.includeEdit !== false,
    includeHires: config.includeHires === true,
    overwriteExisting: config.overwriteExisting === true,
  }
  const store = makeStore(ctx)
  let cached

  const scan = async (refresh = true) => {
    if (!refresh && cached !== undefined) return cached
    cached = await scanModels(site.comfyuiBaseURL)
    return cached
  }

  /** 把扫描结果合成工作流条目；已存在的同名条目按 overwrite 决定留谁。 */
  const mergeWorkflows = (existing, models, aux, overwrite) => {
    const includes = ['base', ...(site.includeEdit ? ['edit'] : []), ...(site.includeHires ? ['hires'] : [])]
    const rows = [...(existing ?? [])]
    const byName = new Map(rows.map((row) => [row.name, row]))
    const added = []
    const skipped = []
    const reused = []

    /** 现有工作流里已经引用了这个模型文件吗？引用了就别再生成一套。 */
    const coveringWorkflow = (file) => rows.find((row) => {
      const body = typeof row.json === 'string' ? row.json : ''
      return body.includes(`"${file}"`)
    })

    for (const model of models) {
      const covering = coveringWorkflow(model.file)
      if (covering !== undefined && !overwrite) {
        reused.push({ model: model.display, workflow: covering.name })
        continue
      }
      const generated = workflowsFor(model, { ...aux, includes })
      if (generated.length === 0) {
        skipped.push({
          model: model.display,
          reason: model.kind === 'flux' ? '缺少 FLUX 配套件（clip_l / t5 / vae）' : '无模板',
        })
        continue
      }
      for (const row of generated) {
        if (byName.has(row.name) && !overwrite) {
          skipped.push({ model: row.name, reason: '同名工作流已存在' })
          continue
        }
        byName.set(row.name, row)
        rows.push(row)
        added.push(row.name)
      }
    }
    return { workflows: rows, added, skipped, reused }
  }

  /**
   * 按用户给的词找目标工作流。
   * 命中优先级：全等 → 忽略大小写全等 → 前缀 → 包含；
   * 同一优先级里取**名字最短**的那个 —— 否则 "juggernaut" 会命中
   * `Juggernaut-XI-Edit` 而不是用户想要的 `Juggernaut-XI`。
   */
  const resolveTarget = (workflows, wanted) => {
    const needle = String(wanted ?? '').trim()
    if (needle.length === 0) return undefined
    const lower = needle.toLowerCase()
    const shortest = (rows) => rows.slice().sort((a, b) => a.name.length - b.name.length)[0]
    return (
      workflows.find((row) => row.name === needle)
      ?? workflows.find((row) => row.name.toLowerCase() === lower)
      ?? shortest(workflows.filter((row) => row.name.toLowerCase().startsWith(lower)))
      ?? shortest(workflows.filter((row) => row.name.toLowerCase().includes(lower)))
    )
  }

  const api = {
    list: tool(
      'comfy_models_list',
      '列出本机 ComfyUI 里已有的生图底模，以及 DSH 里已注册的生图工作流和当前生效的那一个。想知道"我现在能选哪些模型"时用它。',
      listParameters,
      async (args) => {
        const { models, aux, counts } = await scan(args.refresh !== false)
        const cfg = await store.read()
        return JSON.stringify({
          ok: true,
          comfyui: site.comfyuiBaseURL,
          models: models.map((row) => ({ name: row.display, file: row.file, folder: row.folder, kind: row.kind })),
          comfyuiInventory: counts,
          fluxAux: aux,
          dsh: {
            provider: cfg?.provider,
            activeWorkflow: cfg?.activeWorkflow,
            workflows: (cfg?.workflows ?? []).map((row) => row.name),
            pillVisible: cfg?.pillVisible === true,
          },
          settingsWritable: store.ready,
        }, null, 2)
      },
    ),

    sync: tool(
      'comfy_models_sync',
      '扫描 ComfyUI 的全部底模，为还没有对应工作流的模型自动生成标准工作流（文生图 / 改图 / hires），并写进 DSH 的生图配置。下载了新底模之后调用它，用户就能在生图模型列表里直接选到。',
      syncParameters,
      async (args) => {
        const { models, aux } = await scan(true)
        const cfg = await store.read()
        const existing = cfg?.workflows ?? []
        const wanted = Array.isArray(args.only) && args.only.length > 0
          ? models.filter((row) => args.only.some((needle) => row.display.toLowerCase().includes(String(needle).toLowerCase()) || row.file.toLowerCase().includes(String(needle).toLowerCase())))
          : models
        const overwrite = typeof args.overwrite === 'boolean' ? args.overwrite : site.overwriteExisting
        const { workflows, added, skipped, reused } = mergeWorkflows(existing, wanted, aux, overwrite)

        let active = cfg?.activeWorkflow
        if (typeof args.activate === 'string' && args.activate.trim().length > 0) {
          const target = resolveTarget(workflows, args.activate)
          if (target === undefined) {
            throw new Error(`没有叫「${args.activate}」的工作流；现有：${workflows.map((row) => row.name).join(', ')}`)
          }
          active = target.name
        } else if (active === undefined || active.length === 0 || !workflows.some((row) => row.name === active)) {
          active = workflows[0]?.name ?? ''
        }

        const written = await store.write({ workflows, activeWorkflow: active, showProviderPill: true })
        return JSON.stringify({
          ok: true,
          added,
          reused,
          skipped,
          active,
          workflows: workflows.map((row) => row.name),
          writtenTo: written.path,
          backup: written.backup,
          note: '已写回 profile 配置，Loader 会自动热重载。用户现在可以在输入框下方的生图模型选择器里直接切换。',
        }, null, 2)
      },
    ),

    switchModel: tool(
      'comfy_models_switch',
      '切换 DSH 当前使用的生图模型（本质是切换 ComfyUI 工作流）。用户说"换成 XX 模型""用 XX 出图"时调用。只改当前选中的那个，不会动其它工作流。',
      switchParameters,
      async (args) => {
        const cfg = await store.read()
        const workflows = cfg?.workflows ?? []
        if (workflows.length === 0) throw new Error('DSH 里还没有任何 ComfyUI 工作流：先运行 comfy_models_sync')
        const target = resolveTarget(workflows, args.workflow)
        if (target === undefined) {
          throw new Error(`没有匹配「${args.workflow}」的工作流；现有：${workflows.map((row) => row.name).join(', ')}`)
        }
        const written = await store.write({ workflows, activeWorkflow: target.name, showProviderPill: true })
        return JSON.stringify({
          ok: true,
          active: target.name,
          presetPrompt: target.presetPrompt ?? '',
          writtenTo: written.path,
        }, null, 2)
      },
    ),
  }

  ctx.tools.register(api.list)
  ctx.tools.register(api.sync)
  ctx.tools.register(api.switchModel)

  // 启动后自动补一次：装完插件、下完新底模，用户下次开 DSH 就能看见。
  if (config.autoSyncOnStart !== false) {
    const timer = setTimeout(() => {
      scan(true)
        .then(async ({ models, aux }) => {
          const cfg = await store.read()
          if (cfg === undefined) return
          const { workflows, added } = mergeWorkflows(cfg.workflows, models, aux, site.overwriteExisting)
          if (added.length === 0) return
          let active = cfg.activeWorkflow
          if (active === undefined || !workflows.some((row) => row.name === active)) active = workflows[0]?.name ?? ''
          await store.write({ workflows, activeWorkflow: active, showProviderPill: true })
          ctx.logger?.info?.(`dsh-comfy-models: 自动补入 ${added.length} 条工作流（${added.join(', ')}）`)
        })
        .catch((error) => {
          ctx.logger?.debug?.(`dsh-comfy-models: 启动自动同步跳过（${error instanceof Error ? error.message : String(error)}）`)
        })
    }, 20000)
    timer.unref?.()
    ctx.effect(() => () => clearTimeout(timer), 'dsh-comfy-models: startup sync')
  }
}

export { NEG_CLEAN }
