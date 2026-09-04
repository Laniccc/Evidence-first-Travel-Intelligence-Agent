"""Reproducibility metadata, without credentials or host-specific paths."""
from hashlib import sha256
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def runtime_metadata(*, embedding_model=None, llm_model=None):
    def installed(name):
        try:
            return version(name)
        except PackageNotFoundError:
            return "unavailable"
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                         stderr=subprocess.DEVNULL, timeout=5, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT,
                     stderr=subprocess.DEVNULL, timeout=5, text=True).strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = "unavailable", None
    lock = ROOT / "infra/baidu-mcp/package-lock.json"
    server = json.loads(lock.read_text(encoding="utf-8"))["packages"]["node_modules/@baidumap/mcp-server-baidu-map"]["version"] if lock.exists() else "unavailable"
    return {"git_commit": commit, "working_tree_dirty": dirty, "mcp_sdk_version": installed("mcp"),
        "baidu_server_locked_version": server, "embedding_model": embedding_model, "llm_model": llm_model,
        "dataset_hashes": {p.name: sha256(p.read_bytes()).hexdigest()
                           for p in sorted((Path(__file__).parent / "datasets").glob("*.jsonl"))}}
