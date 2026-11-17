"""查任意一张 ComfyUI 出图到底是哪条工作流 / 哪个底模生成的。

ComfyUI 把整张工作流塞进 PNG 的 tEXt 块里，所以不用信卡片上的字，
直接读文件本身。

    python scripts/which_workflow.py                      # 最近 8 张 dsh-* 
    python scripts/which_workflow.py path/to/a.png ...    # 指定文件
"""

import glob
import json
import os
import sys

from PIL import Image

OUT = os.environ.get("COMFYUI_OUTPUT") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "ComfyUI-0.45.0", "output")
OUT = os.path.normpath(OUT)


def describe(path):
    im = Image.open(path)
    meta = getattr(im, "text", {}) or {}
    raw = meta.get("prompt") or meta.get("workflow")
    if not raw:
        return {"file": os.path.basename(path), "size": im.size, "error": "no embedded workflow"}

    graph = json.loads(raw)
    nodes = graph if isinstance(graph, dict) and "1" in graph and isinstance(graph.get("1"), dict) else None
    if nodes is None:
        # UI 格式（nodes 数组）
        flat = {}
        for n in graph.get("nodes", []):
            flat[str(n.get("id"))] = {"class_type": n.get("type"), "inputs": {}}
            for k, v in zip(n.get("inputs", []), n.get("widgets_values") or []):
                flat[str(n["id"])]["inputs"][k] = v
        nodes = flat

    info = {"file": os.path.basename(path), "size": im.size, "ckpt": None, "steps": [], "loras": [], "prefix": None}
    for node in nodes.values():
        cls = node.get("class_type")
        inp = node.get("inputs") or {}
        if cls == "CheckpointLoaderSimple":
            info["ckpt"] = inp.get("ckpt_name")
        elif cls == "KSampler":
            info["steps"].append(f"{inp.get('steps')}步 cfg{inp.get('cfg')} {inp.get('sampler_name')}/{inp.get('scheduler')} denoise{inp.get('denoise')}")
        elif cls == "LoraLoader":
            info["loras"].append(f"{inp.get('lora_name')}@{inp.get('strength_model')}")
        elif cls == "IPAdapterUnifiedLoaderFaceID":
            info["loras"].append(f"FaceID {inp.get('preset')} lora{inp.get('lora_strength')}")
        elif cls == "SaveImage":
            info["prefix"] = inp.get("filename_prefix")
    return info


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if argv:
        files = argv
    else:
        files = sorted(glob.glob(os.path.join(OUT, "dsh-*.png")), key=os.path.getmtime)[-8:]
    for f in files:
        d = describe(f)
        if "error" in d:
            print(f"{d['file']:34s} {d['size'][0]}x{d['size'][1]}  <{d['error']}>")
            continue
        print(f"{d['file']:34s} {d['size'][0]}x{d['size'][1]}")
        print(f"  底模    {d['ckpt']}")
        print(f"  采样    {' | '.join(d['steps'])}")
        if d["loras"]:
            print(f"  附加    {', '.join(d['loras'])}")
        print(f"  前缀    {d['prefix']}")


if __name__ == "__main__":
    main(sys.argv[1:])
