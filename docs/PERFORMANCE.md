# 性能调优实录（RTX 5060 Laptop 8 GB）

**返回** [README](../README.md) · [English](../README.en.md) · [变更日志](../CHANGELOG.md) · [保脸换装](IPADAPTER.md)

这份文档记录把 SDXL 单图从 **328 秒压到 26–33 秒**的完整过程，包括几次走错的弯路。
结论在最后，赶时间可以跳过去直接看。

所有数字：`832×1216`，RealVisXL V5 或 Illustrious-XL，30 步 / cfg 5 / dpmpp_2m karras，
热态（模型已加载）。

---

## 一、起点：328 秒一张

最初的启动脚本带着 `--cache-none`：

```bat
python.exe -s main.py --listen 127.0.0.1 --port 8188 --cache-none
```

冷启动首图 328.6 秒，热态 30.2 秒。当时以为"冷启动慢是因为要读 6.5 GB 权重"，其实
`--cache-none` 让**每一张图都重读一遍权重**——那不是冷启动，是常态。

`--cache-none` 的语义在 ComfyUI 源码里很清楚：

```python
# comfy/cli_args.py:143-144
parser.add_argument("--cache-lru", type=int, default=0, ...)
parser.add_argument("--cache-none", action="store_true", ...)

# execution.py:123
CacheType.NONE → NullCache    # 每个节点每次都重算
```

这个参数是为"节点很多、内存很小"的场景设的，用在 16 GB 的机器上纯属自残。

## 二、换成 `--cache-lru 8`

```bat
python.exe -s main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3
```

| 参数 | 热态单图 |
|---|---|
| `--cache-none`（原） | 30.2 s |
| `--cache-lru 8 --reserve-vram 0.3` | **20.1 s**（4 次重复 20.1–22.1 s） |

省 33%。这一步是纯赚，没有副作用。

`--reserve-vram 0.3` 是给系统留 300 MB 余量，防止 8 GB 卡在峰值时爆显存。

## 三、弯路一：`--fast fp16_accumulation`

看到有这个参数就想试，结果**慢 3.5 倍**：

| 组合 | 热态单图 |
|---|---|
| 只加 `--fast fp16_accumulation` | 86.7 s / 72.5 s / 72.7 s |

原因：fp16 累加在 SM120 上走的是模拟路径，每次矩阵乘都要拆成多段，反而比原生 fp32
累加更慢。**在 50 系笔记本卡上这个参数是负优化。**

## 四、弯路二：`--fast cublas_ops` 与双 fast 的假象

| 组合 | 热态单图 |
|---|---|
| `--cache-lru 8 --reserve-vram 0.3 --fast cublas_ops` | 18.1 s / 18.2 s（首图 70.5 s） |
| 上一行 + `fp16_accumulation` | **16.0 s / 16.1 s**（首图 26.1 s） |

看起来双 fast 又快了一点。当时还做了画质校验（`cl_both_00002_.png` 目视确认毛孔雀斑
没有劣化），差点就写进启动脚本了。

**但这是假象。** 后来复现时这两组参数都变慢了，原因见第六节——那天测的时候显存恰好
是干净的，而 `--fast` 的收益在显存充裕时才显现；显存一被占，它反而放大开销。

## 五、弯路三：`--enable-triton-backend`（最惨的一次）

发现 `import triton` 成功（triton 3.5.1）、`comfy_kitchen` 的 triton backend 报
`available: True`，就加上 `--enable-triton-backend` 想加速注意力。

结果：

| 场景 | 表现 |
|---|---|
| FLUX Q2_K 24 步 | `Model Initialization complete!` 花 **240 s**，单步 **178–295 s/it**，15 分钟只跑到 3/24 步 |
| SDXL 30 步 | run1 284.2 s / run2 142.5 s |

日志里还是 `Using pytorch attention`——**注意力根本没换成 triton**，只是 comfy_kitchen
的其他算子走了 triton 路径，而那些 triton kernel 在 SM120 上需要 JIT 编译，首次运行
极慢，且编译缓存对每个 batch shape 都失效。

更坑的是这会让整个进程卡在"看起来在跑但每步 3 分钟"的状态。中断手段：

```bash
curl -s -X POST http://127.0.0.1:8188/interrupt
curl -s -X POST -H "Content-Type: application/json" -d '{"clear":true}' http://127.0.0.1:8188/queue
```

日志会打出 `Processing interrupted` 和 `Prompt executed in 00:15:55`。

**结论：`--enable-triton-backend` 在 8 GB 的 50 系笔记本卡上不要开。**

## 六、真正的元凶：显存被占

去掉 triton 后 SDXL 还是 141 秒，比早先的 20 秒差一个数量级。查 `nvidia-smi`：

```
memory.total  8151 MiB
memory.used   4485 MiB     ← 只有 6% 利用率，但显存被占了 4.4 GB
memory.free   3415 MiB
```

跑图日志里出现：

```
Model SDXL prepared for dynamic VRAM loading. 4896MB Staged. 0 patches attached.
```

`dynamic VRAM loading` = 权重放不下，只能一部分留显存、一部分留内存，每步换进换出。
步耗时 2.99 s/it。

凶手是谁：Chrome（多个标签）、微信小程序、NVIDIA Overlay、explorer 的几十个渲染上下文。
关掉 ComfyUI 后显存回落到 `1680 MiB used / 6220 MiB free`。

### 干净显存下的真实基线

| 参数 | run1（含加载） | run2 | run3 | run4 | run5 |
|---|---|---|---|---|---|
| `--cache-lru 8 --reserve-vram 0.3` | 153.0 s | **33.2 s** | 31.3 s | 32.1 s | **26.3 s** |
| 同上 + `--fast cublas_ops fp16_accumulation` | 154.9 s | 115.6 s | — | — | — |

**热态 26–33 秒才是这台机器的真实水平**，而双 fast 在干净显存下是 115 秒——比不加参数
慢 3.5 倍。第四节的 16 秒是特定条件下的偶然值，不能作为基线。

## 七、最终结论

```bat
main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3
```

就这四个参数。其它全都别加：

| 参数 | 判定 |
|---|---|
| `--cache-lru 8` | ✅ 必加，省 33% |
| `--reserve-vram 0.3` | ✅ 必加，防爆显存。0.5 太保守会触发 dynamic loading |
| `--fast cublas_ops` | ❌ 显存干净时慢 3.5 倍 |
| `--fast fp16_accumulation` | ❌ 单独用慢 3.5 倍 |
| `--enable-triton-backend` | ❌ 灾难性变慢（每步 178–295 s） |
| `--highvram` | ❌ 8 GB 顶不住 4.9 GB 权重反复换出 |
| `--disable-fast-disk` | ❌ 更慢（19–21 s/it，内存装不下权重） |

### 排查顺序

出图变慢时按这个顺序查，别急着调参数：

1. `nvidia-smi --query-gpu=memory.used,memory.free --format=csv` — free 低于 4 GB 就是它
2. 看日志有没有 `dynamic VRAM loading` — 有就是显存不够
3. 确认启动参数**没有** `--fast` 和 `--enable-triton-backend`
4. 重启 ComfyUI 释放残留显存（进程退出不一定立刻还显存）

第 1 步和第 2 步能解释 90% 的"突然变慢"。

### 卡在 8 GB 的物理上限

SDXL 2.6B 是这张卡的甜点：4.9 GB 权重 + 1.5 GB 激活，刚好塞满 8 GB。

FLUX 12B 在 8 GB 上只有 Q2_K（3.7 GB）能跑，而且慢 3–4 倍、皮肤有量化伪影。
Q3_K_S 能**完整装进**显存（5.0/5.7 GB，`full load: True`）但每步 131–144 秒——
低比特量化在 SM120 上走慢路径，能装下不等于能用。这条反直觉的结论花了一整个下午才确认。

想要 FLUX 全精度或更好的写实底模，硬件上得先换到 16 GB 显存起步。
