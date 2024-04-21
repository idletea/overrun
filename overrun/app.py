from __future__ import annotations

from dataclasses import dataclass, field
from overrun.config import Config, ConfigFailed


@dataclass
class AppBuilder:
    config: Config | ConfigFailed = field(default_factory=Config.attempt_init)
