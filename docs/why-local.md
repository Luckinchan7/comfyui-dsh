# 为什么要本地跑

## 云端的两道关

云端生图服务（DashScope / OpenAI / Seedream）在服务端做内容审核。实际会撞到两种拒绝：

```
# 文字层
DashScope image editing failed (400):
{"code":"DataInspectionFailed","message":"Green net check rejected text (input)"}

# 像素层
DashScope image generation failed (400):
{"code":"DataInspectionFailed","message":"Green net check rejected image (output)"}
```

`(input)` 判的是你发的提示词，措辞还有调整空间。
`(output)` 判的是**生成完之后那张图的像素**——提示词怎么写都不影响结果，因为判定对象
根本不是文字。

还有个容易误判的现象：工具调用显示跑了几十分钟。那是内部在反复「生成 → 送审 → 被拒 →
重试」，每次都要重新采样一遍，白烧时间。

## 生图破甲是怎么回事

很多人的直觉是「装个越狱插件就能生任意图」。其实两条链路是分开的，改一条不影响另一条：

```
对话
 └─ 破甲插件（改 system prompt）  →  LLM 这一跳
                                     ↓  决定调什么工具、写什么 prompt
                                  工具调用 generate_image / edit_image
                                     ↓
                                  生图服务（DashScope / OpenAI …）
                                     ↓  另一条 HTTP，独立鉴权、独立审核
                                  服务端内容审核  ← 这里拒你
```

破甲插件改的是发给 LLM 的 system prompt。生图是插件发出的**另一个 HTTP 请求**，
provider 不同、端点不同、鉴权不同。前一条链路再通，后一条该拒还是拒。

所以真正有效的**生图破甲**不是改提示词，是换链路：把模型搬到本机跑。

## 本地部署改变了什么

- 请求不出本机 → 没有服务端审核这一环
- 出图走本机 GPU，全程离线
- PNG 直接写进 `ComfyUI-0.45.0/output/`
- 每张图的参数（seed / steps / denoise / prompt）都完整记录在 PNG 元数据里，可复现

这不是「绕过规则」，是换了一条**根本不经过审核环节**的链路，跟用本地 Photoshop 画图的
处境一样：没有任何一方在事后检查这张图。

## 代价（实话）

| 项 | 云端 | 本地 |
|---|---|---|
| 单图耗时 | 5–20 秒 | 56–70 秒（RTX 5060 Laptop） |
| 模型能力 | Qwen-Image / GPT-Image，20B+ | SDXL 2.6B |
| 图内文字 | 基本正确 | 会乱，别指望 |
| 手脚细节 | 较好 | 偶尔崩 |
| 磁盘 | 0 | 11 GB |
| 显存 | 0 | 6.5–7 GB |
| 边际成本 | 按张计费 | 0（电费除外） |
| 内容限制 | 服务端判定 | 无 |

要画准确的英文标注、或者商用级写实人像，本地 SDXL 不是好选择——这是模型能力问题，
跟审核无关。本地只解决「无人审核」，不解决「模型不够强」。

## 8 GB 显存能跑什么

| 模型 | 参数 | 权重 | 8 GB 可行？ |
|---|---|---|---|
| SDXL（Illustrious / NoobAI） | 2.6B | 6.5 GB | ✅ 原生 1024，56 秒 |
| Flux.1-dev | 12B | 23 GB | ⚠️ 只能 GGUF Q4，2–3 分钟/张 |
| Qwen-Image | 20B | 40 GB | ❌ 跑不动 |

SDXL 是这张卡的甜点。它的生态（LoRA、ControlNet、embedding）也是二次元插画的事实标准，
要特定角色只需挂对应 LoRA，不用换底模。
