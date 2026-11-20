# 变更日志

本文件记录这个项目的所有重要变更。
格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.4.4] — 2026-11-20

### 修复

- **胶囊选的模型又被调用参数盖掉了**。v1.4.0 为了「不让调用白跑」，把优先级写成
  「显式请求 → 同底模兄弟 → 同族兄弟 → 胶囊 → 其余」。副作用是：界面上胶囊明明选了
  `RealVisXL-V5`，只要工具调用里带了 `workflow: "..."`，出来的就是别的模型 —— 用户看到的
  「我选的这个模型，为什么出的图不是它」就是这个。
  新顺序把权威还给胶囊：**胶囊能胜任就以胶囊为准**（文生图要 0 个 `{{image}}`、改图要恰好 N 个），
  调用里传的 `workflow` 一律让位并附一句 notice 说明忽略了谁；**只有胶囊胜任不了这次调用时**，
  才轮到显式请求，再不行才按「同底模兄弟 → 同族兄弟 → 其余」改道。一条能干的都没有才报错。

### 变更

- `scripts/test-dsh-image-gen-pin.py` 断言从 15 条扩到 17 条，新增「胶囊能胜任时压过显式请求」、
  「胶囊 = 请求时不重复提示」、「胶囊能胜任直接用、不提示」三条路径；测试输出强制 UTF-8，
  在 GBK 控制台下不再是乱码。
- `scripts/patch-dsh-image-gen.py` 的 `HELPERS` 常量改用真正的制表符转义，避免二次修补时
  把 `\t` 字面量写进 `lib/index.js`（曾造成 `SyntaxError: Invalid or unexpected token`）。
- README 中英对应段落改用「胶囊说了算 / 胶囊不胜任才退让」两行表格，示例换成胶囊视角。

### 已知问题

- 容器换代（插件升级、重装 `node_modules`）会静默覆盖补丁，行为回退到上游默认 ——
  升级后重跑 `scripts/patch-dsh-image-gen.py`。

---

## [1.4.3] — 2026-11-20

### 修复

- **FLUX 出图满脸褐色斑点**。`FLUX-Krea` 是 dev 版、`cfg = 1.0`，cfg 为 1 时负向分支
  不参与计算 —— 负向里写多少 `freckles, moles, skin spots` 都等于没写。原 `presetPrompt`
  又是 `RAW photo, photorealistic, natural skin texture, sharp focus`，`natural skin texture`
  这个词在 Q2 量化上直接放大成斑块。两条 `FLUX-Krea*` 工作流的 `presetPrompt` 改为
  `RAW photo, photorealistic, flawless smooth skin, clean even complexion, sharp focus`
  （`-Edit` 少一个 `high detail`）。八组 guidance / 正向措辞对照见 `docs/MODELS.md`。
- 负向串补 `freckles, moles, birthmark, beauty mark, blemishes, skin spots, dark spots,
  age spots, sun spots, acne, pimples, blackheads, blotchy skin, uneven skin tone, rough skin`。
  对 `cfg = 1` 无实际效果，但换成别的 FLUX 变体（cfg > 1）时能直接用。

### 变更

- `docs/preview/checkpoints-4way.jpg` 四格全部换成新图（同 prompt 重出，`832×1216`）。
  FLUX 那格用了去斑后的版本，副标题删掉「皮肤有量化色斑」。
- `docs/MODELS.md` FLUX 一节改结论：原写「Q2_K 皮肤质量过不了关，FLUX 能跑但不必用」，
  现补上完整去斑实验表并改为「斑点不再是拦路虎，但只能靠正向措辞」。
- README 中英四底模表的 FLUX 定位描述同步。

### 已知问题

- `guidance` 提到 4.5 以上肤色会发灰；`porcelain` / `no visible skin texture` /
  `beauty retouched` 会把皮肤推向塑料感并改写构图与衣着 —— 这三类词别用。
- FLUX 冷启动（刚跑完 SDXL，显存要卸载）单张可达 610 s，`comfyuiTimeoutMs` 默认已调到
  1800000。插件报 `timed out` 不等于生成失败，任务仍在 ComfyUI 队列里，去 `/history` 捞。

---

## [1.4.2] — 2026-11-20

### 修复

- **`dsh-comfy-models` 三个工具的畸形 JSON Schema**，这是「整个请求被上游 400」的根因。
  三个 `parameters` 原来是裸属性表：

  ```js
  const listParameters = {
    refresh: { type: 'boolean', description: '…' },
  }
  ```

  而 `ctx.tools.register()`（`@deepseek-ai/dsh-tools/lib/index.js:433`）只对
  `output.schema` 调 `assertSupportedJsonSchema`，**完全不校验 `parameters`** ——
  畸形 schema 就这么被原样塞进模型请求的 `input_schema`
  （`@deepseek-ai/dsh-llm-deepseek/lib/index.js:1782` `input_schema: tool.parameters`；
  OpenAI 风格那边是 `dsh-our-free-model/vendor/channel-pack/pack.js:36477`
  `function: { name, description, parameters: tool.parameters }`）。
  严格校验的上游会直接拒掉**整条请求**：

  ```
  400: Trae refused the request · Trae code 4027 ·
  upstream: tool call failed: tools.6.function.parameters must be a JSON Schema of type object
  ```

  症状是「这个会话发什么都失败」，看起来像会话坏了。修法是给三个 `parameters` 包上
  `{ type: 'object', properties: {...} }`，`switchParameters` 的 `required: true`
  改成标准的 `required: ['workflow']` 数组。

### 新增

- **`scripts/fix-comfy-models-schema.py`**：上面那处修复的幂等补丁器，`--check` 只体检，
  自动备份 `.bak-schema-<ts>`。同时处理 `.local-packages/` 源目录与 `node_modules/`
  两份（它们是硬链接，但 `edit` 会把链接断开成两个独立 inode）。
- **`scripts/audit-tool-schemas.py`**：全量扫 profile 里每个插件的工具 schema。
  用假 ctx 跑 `apply()`、收 `tools.register()` 的 definition，再交给 DSH 自己的
  `assertSupportedJsonSchema` 判。两层报告 —— 根缺 `type: "object"`（会导致 400）
  与用了 DSH 子集之外的 JSON Schema 关键字（`minLength` / `pattern` / `minItems`、
  `type: ["string","array"]` 这类，本地能跑，换严格上游可能炸）。

### 已知问题

- `dsh-connect-workbuddy` 的两个工具在 DSH 子集之外用了 `minLength` / `pattern` /
  `minItems`，`workbuddy_draw_video` 的 `image` 还写成了 `type: ["string","array"]`
  （DSH 只收单一类型字符串）。它们的根 `type` 是 `object`，不会触发 4027，
  但换到做严格 schema 校验的上游时会有风险。

---

## [未发布]

### 计划中

- 多人场景的构图测试（当前所有实测都是单人）
- 手部专项：负向 + 局部重绘的组合配方
- Linux 下的等价脚本（当前只有 Windows）

---

## [1.4.1] — 2026-11-19

### 修复

- **改图工作流现在真的吃 `size` / `aspect_ratio`**。`Illustrious-XL-Edit`、`RealVisXL-V5-Edit`、`RealVisXL-V5-Rework`、`Juggernaut-XI-Edit`、`FLUX-Krea-Edit` 五条原来都是 `LoadImage → VAEEncode` 直连，没有 `EmptyLatentImage`，也就没有 `{{width}}` / `{{height}}`：`edit_image` 传尺寸只会得到一句 `… sets its own frame size … was not applied`，出图永远等于源图分辨率。
  修法是在 `LoadImage` 与 `VAEEncode` 之间插一个 `ImageScale`（`upscale_method: lanczos`、`width: "{{width}}"`、`height: "{{height}}"`、`crop: center`），并把 `VAEEncode.inputs.pixels` 指向它。现在 15 条工作流全部被标记为 `[size]`。
- **`Undress-Inpaint` 回到了 manifest**。此前有一次 `git checkout -- dsh/` 把它从 `workflows.manifest.json` 里抹掉，`fix-workflows.mjs` 只写回 14 条，profile 里那条是残存的旧版本。

### 变更

- `RealVisXL-V5-Edit` / `-Rework` 的 `ImageScale` 节点号是 `12`（这两条原有 9 个节点）；其余三条用 `20`，避免与将来插节点撞号。
- 五条改图工作流的 `crop` 都是 `center` —— 目标比例与源图不同时会裁掉边缘。想保住原构图就别传尺寸。

### 已知问题

- 裁切是硬切，没有做主体居中检测。人像居中问题不大，但主体偏在一侧的图会被切掉一部分。

---

## [1.4.0] — 2026-11-19

### 新增

- `RealVisXL-V5-Rework` 工作流：抄 `RealVisXL-V5-Edit`，`denoise 0.55 → 0.85`、`steps 28 → 32`。用途是换场景 / 换服装 / 换姿态等大改 —— `-Edit` 的 0.55 只能换光换表情，大改会被压回原构图。共 15 条工作流。
- `Undress-Inpaint` 工作流入库（此前只在本地 profile 里，仓库没有源文件）。

### 变更

- **`patch-dsh-image-gen.py` 语义重写**：从「胶囊绝对优先、不匹配就报错」改成「永不让调用白跑」。
  - 去掉 `pinActiveWorkflow` —— 它让胶囊的选择压过一切，agent 无法自行解除（胶囊只有 UI 能点），把 agent 逼去绕开插件直接打 `/prompt`，旁路掉 `saveGenerated`，`output` 与修订链全部丢失。
  - 新的 `comfyUIResolveWorkflow(active, args, sourceImages)` 候选顺序：**显式请求 → 它的同底模兄弟（`ckpt_name`/`unet_name` 相同）→ 同族兄弟（去掉 `-(Edit|HiRes|FaceID|Inpaint)` 后缀同名）→ 胶囊 → 胶囊的兄弟 → 其余全部**，取第一条 `fits()` 通过的。`fits()`：改图时 `slots.images === sourceImages`，文生图时 `slots.images === 0`。
  - 改道时给中文 notice：`请求的「X」N 个 {{image}} 输入，做不了这次调用，已自动改用「Y」。` / `胶囊里的「X」…`。一条能干的都没有才抛 `没有能干这次调用的工作流：…`。
  - 同底模优先是必须的：第一版按列表顺序退回，`edit_image` 传 `RealVisXL-V5` 时跳到了 `FLUX-Krea-Edit`（异底模），画质与身份全崩。
- **FaceID 三条工作流的 `weight_faceidv2` 从 1.0 提到 1.2，`weight` 从 0.85 降到 0.8**。1.0 时只要 prompt 与参考图冲突（换人种/年龄/风格）身份就被文本压过去 —— 实测参考图为欧裔、prompt 写 `portrait of a young East Asian woman`，1.0 出东亚脸，1.2 出参考图那个人。
- **FaceID 三条工作流的 `presetPrompt` 改成中性串**。原来是 `portrait of a person ... detailed face`，导致任何调用都被压成证件照：prompt 写「全身站在天台穿墨绿长裙」，出的是灰底白 T 胸像。现在 preset 只有 `RAW photo, photorealistic, natural skin texture, sharp focus`，构图交给调用方。
- **`Undress-Inpaint` 提示词去自我冲突**：正向删掉 `fair pale skin / very light skin tone / porcelain skin`（与「同肤色」矛盾）；负向删掉 `underwear, bra, panties`（与正向语义打架）和整簇 `tan skin, dark skin, brown skin, olive skin, sun tanned, tanned body`（会把深肤色一律推向浅肤色），只留 `sunburn, tan lines, two-tone skin, dark neck, uneven skin tone`。

### 修复

- `patch-dsh-image-gen.py` 的幂等性：第 1、3 条补丁的锚点打完后仍在文本里，二次运行会重复插入。现在每条带 `guard` 串，已应用就跳过，`--check` 输出 `0 条已应用, changed=False`。
- `test-dsh-image-gen-pin.py` 的模块路径：`"file:///" + path.replace("\\","/")` 在 Windows 上反斜杠被吃掉，报 `ERR_MODULE_NOT_FOUND: Cannot find module 'C:UsersdevinAppDataLocalTemp...'`。改用 `pathlib.Path(tmp_mod).as_uri()`。
- 两个脚本都 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，修 GBK 控制台乱码。

### 已知问题

- 插件升级会静默覆盖补丁（`node_modules` 被重装），升级后发现行为回退就重跑 `scripts/patch-dsh-image-gen.py`。
- `lib/yaml-store.js` 的 `writeImageGenConfig` 用 `/^ {0,4}\S/` 判断 `comfyuiWorkflows` 块结束，多行 JSON 会被误判成块边界导致 YAML 解析失败。工作流 JSON 必须压成单行再写入；仓库里的源文件仍保持 pretty 格式。

---

## [1.3.1] — 2026-11-18

### 新增

- **`scripts/patch-dsh-image-gen.py`**：让 `dsh-image-gen` 严格按输入栏胶囊里选的工作流出图。
  三处行为改动 —— 胶囊优先（调用参数不再覆盖）、模式不匹配抛中文错误并给出最接近的替代项、
  卡片显示真实底模文件名。幂等，带 `--check` / `--revert`，设 `comfyuiPinActiveWorkflow: false` 可关闭。
- **`scripts/which_workflow.py`**：读 PNG 里 `tEXt` 块嵌的工作流，反查任意一张图是哪条工作流、
  哪个底模、什么采样参数出的。HiRes 两段采样会分别列出。
- **`scripts/test-dsh-image-gen-pin.py`**：上面那个补丁的单元测试，14 条断言，不需要 DSH 运行时
  （从打包文件里按花括号配平抠出函数，拼桩模块跑）。
- **`Juggernaut-XI-FaceID-HiRes`** 工作流：FaceID 保脸 + 1.5× 二次采样，1248×1824 输出。

### 变更

- 工作流 12 → 13 条，`workflows.manifest.json` 同步。
- 三个脚本去掉写死的绝对路径：插件目录按 `--plugin-dir` → `DSH_IMAGE_GEN_DIR` →
  `~/.dsh/profiles/{desktop,default}/node_modules` 顺序找，node 找不到时退回 `PATH`，
  临时文件落到系统 temp 而不是 `D:\ComfyUI\dl\`。
- `which_workflow.py` 输出强制 UTF-8，避免 GBK 控制台下中文变乱码。

### 已知问题

- 补丁改的是 `node_modules` 里的打包产物，`dsh-image-gen` 升级后会被覆盖，需要重跑。
- 改完必须重载插件（`plugin_manager` 关再开），光改文件运行时仍是旧代码。

---

## [1.3.0] — 2026-11-17

### 新增

- **IPAdapter FaceID 保脸换装**。装 `ComfyUI_IPAdapter_plus`，配 `ip-adapter-faceid-plusv2_sdxl`
  + 对应 LoRA + `ip-adapter-plus-face_sdxl_vit-h`，insightface `buffalo_l` 算 512 维身份向量。
  同一个人换衣服/换场景/换姿势，脸不变。
- 两条 DSH 工作流：`RealVisXL-V5-FaceID`、`Juggernaut-XI-FaceID`，吃 `[1 image] + [size]`。
- **`docs/IPADAPTER.md`**：两种 preset（PLUS vs FaceID PLUS V2）的机制差别、参数甜点表、
  真人/动漫两组实测、五个坑（hf-mirror 的 Content-Length、`.bin` 是 ZIP 不是 safetensors、
  `models/insightface/models/` 双层目录、onnxruntime 无 CUDA provider、preset 名字带括号）。
- README 中英文各加一节「锁住同一个人 / Keeping the same person」+ 三张对照图
  （`ipadapter-faceid-real.jpg`、`ipadapter-banding.jpg`、`ipadapter-dressup.jpg`）。

### 变更

- 工作流 10 → 12 条。
- Python 依赖新增：`insightface 2.1`、`onnxruntime 1.32.0`、`opencv-python 5.0.0.93`、
  `scikit-image 0.26.0`、`onnx 1.23.2`。
- 磁盘占用增加约 6.4 GB（FaceID 1.49 GB + 两个 plus 0.85×2 + LoRA 0.37 + clip_vision 2.53
  + buffalo_l 0.34）。

### 已知问题

- `PLUS (high strength)` 在 Illustrious-XL 上会出横向彩虹条（`weight >= 0.35` 就出现），
  写实 SDXL 上同参数干净。保脸请用 FaceID。
- insightface 只取检测分值最高的那张脸，多人参考图会认错主角。
- det_score < 0.4（大侧脸）时身份向量质量下降，脸开始飘。
- 全身远景脸只占几十像素时 FaceID 基本失效。

---

## [1.2.2] — 2026-11-17

启动器默认不再弹浏览器。上一版把「服务已在运行 → 直接开浏览器」做成了无条件行为，
后台常驻时窗口会无缘无故弹出来。

### 变更

- **`启动ComfyUI.bat` 默认只起服务，不开浏览器。** 要看界面自己在浏览器里开
  `http://127.0.0.1:8188`。收藏一次即可，不必每次等它弹。
- **新增 `-open` / `--open` 开关**：显式要求「服务就绪后自动开浏览器」。行为与
  1.2.1 相同，只是从默认改成按需。
- **新增 `--no-browser`**：显式表达默认行为，方便脚本里写清楚意图。
- 服务已在运行时，默认只打印 `ComfyUI is already running.` + URL 然后退出；
  带 `-open` 才额外开浏览器。

### 关于参数的实现细节

cmd 的 `if /i "%%~a"=="-open=0"` 这种带等号的字面量比较会被错误切分 —— 实测
`-open=0` 会命中 `-open=1` 那一行，结果「显式关掉浏览器」反而打开了浏览器。
所以开关只保留不带等号的形式：`-open` / `--open` / `--no-browser`。

---

## [1.2.1] — 2026-11-17

启动器重写：双击不再撞端口，服务起来自动开浏览器。

### 修复

- **`启动ComfyUI.bat` 在服务已运行时直接报 `Port 8188 is already in use`**。
  这是窗口里唯一能看到的东西，用户会以为坏了。现在改成先探测 8188：在听就
  `start` 打开浏览器并退出。
- **启动后要手动复制地址**。新增 `open_when_ready.bat`，轮询端口直到服务应答再
  开浏览器，不靠猜「等 25 秒够不够」。
- **`start.bat` 里 `call "%~dp0启动ComfyUI.bat"` 报
  `is not recognized as an internal or external command`**。`.bat` 被 cmd 按 OEM
  代码页解码，非 936 环境下中文文件名变成乱码路径。改成两份独立实现：中文名那份
  给资源管理器双击，`start.bat` 是纯 ASCII 副本给终端和自动化用。
- **`start.bat` 的注释还写着 `--fast cublas_ops fp16_accumulation` 和
  「71-164s per 1024x1024」**，那是已经推翻的旧结论。改为 26–33 s @ 832×1216
  并明确写「别加 --fast / --enable-triton-backend」。

### 新增

- **`docs/preview/three-modes.jpg`**：同 seed 同 prompt 下普通 / HiRes / Edit
  三模式并排（832×1216 直出、1248×1824 二次采样、denoise 0.55 改图），标注分辨率
  与实测耗时，用于说明三者的节点图差异。
- **`open_when_ready.bat`**：等待 8188 应答后调用默认浏览器，最多等 4 分钟。

### 关于三模式的实测数据

同 seed 5150、同 prompt、Juggernaut-XI-v11：

| 模式 | 节点数 | 输出 | 耗时 |
|---|---|---|---|
| 普通 | 7 | 832×1216 | 24–30 s（热） |
| HiRes | 11 | 1248×1824 | 58 s（热） |
| Edit | 8 | = 输入图 | 38.5 s |

普通与 HiRes 出来的构图、姿态、光位几乎完全一致 —— 第二段 denoise 只有 0.35，
结构由第一段决定。所以 HiRes 不能用来试稿，只适合定稿后放大。

---

## [1.2.0] — 2026-11-16

README 从纯文字改成图文页。补上 banner、四张实测截图，中英文两版同时重排。

### 新增

- **`docs/banner.svg`**：手写 SVG，900×200，深色渐变 + 三色底线。不依赖外部图片，
  GitHub 直接渲染。
- **`docs/preview/checkpoints-4way.jpg`**：四个底模同一 prompt、同一场景的 2×2 对比。
  Illustrious 那张是新跑的 —— 用写实 prompt 强扭动漫底模，出来的仍是插画。
- **`docs/preview/text-rendering.jpg`**：`KRA COFFEE` / `KREA. COFFEE` / `KIRE A`
  三方拼图，直接展示图内文字有多不可靠。
- **`docs/preview/clean-skin.jpg`**：白净皮肤定版样图（1248×1824，44 s）。
- **`docs/preview/slider.jpg`**：Denoise 滑杆页实际截图。
- 中文版加「四个底模，一张图看清差别」「白净皮肤」「图内文字，别指望」三节。
- 英文版加对应的 "Four checkpoints", "Clean skin", "In-image text" 三节。
- 两版顶部统一加六个徽章：DSH 目标版本、当前版本、底模数、工作流数、许可、平台。

### 变更

- **`README.md` 重排**：底模对比表移到最前面，速度表紧随，安装与接线后置。
  原先开头是三段散文，读者要滚过一屏才知道能干什么。
- **`README.en.md` 重写**：与中文版逐节对应，不再是早期的简版。
- 预览图全部转 JPEG（q88，宽 ≤ 1400），四张合计 968 KB —— 原 PNG 版 11 MB。

### 备注

- 截图里没有版本号水印，避免下一次改版本时图又过期。
- 四底模对比图里的 Illustrious 那张用的是写实 prompt，是刻意的反例：
  告诉读者「拿动漫底模写 `RAW photo` 不会变成照片」。

---

## [1.1.1] — 2026-11-16

纯文档版本，没有代码变更。补上 README 该有的三样东西：英文说明、变更日志、
适配矩阵。

### 新增

- **`README.en.md`**：全文英文，结构与中文版对齐。项目对外是「在 Windows 上把
  生图搬到本机」的方案，英文说明是入口的一部分。
- **`CHANGELOG.md`**：本文件。Keep a Changelog 格式，含已知问题清单。
- **`docs/COMPATIBILITY.md`**：适配矩阵。
  - 显卡档位：4 / 6 / 8 / 12 / 16 / 24 GB 各自能跑什么
  - CUDA 版本：cu130 / cu126 / cu121 对应哪代卡，`install.ps1` 里改哪三行
  - 操作系统：Windows 10/11、Linux、macOS、WSL2 的状态
  - 版本对照：Python / torch / ComfyUI / DSH / `dsh-image-gen`
  - 端口冲突、路径要求
  - 「不适配就不适配」清单：物理限制，调参数解决不了

### 变更

- **`README.md` 顶部加导航**：中文 · English · 变更日志 · 适配说明。
- **`README.md` 新增「适配说明」节**：显存、CUDA、系统、版本四张摘要表，
  详细内容指向 `docs/COMPATIBILITY.md`。
- **`README.md` 底部加版本对照表**：v1.0.0 与 v1.1.0 的底模、启动参数、磁盘差异。
- **`README.md` 速度表修正**：Illustrious-XL 24→26–33 s、RealVisXL 20→26–31 s。
  原先的 20 s 是显存恰好空闲时的偶然值，不是可复现基线。
- **`docs/INSTALL-QUICK.md`**：步骤从 7 改成 9（补第 7 步写实底模、第 8 步 FLUX），
  补三个开关的用法与体积代价，`Disk used` 从 10.8 GB 改为 15.0 GB。

---

## [1.1.0] — 2026-11-16

从"只有动漫底模"变成"四个底模可选"，速度调优走完全程，并补上底模切换插件。

### 新增

- **三个写实底模**，`install.ps1` 三个开关按需装：
  - `-WithRealistic` — RealVisXL V5.0 fp16（6.5 GB），写实默认档，纪实/生活感最准
  - `-WithJuggernaut` — Juggernaut XI v11（6.6 GB），商业/电影感，手部结构更稳
  - `-WithFlux` — FLUX.1 Krea dev Q2_K + T5 + CLIP-L + VAE + ComfyUI-GGUF 节点（9.1 GB）
- **`dsh-comfy-models` 插件**（`plugin/`）：三个工具 `comfy_models_list` /
  `comfy_models_sync` / `comfy_models_switch`。改 profile 的 `cordis.patch.yml`，
  靠 HMR 热重载，切换底模不用重启 DSH。
- **`dsh/install-plugin.ps1`**：插件的一键安装，自动定位 profile，幂等。
- **`scripts/fetch_parts.sh`**：断点续传下载器，校验 HTTP 206 状态、每段字节数、
  文件魔数。因为 hf-mirror 被限流时会把报错页当正文写进文件，大小完全吻合。
- **`scripts/bench_final.py`**：SDXL / FLUX 两种图的最小测速脚本。
- **`scripts/pack-release.ps1`**：用 `git archive` 打包发行版，保证 zip 与仓库
  一致，不会混入 `node_modules`、模型或 output。
- **`docs/MODELS.md`**：四个底模横向实测。六场景对拍、FLUX 四档量化、图内文字
  对比、提示词四风格、参数甜点、备案清单。
- **`docs/PERFORMANCE.md`**：从 328 秒压到 20 秒的全过程，含三次走错的弯路。
- **`dsh/export-from-profile.mjs`**：从真实 profile 反向导出工作流到仓库。
- **`plugin/restore_anime_neg.mjs`**：把动漫底模的负向改回原版（反 CG 负向用在
  动漫模型上会适得其反）。
- 十种适配组合的说明，见 [README 的「适配说明」](README.md#适配说明)。

### 变更

- **工作流从 2 条扩到 10 条**：4 底模 × 文生图/改图，另加 RealVisXL 和 Juggernaut
  两条 HiRes（1.5× → 1248×1824）。
- **启动参数统一为 `--cache-lru 8 --reserve-vram 0.3`**，并移除了
  `--cache-none`、`--fast cublas_ops`、`--fast fp16_accumulation`、
  `--enable-triton-backend`。这四个在这张卡上都是负优化，理由见
  [docs/PERFORMANCE.md](docs/PERFORMANCE.md)。
- **`install.ps1` 从 7 步扩到 9 步**，第 7 步写实底模、第 8 步 FLUX，都可跳过；
  第 9 步冒烟测试。
- **负向按底模分三档**：动漫 178 字符、写实六条 651 字符（去斑点 + 反 CG）、
  FLUX 152 字符（cfg=1 下负向不生效，不写长）。
- **README 整篇重写**：加了四个底模选择表、启动参数表（含三条"别加"的理由）、
  插件装法、适配矩阵、新速度表。
- `docs/why-local.md` 的显存表按实测重写：SDXL 26–33 秒、Q2_K 82 秒有伪影、
  Q3_K_S 装得进显存但每步 131 秒、Q4_K_S 溢出。

### 修复

- **速度慢的真正原因不是参数，是显存被占**。浏览器 + 微信 + NVIDIA Overlay 吃掉
  2 GB，剩 3.4 GB 时日志出现 `dynamic VRAM loading`，每步 2.99 s/it。同一套参数在
  显存干净时是 26–33 秒。此前把 16 秒当作基线是错的——那是显存刚好空闲时的偶然值。
- **`plugin/lib/catalog.js` 的 `NEG_CLEAN` 少 7 项**。插件里是 612 字符，而 profile
  里 8 条工作流实际是 651 字符，少了 `beauty mark`、`liver spots`、`patchy skin`
  等。这会让插件新生成的工作流比现有的少过滤一批斑点。
- **反 CG 负向被误用到动漫底模**。`apply_neg.mjs` 把 `cartoon, anime, illustration,
  painting...` 写进了 Illustrious-XL 的负向，与模型本身的风格打架。
- **`install-plugin.ps1` 的 BOM 问题**。PowerShell 5.1 的 `Set-Content -Encoding utf8`
  会写 BOM，Node 拒绝解析带 BOM 的 `package.json`。
- **`install-plugin.ps1` 的非法 JSON**。`"dependencies": {}` 为空时文本拼接会生成
  `"...",}`，改用 `ConvertFrom-Json` 校验后结构化重写。
- **hf-mirror 把限流页写进模型文件**。下载的 T5 大小完全正确但开头是
  `We had to rate limit you, you hit the quota of...`，加载报 `GGUF magic invalid`。

### 已知问题

- FLUX Q2_K 在 8 GB 卡上皮肤会出现量化色斑（脸颊、手臂成片褐色斑点）。这不是提示词
  问题，是低比特量化的伪影。要干净皮肤请用 SDXL 底模。
- 手部仍会翻车，尤其双手交叠和持物。Juggernaut 比 RealVisXL 稳，但都不保证。
- 大笑特写的牙齿偏整齐偏白，有贴片感。
- 多人场景未测。
- 图内短英文招牌的拼写不稳定：同一 prompt 下 FLUX 写成 `KRA COFFEE`、
  RealVisXL 写成 `KREA. COFFEE`、Juggernaut 写成 `KIRE A`。别指望。

---

## [1.0.0] — 2026-11-15

首个可用版本。ComfyUI 独立进程 + DSH 插件调用，配套自制 Denoise 滑杆页。

### 新增

- **`install.ps1`**：七步一键安装，全程幂等，中断了重跑会跳过已完成的部分。
- **ComfyUI 0.45.0** 独立部署，不改上游一行。
- **`python-base/`**：独立的 Python 3.12 副本，不污染系统 Python。
- **Denoise 滑杆页**（`slider/`，8189 端口）：零依赖 Node 服务，上传图、拖滑杆、
  实时对比源图与结果，历史记录可回填参数。
- **`dsh/apply-workflows.mjs`**：把 workflow JSON 写进 profile 的
  `cordis.patch.yml`，支持 `--dry-run` / `--revert`。
- **`docs/INSTALL-QUICK.md`**：逐步骤说明 + 常见失败处理。
- **`docs/AGENT-PROMPT.md`**：整段复制给 AI，让它自己走完安装。
- **`docs/why-local.md`**：为什么本地跑、代价对照。
- Illustrious-XL v1.1 动漫底模 + 两条 workflow（文生图 / 图生图）。

### 修复

真机在干净目录跑了 8 轮，每轮卡在不同地方：

- **PowerShell 把 curl 的进度条当错误**：`$ErrorActionPreference = 'Stop'` 下第一步
  就中断。所有外部调用改走 `Invoke-Native`，临时降级 `Continue`。
- **torch 被装成 CPU 版**：阿里云 `/pytorch-wheels/cu130` 是普通 HTML 页不是
  PEP 503 索引，`--find-links` 会静默回落到 PyPI。改成 whl 直链。
- **1.7 GB wheel 下载被 15 秒读超时打断**：改用 `curl -C -` 断点续传，落盘后本地装。
- **装完 `import torch` 崩在 `typing_extensions`**：`--no-deps` 装法缺运行时依赖，
  脚本显式补九个包并探针验证。
- **PyPI 镜像临时抽风** `ChunkedEncodingError`：四个镜像按序回退（清华 → 腾讯 →
  阿里 → 官方）。
- **重复跑报 `Move-Item : The file exists`**：中断留下的目录改成逐项合并。
- **目录搬了就坏**：`pyvenv.cfg` 里是绝对路径，脚本建完 venv 立刻重指当前目录。

---

## 版本说明

| 版本 | 底模 | 启动参数 | 磁盘 |
|---|---|---|---|
| v1.0.0 | Illustrious-XL（动漫） | `--cache-none` | 11 GB |
| v1.1.0 | + RealVisXL V5 / Juggernaut XI / FLUX Krea | `--cache-lru 8 --reserve-vram 0.3` | 15–33 GB |
| v1.1.1 | 同上（纯文档） | 同上 | 同上 |

[未发布]: https://github.com/devin667/comfyui-dsh/compare/v1.4.4...HEAD
[1.4.4]: https://github.com/devin667/comfyui-dsh/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/devin667/comfyui-dsh/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/devin667/comfyui-dsh/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/devin667/comfyui-dsh/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/devin667/comfyui-dsh/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/devin667/comfyui-dsh/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/devin667/comfyui-dsh/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/devin667/comfyui-dsh/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/devin667/comfyui-dsh/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/devin667/comfyui-dsh/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/devin667/comfyui-dsh/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/devin667/comfyui-dsh/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/devin667/comfyui-dsh/releases/tag/v1.0.0
