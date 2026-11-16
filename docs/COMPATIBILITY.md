# 适配说明

**返回** [README](../README.md) · [English](../README.en.md) · [变更日志](../CHANGELOG.md)

这份文档回答一个问题：**在你这台机器上，这套东西能不能跑、能跑什么、要改哪里。**

所有「实测」行都来自同一台机器：RTX 5060 Laptop 8 GB / 16 GB 内存 / Windows 11 24H2
(build 26100) / 驱动 617.42 / Python 3.12.13 / torch 2.9.0+cu130。其余行是按架构
推理的估计值，标注了依据。

---

## 一、显卡与显存

这张表是选型的第一道门槛。SDXL 的权重是 4.9 GB，FLUX 12B 全精度约 24 GB，
所以显存决定了「能用什么」而不只是「快慢」。

| 显存 | SDXL 底模 | FLUX Krea | 建议 |
|---|---|---|---|
| 4 GB | ⚠️ 能启动，1024×1024 会 OOM | ❌ | 降到 512×768、`--reserve-vram 0.5`。勉强可用但很痛苦 |
| 6 GB | ✅ 768×1024 稳，832×1216 需留意占用 | ❌ | 关掉浏览器再跑。1024×1024 有 OOM 风险 |
| **8 GB（实测）** | ✅ **832×1216 稳，26–33 秒** | ⚠️ 仅 Q2_K，82 秒，皮肤有量化色斑 | 本仓库的目标配置 |
| 12 GB | ✅ 1024×1024 无压力，可开 HiRes 2× | ⚠️ Q4_K_S 能完整加载 | FLUX 建议从这里起步 |
| 16 GB | ✅ 1440×1440 可用 | ✅ Q6_K / Q8_0 可用 | 甜点区，FLUX 与 SDXL 都舒服 |
| 24 GB | ✅ 原生 2048 | ✅ 全精度 fp16 | 不再需要量化 |

**关键结论（实测，反直觉）**：FLUX Q3_K_S 在 8 GB 卡上日志写着
`loaded completely; 5019/5700 MB, full load: True`，看起来完美，但每步 131–144 秒，
20 步跑不完。低比特量化在 SM120 上走慢路径。**能装下不等于能用。**

### 显存被占用是最常见的「变慢」原因

8 GB 卡上，Chrome + 微信 + NVIDIA Overlay 能吃掉 2 GB。剩 3.4 GB 时：

```
Model SDXL prepared for dynamic VRAM loading. 4896MB Staged
每步 2.99 s/it → 单图 142 秒
```

剩 6.2 GB 时同一套参数是 26–33 秒。**差距 4 倍，比任何启动参数都重要。**

排查命令：

```powershell
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

---

## 二、驱动与 CUDA

| 组合 | 状态 | 说明 |
|---|---|---|
| RTX 50 系（Blackwell / sm_120）+ cu130 | ✅ 必须 | 本仓库的默认路径。cu126 / cu128 会报 `You need pytorch with cu130 or higher to use optimized CUDA operations` |
| RTX 40 系（Ada / sm_89）+ cu126 或 cu130 | ✅ | 把 `$TorchWhl` 换成对应 cu 版本，其余不用动 |
| RTX 30 系（Ampere / sm_86）+ cu121 或 cu126 | ✅ | 同上 |
| RTX 20 系（Turing / sm_75）+ cu121 | ✅ | 同上，速度约慢一半 |
| GTX 16 系 / 10 系 | ⚠️ | 无 Tensor Core，SDXL 能跑但慢 3–5 倍 |
| 纯 CPU | ❌ | 能启动，一张图 20 分钟以上，没有实用价值 |
| AMD / Intel 显卡 | ❌ | 本仓库只装了 CUDA 版 torch |

驱动版本：**≥ 570**（cu130 要求）。本机是 617.42。

### 换 CUDA 版本的改法

`install.ps1` 顶部三行：

```powershell
$TorchIdx = 'https://mirrors.aliyun.com/pytorch-wheels/cu130'
$TorchWhl = 'https://mirrors.aliyun.com/pytorch-wheels/cu130/torch-2.9.0%2Bcu130-cp312-cp312-win_amd64.whl'
$TvWhl    = 'https://mirrors.aliyun.com/pytorch-wheels/cu130/torchvision-0.24.0%2Bcu130-cp312-cp312-win_amd64.whl'
```

把 `cu130` 换成目标版本即可。**不要用 `pip install torch --index-url .../cu126`
那种装法**——会连带把 torchvision 和一堆依赖顶成 CPU 版。

---

## 三、操作系统

| 系统 | 状态 | 说明 |
|---|---|---|
| Windows 11 x64（实测 build 26100） | ✅ | 本仓库的唯一实测平台 |
| Windows 10 x64 21H2+ | ✅ | 脚本只用了 `Expand-Archive`、`Get-FileHash`、`tar.exe`，都自带 |
| Windows Server 2019+ | ⚠️ | 缺 Microsoft Store 相关组件不影响，但要自己确认 `tar.exe` 存在 |
| Windows 7 / 8 | ❌ | `tar.exe` 和 `Expand-Archive` 都没有 |
| Linux | ⚠️ | ComfyUI 本体没问题，但 `install.ps1` 和两个 `.bat` 要重写。没有现成脚本 |
| macOS | ⚠️ | 只能 MPS，SDXL 一张图 2–5 分钟，本仓库未适配 |
| WSL2 | ⚠️ | 可以用，但需要 WSL 的 CUDA 直通，且显存显示与原生不同 |

**路径要求**：不要有空格、不要有中文。`install.ps1` 里有几处 `Join-Path` 拼接，
空格路径在 `Invoke-Native` 的参数数组里会出问题。

---

## 四、Python 与依赖版本

`install.ps1` 会自己装以下版本，一般不手动干预。

| 包 | 版本 | 为什么是这个版本 |
|---|---|---|
| Python | 3.12.13 | ComfyUI 0.45.0 支持范围内，3.13 有若干 wheel 缺失 |
| torch | 2.9.0+cu130 | sm_120 需要 cu130；2.9 是当前 cu130 的最新稳定版 |
| torchvision | 0.24.0+cu130 | 必须与 torch 配套 |
| transformers | 5.23.0 | ComfyUI 0.45.0 要求 ≥ 4.37，5.x 实测可用 |
| safetensors | 0.8.0 | — |
| gguf | 0.19.0 | 只有装 FLUX 才需要，`≥ 0.13.0` |
| sentencepiece | 0.2.3 | FLUX 的 T5 tokenizer 需要 |
| protobuf | 7.36.2 | sentencepiece 需要 |

**已知版本冲突**：装完 ComfyUI 的 `requirements.txt` 后 torch 会被顶成 CPU 版
（因为 requirements 里 pin 了 `torch`）。`install.ps1` 装依赖时会把
torch / torchvision / torchaudio 三行过滤掉，并在装完后再检查一次，掉了就重装。
手动排查：

```powershell
.\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"
```

必须是 `2.9.0+cu130 True`。

---

## 五、ComfyUI 版本

| 版本 | 状态 | 说明 |
|---|---|---|
| **0.45.0（实测）** | ✅ | 本仓库锁定的版本 |
| 0.4x 其他小版本 | ✅ | 一般可以直接换 tag，注意 `cli_args.py` 里 `--cache-lru` 是否存在 |
| 0.3.x 及更早 | ⚠️ | 可能没有 `--cache-lru`（旧版是 `--cache-lru` 早就有了，但 `--reserve-vram` 是 0.3.4 之后加的） |
| 最新 main | ⚠️ | 未测。`--fast` 相关的行为可能变化 |

换版本改 `install.ps1` 两处：

```powershell
$ComfyUrl = 'https://gh-proxy.com/https://github.com/comfyanonymous/ComfyUI/archive/refs/tags/v0.45.0.tar.gz'
$ComfyAlt = 'https://codeload.github.com/comfyanonymous/ComfyUI/tar.gz/refs/tags/v0.45.0'
$ComfyDir = Join-Path $Root 'ComfyUI-0.45.0'
```

三处都要改，目录名也要跟着改。

### 节点依赖

| 节点 | 用途 | 必需性 |
|---|---|---|
| 内置 `CheckpointLoaderSimple` | SDXL 底模 | 必需 |
| `ComfyUI-GGUF`（city96/ComfyUI-GGUF） | 读 FLUX 的 `.gguf` | 只有 FLUX 需要 |
| `UnetLoaderGGUF` / `DualCLIPLoaderGGUF` | FLUX 的 unet 与双文本编码器 | 只有 FLUX 需要 |

GGUF 节点读的目录（`custom_nodes/ComfyUI-GGUF/nodes.py:32-33`）：

```python
update_folder_names_and_paths("unet_gguf", ["diffusion_models", "unet"])
update_folder_names_and_paths("clip_gguf", ["text_encoders", "clip"])
```

所以 FLUX 的权重放 `models/diffusion_models/`，T5 与 CLIP-L 放
`models/text_encoders/`。

---

## 六、底模与节点的组合

| 底模 | 加载节点 | 需要的文件 | 8 GB 可行 |
|---|---|---|---|
| Illustrious-XL v1.1 | `CheckpointLoaderSimple` | 单个 `.safetensors`（6.5 GB） | ✅ |
| RealVisXL V5.0 fp16 | `CheckpointLoaderSimple` | 单个 `.safetensors`（6.5 GB） | ✅ |
| Juggernaut XI v11 | `CheckpointLoaderSimple` | 单个 `.safetensors`（6.6 GB） | ✅ |
| FLUX Krea Q2_K | `UnetLoaderGGUF` + `DualCLIPLoaderGGUF` + `VAELoader` | 4 个文件（9.1 GB） | ⚠️ 慢 3–4 倍 |

SDXL 三个是同一个架构，**可以共用同一套 workflow，只换 `ckpt_name` 字段**。
FLUX 的图结构完全不同（多 `FluxGuidance`、`EmptySD3LatentImage`，cfg 必须 1.0），
不能与 SDXL 的 workflow 互换。

### 显存和量化的对应（FLUX）

| 量化 | 体积 | 8 GB 上加载 | 每步耗时 | 判断 |
|---|---|---|---|---|
| Q8_0 | 12.6 GB | ❌ | — | 跑不动 |
| Q6_K | 9.8 GB | ❌ | — | 跑不动 |
| Q5_K_S | 8.1 GB | ❌ | — | 跑不动 |
| Q4_K_S | 6.3 GB | `loaded partially; 554 MB offloaded` | 130–400 s | ❌ 已删 |
| Q3_K_S | 5.0 GB | `loaded completely; full load: True` | 131–144 s | ❌ 已删 |
| **Q2_K（实测保留）** | **3.7 GB** | 完整 | **2.8–3.7 s/步** | ⚠️ 皮肤有量化色斑 |

---

## 七、DSH 版本

| 组件 | 版本 | 说明 |
|---|---|---|
| DSH | 0.2.2-rc.3（本机） | 插件机制在这一版上验证 |
| `dsh-image-gen` | 0.11.3 | ComfyUI provider 由它提供 |
| `dsh-comfy-models` | 0.1.0（本仓库） | 底模切换 |

### 一个必须知道的不兼容

`dsh-image-gen` 的**图像生成工作台（Studio）不支持 ComfyUI**。
`CLOUD_IMAGE_PROVIDERS` 列表里没有 `comfyui`，工作台会回落到第一个配了 key 的
云端 provider。**工作台里出图仍然走云端。**

不受影响的是 Agent 工具链路：`generate_image` / `generate_images` / `edit_image`
在 `generateSingle` / `editComfyUIImage` 分支里对 comfyui 是完整支持的。所以聊天里
让 Agent 出图走本地，工作台里动手点还是云端。

### 配置生效方式

改 `cordis.patch.yml` 后**不用重启**——该文件被 HMR 监听，约 10–15 秒热重载。
需要重启的只有：

- `lib/*.js` 代码本体（Node 模块已缓存）
- `package.json` 的依赖或 `- insert:` 注册块
- ComfyUI 那边的底模、节点、启动参数

### 插件注册的坑

`cordis.patch.yml` 里必须写成 **`- insert:` 列表形式**：

```yaml
- insert:
    - id: dsh-comfy-models
      name: dsh-comfy-models
```

平铺写 `- id: dsh-comfy-models` 会让 plugin-manager 报 unknown-plugin。

---

## 八、端口占用

| 端口 | 用途 | 冲突时怎么办 |
|---|---|---|
| 8188 | ComfyUI API | 改 `启动ComfyUI.bat` 里的 `--port`，同时改 profile 里的 `comfyuiBaseURL` |
| 8189 | Denoise 滑杆 | 改 `slider/server.mjs` 里的 `PORT` 常量 |

端口只绑 `127.0.0.1`，局域网内其他机器访问不到。

---

## 九、本机已装的实际版本（供对照）

```
NVIDIA GeForce RTX 5060 Laptop GPU, 8151 MiB, driver 617.42
Windows 11 家庭版 中文版, 10.0.26100
Python 3.12.13
torch 2.9.0+cu130 / torchvision 0.24.0+cu130 / CUDA 13.0
transformers 5.23.0 / safetensors 0.8.0 / gguf 0.19.0 / sentencepiece 0.2.3 / protobuf 7.36.2
ComfyUI 0.45.0
DSH 0.2.2-rc.3 / dsh-image-gen 0.11.3 / dsh-comfy-models 0.1.0
```

启动参数：

```bat
python.exe -s main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3
```

---

## 十、不适配就不适配，别硬凑

以下这些是物理限制，调参数解决不了：

- **4 GB 显存跑 SDXL 1024×1024**：权重 4.9 GB 塞不进 4 GB，只能走
  `dynamic VRAM loading`，每步 3 秒以上，一张图 3 分钟起。
- **8 GB 显存跑 FLUX 全精度**：24 GB 权重，差三倍。
- **纯 CPU 跑 SDXL**：一张图 20 分钟以上。
- **图内文字**：SDXL 和 FLUX 都不稳定。同一 prompt 下实测 FLUX 写 `KRA COFFEE`、
  RealVisXL 写 `KREA. COFFEE`、Juggernaut 写 `KIRE A`。要准确文字请后期加。
- **多人场景**：未测，且 SDXL 在多人构图上普遍容易糊。

想要更好的，路径是换硬件（16 GB 显存起步），不是换参数。
