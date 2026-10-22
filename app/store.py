"""
app/store.py  -  JSON persistence for remotes.

Schema (backward-compatible with the Android app):
{ "notes": str, "keys": {KEY: code_object}, "macros": {NAME: str} }
code_object: proto, name, addr, cmd, khz, raw, note (unknown fields preserved).
Migration: plain {KEY: code} files (v0) are wrapped in {"keys": ...}.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DIR = Path(__file__).parent.parent / "remotes"


def _safe_name(name: str) -> str:
    return "".join(c for c in name.strip() if c.isalnum() or c in " _-")


def _key_name(text: str) -> str:
    return text.strip().upper().replace(" ", "_")


class Store:
    def __init__(self, directory: Optional[Path] = None):
        self.dir = directory or _DEFAULT_DIR
        self.dir.mkdir(exist_ok=True)

    def path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def names(self) -> List[str]:
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def exists(self, name: str) -> bool:
        return self.path(name).exists()

    def load(self, name: str) -> Dict[str, Any]:
        return self.normalize(json.loads(self.path(name).read_text(encoding="utf-8")))

    @staticmethod
    def normalize(raw: Any) -> Dict[str, Any]:
        """Canonical schema for parsed JSON; raises ValueError if it is unusable.

        Migrates v0 files, drops entries that are not key objects, keeps unknown fields."""
        if not isinstance(raw, dict):
            raise ValueError("the top level must be an object")
        if "keys" not in raw:
            raw = {"keys": raw}
        if not isinstance(raw["keys"], dict):
            raise ValueError('"keys" must be an object')
        raw["keys"] = {str(k): v for k, v in raw["keys"].items() if isinstance(v, dict)}
        if not isinstance(raw.get("notes"), str):
            raw["notes"] = ""
        macros = raw.get("macros")
        raw["macros"] = ({str(k): v for k, v in macros.items() if isinstance(v, str)}
                         if isinstance(macros, dict) else {})
        return raw

    def save(self, name: str, data: Dict[str, Any]) -> None:
        self.path(name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def create(self, name: str) -> None:
        self.save(name, {"notes": "", "keys": {}, "macros": {}})

    def delete(self, name: str) -> None:
        self.path(name).unlink(missing_ok=True)

    def rename(self, old: str, new_name: str) -> None:
        self.path(old).rename(self.path(new_name))

    def duplicate(self, src: str, dst: str) -> None:
        shutil.copy(self.path(src), self.path(dst))

    @staticmethod
    def safe_name(text: str) -> str:
        return _safe_name(text)

    @staticmethod
    def key_name(text: str) -> str:
        return _key_name(text)

    @staticmethod
    def code_summary(code: Dict[str, Any]) -> str:
        return (f"Protocol {code.get('name', 'RAW')}, address {code.get('addr', '-')}, "
                f"command {code.get('cmd', '-')}\n"
                f"{len(code.get('raw', []))} pulses at {code.get('khz', 38)} kHz")
