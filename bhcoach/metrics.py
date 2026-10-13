"""리플레이 명령 기록 → 플레이어별 빌드 지표

주의: 리플레이에는 '명령'만 기록되므로 자원 부족으로 실패한 건설 명령도 포함된다.
따라서 모든 지표는 '지시 시점' 기준 근사치다.
"""
from __future__ import annotations

FRAME_SEC = 0.042  # Fastest 속도 기준 1프레임 = 42ms

# (지표 키, 명령 종류, 대상 이름) - 처음 등장한 시각(초)을 기록
FIRST_EVENTS: dict[str, list[tuple[str, str, str]]] = {
    "Protoss": [
        ("forge", "build", "Forge"),
        ("gateway", "build", "Gateway"),
        ("cannon", "build", "Photon Cannon"),
        ("core", "build", "Cybernetics Core"),
        ("nexus2", "build", "Nexus"),
        ("stargate", "build", "Stargate"),
        ("robo", "build", "Robotics Facility"),
        ("citadel", "build", "Citadel of Adun"),
        ("archives", "build", "Templar Archives"),
        ("corsair", "unit", "Corsair"),
        ("observer", "unit", "Observer"),
        ("reaver", "unit", "Reaver"),
        ("dt", "unit", "Dark Templar"),
        ("ht", "unit", "High Templar"),
    ],
    "Zerg": [
        ("pool", "build", "Spawning Pool"),
        ("hatch2", "build", "Hatchery"),
        ("extractor", "build", "Extractor"),
        ("lair", "unit", "Lair"),
        ("hydra_den", "build", "Hydralisk Den"),
        ("spire", "build", "Spire"),
        ("hive", "unit", "Hive"),
        ("zergling", "unit", "Zergling"),
        ("mutal", "unit", "Mutalisk"),
        ("scourge", "unit", "Scourge"),
        ("lurker", "unit", "Lurker"),
    ],
    "Terran": [
        ("barracks", "build", "Barracks"),
        ("factory", "build", "Factory"),
        ("starport", "build", "Starport"),
        ("cc2", "build", "Command Center"),
    ],
}

# (지표 키, 건물 이름, 기준 분) - 해당 시각까지 지은 건물 수 (같은 위치 중복 제거)
COUNT_EVENTS: dict[str, list[tuple[str, str, int]]] = {
    "Protoss": [
        ("cannon@3", "Photon Cannon", 3),
        ("cannon@5", "Photon Cannon", 5),
        ("cannon@8", "Photon Cannon", 8),
        ("gateway@6", "Gateway", 6),
        ("stargate@10", "Stargate", 10),
    ],
    "Zerg": [
        ("creep@5", "Creep Colony", 5),
        ("creep@8", "Creep Colony", 8),
        ("hatch@6", "Hatchery", 6),
    ],
    "Terran": [],
}

LABELS = {
    "forge": "포지", "gateway": "게이트웨이", "cannon": "첫 캐논", "core": "코어",
    "nexus2": "2넥서스", "stargate": "스타게이트", "robo": "로보틱스", "citadel": "시타델",
    "archives": "아카이브", "corsair": "첫 커세어", "observer": "첫 옵저버", "reaver": "첫 리버",
    "dt": "첫 다크", "ht": "첫 하이템플러",
    "pool": "스포닝풀", "hatch2": "2해처리", "extractor": "익스트랙터", "lair": "레어",
    "hydra_den": "히드라덴", "spire": "스파이어", "hive": "하이브", "zergling": "첫 저글링",
    "mutal": "첫 뮤탈", "scourge": "첫 스커지", "lurker": "첫 럴커",
    "barracks": "배럭", "factory": "팩토리", "starport": "스타포트", "cc2": "2커맨드",
    "cannon@3": "캐논 수 @3분", "cannon@5": "캐논 수 @5분", "cannon@8": "캐논 수 @8분",
    "gateway@6": "게이트 수 @6분", "stargate@10": "스타게이트 수 @10분",
    "creep@5": "크립 수 @5분", "creep@8": "크립 수 @8분", "hatch@6": "추가 해처리 수 @6분",
}

_UNIT_CMD_TYPES = {"Train", "Unit Morph", "Building Morph", "Train Fighter"}


def fmt_time(sec: float | None) -> str:
    if sec is None:
        return "-"
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


def _target_name(cmd: dict) -> str | None:
    return (cmd.get("Unit") or {}).get("Name")


def _player_events(cmds: list[dict], pid: int) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(건설 이벤트, 유닛/변태 이벤트) - 건설은 같은 건물·같은 타일 반복 지시를 1회로 합침"""
    seen: set[tuple[str, int, int]] = set()
    builds, units = [], []
    for c in cmds:
        if c["PlayerID"] != pid:
            continue
        ctype = c["Type"]["Name"]
        name = _target_name(c)
        if not name:
            continue
        if ctype == "Build":
            pos = c.get("Pos") or {}
            key = (name, pos.get("X", -1), pos.get("Y", -1))
            if key in seen:
                continue
            seen.add(key)
            builds.append((c["Frame"], name))
        elif ctype in _UNIT_CMD_TYPES:
            units.append((c["Frame"], name))
    return builds, units


def extract_player_metrics(cmds: list[dict], pid: int, race: str) -> dict[str, float | int | None]:
    builds, units = _player_events(cmds, pid)
    metrics: dict[str, float | int | None] = {}

    for key, kind, name in FIRST_EVENTS.get(race, []):
        source = builds if kind == "build" else units
        frame = next((f for f, n in source if n == name), None)
        metrics[key] = round(frame * FRAME_SEC, 1) if frame is not None else None

    for key, name, minute in COUNT_EVENTS.get(race, []):
        limit = minute * 60 / FRAME_SEC
        metrics[key] = sum(1 for f, n in builds if n == name and f <= limit)

    return metrics
