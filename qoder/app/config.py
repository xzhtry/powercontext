"""Application configuration and runtime path selection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "app" / "static"
DOCS_DIR = ROOT / "docs"


def _default_runtime() -> Path:
    override = os.environ.get("RT_RUNTIME")
    if override:
        # Do not call resolve(): a caller may deliberately use an ASCII junction
        # to keep native seekdb away from non-ASCII paths. resolve() would turn
        # that junction back into the underlying Unicode path.
        runtime = Path(override).expanduser()
        return runtime if runtime.is_absolute() else (ROOT / runtime).absolute()
    # Native seekdb builds on Windows are happier with an ASCII-only path.
    # Keep runtime data outside a repository whose path contains non-ASCII
    # characters, while still defaulting to the repository for normal clones.
    if any(ord(char) > 127 for char in str(ROOT)):
        return Path.home() / "ResearchThread"
    return ROOT / "runtime"


@dataclass(frozen=True)
class Settings:
    root: Path
    runtime: Path
    data_dir: Path
    static_dir: Path
    seekdb_base: Path
    seekdb_port: int
    powercontext_home: Path
    powercontext_port: int
    powercontext_url: str
    host: str
    port: int
    seed_demo: bool
    autostart: bool
    session_file: Path
    scope_file: Path

    @property
    def seekdb_store(self) -> Path:
        return self.seekdb_base / "store"

    @property
    def powercontext_db(self) -> Path:
        return self.powercontext_home / "powercontext.db"

    def ensure_directories(self) -> None:
        for path in (
            self.runtime,
            self.seekdb_base / "etc",
            self.seekdb_base / "log",
            self.seekdb_base / "run",
            self.seekdb_store,
            self.powercontext_home,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    runtime = _default_runtime()
    seekdb_port = int(os.environ.get("RT_SEEKDB_PORT", "18881"))
    powercontext_port = int(os.environ.get("RT_PC_PORT", "18765"))
    return Settings(
        root=ROOT,
        runtime=runtime,
        data_dir=DATA_DIR,
        static_dir=STATIC_DIR,
        seekdb_base=runtime / "seekdb-server",
        seekdb_port=seekdb_port,
        powercontext_home=runtime / "powercontext",
        powercontext_port=powercontext_port,
        powercontext_url=os.environ.get(
            "RT_PC_URL", f"http://127.0.0.1:{powercontext_port}"
        ).rstrip("/"),
        host=os.environ.get("RT_HOST", "127.0.0.1"),
        port=int(os.environ.get("RT_PORT", "8787")),
        seed_demo=os.environ.get("RT_SEED_DEMO", "1") != "0",
        autostart=os.environ.get("RT_AUTOSTART", "1") != "0",
        session_file=runtime / "session.json",
        scope_file=runtime / "powercontext-scope.json",
    )
