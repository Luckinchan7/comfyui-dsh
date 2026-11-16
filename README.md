# ComfyUI + DSH 本地生图（Windows / RTX 50 系显卡）

中文 · [English](README.en.md) · [变更日志](CHANGELOG.md) · [适配说明](docs/COMPATIBILITY.md)

一套能落地的本地生图方案：**ComfyUI 独立进程**跑在本机 8188 端口，**DSH 插件**
`dsh-image-gen` 通过 HTTP 调用它。生图链路全程在本机完成，能有效避开云端审核，
不消耗生图 token，产出直接落在自己硬盘上。

配套：

- **Denoise 滑杆页面**（8189 端口）：上传一张图，拖滑杆从「微调」到「基本重画」，实时对比。
- **`dsh-comfy-models` 插件**：在 DSH 里一句话切换底模、自动扫描新模型生成工作流。
- **四个底模**：动漫（Illustrious-XL）+ 写实三档（RealVisXL V5 / Juggernaut XI / FLUX Krea）。

---

## 这套东西解决什么问题

云端生图服务（DashScope / OpenAI / Seedream）在服务端有内容审核，触发后请求被直接拒绝：

```
DashScope image generation failed (400):
{"code":"DataInspectionFailed","message":"Green net check rejected image (output)"}
```

`(input)` 是文字层拦截，改措辞还有机会过；`(output)` 是**图生成出来后送审被拒**，
判定对象是像素，提示词怎么写都没用。

本地部署把整条生成链路搬到自己机器上：请求不出本机，也就没有服务端审核这一环。

细节、代价对比和 8 GB 显存能跑什么，见 [docs/why-local.md](docs/why-local.md)。

---

## 装了什么

| 内容 | 位置 | 说明 |
|---|---|---|
| ComfyUI 源码 | `ComfyUI-0.45.0/` | 上游 v0.45.0，不改一行 |
| Python 运行时 | `python-base/` | 独立 3.12 副本，不污染系统 Python |
| Python 环境 | `venv/` | torch 2.9.0+cu130 + 90 个包 |
| **SDXL 动漫底模** | `models/checkpoints/` | Illustrious-XL v1.1，6.5 GB |
| **SDXL 写实底模** | `models/checkpoints/` | RealVisXL V5.0 fp16，6.5 GB（默认）；Juggernaut XI v11，6.6 GB |
| **FLUX 底模** | `models/diffusion_models/` | flux1-krea-dev-Q2_K.gguf，3.7 GB |
| **FLUX 文本编码器** | `models/text_encoders/` | t5-v1_1-xxl-Q4_K_S（2.55 GB）+ clip_l（235 MB） |
| **FLUX VAE** | `models/vae/` | flux_ae.safetensors，320 MB |
| **GGUF 加载节点** | `custom_nodes/ComfyUI-GGUF/` | 读 FLUX 量化权重 |
| Denoise 滑杆 | `slider/` | 零依赖 Node 服务，8189 端口 |
| DSH 接入配置 | `dsh/` | workflow JSON + 补丁片段 + 应用脚本 |
| **DSH 底模切换插件** | `plugin/` | `dsh-comfy-models`，三个工具 |
| **辅助脚本** | `scripts/` | 断点续传下载器、测速脚本 |

**仓库里不含**（体积太大，安装脚本按需下载）：

- 模型权重 ≈ 19 GB — 从 HF 镜像拉
- `venv/` 4.3 GB — 本地生成
- `python-base/` 381 MB — 从官方便携版复制
- ComfyUI 源码 — 按 tag 下载

装完约占 **33 GB 磁盘**（只装 SDXL 一个底模约 15 GB）。

### 四个底模怎么选

| 想要 | 用 |
|---|---|
| 真人照片、生活感、纪实 | **RealVisXL V5**（默认） |
| 商业人像、海报、电影感、手要稳 | Juggernaut XI v11 |
| 二次元插画 | Illustrious-XL |
| 场景理解最强的一张 | FLUX Krea Q2_K（慢 3–4 倍，皮肤有量化伪影） |

完整对比（六场景画质、FLUX 四档量化实测、提示词四风格、参数甜点、备案清单）
见 **[docs/MODELS.md](docs/MODELS.md)**。

---

## 三步装完

**方式一：下 Release（不用装 git）**

到 [Releases](https://github.com/devin667/comfyui-dsh/releases/latest) 下 `comfyui-dsh.zip`，
解压到 `D:\ComfyUI`，然后：

```powershell
cd D:\ComfyUI
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**方式二：git clone**

```powershell
git clone https://github.com/devin667/comfyui-dsh.git D:\ComfyUI
cd D:\ComfyUI
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

两者内容一致。`install.ps1` 分 9 步、全程幂等，中断了直接重跑：

1. 下载 Python 3.12 便携版 → `python-base\`（不动系统 Python）
2. 建 venv，`pyvenv.cfg` 重指当前目录（整个文件夹可搬移）
3. 装 **torch 2.9.0+cu130**（RTX 50 系必须 cu130，cu126/cu128 会报
   `You need pytorch with cu130 or higher to use optimized CUDA operations`）
4. 下载 ComfyUI v0.45.0 源码
5. 装其余依赖（Torch 已就位，不会被顶成 CPU 版）
6. 下载 Illustrious-XL 模型（走 hf-mirror，比 HF 官方快两个数量级）
7. **可选**下载写实底模：`-WithRealistic`（RealVisXL V5）、`-WithJuggernaut`（Juggernaut XI）
8. 冒烟测试：`cuda True` / 显卡型号 / 显存 / `matmul ok`

```powershell
# 只装动漫底模（默认，15 GB）
.\install.ps1

# 加上 RealVisXL V5（写实默认档，+6.5 GB）
.\install.ps1 -WithRealistic

# 要装 FLUX Krea（+9 GB，需要先装 GGUF 节点）
.\install.ps1 -WithRealistic -WithFlux
```

装完双击 `启动ComfyUI.bat`，再跑一次 `node .\dsh\apply-workflows.mjs` 接到 DSH。
逐步骤说明和排错见 **[docs/INSTALL-QUICK.md](docs/INSTALL-QUICK.md)**。

想让 AI 帮你装？把 **[docs/AGENT-PROMPT.md](docs/AGENT-PROMPT.md)** 里的整段话
复制给 DSH（或任何能跑命令的 agent），它自己会走完全程并自查。

---

## 硬件要求

| 项 | 最低 | 我这台实测 |
|---|---|---|
| 显卡 | 6 GB 显存，支持 CUDA | RTX 5060 Laptop，8 GB |
| 内存 | 16 GB | 16 GB |
| 磁盘 | 15 GB 空闲（四底模全装 33 GB） | 552 GB |
| 系统 | Windows 10/11 x64 | — |

8 GB 显存跑 SDXL 832×1216 刚好够，但**实际可用显存要看当时占用**：浏览器 + 微信 +
NVIDIA Overlay 能吃掉 2 GB。这一点比任何启动参数都重要，见下面的速度一节。

**不支持 4 GB 显存 / 纯 CPU 跑 SDXL**——能启动，但一张图要 20 分钟以上，没有实用价值。

---

## 适配说明

完整矩阵（各档显存、CUDA 版本、操作系统、Python 与 ComfyUI 版本、DSH 版本、
端口冲突）见 **[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)**。这里只放最常被问到的。

### 显卡与显存

| 显存 | SDXL | FLUX Krea | 建议 |
|---|---|---|---|
| 4 GB | ⚠️ 1024×1024 会 OOM | ❌ | 降到 512×768，很痛苦 |
| 6 GB | ✅ 768×1024 稳 | ❌ | 关浏览器再跑 |
| **8 GB（实测）** | ✅ **832×1216，26–33 s** | ⚠️ 仅 Q2_K，82 s，皮肤有伪影 | 本仓库的目标配置 |
| 12 GB | ✅ 1024×1024 无压力 | ⚠️ Q4_K_S 能完整加载 | FLUX 从这里起步 |
| 16 GB | ✅ 1440×1440 | ✅ Q6_K / Q8_0 | 甜点区 |
| 24 GB | ✅ 原生 2048 | ✅ 全精度 fp16 | 不需要量化 |

### 驱动与 CUDA

| 组合 | 状态 |
|---|---|
| RTX 50 系（sm_120）+ cu130 | ✅ 必须，本仓库默认 |
| RTX 40 系（sm_89）+ cu126 / cu130 | ✅ 改 `$TorchWhl` 即可 |
| RTX 30 系（sm_86）+ cu121 / cu126 | ✅ 同上 |
| RTX 20 系（sm_75）+ cu121 | ✅ 同上，约慢一半 |
| GTX 16 系 / 10 系 | ⚠️ 无 Tensor Core，慢 3–5 倍 |
| 纯 CPU | ❌ 一张图 20 分钟以上 |
| AMD / Intel | ❌ 只装了 CUDA 版 torch |

驱动要求 **≥ 570**（cu130）。本机 617.42。

### 系统

| 系统 | 状态 |
|---|---|
| Windows 11 x64（实测 build 26100） | ✅ 唯一实测平台 |
| Windows 10 x64 21H2+ | ✅ 脚本只用了自带的 `tar.exe` / `Expand-Archive` |
| Linux | ⚠️ ComfyUI 本体没问题，`install.ps1` 与两个 `.bat` 要重写 |
| macOS | ⚠️ 只能 MPS，一张图 2–5 分钟，未适配 |
| Windows 7 / 8 | ❌ 缺 `tar.exe` |

**路径不要有空格和中文。**

### 版本

| 组件 | 版本 |
|---|---|
| Python | 3.12.13 |
| torch / torchvision | 2.9.0+cu130 / 0.24.0+cu130 |
| ComfyUI | 0.45.0 |
| DSH | 0.2.2-rc.3 |
| `dsh-image-gen` | 0.11.3 |
| `dsh-comfy-models` | 0.1.0（本仓库） |

### 不适配就不适配

以下都是物理限制，调参数解决不了：4 GB 跑 SDXL 1024×1024、8 GB 跑 FLUX 全精度、
纯 CPU 跑 SDXL、图内文字（两个架构都不稳）、多人场景（未测且普遍容易糊）。
想要更好的，路径是换硬件到 16 GB 显存起步。

---

## 出图速度（RTX 5060 Laptop 8 GB 实测）

条件：`832×1216`，SDXL 30 步 / cfg 5 / dpmpp_2m karras。

| 底模 | 热态单图 | 首图（含加载） | HiRes 1.5×（1248×1824） |
|---|---|---|---|
| Illustrious-XL | 26–33 s | 150 s | 62 s |
| **RealVisXL V5** | **26–31 s** | 150 s | **58 s** |
| Juggernaut XI v11 | 24–30 s | 150 s | 58 s |
| FLUX Krea Q2_K（24 步） | 82 s | 240 s | — |

单图耗时的浮动来自显存占用，不是参数：浏览器 + 微信吃掉 2 GB 时会掉到 140 秒级别，
见下面「启动参数」的最后一节。

### 启动参数

```bat
main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3
```

就这四个，别的都别加。逐个说明：

| 参数 | 为什么 |
|---|---|
| `--cache-lru 8` | 缓存节点结果。**必须加**：默认 `--cache-none` 会让每个节点每次重算，配套的 `--cache-lru 8` 把 -60% 时间省掉 |
| `--reserve-vram 0.3` | 给系统留 300 MB 显存余量。0.5 太保守会触发 dynamic VRAM loading，0 又会在跑 FLUX 时爆 |
| ~~`--fast cublas_ops`~~ | **别加**。显存干净时反而慢（115 s vs 32 s） |
| ~~`--fast fp16_accumulation`~~ | **别加**。单独使用慢 3.5 倍（72–87 s vs 20 s） |
| ~~`--enable-triton-backend`~~ | **别加**。装了 triton 3.5.1 反而灾难性变慢（FLUX 每步 178–295 s） |
| ~~`--highvram`~~ | 别加，8 GB 顶不住 4.9 GB 权重反复换出 |

踩坑全过程（哪种组合多快、为什么 triton 反而更慢、显存被浏览器吃掉 2 GB
后的真实基线）见 **[docs/PERFORMANCE.md](docs/PERFORMANCE.md)**。

**一条最实用的经验**：出图变慢时先看 `nvidia-smi` 的 `memory.free`。剩 3.4 GB 和剩
6.2 GB 的差距是 142 秒 vs 32 秒——比换任何参数都有效。

---

## Denoise 滑杆怎么用

双击 `启动Denoise滑杆.bat`，浏览器开 `http://127.0.0.1:8189`。

滑杆范围 0.05–1.00，语义对照：

| denoise | 效果 |
|---|---|
| 0.05–0.20 | 几乎不动，只补细节 |
| 0.20–0.40 | 轻微改动（换表情、加配饰） |
| 0.40–0.55 | 保守改动，人物身份稳 |
| 0.55–0.75 | 中幅改动（**0.55 是默认档**） |
| 0.75–0.88 | 大幅改动（明显重绘的上限大约 0.8） |
| 0.88–0.97 | 激进，脸开始漂 |
| 0.97–1.00 | 基本等于只用源图定构图 |

**提示词必须用英文，而且要用标签式**，不是自然语言句子。同一张图、同 seed、
同 denoise 下实测：

```
中文： 就这个姿势，画风不变，人物样貌不变，把背景换成白天的海边   → 背景基本没动
英文： same pose, same art style, same girl, identical face,
       identical long silver hair, sunny beach background,
       bright daylight, clear sky                                 → 改到位
```

原因是 SDXL 的文本编码器按英文标签训练，中文进去基本等于噪声。要写「状态标签」
（`sunny beach`、`bright daylight`）而不是「动作指令」（`change the background to`），
后者模型响应很弱。

---

## 接到 DSH 上

前提：DSH 已装 `dsh-image-gen` 插件（0.11.x）。

```powershell
# 把 workflow 写进 profile 配置（脚本会先备份再改）
node .\dsh\apply-workflows.mjs
```

然后重启 DSH，设置 → 插件 → 图像生成：

- Provider 选 `comfyui`
- Base URL 填 `http://127.0.0.1:8188`

之后 `generate_image` / `edit_image` 工具调用全部走本地。

**注意一个坑**：`dsh-image-gen` 的**图像生成工作台（Studio）不支持 ComfyUI**。
`CLOUD_IMAGE_PROVIDERS` 这个列表里没有 `comfyui`，所以工作台会回落到第一个配了 key 的
云端 provider。工作台里出图仍然是云端出的。

不受影响的是 Agent 工具链路——`generate_image`、`generate_images`、`edit_image` 三个
工具在 `generateSingle` / `editComfyUIImage` 分支里对 comfyui 是完整支持的。

### 切换底模：`dsh-comfy-models` 插件

`dsh-image-gen` 自己只能选工作流，改模型要手改 YAML + 重启。这个插件补上这一段。

装法（`plugin/` 目录里有完整源码和 README）：

```powershell
# 1. 拷进 profile 的本地包目录
xcopy /E /I plugin "%USERPROFILE%\.dsh\profiles\desktop\.local-packages\dsh-comfy-models"

# 2. profile 的 package.json 里加依赖
#    "dsh-comfy-models": "file:./.local-packages/dsh-comfy-models"

# 3. profile 的 cordis.patch.yml 里加注册块（必须是 - insert: 列表形式）
```

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

三个工具：

| 工具 | 作用 |
|---|---|
| `comfy_models_list` | 列出 ComfyUI 里所有底模 + 当前工作流 + 当前激活项 |
| `comfy_models_sync` | 扫到新底模就自动生成 文生图 / 改图 / HiRes 三条工作流 |
| `comfy_models_switch` | 一句话切模型：`juggernaut` / `flux` / `realvis` 都能命中 |

匹配优先级：全等 → 忽略大小写全等 → 前缀 → 包含，同级取名字最短的
（所以 `juggernaut` 命中 `Juggernaut-XI` 而不是 `Juggernaut-XI-Edit`）。

改的是 profile 的 `cordis.patch.yml`，该文件被 HMR 监听，**改完十几秒自动生效，不用重启 DSH**。
详细说明见 [plugin/README.md](plugin/README.md)。

---

## 安全与卸载

- **不写注册表**、**不装系统服务**、**不加开机启动**
- 不动显卡驱动，不装内核驱动
- 不跑的时候：0 进程、0 显存、0 CPU
- 卸载：结束 python 进程，删掉整个目录

端口只绑 `127.0.0.1`，局域网内其他机器访问不到。

---

## 目录结构

```
ComfyUI-0.45.0/           ComfyUI 源码（v0.45.0，未改动）
  models/checkpoints/     Illustrious-XL / RealVisXL-V5.0 / Juggernaut-XI-v11
  models/diffusion_models/ flux1-krea-dev-Q2_K.gguf
  models/text_encoders/   t5-v1_1-xxl-Q4_K_S.gguf + clip_l.safetensors
  models/vae/             flux_ae.safetensors
  models/upscale_models/  4x-UltraSharp.pth
  custom_nodes/ComfyUI-GGUF/   FLUX GGUF 加载节点
  input/                  上传的源图落这里
  output/                 生成的图落这里
  main.py
python-base/              独立 Python 3.12（可整目录搬移）
venv/                     Python 环境
slider/
  server.mjs              零依赖 HTTP 服务
  index.html              滑杆页面
  cli.mjs                 命令行入口
dsh/
  workflows/              workflow JSON（4 底模 × 文生图/改图/HiRes）
  workflows.manifest.json 工作流元数据 + 预设提示词
  apply-workflows.mjs     写进 cordis.patch.yml
  export-from-profile.mjs 从 profile 反向导出
plugin/                    dsh-comfy-models 插件（lib/catalog.js 等）
scripts/
  fetch_parts.sh          断点续传下载器（带魔数校验）
  bench_final.py          测速脚本
docs/
  INSTALL-QUICK.md        逐步骤安装说明 + 排错
  AGENT-PROMPT.md         复制给 AI 让它自己装的 prompt
  why-local.md            为什么本地跑 / 代价对比
  MODELS.md               四个底模横向实测
  PERFORMANCE.md          启动参数调优与显存争用
  COMPATIBILITY.md        显卡/驱动/系统/版本适配矩阵
启动ComfyUI.bat           启动 ComfyUI（已在跑就提示）
启动Denoise滑杆.bat       启动滑杆页（已在跑就打开浏览器）
install.ps1               一键安装
CHANGELOG.md              版本变更日志
README.en.md              英文说明
```

---

## 常见问题

**Q: 报 `Could not connect to ComfyUI at http://127.0.0.1:8188`**
ComfyUI 没启动。`dsh-image-gen` 没有 provider 回退逻辑，连不上就直接抛错，不会静默切到
云端。双击 `启动ComfyUI.bat`。

**Q: 报 `You need pytorch with cu130 or higher`**
torch 版本不对。RTX 50 系（Blackwell / sm_120）必须 cu130：
```powershell
.\venv\Scripts\pip.exe install --no-deps --force-reinstall "https://mirrors.aliyun.com/pytorch-wheels/cu130/torch-2.9.0%2Bcu130-cp312-cp312-win_amd64.whl"
```

**Q: 装依赖时 `pip` 把 torch 降级成 CPU 版**
`pip install -r requirements.txt` 会重装 torch。装完必须检查：
```powershell
.\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"
```
应当输出 `2.9.0+cu130 True`。

**Q: 出图 200 秒以上**
先看 `nvidia-smi` 的 `memory.free`。低于 4 GB 就是显存被别的程序占了，关浏览器/微信。
其次确认启动参数**只有** `--cache-lru 8 --reserve-vram 0.3`，掺了 `--fast` 或
`--enable-triton-backend` 会慢一个数量级。详见 [docs/PERFORMANCE.md](docs/PERFORMANCE.md)。

**Q: 出的图满脸雀斑斑点**
提示词里写了 `freckles`。去掉它，并在负向里加斑点类词（清单见
[docs/MODELS.md](docs/MODELS.md) 第四节）。不是模型缺陷。

**Q: 写实模型出的图像棚拍、不像真人**
`masterpiece, best quality, 8k` 这类词会把写实模型拉向影楼美化。要日常感就写
`amateur snapshot, taken on iPhone, unedited, grain`。同理 cfg 用 5，别用 7。

**Q: 想换模型**
任何 SDXL 系 checkpoint 丢进 `models/checkpoints/` 即可，装了这个插件就跑一次
`comfy_models_sync` 自动生成工作流。FLUX 系需要 GGUF 量化 + ComfyUI-GGUF 节点，
8 GB 卡上只有 Q2_K 能跑但皮肤有伪影，详见 [docs/MODELS.md](docs/MODELS.md)。

**Q: 下载的模型文件大小对但加载报 `GGUF magic invalid`**
hf-mirror 在被限流时会把报错页当正文写进文件，大小完全吻合。用 `scripts/fetch_parts.sh`
下载，它校验 HTTP 206 状态 + 每段字节数 + 文件魔数。

---

## 版本

| 版本 | 底模 | 启动参数 | 磁盘 |
|---|---|---|---|
| v1.0.0（2026-11-15） | Illustrious-XL（动漫） | `--cache-none` | 11 GB |
| **v1.1.0（2026-11-16）** | + RealVisXL V5 / Juggernaut XI / FLUX Krea | `--cache-lru 8 --reserve-vram 0.3` | 15–33 GB |

逐条变更见 **[CHANGELOG.md](CHANGELOG.md)**。

---

## 许可

本仓库的脚本与滑杆页面：MIT。

ComfyUI 源码：GPL-3.0，来自 [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI)。

模型权重许可见各自仓库：Illustrious-XL v1.1（非商用）、RealVisXL V5.0、
Juggernaut XI v11、FLUX.1 Krea dev（非商用）。仓库里不包含模型权重，安装脚本仅提供下载指引。
