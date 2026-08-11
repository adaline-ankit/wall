from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import WallSpec


def load_spec(path: Path) -> WallSpec:
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("WallSpec must be a YAML object")
    return WallSpec.model_validate(raw)


def dump_spec(spec: WallSpec) -> str:
    dumped: str = yaml.safe_dump(spec.model_dump(mode="json", exclude_none=True), sort_keys=False)
    return dumped
