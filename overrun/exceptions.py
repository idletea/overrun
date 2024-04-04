from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TargetErrors(Exception):
    invalid_target_messages: list[str] = field(default_factory=list)
    target_name_conflicts: list[str] = field(default_factory=list)
