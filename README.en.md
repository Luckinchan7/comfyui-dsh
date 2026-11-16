# ComfyUI + DSH — local image generation (Windows / RTX 50 series)

[中文说明](README.md) · **English**

A local image generation stack that actually installs: **ComfyUI runs as its own process**
on `127.0.0.1:8188`, and the **DSH plugin** `dsh-image-gen` calls it over HTTP.
The whole generation path stays on your machine — no server-side moderation, no
per-image billing, output lands on your own disk.

Bundled with it:

- A **Denoise slider page** (port 8189): drop in an image, drag the slider from
  "barely touch it" to "repaint it", compare source and result live.
- The **`dsh-comfy-models` plugin**: switch checkpoints with one sentence, auto-generate
  workflows for any newly added model.
- **Four checkpoints**: one anime (Illustrious-XL) plus three photoreal
  (RealVisXL V5 / Juggernaut XI / FLUX Krea).

---

## What this solves

Cloud image services (DashScope / OpenAI / Seedream) moderate on the server and reject
the request outright:

```
DashScope image generation failed (400):
{"code":"DataInspectionFailed","message":"Green net check rejected image (output)"}
```

`(input)` is a text-layer block — rewording might get through. `(output)` means
**the image was generated and then rejected on its pixels**; no prompt wording helps.

Local deployment moves the whole pipeline onto your own machine. The request never
leaves the host, so there is no server-side moderation step to hit.

Background, cost comparison, and what 8 GB of VRAM can actually do:
[docs/why-local.md](docs/why-local.md) (Chinese).

---

## What gets installed

| Component | Location | Notes |
|---|---|---|
| ComfyUI source | `ComfyUI-0.45.0/` | Upstream v0.45.0, not a line changed |
| Python runtime | `python-base/` | Standalone 3.12 copy, system Python untouched |
| Python environment | `venv/` | torch 2.9.0+cu130 + 90 packages |
| **SDXL anime checkpoint** | `models/checkpoints/` | Illustrious-XL v1.1, 6.5 GB |
| **SDXL photoreal checkpoints** | `models/checkpoints/` | RealVisXL V5.0 fp16 (default), Juggernaut XI v11 |
| **FLUX checkpoint** | `models/diffusion_models/` | flux1-krea-dev-Q2_K.gguf, 3.7 GB |
| **FLUX text encoders** | `models/text_encoders/` | t5-v1_1-xxl-Q4_K_S (2.55 GB) + clip_l (235 MB) |
| **FLUX VAE** | `models/vae/` | flux_ae.safetensors, 320 MB |
| **GGUF loader nodes** | `custom_nodes/ComfyUI-GGUF/` | Loads quantized FLUX weights |
| Denoise slider | `slider/` | Zero-dependency Node service, port 8189 |
| DSH wiring | `dsh/` | workflow JSON + patch block + apply script |
| **Checkpoint switcher plugin** | `plugin/` | `dsh-comfy-models`, three tools |
| **Helper scripts** | `scripts/` | Resumable downloader, benchmark |

**Not in the repo** (too large — the installer fetches them):

- Model weights ≈ 19 GB — from the HF mirror
- `venv/` 4.3 GB — built locally
- `python-base/` 381 MB — copied from the official portable build
- ComfyUI source — downloaded by tag

Full install is about **33 GB** on disk (15 GB with only one SDXL checkpoint).

### Which checkpoint to use

| You want | Use |
|---|---|
| Real people, candid, documentary feel | **RealVisXL V5** (default) |
| Commercial portrait, poster, cinematic, steadier hands | Juggernaut XI v11 |
| Anime / illustration | Illustrious-XL |
| Best scene comprehension in one image | FLUX Krea Q2_K (3–4× slower, quantization spots on skin) |

Full comparison (six scenes, FLUX quantization tiers, prompt styles, parameter sweet
spots) is in [docs/MODELS.md](docs/MODELS.md) (Chinese).

---

## Install

**Option 1: download the release (no git needed)**

Grab `comfyui-dsh.zip` from [Releases](https://github.com/devin667/comfyui-dsh/releases/latest),
unzip to `D:\ComfyUI`, then:

```powershell
cd D:\ComfyUI
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**Option 2: git clone**

```powershell
git clone https://github.com/devin667/comfyui-dsh.git D:\ComfyUI
cd D:\ComfyUI
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Same content either way. `install.ps1` runs 9 steps and is idempotent — interrupt it and
just run it again:

1. Download the Python 3.12 portable build → `python-base\` (system Python untouched)
2. Create the venv, repoint `pyvenv.cfg` at the current folder (the tree stays movable)
3. Install **torch 2.9.0+cu130** (RTX 50 series requires cu130; cu126/cu128 fails with
   `You need pytorch with cu130 or higher to use optimized CUDA operations`)
4. Download ComfyUI v0.45.0 source
5. Install remaining dependencies (torch is excluded so pip cannot swap in a CPU build)
6. Download the Illustrious-XL checkpoint (via hf-mirror, two orders of magnitude faster)
7. **Optional** photoreal checkpoints: `-WithRealistic`, `-WithJuggernaut`
8. **Optional** FLUX: `-WithFlux` (also clones ComfyUI-GGUF and installs gguf deps)
9. Smoke test: `cuda True` / GPU name / VRAM / `matmul ok`

```powershell
# Anime checkpoint only (default, 15 GB)
.\install.ps1

# Add RealVisXL V5 — the photoreal default (+6.5 GB)
.\install.ps1 -WithRealistic

# Add FLUX Krea too (+9.1 GB, needs the GGUF nodes)
.\install.ps1 -WithRealistic -WithFlux
```

Then double-click `启动ComfyUI.bat` and run `node .\dsh\apply-workflows.mjs` to wire it
into DSH. Step-by-step notes and troubleshooting: [docs/INSTALL-QUICK.md](docs/INSTALL-QUICK.md).

Want an AI to do it? Paste the whole block from
[docs/AGENT-PROMPT.md](docs/AGENT-PROMPT.md) into DSH (or any agent that can run
commands) and it will walk the install and self-check.

---

## Requirements

| Item | Minimum | This machine |
|---|---|---|
| GPU | 6 GB VRAM, CUDA capable | RTX 5060 Laptop, 8 GB |
| RAM | 16 GB | 16 GB |
| Disk | 15 GB free (33 GB with all four checkpoints) | 552 GB |
| OS | Windows 10/11 x64 | Windows 11 26100 |
| Driver | ≥ 570 (cu130) | 617.42 |

8 GB of VRAM is just enough for SDXL at 832×1216, but **usable VRAM depends on what else
is running**: a browser plus WeChat plus NVIDIA Overlay eats 2 GB. That matters more
than any launch flag — see below.

**Not supported: 4 GB VRAM or CPU-only for SDXL.** It starts, but a single image takes
20+ minutes, which has no practical value.

Details for other GPUs, CUDA versions, OSes, ComfyUI versions and DSH versions:
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) (Chinese).

---

## Speed (measured on RTX 5060 Laptop, 8 GB)

Conditions: `832×1216`, SDXL 30 steps / cfg 5 / dpmpp_2m karras.

| Checkpoint | Warm image | First image (incl. load) | HiRes 1.5× (1248×1824) |
|---|---|---|---|
| Illustrious-XL | 26 s | 150 s | 62 s |
| **RealVisXL V5** | **26–31 s** | 150 s | **58 s** |
| Juggernaut XI v11 | 24–30 s | 150 s | 58 s |
| FLUX Krea Q2_K (24 steps) | 82 s | 240 s | — |

### Launch flags

```bat
main.py --listen 127.0.0.1 --port 8188 --cache-lru 8 --reserve-vram 0.3
```

Those four, nothing else. Why:

| Flag | Reason |
|---|---|
| `--cache-lru 8` | Cache node results. **Required** — the `--cache-none` default recomputes every node every time |
| `--reserve-vram 0.3` | Leave 300 MB for the desktop. 0.5 is too conservative and triggers dynamic VRAM loading; 0 OOMs on FLUX |
| ~~`--fast cublas_ops`~~ | **Don't.** With clean VRAM it is 3.5× slower (115 s vs 32 s) |
| ~~`--fast fp16_accumulation`~~ | **Don't.** 3.5× slower on its own (72–87 s vs 20 s) |
| ~~`--enable-triton-backend`~~ | **Don't.** Catastrophic — FLUX runs 178–295 s per step |
| ~~`--highvram`~~ | Don't. 8 GB cannot hold the 4.9 GB weights without thrashing |

The full investigation (which combination was faster, why triton made it worse, the real
baseline once the browser stopped eating 2 GB) is in
[docs/PERFORMANCE.md](docs/PERFORMANCE.md) (Chinese).

**The single most useful lesson**: when generation gets slow, check
`nvidia-smi` for `memory.free` first. 3.4 GB free versus 6.2 GB free is 142 seconds
versus 32 seconds — bigger than any flag you can change.

---

## The Denoise slider

Double-click `启动Denoise滑杆.bat`, open `http://127.0.0.1:8189`.

Range 0.05–1.00:

| denoise | Effect |
|---|---|
| 0.05–0.20 | Barely changes anything, just adds detail |
| 0.20–0.40 | Small edits (change expression, add accessory) |
| 0.40–0.55 | Conservative edit, identity preserved |
| 0.55–0.75 | Medium edit (**0.55 is the default**) |
| 0.75–0.88 | Large edit (visible repaint tops out around 0.8) |
| 0.88–0.97 | Aggressive, the face starts drifting |
| 0.97–1.00 | Basically only using the source for composition |

**Prompts must be English and tag-style**, not natural-language sentences. Measured on
the same image, seed and denoise:

```
Chinese:  keep this pose, same art style, same girl, change background to a sunny beach
          → background barely moved
English:  same pose, same art style, same girl, identical face,
          identical long silver hair, sunny beach background,
          bright daylight, clear sky                    → worked
```

SDXL's text encoder is trained on English tags; Chinese is close to noise. And write
**state tags** (`sunny beach`, `bright daylight`) rather than **motion instructions**
(`change the background to`) — the latter gets a weak response.

---

## Wiring into DSH

Requires the `dsh-image-gen` plugin (0.11.x).

```powershell
# writes the workflows into your profile config (backs it up first)
node .\dsh\apply-workflows.mjs
```

Then restart DSH, Settings → Plugins → Image generation:

- Provider: `comfyui`
- Base URL: `http://127.0.0.1:8188`

From then on `generate_image` / `edit_image` go local.

**One gotcha**: `dsh-image-gen`'s **Studio (image workbench) does not support ComfyUI.**
`comfyui` is missing from `CLOUD_IMAGE_PROVIDERS`, so Studio falls back to the first
cloud provider that has a key. Images made in Studio still go to the cloud.

Unaffected is the agent tool path: `generate_image`, `generate_images` and `edit_image`
fully support comfyui in the `generateSingle` / `editComfyUIImage` branches. So asking
the agent in chat goes local; clicking around in Studio still goes to the cloud.

### Switching checkpoints: the `dsh-comfy-models` plugin

`dsh-image-gen` can only pick a workflow — changing the model means hand-editing YAML
and restarting. This plugin covers that gap.

```powershell
powershell -ExecutionPolicy Bypass -File .\dsh\install-plugin.ps1
```

It copies `plugin/` into the profile, adds the dependency, and appends the registration
block. Idempotent, backs up every file it touches. Dry run with `-DryRun`.

Three tools:

| Tool | What it does |
|---|---|
| `comfy_models_list` | List every checkpoint ComfyUI sees, plus the active workflow |
| `comfy_models_sync` | Generate text-to-image / edit / HiRes workflows for any new checkpoint |
| `comfy_models_switch` | Switch with one word: `juggernaut`, `flux`, `realvis` all match |

Match order: exact → case-insensitive exact → prefix → substring, shortest name wins
at each tier (so `juggernaut` hits `Juggernaut-XI`, not `Juggernaut-XI-Edit`).

It edits the profile's `cordis.patch.yml`, which is watched by HMR — **changes take
effect in 10–15 seconds, no DSH restart**. Details: [plugin/README.md](plugin/README.md)
(Chinese).

---

## Safety and uninstall

- **No registry writes**, **no system service**, **no startup entry**
- Does not touch the GPU driver or install kernel drivers
- When not running: 0 processes, 0 VRAM, 0 CPU
- Uninstall: kill the python process, delete the folder

Ports bind to `127.0.0.1` only, so other machines on the LAN cannot reach them.

---

## Layout

```
ComfyUI-0.45.0/           ComfyUI source (v0.45.0, unmodified)
  models/checkpoints/     Illustrious-XL / RealVisXL-V5.0 / Juggernaut-XI-v11
  models/diffusion_models/ flux1-krea-dev-Q2_K.gguf
  models/text_encoders/   t5-v1_1-xxl-Q4_K_S.gguf + clip_l.safetensors
  models/vae/             flux_ae.safetensors
  models/upscale_models/  4x-UltraSharp.pth
  custom_nodes/ComfyUI-GGUF/   FLUX GGUF loader
  input/                  uploaded source images
  output/                 generated images
  main.py
python-base/              standalone Python 3.12 (whole folder is movable)
venv/                     Python environment
slider/
  server.mjs              zero-dependency HTTP service
  index.html              the slider page
  cli.mjs                 CLI entry
dsh/
  workflows/              workflow JSON (4 checkpoints × t2i / edit / HiRes)
  workflows.manifest.json metadata + preset prompts
  apply-workflows.mjs     writes into cordis.patch.yml
  export-from-profile.mjs reverse-exports from a live profile
  install-plugin.ps1      installs the checkpoint-switcher plugin
plugin/                   dsh-comfy-models (lib/catalog.js etc.)
scripts/
  fetch_parts.sh          resumable downloader (magic-number checked)
  bench_final.py          benchmark
  pack-release.ps1        builds the release zip via git archive
docs/
  INSTALL-QUICK.md        step-by-step install + troubleshooting
  AGENT-PROMPT.md         paste into an AI to have it install
  why-local.md            why local / cost comparison
  MODELS.md               four checkpoints measured side by side
  PERFORMANCE.md          launch-flag tuning and VRAM contention
  COMPATIBILITY.md        GPU / driver / OS / version matrix
启动ComfyUI.bat           start ComfyUI (warns if already running)
启动Denoise滑杆.bat       start the slider page
install.ps1               one-command install
CHANGELOG.md              version history
```

---

## FAQ

**Q: `Could not connect to ComfyUI at http://127.0.0.1:8188`**
ComfyUI is not running. `dsh-image-gen` has no provider fallback — it throws instead of
silently going to the cloud. Double-click `启动ComfyUI.bat`.

**Q: `You need pytorch with cu130 or higher`**
Wrong torch build. RTX 50 series (Blackwell / sm_120) requires cu130:
```powershell
.\venv\Scripts\pip.exe install --no-deps --force-reinstall "https://mirrors.aliyun.com/pytorch-wheels/cu130/torch-2.9.0%2Bcu130-cp312-cp312-win_amd64.whl"
```

**Q: pip downgraded torch to a CPU build**
`pip install -r requirements.txt` reinstalls torch. Always verify afterwards:
```powershell
.\venv\Scripts\python.exe -c "import torch;print(torch.__version__, torch.cuda.is_available())"
```
It must print `2.9.0+cu130 True`.

**Q: A single image takes 200+ seconds**
Check `nvidia-smi` for `memory.free` first. Below 4 GB means something else is holding
VRAM — close the browser and WeChat. Then confirm the launch flags are **only**
`--cache-lru 8 --reserve-vram 0.3`; adding `--fast` or `--enable-triton-backend` makes
it an order of magnitude slower. See [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

**Q: Every face comes out covered in freckles and spots**
The prompt says `freckles`. Remove it and add spot words to the negative
(`freckles, moles, birthmark, blemishes, skin spots, acne, large pores...`).
Not a model defect — see section 4 of [docs/MODELS.md](docs/MODELS.md).

**Q: The photoreal model looks like a studio photoshoot, not a real person**
`masterpiece, best quality, 8k` pushes a photoreal model toward airbrushed beauty
retouching. For a candid feel write `amateur snapshot, taken on iPhone, unedited, grain`.
Keep cfg at 5, not 7.

**Q: I want a different model**
Any SDXL checkpoint works — drop it in `models/checkpoints/` and run
`comfy_models_sync` to generate workflows automatically. FLUX needs GGUF quantization
plus the ComfyUI-GGUF nodes; on 8 GB only Q2_K runs and it adds skin artifacts. See
[docs/MODELS.md](docs/MODELS.md).

**Q: The model file size is exactly right but loading fails with `GGUF magic invalid`**
hf-mirror writes its rate-limit HTML page into the target file, and the byte count
matches exactly. Use `scripts/fetch_parts.sh` — it validates the HTTP 206 status, each
part's byte count, and the file magic number.

---

## License

Scripts and the slider page in this repo: MIT.

ComfyUI source: GPL-3.0, from [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI).

Model weights keep their own licenses (see each repo): Illustrious-XL v1.1
(non-commercial), RealVisXL V5.0, Juggernaut XI v11, FLUX.1 Krea dev (non-commercial).
No weights are included here; the installer only points at download locations.
