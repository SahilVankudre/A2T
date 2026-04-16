"""
VoxScript POC — Environment Verification
Run this after setup to confirm everything works.

Usage:
    python verify_setup.py
"""

import sys
import subprocess
import importlib


def check(name: str, fn):
    try:
        result = fn()
        print(f"  [OK]  {name}: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False


def main():
    print("\n" + "=" * 60)
    print("  VoxScript POC — Environment Verification")
    print("=" * 60 + "\n")

    results = []

    # ── Python ────────────────────────────────────
    print("1. Python")
    results.append(check("Version", lambda: sys.version.split()[0]))

    # ── PyTorch + CUDA ────────────────────────────
    print("\n2. PyTorch + CUDA")
    results.append(check("PyTorch", lambda: importlib.import_module("torch").__version__))

    import torch
    results.append(check("CUDA available", lambda: f"{torch.cuda.is_available()}"))
    if torch.cuda.is_available():
        results.append(check("GPU name", lambda: torch.cuda.get_device_name(0)))
        results.append(check("VRAM", lambda: f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"))
        results.append(check("CUDA version", lambda: torch.version.cuda))
    else:
        print("  [WARN] No CUDA — will use CPU (much slower)")

    # ── faster-whisper ────────────────────────────
    print("\n3. faster-whisper")
    results.append(check("Version", lambda: importlib.import_module("faster_whisper").__version__))

    # ── FastAPI stack ─────────────────────────────
    print("\n4. FastAPI stack")
    results.append(check("FastAPI", lambda: importlib.import_module("fastapi").__version__))
    results.append(check("SQLAlchemy", lambda: importlib.import_module("sqlalchemy").__version__))
    results.append(check("asyncpg", lambda: importlib.import_module("asyncpg").__version__))
    results.append(check("Alembic", lambda: importlib.import_module("alembic").__version__))
    results.append(check("Pydantic", lambda: importlib.import_module("pydantic").__version__))

    # ── ffmpeg ────────────────────────────────────
    print("\n5. System tools")
    def check_ffmpeg():
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5, shell=True)
        return r.stdout.split("\n")[0].split(" ")[2] if r.returncode == 0 else "NOT FOUND"
    results.append(check("ffmpeg", check_ffmpeg))

    def check_ffprobe():
        r = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=5, shell=True)
        return "OK" if r.returncode == 0 else "NOT FOUND"
    results.append(check("ffprobe", check_ffprobe))

    # ── PostgreSQL ────────────────────────────────
    print("\n6. PostgreSQL")
    def check_psql():
        r = subprocess.run(["psql", "--version"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else "NOT FOUND"
    results.append(check("psql client", check_psql))

    def check_pg_connection():
        r = subprocess.run(
            ["psql", "-U", "voxscript", "-d", "voxscript", "-c", "SELECT 1;", "-t", "-A"],
            capture_output=True, text=True, timeout=5,
            env={**__import__("os").environ, "PGPASSWORD": "voxscript"},
        )
        if r.returncode == 0 and "1" in r.stdout:
            return "Connected successfully"
        return f"FAILED: {r.stderr.strip()}"
    results.append(check("Database connection", check_pg_connection))

    # ── Node.js ───────────────────────────────────
    print("\n7. Node.js")
    def check_node():
        r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else "NOT FOUND"
    results.append(check("Node.js", check_node))

    def check_npm():
        r = subprocess.run(["npm", "--version"], capture_output=True, text=True, timeout=5, shell=True)
        return r.stdout.strip() if r.returncode == 0 else "NOT FOUND"
    results.append(check("npm", check_npm))

    # ── Model test (optional, slow) ───────────────
    print("\n8. ASR model test")
    if torch.cuda.is_available():
        def test_model():
            from faster_whisper import WhisperModel
            model = WhisperModel("large-v3-turbo", device="cuda", compute_type="int8_float16")
            vram = torch.cuda.memory_allocated() / 1024**3
            del model
            torch.cuda.empty_cache()
            return f"Loaded OK ({vram:.1f} GB VRAM used)"
        print("  Loading model (this takes 10-30 seconds on first run)...")
        results.append(check("large-v3-turbo (int8_float16)", test_model))
    else:
        print("  [SKIP] No CUDA available, skipping model load test")

    # ── Summary ───────────────────────────────────
    passed = sum(1 for r in results if r)
    failed = len(results) - passed

    print("\n" + "=" * 60)
    if failed == 0:
        print(f"  ALL {passed} CHECKS PASSED — ready to start development!")
    else:
        print(f"  {passed} passed, {failed} FAILED — fix the issues above")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()