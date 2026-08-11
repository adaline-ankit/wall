from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wall_harness.models import WallSpec
from wall_harness.spec import load_spec


@dataclass(frozen=True)
class WallRecord:
    path: Path
    spec: WallSpec


class WallWorkspace:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"Wall workspace not found: {self.path}")

    @property
    def root(self) -> Path:
        return self.path if self.path.is_dir() else self.path.parent

    def records(self) -> list[WallRecord]:
        paths = (
            sorted([*self.path.glob("*.yaml"), *self.path.glob("*.yml")])
            if self.path.is_dir()
            else [self.path]
        )
        if not paths:
            raise ValueError(f"No WallSpec YAML files found in {self.path}")
        records = [WallRecord(path=path, spec=load_spec(path)) for path in paths]
        names = [record.spec.name for record in records]
        if len(names) != len(set(names)):
            raise ValueError("Every WallSpec in a workspace must have a unique name")
        return records

    def resolve(self, name: str | None = None) -> WallRecord:
        records = self.records()
        if name is None:
            return records[0]
        try:
            return next(record for record in records if record.spec.name == name)
        except StopIteration as exc:
            raise KeyError(name) from exc
