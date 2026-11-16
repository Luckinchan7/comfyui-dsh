# 底模选型：从二次元到写实（RTX 5060 Laptop 8 GB 实测）

**返回** [README](../README.md) · [English](../README.en.md) · [变更日志](../CHANGELOG.md)

起因：原来装的 `Illustrious-XL v1.1` 是动漫底模，无论提示词怎么写都出插画。要真人照片
就得换底模。这份文档是三个写实底模 + 一个 FLUX 量化档在同一台机器、同一批提示词下的
横向实测记录，含文件校验、速度、画质定性和各自的适用场景。

所有数字都在 RTX 5060 Laptop（8 GB VRAM / 16 GB RAM）、`832×1216`、热态下测得，
启动参数为 `--cache-lru 8 --reserve-vram 0.3`（最优组合的推导过程见
[PERFORMANCE.md](PERFORMANCE.md)）。

---

## 一、装了什么

| 底模 | 文件 | 体积 | 类型 | 用途 |
|---|---|---|---|---|
| Illustrious-XL v1.1 | `Illustrious-XL-v1.1.safetensors` | 6.5 GB | SDXL 动漫 | 保留，二次元插画 |
| **RealVisXL V5.0** | `RealVisXL_V5.0_fp16.safetensors` | 6.5 GB | SDXL 写实 | **默认**，纪实/生活感 |
| Juggernaut XI v11 | `Juggernaut-XI-v11_fp16.safetensors` | 6.6 GB | SDXL 写实 | 商业/电影感备选 |
| FLUX.1 Krea dev | `flux1-krea-dev-Q2_K.gguf` | 3.7 GB | FLUX 12B | 精品出图，慢 3–4 倍 |

FLUX 配套件（放 `models/text_encoders/` 与 `models/vae/`）：

| 文件 | 体积 | 说明 |
|---|---|---|
| `t5-v1_1-xxl-encoder-Q4_K_S.gguf` | 2.55 GB | T5 文本编码器，GGUF 量化 |
| `clip_l.safetensors` | 235 MB | CLIP-L |
| `flux_ae.safetensors` | 320 MB | FLUX VAE |

全部从 hf-mirror 下载，总计约 19 GB 磁盘。

### 文件校验方法

`.safetensors` 用 header 自洽性校验，几十毫秒就能确认没被截断或写坏：

```python
import json, struct
f = open(path, "rb")
n = struct.unpack("<Q", f.read(8))[0]
hdr = json.loads(f.read(n))
total = 8 + n + max(v["data_offsets"][1] for k, v in hdr.items() if k != "__metadata__")
print(total == os.path.getsize(path))   # 必须 True
```

`.gguf` 校验魔数 `47475546`（ASCII `GGUF`）+ 用 `gguf.GGUFReader` 读张量数：

```python
from gguf import GGUFReader
r = GGUFReader(path)
print(len(r.tensors), r.get_field("general.architecture"))
```

---

## 二、速度

同参数（SDXL：30 步 / cfg 5 / dpmpp_2m karras；FLUX：24 步 / cfg 1 / euler simple），
`832×1216`，热态：

| 底模 | 单图 | HiRes 1.5×（→1248×1824） |
|---|---|---|
| Illustrious-XL | 26–33 s | 62 s |
| **RealVisXL V5** | **26–31 s** | **58 s** |
| Juggernaut XI v11 | 24–30 s | 58 s |
| FLUX Krea Q2_K | 82 s | — |

（单图耗时的浮动来自显存占用——浏览器和微信吃掉 2 GB 时会掉到 140 秒级别，
见 [PERFORMANCE.md](PERFORMANCE.md)。HiRes 那列是显存干净时测的。）

FLUX 各量化档在 8 GB 卡上的真实表现（这一步踩了不少坑）：

| 量化 | 体积 | 加载情况 | 每步 | 结论 |
|---|---|---|---|---|
| Q8_0 / Q6_K | 12 / 9.5 GB | — | — | 装不进 8 GB |
| Q4_K_S | 6.3 GB | `loaded partially`，554 MB 溢出到内存 | 130–400 s | 20 步跑不完，删 |
| Q3_K_S | 5.0 GB | `loaded completely` 5.0/5.7 GB | 131–144 s | 仍然太慢，删 |
| **Q2_K** | **3.7 GB** | `loaded completely` 3.9/5.5 GB | **3.0–3.7 s** | **可用** |

Q3_K_S 明明完整装进了显存却比 Q2_K 慢 40 倍，说明瓶颈不在显存容量而在解量化开销 ——
低比特量化在 SM120 上走的是慢路径。这是 8 GB 卡的反直觉结论：**能装下不等于能用**。

---

## 三、画质定性

同一批提示词、同 seed，六场景对拍（人像 / 皮肤微距 / 全身 / 双手握杯 / 厨房随手拍 /
雨天街景），逐张裁切放大比对。

### RealVisXL V5 vs Juggernaut XI v11

| 场景 | RealVisXL V5 | Juggernaut XI v11 |
|---|---|---|
| 人像 | 色中性偏冷，皮肤不均（小斑点、血丝），最像真人 | 雀斑极锐，对比强偏红暖，有轻微美颜均匀感 |
| 皮肤微距 | 汗珠略糊偏亮 | 汗珠边缘极锐，毛孔胡茬分层，戏剧光 |
| 全身 | 手脚略含糊，画面平 | 脚趾清楚，布纹强，商业片构图 |
| 双手握杯 | 出现多指/融合 | **手指正确**（左 4 指 + 拇指） |
| 厨房随手拍 | **真实乱厨房**：台面杂物、色温偏黄、杯子随意 | 杂志内页：黄橱柜饱和、摆盘讲究、太干净 |
| 雨天街景 | 平光，腿部真实动感模糊，招牌无字 | 电影感强，但招牌乱码 `STIAN OF BOPS` |

定性：**Juggernaut = 商业/电影档**（锐、透、结构准、手更稳，但过度精致）；
**RealVisXL = 纪实/生活档**（色彩中性、画面平、脏乱差照收）。两个都留。

### FLUX Krea Q2_K

场景理解明显更强（厨房杂物、抽屉、窗光的关系都对，构图更"懂事"），手部结构也比 SDXL
稳。但 **Q2 量化在皮肤上留了大量密集褐色斑点** —— 脸颊、手臂、手背成片，是量化的色斑
伪影，不是雀斑。

定量验证（64×64 块最小方差，测平坦区噪点）：FLUX 15.5 / RealVisXL 15.3 / Juggernaut 15.7
—— 平坦区没差别，**损伤只集中在皮肤色块**，所以是真的量化伪影而不是全局噪声。

结论：8 GB 卡上能跑的最高可用量化是 Q2_K，而 Q2_K 的皮肤质量过不了关。**FLUX 在 8 GB
卡上属于"能跑但不必用"**：慢 3–4 倍，换来的场景理解提升被皮肤伪影抵消。

### 图内文字（三方同 prompt）

`a small cafe storefront at dusk, a wooden sign above the door reading "KREA COFFEE"`

| 模型 | 结果 |
|---|---|
| FLUX Q2_K | `KRA COFFEE`（漏 E） |
| RealVisXL V5 | `KREA. COFFEE`（几乎全对） |
| Juggernaut XI | `KIRE A`（大错） |

SDXL 对短英文招牌的拼写能力不稳定，同 prompt 不同 seed 差异很大。**要准确的图内文字，
本地 SDXL/FLUX 都别指望**，这是模型能力问题。

---

## 四、提示词：写实模型最容易踩的坑

RealVisXL 对**摄影语言**极度敏感。照抄动漫模型那套 `masterpiece, best quality, 8k` 会让
它跑向棚拍美化，反而是四种写法里最假的。

同 seed（999）、`896×1152` 四联测：

| 写法 | 效果 |
|---|---|
| `professional studio portrait, beauty dish, flawless skin, masterpiece` | 影楼感，最假 |
| `RAW photo, natural skin texture, visible pores, 85mm f1.8` | 干净照片，通用首选 |
| `amateur snapshot, taken on iPhone, unedited, candid family photo, grain` | **最像真人随手拍** |
| `35mm film, Kodak Portra 400, unretouched` | 胶片味 |

**想要日常真实感，必须写 `amateur snapshot / iPhone / unedited / grain`。**
写 `flawless skin` 就要接受棚拍感。

### 斑点问题：来源是提示词，不是模型

一开始出的图满脸雀斑斑点，排查下来是 `rv5_pipeline.py` 的 portrait 提示词里写着一个
`freckles`。去掉它、并在负向里压住斑点类词，皮肤立刻干净：

```
freckles, moles, birthmark, beauty mark, blemishes, skin spots, dark spots,
age spots, sun spots, liver spots, acne, pimples, acne scars, blackheads,
rosacea, redness on cheeks, blotchy skin, uneven skin tone, patchy skin,
textured skin, rough skin, oily skin, greasy skin, shiny forehead,
large pores, visible pores, wrinkles, skin imperfection, dirty skin
```

配套正向：

```
professional studio portrait photograph, a young woman with fair clean skin,
flawless smooth complexion, clear even skin tone, no freckles, no blemishes,
soft beauty dish lighting, subtle rim light, 85mm f/1.8 lens,
shallow depth of field, sharp detailed eyes, natural catchlight,
photorealistic, high detail, high end photography
```

生活感版本把 `studio / beauty dish` 换成 `RAW photo / soft natural window light`，
保留 `fair clean skin / smooth flawless complexion / even clear tone`。

### 参数甜点

- **cfg 5.0**。cfg 7 会让皮肤硬化出塑料感，这是写实模型和动漫模型最大的参数差异。
- **dpmpp_2m karras 30 步**足够；作者 README 推荐 50 步，实测 30 步已经收敛。
- **dpmpp_sde karras** 纹理更细但慢 1.7 倍（52 s vs 30 s），只在出精品图时用。
- **hires fix** 用 `4x-UltraSharp`，denoise 0.1–0.3，放大 1.1–1.5×。denoise 超过 0.4
  会改脸。

### 加速 LoRA 别用

试过 `sdxl_lightning_4step_lora`：6 步 216 s（冷启动无优势），8 步 131 s。
更严重的是画质 —— 雀斑变硬边褐斑、皮肤出现网格噪点、毛孔变成陨石坑。**写实模型 +
蒸馏加速会毁掉微纹理**，这是原理性的：蒸馏模型训练目标就是跳步，跳过的那部分正是
高频细节。

---

## 五、备案清单（hf-mirror 可达性实测）

| 仓库 | 体积 | 状态 |
|---|---|---|
| `SG161222/RealVisXL_V5.0` | 6.5 GB | ✅ 已装，默认 |
| `RunDiffusion/Juggernaut-XI-v11` | 6.6 GB | ✅ 已装，备选 |
| `RunDiffusion/Juggernaut-XL-v9` | — | 可达，未装 |
| `SG161222/RealVisXL_V4.0` | — | 可达，未装 |
| `Lykon/dreamshaper-xl-1-0` | — | 可达，未装 |
| `SG161222/Realistic_Vision_V6.0_B1_noVAE` | — | 可达，未装 |
| `QuantStack/FLUX.1-Krea-dev-GGUF` | 3.7–12 GB | ✅ Q2_K 已装 |
| epiCRealism XL / CyberRealistic XL / AbsoluteReality 1.8 | — | ❌ 404，只在 CivitAI |

**CivitAI 上的那批顶级写实模型（epiCRealism、CyberRealistic、AbsoluteReality）在
hf-mirror 上都拿不到**，只能从 CivitAI 下（需要账号 + 可能过 Cloudflare）。这是一条
明确的路线：如果要再上一个档，去 CivitAI 下这几个，别在 HF 镜像里翻。

---

## 六、结论

| 你的需求 | 用哪个 |
|---|---|
| 日常真人照片、生活感、纪实 | **RealVisXL V5**（默认） |
| 商业人像、海报、电影感、手要稳 | Juggernaut XI v11 |
| 二次元插画 | Illustrious-XL（保留） |
| 要场景理解最好的一张 | FLUX Krea Q2_K（慢 3–4 倍，皮肤有伪影） |

8 GB 显存的现实：SDXL 2.6B 是这张卡的甜点。FLUX 12B 能塞进 Q2_K 但不划算，
Qwen-Image 20B 想都别想。想要 FLUX 全精度或更好的写实底模，先换卡（16 GB 起步）。
