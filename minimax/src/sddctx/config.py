"""运行路径与配置。

所有可写状态（seekdb 数据目录、PowerContext 数据、日志）默认放在
``minimax/runtime`` 下；在 WSL 的 /mnt/* 路径上 seekdb 无法打开数据库，
因此检测到 drvfs 路径时自动退回到 ``$HOME/.local/share/sddctx``。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEMO_APP = PACKAGE_ROOT / "demo_app"
SAMPLES = PACKAGE_ROOT / "samples"
EVIDENCE = PACKAGE_ROOT / "evidence"
DEFAULT_PC_URL = "http://127.0.0.1:8765"


def _is_drvfs(path: Path) -> bool:
    return str(path).startswith("/mnt/")


def default_runtime() -> Path:
    override = os.environ.get("SDDCTX_RUNTIME")
    if override:
        return Path(override).expanduser().resolve()
    candidate = (PACKAGE_ROOT / "runtime").resolve()
    if _is_drvfs(candidate):
        # seekdb 的嵌入式引擎不支持 drvfs（/mnt/c、/mnt/d）上的文件布局。
        return Path.home() / ".local" / "share" / "sddctx"
    return candidate


@dataclass(frozen=True)
class Settings:
    runtime: Path
    db_path: Path
    powercontext_url: str
    scope_file: Path

    @property
    def state_dir(self) -> Path:
        return self.runtime / "state"

    @property
    def work_dir(self) -> Path:
        return self.runtime / "work"


def load_settings() -> Settings:
    runtime = default_runtime()
    return Settings(
        runtime=runtime,
        db_path=runtime / "seekdb",
        powercontext_url=os.environ.get("POWERCONTEXT_URL", DEFAULT_PC_URL).rstrip("/"),
        scope_file=runtime / "powercontext-scope.json",
    )


def ensure_runtime(settings: Settings) -> None:
    settings.runtime.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    settings.work_dir.mkdir(parents=True, exist_ok=True)
