# 变更日志

本文件记录这个项目的所有重要变更。
格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布]

### 计划中

- 多人场景的构图测试（当前所有实测都是单人）
- 手部专项：负向 + 局部重绘的组合配方
- Linux 下的等价脚本（当前只有 Windows）

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

[未发布]: https://github.com/devin667/comfyui-dsh/compare/v1.2.0...HEAD
[1.2.2]: https://github.com/devin667/comfyui-dsh/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/devin667/comfyui-dsh/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/devin667/comfyui-dsh/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/devin667/comfyui-dsh/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/devin667/comfyui-dsh/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/devin667/comfyui-dsh/releases/tag/v1.0.0
