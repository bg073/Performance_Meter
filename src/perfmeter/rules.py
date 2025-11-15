from dataclasses import dataclass, field
from pathlib import Path
from typing import Set


@dataclass
class Rules:
    exclude_apps: Set[str] = field(default_factory=set)
    include_apps: Set[str] = field(default_factory=set)

    def is_app_metrics_allowed(self, exe_name: str) -> bool:
        name = (exe_name or '').lower()
        if self.include_apps:
            return name in self.include_apps
        if name in self.exclude_apps:
            return False
        return True


def load_rules(path: Path) -> Rules:
    exclude: Set[str] = set()
    include: Set[str] = set()
    section = None
    if not path.exists():
        return Rules()
    for raw in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.lower() == '[exclude_apps]':
            section = 'exclude'
            continue
        if line.lower() == '[include_apps]':
            section = 'include'
            continue
        if section == 'exclude':
            exclude.add(line.lower())
        elif section == 'include':
            include.add(line.lower())
    return Rules(exclude_apps=exclude, include_apps=include)
