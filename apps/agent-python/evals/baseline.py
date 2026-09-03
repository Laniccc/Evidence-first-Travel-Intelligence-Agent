"""Capture a reproducible test and code-size baseline for consolidation work."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = AGENT_ROOT.parent


def _python_stats(root: Path) -> dict[str, int]:
    files = [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]
    line_count = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in files)
    return {"files": len(files), "lines": line_count}


def _run(
    name: str,
    command: list[str],
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
    display_command: list[str] | None = None,
) -> dict:
    started = time.perf_counter()
    env = os.environ.copy()
    env.update(extra_env or {})
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return {
        "name": name,
        "command": display_command or command,
        "exit_code": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "output_tail": combined[-4000:],
    }


def _common_checkout_root() -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=AGENT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    common_dir = Path(completed.stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (AGENT_ROOT / common_dir).resolve()
    return common_dir.parent


def capture() -> dict:
    mvn = shutil.which("mvn.cmd") or shutil.which("mvn") or "mvn"
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    node = shutil.which("node.exe") or shutil.which("node") or "node"
    offline_env = {"DEEPSEEK_API_KEY": "offline-baseline-key"}
    common_checkout = _common_checkout_root()
    shared_web = common_checkout / "apps" / "web"
    shared_vite = shared_web / "node_modules" / "vite" / "bin" / "vite.js"
    local_vite = APPS_ROOT / "web" / "node_modules" / "vite" / "bin" / "vite.js"
    if local_vite.exists() or not shared_vite.exists():
        web_command = [npm, "run", "build"]
    else:
        web_command = [
            node,
            str(shared_vite),
            "build",
            str(APPS_ROOT / "web"),
            "--config",
            str(shared_web / "vite.config.js"),
        ]
    commands = [
        _run(
            "python_tests",
            [sys.executable, "-m", "pytest", "-q"],
            AGENT_ROOT,
            extra_env=offline_env,
            display_command=["python", "-m", "pytest", "-q"],
        ),
        _run(
            "java_tests",
            [mvn, "test", "-q"],
            APPS_ROOT / "api-java",
            display_command=["mvn", "test", "-q"],
        ),
        _run(
            "web_build",
            web_command,
            APPS_ROOT / "web",
            display_command=["npm", "run", "build"],
        ),
    ]
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "scope": {
            "supported": ["fact_query", "suitability", "comparison", "clarification"],
            "retired": [
                "itinerary",
                "nearby",
                "crowd_estimation",
                "review_crawler",
                "ticket_crawler",
            ],
        },
        "code_size": {
            "app": _python_stats(AGENT_ROOT / "app"),
            "tests": _python_stats(AGENT_ROOT / "tests"),
        },
        "commands": commands,
        "all_commands_passed": all(command["exit_code"] == 0 for command in commands),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = capture()
    output = args.output if args.output.is_absolute() else AGENT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0 if report["all_commands_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
