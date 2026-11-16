# 给别人用的安装 Prompt

把下面整段复制给你的 DSH（或任何能跑命令的 AI agent），它会自己装完。

前提：Windows 10/11、NVIDIA 显卡显存 ≥ 8 GB、16 GB 内存、目标盘 ≥ 12 GB 空闲。
不需要管理员权限。

---

## 完整版（推荐）

````text
帮我在这台 Windows 机器上装一套本地生图环境：ComfyUI 跑在本机 8188 端口，
然后接到 DSH 里，让生图走本机显卡而不是云端。

## 要做的事

1. 下载安装包：
   https://github.com/devin667/comfyui-dsh/releases/latest/download/comfyui-dsh.zip

   校验 sha256 应当是：
   ae3154031151cd8b5b0fdb70a0d784983b9144501cc49b63b8a87605490e9165

2. 解压到 D:\ComfyUI（路径不要有空格和中文）。

3. 运行安装脚本：

   cd D:\ComfyUI
   powershell -ExecutionPolicy Bypass -File .\install.ps1

   这一步要 15–40 分钟（会下 Python 45 MB、torch 1.7 GB、模型 6.46 GB）。
   用后台任务跑，别让工具超时打断。脚本全程幂等，中断了直接重跑，已下好的会跳过。

   默认只装动漫底模 Illustrious-XL。要真人写实输出，加参数：
     -WithRealistic    +6.5 GB，RealVisXL V5（写实默认档）
     -WithJuggernaut   +6.6 GB，Juggernaut XI（商业/电影感）
     -WithFlux         +9.1 GB，FLUX Krea Q2_K + GGUF 节点（8 GB 卡能跑但慢 3-4 倍）

   例：powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithRealistic

4. 判断安装成功的唯一标准，是最后打印出这段：

     Install complete.

     Next:
       1. double-click the "start ComfyUI" .bat    -> 127.0.0.1:8188
       2. double-click the "start slider" .bat     -> 127.0.0.1:8189
       3. node .\dsh\apply-workflows.mjs      wires the workflows into DSH

     Disk used: 15.0 GB

   以及第 9 步冒烟测试里 cuda 是 True、matmul 是 ok。
   看到 "Install complete." 之前都不要认为装好了。

5. 启动 ComfyUI 并确认它在监听：

   D:\ComfyUI\启动ComfyUI.bat

   窗口里出现 Starting server -> http://127.0.0.1:8188 才算起来。
   然后验证端口：curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8188/
   返回 200 才算通。

6. 把 workflow 接到 DSH：

   cd D:\ComfyUI
   node .\dsh\apply-workflows.mjs

   它会往 %USERPROFILE%\.dsh\profiles\desktop\cordis.patch.yml 写入
   provider: comfyui 和两个 workflow（文生图 + 图生图），并自动备份原文件。

7. 重启一次 DSH 桌面版，让配置生效。

## 注意

- 不要装显卡驱动、不要装 Npcap/WinPcap 这类内核组件、不要加系统服务或开机启动。
- 不要用管理员权限做任何事，普通用户就够。
- 不要把我这台机器上的模型、venv、python-base 拷过去，脚本会自己下。
- 不要删除 D:\ComfyUI\venv 或 python-base，那是环境本体。

## 出问题按这个查

- 报 "无法加载文件 ... 禁止运行脚本"：就是你漏了 -ExecutionPolicy Bypass。
- 报 NativeCommandError 但脚本还在往下走：正常，忽略；如果中断了直接重跑。
- 报 torch install failed：先看第 3 步是不是打了 OK torch 2.9.0+cu130 cuda=True。
  已经 OK 就说明只是探针误判，继续往下走。真失败的话手工补依赖：
    D:\ComfyUI\venv\Scripts\python.exe -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple/ typing_extensions filelock sympy networkx jinja2 fsspec numpy pillow setuptools
- 依赖装到一半报 ChunkedEncodingError：某个 PyPI 镜像抽风，重跑即可，脚本会换镜像。
- 重复跑报 Move-Item : The file exists：不用管，脚本会合并。
- torch 装成 CPU 版（cuda False）：验证命令是
    D:\ComfyUI\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"
  必须是 2.9.0+cu130 True。不是就重装：
    D:\ComfyUI\venv\Scripts\pip.exe install --no-deps --force-reinstall "https://mirrors.aliyun.com/pytorch-wheels/cu130/torch-2.9.0%2Bcu130-cp312-cp312-win_amd64.whl"
- 报 Could not connect to ComfyUI at http://127.0.0.1:8188：ComfyUI 没启动，双击那个 bat。
- 出图超过 3 分钟：内存不够，关掉浏览器标签和壁纸软件。16 GB 内存实测 1024x1024 约 56 秒。

## 装完怎么用

在 DSH 里直接说「画一张 xxx」就走本机了。

想手动调 denoise 就双击 D:\ComfyUI\启动Denoise滑杆.bat，浏览器会开
http://127.0.0.1:8189 —— 传一张图，拖滑杆 0.05 到 1.00，
0.05 几乎不动、0.55 中等改动、0.95 基本重画。

提示词要用英文 Danbooru 标签（best quality, masterpiece, 1girl, solo, silver hair
这种），不要写中文句子，也不要写 "please remove the xxx" 这种自然语言指令，
SDXL 的文本编码器按标签训练，长句和中文基本等于噪声。

装完后告诉我冒烟测试里的显卡型号和显存，以及第一次文生图花了多少秒。
````

---

## 简版（对方已经有 DSH，只想一句话装完）

````text
装本地生图：下 https://github.com/devin667/comfyui-dsh/releases/latest/download/comfyui-dsh.zip
解压到 D:\ComfyUI，跑 powershell -ExecutionPolicy Bypass -File .\install.ps1（后台跑，20-40 分钟，
幂等可重跑），看到 "Install complete." 和 cuda True 就算好；然后双击 启动ComfyUI.bat，
等 "Starting server -> http://127.0.0.1:8188"，再跑 node .\dsh\apply-workflows.mjs，
重启 DSH。不用管理员，不装驱动。
````
