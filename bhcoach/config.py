"""설정 로드 (config.json, 없으면 기본값)"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_PATH = Path("config.json")


def _default_replay_dir() -> str:
    return str(Path.home() / "Documents" / "StarCraft" / "Maps" / "Replays")


@dataclass
class Config:
    my_name: str = "KIMCHI2022"
    replay_dir: str = field(default_factory=_default_replay_dir)
    screp_path: str = "bin/screp.exe"
    db_path: str = "data/bhcoach.db"
    report_dir: str = "reports"
    # 맵 이름에 포함되면 빅헌터로 판정 (대소문자 무시)
    map_keywords: list[str] = field(default_factory=lambda: ["big hunters", "빅헌"])
    # 승/패 비교 리포트를 켜는 최소 경기 수
    min_games_for_compare: int = 30
    watch_interval_sec: float = 5.0
    open_browser: bool = True

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
