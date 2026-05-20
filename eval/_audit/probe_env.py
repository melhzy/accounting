"""Probe the active Python env for fine-tuning readiness."""
import sys
import platform

print("python      :", platform.python_version())
print("executable  :", sys.executable)
try:
    import torch
    print("torch       :", torch.__version__)
    print("cuda_avail  :", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("cuda_version:", torch.version.cuda)
        for i in range(torch.cuda.device_count()):
            p = torch.cuda.get_device_properties(i)
            print(f"gpu[{i}]      : {p.name}, {p.total_memory/1024**3:.1f} GB, sm_{p.major}{p.minor}")
except Exception as e:
    print("torch       : FAIL -", e)

for mod in ("unsloth", "transformers", "peft", "trl", "bitsandbytes",
            "accelerate", "datasets", "vllm", "tiktoken", "seedhash",
            "openpyxl", "docx", "xformers"):
    try:
        m = __import__(mod)
        v = getattr(m, "__version__", "installed")
        print(f"{mod:13s}:", v)
    except ImportError:
        print(f"{mod:13s}: -")
    except Exception as e:
        print(f"{mod:13s}: ERROR {type(e).__name__}: {e}")
