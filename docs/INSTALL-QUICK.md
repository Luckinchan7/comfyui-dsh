# 三步装完（Windows）

## 前提

| 项 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11 x64 |
| 显卡 | NVIDIA，显存 ≥ 8 GB（RTX 20 系及以上；30/40/50 系原生支持） |
| 磁盘 | 目标盘 ≥ 12 GB 空闲 |
| 网络 | 能访问 mirrors / npmmirror / hf-mirror（国内直连正常） |
| 权限 | 普通用户即可，**不需要管理员**，不装驱动、不写注册表、不加服务 |

## 第一步：下载

到 [Releases](https://github.com/devin667/comfyui-dsh/releases/latest) 下载：

- `comfyui-dsh.zip`（约 60 KB，只有脚本，不含模型和 Python）

解压到你想装的位置，比如 `D:\ComfyUI`。路径**不要带空格和中文**。

## 第二步：跑安装脚本

在解压出来的目录里，右键 `install.ps1` → **使用 PowerShell 运行**。

或者开一个 PowerShell 窗口：

```powershell
cd D:\ComfyUI
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

脚本会依次做 9 件事，全程有进度输出：

```
[1] Python 3.12 runtime (standalone copy, system Python untouched)
[2] virtual environment
[3] PyTorch with CUDA 13 (RTX 50 series / Blackwell sm_120 needs cu130)
[4] ComfyUI source v0.45.0
[5] ComfyUI Python dependencies
[6] SDXL checkpoint - Illustrious-XL v1.1 (6.46 GB)
[7] photoreal SDXL checkpoints      <- 可选
[8] FLUX.1 Krea dev                 <- 可选
[9] smoke test
```

大概 15–40 分钟，取决于网速。**中断了直接重跑就行**，每一步都是幂等的，已下好的会跳过。

### 要不要装写实底模

默认只装动漫底模 Illustrious-XL。要真人照片就加开关：

```powershell
# 写实默认档 RealVisXL V5（+6.5 GB，推荐加上）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithRealistic

# 再加 Juggernaut XI，商业/电影感，手部更稳（+6.6 GB）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithRealistic -WithJuggernaut

# 再加 FLUX Krea（+9.1 GB，8 GB 卡上慢 3-4 倍，皮肤有量化伪影）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithRealistic -WithFlux
```

第 7、8 步没请求就打印一行 skip，不会阻断后面的步骤。选哪个底模见
[MODELS.md](MODELS.md)，显存够不够见 [COMPATIBILITY.md](COMPATIBILITY.md)。

跑完看到这个就算成功：

```
  Install complete.

  Next:
    1. double-click the "start ComfyUI" .bat    -> 127.0.0.1:8188
    2. double-click the "start slider" .bat     -> 127.0.0.1:8189
    3. node .\dsh\apply-workflows.mjs      wires the workflows into DSH

  Disk used: 15.0 GB
```

## 第三步：接到 DSH

双击 `启动ComfyUI.bat`，等窗口里出现：

```
Starting server -> http://127.0.0.1:8188
```

然后执行一次：

```powershell
node .\dsh\apply-workflows.mjs
```

这条命令会往 `~/.dsh/profiles/desktop/cordis.patch.yml` 里写入 `provider: comfyui`
和两个 workflow（文生图 + 图生图）。写完重启一次 DSH 桌面版即可。

之后在 DSH 里直接让我生图，就是走本机显卡了。

---

## 想调 denoise 就双击另一个 bat

`启动Denoise滑杆.bat` → 浏览器打开 `http://127.0.0.1:8189`。

上传一张图，拖滑杆（0.05–1.00）：

| 区间 | 效果 |
| --- | --- |
| 0.05 – 0.20 | 几乎不动，只去噪 |
| 0.20 – 0.40 | 轻微改变（表情、光线） |
| 0.40 – 0.55 | 保守，构图和人都不变 |
| 0.55 – 0.75 | 中等幅度，服装/背景能改 |
| 0.75 – 0.88 | 大幅重绘，脸开始漂 |
| 0.88 – 0.97 | 只借构图 |
| 0.97 – 1.00 | 等于重画 |

两套 prompt 都要用**英文 Danbooru 标签**，不要写自然语言句子 —— SDXL 的文本编码器
是按标签训练的，中文和长句基本等于噪声。

---

## 出问题看这里

**`install.ps1` 一闪就没了**
用 PowerShell 窗口跑，别双击。

**报 `无法加载文件 ... 因为在此系统上禁止运行脚本`**
这就是上面那条 `-ExecutionPolicy Bypass` 的作用，照着敲。

**`torch install failed` 但日志里 wheel 下载成功了**
脚本内部会自己补依赖。如果还是失败，手工补一次：

```powershell
.\venv\Scripts\python.exe -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple/ typing_extensions filelock sympy networkx jinja2 fsspec numpy pillow setuptools
```

**依赖装到一半报 `ChunkedEncodingError`**
某个 PyPI 镜像临时抽风。脚本会自己换下一个镜像，多跑几次也能过。

**`Could not connect to ComfyUI at http://127.0.0.1:8188`**
ComfyUI 没启动。双击 `启动ComfyUI.bat`，等 `Starting server` 出来再试。

**出图很慢（> 3 分钟）**
先看显存，不是内存。任务管理器 → 性能 → GPU → 专用 GPU 内存，或者：

```powershell
nvidia-smi --query-gpu=memory.used,memory.free --format=csv
```

`memory.free` 低于 4 GB 就是它——关浏览器标签、微信小程序、NVIDIA Overlay。
8 GB 卡上剩 6.2 GB 跑一张 832×1216 是 26–33 秒，剩 3.4 GB 就变 142 秒。

启动参数只该有 `--cache-lru 8 --reserve-vram 0.3`。掺了 `--fast cublas_ops`、
`--fast fp16_accumulation` 或 `--enable-triton-backend` 会慢一个数量级
（原因见 [PERFORMANCE.md](PERFORMANCE.md)）。

**换显卡了 / 搬目录了**
整个文件夹搬过去，重跑一次 `install.ps1`，它会重指 `pyvenv.cfg`，环境继续能用。

**想彻底删掉**
删掉整个文件夹。没有服务、没有注册表、没有开机启动，显卡驱动也没动过。
