"""最终配置现场复测：SDXL 30 步 / FLUX 24 步，热态。"""
import json, time, urllib.request

BASE = "http://127.0.0.1:8188"


def post(g):
    req = urllib.request.Request(
        BASE + "/prompt",
        data=json.dumps({"prompt": g, "client_id": "bench"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req).read())["prompt_id"]


def wait(pid, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(urllib.request.urlopen(BASE + f"/history/{pid}").read())
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed") or st.get("status_str") == "success":
                return time.time() - t0
        time.sleep(0.5)
    raise TimeoutError(pid)


POS = "RAW photo, portrait of a young woman with fair clean skin, soft window light, 85mm f/1.8, photorealistic, high detail"
NEG = (
    "freckles, moles, birthmark, blemishes, skin spots, dark spots, acne, pimples, "
    "blotchy skin, uneven skin tone, textured skin, visible pores, wrinkles, "
    "cartoon, anime, illustration, painting, 3d render, cgi, plastic skin, airbrushed, "
    "deformed, bad anatomy, bad hands, extra fingers, blurry, lowres, watermark, text"
)


def sdxl(seed=1, steps=30, prefix="bench_sdxl"):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "RealVisXL_V5.0_fp16.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": POS, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": 5.0,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras",
                         "denoise": 1, "model": ["1", 0], "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
    }


def flux(seed=1, steps=24, prefix="bench_flux"):
    return {
        "1": {"class_type": "UnetLoaderGGUF",
              "inputs": {"unet_name": "flux1-krea-dev-Q2_K.gguf"}},
        "2": {"class_type": "DualCLIPLoaderGGUF",
              "inputs": {"clip_name1": "clip_l.safetensors",
                         "clip_name2": "t5-v1_1-xxl-encoder-Q4_K_S.gguf", "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux_ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": POS, "clip": ["2", 0]}},
        "6": {"class_type": "FluxGuidance", "inputs": {"guidance": 3.5, "conditioning": ["4", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": 1.0,
                         "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1, "model": ["1", 0], "positive": ["6", 0],
                         "negative": ["5", 0], "latent_image": ["7", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage",
               "inputs": {"filename_prefix": prefix, "images": ["9", 0]}},
    }


if __name__ == "__main__":
    print("== SDXL RealVisXL-V5 832x1216 30步 cfg5 (warm)")
    for i in range(2):
        t = wait(post(sdxl(seed=100 + i)))
        print(f"  run{i+1}: {t:.1f}s")

    print("== FLUX Krea Q2_K 832x1216 24步 (warm, 首张含加载)")
    for i in range(2):
        t = wait(post(flux(seed=200 + i)), timeout=2400)
        print(f"  run{i+1}: {t:.1f}s")
