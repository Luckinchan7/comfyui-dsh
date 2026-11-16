/**
 * dsh-comfy-models —— 模型目录与工作流模板
 *
 * 只做两件事：
 *   1. 把 ComfyUI 里"手上的底模"枚举出来（checkpoints / diffusion_models）；
 *   2. 给每个底模生成一套可直接跑的标准工作流 JSON。
 *
 * 模板里的 {{prompt}} / {{width}} / {{height}} / {{seed}} / {{image}} 是
 * dsh-image-gen 约定的占位符，一个都不能少也不能改名字。
 */

/** 统一负向：反 CG + 去斑点。用户要"皮肤白净"，所以默认就把雀斑/油光压掉。
 *  与 cordis.patch.yml 里 8 条 SDXL 工作流写死的负向逐字一致（651 字符）。 */
export const NEG_CLEAN = [
  'freckles', 'moles', 'birthmark',
  'beauty mark', 'blemishes', 'skin spots',
  'dark spots', 'age spots', 'sun spots',
  'liver spots', 'acne', 'pimples',
  'acne scars', 'blackheads', 'rosacea',
  'redness on cheeks', 'blotchy skin', 'uneven skin tone',
  'patchy skin', 'textured skin', 'rough skin',
  'oily skin', 'greasy skin', 'shiny forehead',
  'large pores', 'visible pores', 'wrinkles',
  'skin imperfection', 'dirty skin', 'cartoon',
  'anime', 'illustration', 'painting',
  'drawing', 'sketch', '3d render',
  'cgi', 'octane render', 'unreal engine',
  'plastic skin', 'airbrushed', 'waxy',
  'doll', 'mannequin', 'oversmooth',
  'oversaturated', 'deformed', 'bad anatomy',
  'bad hands', 'extra fingers', 'blurry',
  'lowres', 'jpeg artifacts', 'watermark',
  'text', 'signature', 'logo',
].join(', ')

/** FLUX 用短负向：cfg=1 下负向本来就几乎不起作用，写长了只是浪费 token。 */
export const NEG_FLUX = [
  'cartoon', 'anime', 'illustration', 'painting', '3d render', 'cgi',
  'plastic skin', 'airbrushed', 'oversmooth', 'freckles', 'skin spots',
  'blurry', 'lowres', 'watermark', 'text', 'signature',
].join(', ')

const SDXL_DEFAULTS = {
  steps: 30, cfg: 5.0, sampler: 'dpmpp_2m', scheduler: 'karras',
  negative: NEG_CLEAN, prefix: 'dsh',
}
const FLUX_DEFAULTS = {
  steps: 24, cfg: 1.0, guidance: 3.5, sampler: 'euler', scheduler: 'simple',
  negative: NEG_FLUX, prefix: 'dsh-flux',
}

/** SDXL 系底模的文生图工作流。 */
export function sdxlText2Image(ckpt, opts = {}) {
  const o = { ...SDXL_DEFAULTS, ...opts }
  return {
    1: { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: ckpt } },
    2: { class_type: 'CLIPTextEncode', inputs: { text: '{{prompt}}', clip: ['1', 1] } },
    3: { class_type: 'CLIPTextEncode', inputs: { text: o.negative, clip: ['1', 1] } },
    4: { class_type: 'EmptyLatentImage', inputs: { width: '{{width}}', height: '{{height}}', batch_size: 1 } },
    5: {
      class_type: 'KSampler',
      inputs: {
        seed: '{{seed}}', steps: o.steps, cfg: o.cfg,
        sampler_name: o.sampler, scheduler: o.scheduler, denoise: 1,
        model: ['1', 0], positive: ['2', 0], negative: ['3', 0], latent_image: ['4', 0],
      },
    },
    6: { class_type: 'VAEDecode', inputs: { samples: ['5', 0], vae: ['1', 2] } },
    7: { class_type: 'SaveImage', inputs: { filename_prefix: o.prefix, images: ['6', 0] } },
  }
}

/** SDXL 系底模的改图工作流（LoadImage → VAEEncode → 低 denoise 重采样）。 */
export function sdxlImage2Image(ckpt, opts = {}) {
  const o = { ...SDXL_DEFAULTS, ...opts }
  return {
    1: { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: ckpt } },
    2: { class_type: 'CLIPTextEncode', inputs: { text: '{{prompt}}', clip: ['1', 1] } },
    3: { class_type: 'CLIPTextEncode', inputs: { text: o.negative, clip: ['1', 1] } },
    5: {
      class_type: 'KSampler',
      inputs: {
        seed: '{{seed}}', steps: 28, cfg: o.cfg,
        sampler_name: o.sampler, scheduler: o.scheduler, denoise: 0.55,
        model: ['1', 0], positive: ['2', 0], negative: ['3', 0], latent_image: ['11', 0],
      },
    },
    6: { class_type: 'VAEDecode', inputs: { samples: ['5', 0], vae: ['1', 2] } },
    7: { class_type: 'SaveImage', inputs: { filename_prefix: o.prefix + '-edit', images: ['6', 0] } },
    10: { class_type: 'LoadImage', inputs: { image: '{{image}}', upload: 'image' } },
    11: { class_type: 'VAEEncode', inputs: { pixels: ['10', 0], vae: ['1', 2] } },
  }
}

/** SDXL 系底模的 hires 工作流（1.5× lanczos + 低 denoise 二压）。 */
export function sdxlHiRes(ckpt, opts = {}) {
  const o = { ...SDXL_DEFAULTS, ...opts }
  return {
    1: { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: ckpt } },
    2: { class_type: 'CLIPTextEncode', inputs: { text: '{{prompt}}', clip: ['1', 1] } },
    3: { class_type: 'CLIPTextEncode', inputs: { text: o.negative, clip: ['1', 1] } },
    4: { class_type: 'EmptyLatentImage', inputs: { width: '{{width}}', height: '{{height}}', batch_size: 1 } },
    5: {
      class_type: 'KSampler',
      inputs: {
        seed: '{{seed}}', steps: o.steps, cfg: o.cfg,
        sampler_name: o.sampler, scheduler: o.scheduler, denoise: 1,
        model: ['1', 0], positive: ['2', 0], negative: ['3', 0], latent_image: ['4', 0],
      },
    },
    6: { class_type: 'VAEDecode', inputs: { samples: ['5', 0], vae: ['1', 2] } },
    7: { class_type: 'ImageScaleBy', inputs: { image: ['6', 0], upscale_method: 'lanczos', scale_by: 1.5 } },
    8: { class_type: 'VAEEncode', inputs: { pixels: ['7', 0], vae: ['1', 2] } },
    10: {
      class_type: 'KSampler',
      inputs: {
        seed: '{{seed}}', steps: 18, cfg: o.cfg,
        sampler_name: o.sampler, scheduler: o.scheduler, denoise: 0.35,
        model: ['1', 0], positive: ['2', 0], negative: ['3', 0], latent_image: ['8', 0],
      },
    },
    11: { class_type: 'VAEDecode', inputs: { samples: ['10', 0], vae: ['1', 2] } },
    9: { class_type: 'SaveImage', inputs: { filename_prefix: o.prefix + '-hires', images: ['11', 0] } },
  }
}

/** FLUX GGUF 的文生图工作流（UnetLoaderGGUF + DualCLIPLoaderGGUF）。 */
export function fluxText2Image(unet, clipL, t5, vae, opts = {}) {
  const o = { ...FLUX_DEFAULTS, ...opts }
  return {
    1: { class_type: 'UnetLoaderGGUF', inputs: { unet_name: unet } },
    2: {
      class_type: 'DualCLIPLoaderGGUF',
      inputs: { clip_name1: clipL, clip_name2: t5, type: 'flux' },
    },
    3: { class_type: 'VAELoader', inputs: { vae_name: vae } },
    4: { class_type: 'CLIPTextEncode', inputs: { text: '{{prompt}}', clip: ['2', 0] } },
    5: { class_type: 'CLIPTextEncode', inputs: { text: o.negative, clip: ['2', 0] } },
    6: { class_type: 'FluxGuidance', inputs: { conditioning: ['4', 0], guidance: o.guidance } },
    7: {
      class_type: 'EmptySD3LatentImage',
      inputs: { width: '{{width}}', height: '{{height}}', batch_size: 1 },
    },
    8: {
      class_type: 'KSampler',
      inputs: {
        seed: '{{seed}}', steps: o.steps, cfg: o.cfg,
        sampler_name: o.sampler, scheduler: o.scheduler, denoise: 1,
        model: ['1', 0], positive: ['6', 0], negative: ['5', 0], latent_image: ['7', 0],
      },
    },
    9: { class_type: 'VAEDecode', inputs: { samples: ['8', 0], vae: ['3', 0] } },
    10: { class_type: 'SaveImage', inputs: { images: ['9', 0], filename_prefix: o.prefix } },
  }
}

/** FLUX GGUF 的改图工作流。 */
export function fluxImage2Image(unet, clipL, t5, vae, opts = {}) {
  const o = { ...FLUX_DEFAULTS, ...opts }
  return {
    1: { class_type: 'UnetLoaderGGUF', inputs: { unet_name: unet } },
    2: {
      class_type: 'DualCLIPLoaderGGUF',
      inputs: { clip_name1: clipL, clip_name2: t5, type: 'flux' },
    },
    3: { class_type: 'VAELoader', inputs: { vae_name: vae } },
    4: { class_type: 'CLIPTextEncode', inputs: { text: '{{prompt}}', clip: ['2', 0] } },
    5: { class_type: 'CLIPTextEncode', inputs: { text: o.negative, clip: ['2', 0] } },
    6: { class_type: 'FluxGuidance', inputs: { conditioning: ['4', 0], guidance: o.guidance } },
    8: {
      class_type: 'KSampler',
      inputs: {
        seed: '{{seed}}', steps: 24, cfg: o.cfg,
        sampler_name: o.sampler, scheduler: o.scheduler, denoise: 0.62,
        model: ['1', 0], positive: ['6', 0], negative: ['5', 0], latent_image: ['12', 0],
      },
    },
    9: { class_type: 'VAEDecode', inputs: { samples: ['8', 0], vae: ['3', 0] } },
    10: { class_type: 'SaveImage', inputs: { images: ['9', 0], filename_prefix: o.prefix + '-edit' } },
    11: { class_type: 'LoadImage', inputs: { image: '{{image}}', upload: 'image' } },
    12: { class_type: 'VAEEncode', inputs: { pixels: ['11', 0], vae: ['3', 0] } },
  }
}

/**
 * 从一个底模文件描述生成整套工作流。
 * @param {{file:string, folder:'checkpoints'|'diffusion_models', display:string, kind:'sdxl'|'flux'}} model
 * @param {{clipL?:string, t5?:string, vae?:string, includes?:string[]}} aux  FLUX 需要的配套件
 * @returns {Array<{name:string, presetPrompt:string, json:string}>}
 */
export function workflowsFor(model, aux = {}) {
  const includes = aux.includes ?? ['base', 'edit']
  const out = []
  const preset = 'RAW photo, photorealistic, natural skin texture, high detail, sharp focus'
  if (model.kind === 'flux') {
    const args = [model.file, aux.clipL, aux.t5, aux.vae]
    if (!aux.clipL || !aux.t5 || !aux.vae) return []
    if (includes.includes('base')) {
      out.push({
        name: model.display,
        presetPrompt: preset,
        json: JSON.stringify(fluxText2Image(...args)),
      })
    }
    if (includes.includes('edit')) {
      out.push({
        name: model.display + '-Edit',
        presetPrompt: preset,
        json: JSON.stringify(fluxImage2Image(...args)),
      })
    }
    return out
  }
  if (includes.includes('base')) {
    out.push({
      name: model.display,
      presetPrompt: preset,
      json: JSON.stringify(sdxlText2Image(model.file)),
    })
  }
  if (includes.includes('edit')) {
    out.push({
      name: model.display + '-Edit',
      presetPrompt: preset,
      json: JSON.stringify(sdxlImage2Image(model.file)),
    })
  }
  if (includes.includes('hires')) {
    out.push({
      name: model.display + '-HiRes',
      presetPrompt: preset,
      json: JSON.stringify(sdxlHiRes(model.file)),
    })
  }
  return out
}

/** 从文件名猜模型系别：gguf 一律当 FLUX/UNet 路线，其余当 SDXL。 */
export function kindOf(folder, file) {
  if (/\.gguf$/i.test(file)) return 'flux'
  if (folder === 'diffusion_models') return 'flux'
  return 'sdxl'
}

/** 文件名 → 人类可读的显示名（去掉扩展名与 fp16 之类后缀）。 */
export function displayNameOf(file) {
  return file
    .replace(/\.(safetensors|ckpt|gguf)$/i, '')
    .replace(/[_-]?(fp16|fp32|bf16|noVAE|vae)$/i, '')
    .replace(/[_.]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}
