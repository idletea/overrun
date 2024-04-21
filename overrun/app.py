from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, field
from typing import BinaryIO
import rich
import tomli_w
from rich.table import Table
from overrun.config import Config, ConfigFailed

TAB = "    "


@dataclass
class AppBuilder:
    config: Config | ConfigFailed = field(default_factory=Config.attempt_init)

    def doctor(self):
        # config info or config fail reason
        table = Table(box=None, pad_edge=False, show_header=False)
        if isinstance(self.config, Config):
            table.add_row("[bold]currently usable", "[green]True")
        else:
            table.add_row("[bold]currently usable", "[red]False")
            table.add_row("[bold]reason", self.config.cause)
        rich.print(table)

        # dirs we'd use to locate resources
        if isinstance(self.config, Config):
            rich.print("\n[bold]dirs")
            table = Table(box=None, pad_edge=False, show_header=False)
            table.add_row(
                f"{TAB}[bold]current project",
                f"[magenta]{self.config.current_working_project}",
            )

            if self.config.sibling_projects:
                table.add_row(
                    f"{TAB}[bold]sibling projects",
                )
                for sibling in self.config.sibling_projects:
                    table.add_row("", f"[magenta]{sibling}")
            else:
                table.add_row(f"{TAB}[bold]sibling projects", "[#999999]<none>")

            rich.print(table)

        buffer = io.BytesIO()
        rich.print("\n[bold]config")
        self.dump_config(write_to=buffer)
        buffer.seek(0, 0)
        for line in buffer.readlines():
            sys.stdout.write(f"{TAB}{line.decode('utf-8')}")

    def dump_config(self, write_to: BinaryIO | None = None):
        output = write_to if write_to else sys.stdout.buffer
        options = self.config.options

        if options:
            # the json roundtrip serializes things to strings the tomllib refuses to
            toml = tomli_w.dumps(json.loads(options.model_dump_json()))
            output.write(toml.encode("utf-8"))
        else:
            output.write(b"<could not load a valid config>")
