# dsh-comfy-models

把本机 **ComfyUI 里已经下载好的生图底模**，变成 DSH 里可以自由切换的生图模型。

装完之后不用再手改 YAML：下一个底模 → 一句 `comfy_models_sync` → 输入框下方的生图模型选择器里就多一个可选项。切换只改"当前选中的那一个"，其它工作流一条都不动。

---

## 它解决什么

换底模原来要手工做三件事，缺一件就报错：

1. 往 `models/checkpoints` 放 `.safetensors`（FLUX 是 `models/diffusion_models` 放 `.gguf`）；
2. 手写一段 ComfyUI API 格式的 workflow JSON，`{{prompt}}` / `{{width}}` / `{{height}}` / `{{seed}}` 一个都不能错；
3. 改 `cordis.patch.yml` 里的 `comfyuiWorkflows` 与 `comfyuiActiveWorkflow`，还必须重启。

这个插件把 2、3 自动化。**写的是 profile 的 `cordis.patch.yml` 本身** —— 那份文件被 HMR 监听，改它等价于从设置面板改了一次，Loader 自己热重载。所以设置面板、输入框药丸、插件工具三个入口读的是同一份数据。

---

## 装法

```
C:\Users\devin\.dsh\profiles\desktop\.local-packages\dsh-comfy-models\
C:\Users\devin\.dsh\profiles\desktop\node_modules\dsh-comfy-models\      ← 运行时实际加载这份
```

`package.json` 加依赖：

```json
"dependencies": {
  "dsh-comfy-models": "file:./.local-packages/dsh-comfy-models"
}
```

`cordis.patch.yml` 加进 insert 列表（**必须是 `- insert:` 下面**，否则 plugin-manager 里认不出来）：

```yaml
- insert:
    - id: dsh-comfy-models
      name: dsh-comfy-models
      config:
        comfyuiBaseURL: http://127.0.0.1:8188
        autoSyncOnStart: true
        includeEdit: true
        includeHires: false
        overwriteExisting: false
```

重启 DSH，工具列表里出现三个工具。

---

## 三个工具

### `comfy_models_list`

读 ComfyUI 的 `/object_info`，列出：

- 现有的全部底模（`checkpoints` 的 `.safetensors` + `diffusion_models` 的 `.gguf`）；
- DSH 里已注册的工作流与当前生效的那个；
- FLUX 配套件自动识别结果（clip_l / t5 / vae）。

实测输出：

```
models: Illustrious-XL-v1-1 | Juggernaut-XI-v11 | RealVisXL-V5-0 | flux1-krea-dev-Q2-K
dsh.activeWorkflow: RealVisXL-V5   workflows: 10   pillVisible: true
```

### `comfy_models_sync`

把 ComfyUI 的底模同步成 DSH 工作流。关键行为：

- **已有工作流引用了这个模型文件就跳过**（扫 JSON 里的 `"<文件名>"`），不会生成重复的 `RealVisXL-V5-0`；
- 生成 `<模型名>` / `<模型名>-Edit` / `<模型名>-HiRes`（后两个受配置控制）；
- FLUX 走 `UnetLoaderGGUF` + `DualCLIPLoaderGGUF(type=flux)` + `FluxGuidance`，SDXL 走 `CheckpointLoaderSimple`；
- 同时把 `showProviderPill` 打开 —— 这是让用户在界面上自己点选模型的入口。

实跑（幂等验证，四台模型全被现有工作流覆盖）：

```
added:  []
reused: Illustrious-XL-v1-1 → Illustrious-XL
        Juggernaut-XI-v11   → Juggernaut-XI-Edit
        RealVisXL-V5-0      → RealVisXL-V5
        flux1-krea-dev-Q2-K → FLUX-Krea
```

### `comfy_models_switch`

切换当前生图模型。匹配优先级：全等 → 忽略大小写全等 → 前缀 → 包含；
**同一优先级取名字最短的** —— 否则 `juggernaut` 会命中 `Juggernaut-XI-Edit` 而不是 `Juggernaut-XI`。

实测：

```
juggernaut            → Juggernaut-XI
flux                  → FLUX-Krea
realvis               → RealVisXL-V5
Illustrious-XL        → Illustrious-XL
JUGGERNAUT-XI-HIRES   → Juggernaut-XI-HiRes
```

---

## 默认负向：去斑点

生成的工作流默认带一套"皮肤白净"负向（`lib/catalog.js` 的 `NEG_CLEAN`）：

```
freckles, moles, birthmark, blemishes, skin spots, dark spots, age spots,
sun spots, acne, pimples, acne scars, blackheads, rosacea, redness on cheeks,
blotchy skin, uneven skin tone, textured skin, rough skin, oily skin,
greasy skin, shiny forehead, large pores, visible pores, wrinkles,
skin imperfection, dirty skin, ...
```

正向模板统一为 `RAW photo, photorealistic, natural skin texture, high detail, sharp focus`。

FLUX 用 `NEG_FLUX` 短版（cfg=1 下负向本来就几乎不生效，写长了纯浪费 token）。

---

## 结构

```
lib/index.js      插件本体：探针、三个工具、启动自动同步
lib/catalog.js    工作流模板（SDXL 文生图/改图/hires、FLUX 文生图/改图）
lib/yaml-store.js 直接读写 cordis.patch.yml：读用 js-yaml，写用文本外科手术
```

`yaml-store.js` 的写法要点：只替换 image-gen 段的 `comfyuiWorkflows:` 块与 `comfyuiActiveWorkflow` / `showProviderPill` / `provider` 几个标量，其余字节原样保留（注释、`!!js` 表达式、其它插件配置）。

改写的等价性验证（沙盒副本上跑）：

```
rows: 19 → 19
non-imagegen deep equal: true
workflow entries 逐字节相同: 10/10
active changed: RealVisXL-V5 → Juggernaut-XI
```

写之前自动落一份 `cordis.patch.yml.bak-comfymodels-<ts>`，写用临时文件 + rename。

---

## 配置项

| 键 | 默认 | 说明 |
|---|---|---|
| `comfyuiBaseURL` | `http://127.0.0.1:8188` | ComfyUI 地址 |
| `autoSyncOnStart` | `true` | 启动 20 秒后自动补一次新底模 |
| `includeEdit` | `true` | 是否生成改图工作流 |
| `includeHires` | `false` | 是否生成 hires 工作流 |
| `overwriteExisting` | `false` | 同名工作流是否覆盖（默认保留手改过的那份） |

---

## 已知边界

- 只读 ComfyUI 的 `/object_info`，不扫磁盘 —— ComfyUI 没启动时扫不到模型，但已有工作流照样能切换。
- FLUX 配套件靠文件名猜（含 `clip_l` / `t5` / `flux` 的优先），命名太怪识别不到会跳过并给出原因，不会硬塞坏工作流。
- 写配置后 Loader 会热重载，工具注册表会短暂重挂（几百毫秒内调用可能报 `unknown tool`），重试即可。
- `settings` / `configEditor` 服务在不同 DSH 版本上对 image-gen 这种 schema 派生表单取值不一致（0.1.2–0.1.6 有 `installSection`，0.2.x 换掉了），所以这里绕开服务层直接操作文件。
