"""screp 실행 → 게임/플레이어 정보 추출"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .metrics import FRAME_SEC, extract_player_metrics


class ReplayParseError(Exception):
    pass


@dataclass
class PlayerResult:
    player_id: int
    name: str
    race: str
    team: int
    won: bool | None
    apm: int
    eapm: int
    last_cmd_sec: float | None
    left_sec: float | None
    metrics: dict = field(default_factory=dict)


@dataclass
class GameResult:
    file_hash: str
    file_path: str
    start_time: str
    map_name: str
    title: str
    game_type: str
    matchup: str
    length_sec: float
    winner_team: int | None
    saver_name: str | None
    players: list[PlayerResult]


def file_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def run_screp(screp_path: str, replay: Path) -> dict:
    # 윈도우에서 콘솔 창이 깜빡이지 않도록 CREATE_NO_WINDOW 지정
    flags = 0x08000000 if sys.platform == "win32" else 0
    try:
        proc = subprocess.run(
            [screp_path, "-cmds", "-indent=false", str(replay)],
            capture_output=True, timeout=60, creationflags=flags,
        )
    except FileNotFoundError as e:
        raise ReplayParseError(f"screp 실행 파일을 찾을 수 없습니다: {screp_path}") from e
    except subprocess.TimeoutExpired as e:
        raise ReplayParseError(f"screp 시간 초과: {replay}") from e

    if proc.returncode != 0:
        raise ReplayParseError(proc.stderr.decode("utf-8", "replace").strip() or "screp 실패")
    try:
        return json.loads(proc.stdout.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ReplayParseError(f"screp 출력 해석 실패: {e}") from e


def _clean_map_name(raw: str) -> str:
    # 맵 이름 끝의 색상 코드/깨진 문자 제거
    return "".join(ch for ch in raw if ch.isprintable() and ch != "�").strip()


def parse_replay(screp_path: str, replay: Path) -> GameResult:
    data = run_screp(screp_path, replay)
    header = data["Header"]
    computed = data.get("Computed") or {}
    cmds = (data.get("Commands") or {}).get("Cmds") or []

    winner = computed.get("WinnerTeam") or None  # 0 = 판정 불가
    descs = {d["PlayerID"]: d for d in computed.get("PlayerDescs") or []}
    left = {c["PlayerID"]: c["Frame"] * FRAME_SEC for c in computed.get("LeaveGameCmds") or []}

    players: list[PlayerResult] = []
    names_by_id: dict[int, str] = {}
    for p in header["Players"]:
        if p["Type"]["Name"] not in ("Human", "Computer"):
            continue  # 옵저버 슬롯 등 제외
        pid, race = p["ID"], p["Race"]["Name"]
        names_by_id[pid] = p["Name"]
        desc = descs.get(pid, {})
        last_frame = desc.get("LastCmdFrame")
        players.append(PlayerResult(
            player_id=pid,
            name=p["Name"],
            race=race,
            team=p["Team"],
            won=(p["Team"] == winner) if winner else None,
            apm=desc.get("APM", 0),
            eapm=desc.get("EAPM", 0),
            last_cmd_sec=round(last_frame * FRAME_SEC, 1) if last_frame is not None else None,
            left_sec=round(left[pid], 1) if pid in left else None,
            metrics=extract_player_metrics(cmds, pid, race),
        ))

    return GameResult(
        file_hash=file_hash(replay),
        file_path=str(replay),
        start_time=header.get("StartTime", ""),
        map_name=_clean_map_name(header.get("Map", "")),
        title=header.get("Title", ""),
        game_type=(header.get("Type") or {}).get("Name", ""),
        matchup=_matchup(players),
        length_sec=round(header.get("Frames", 0) * FRAME_SEC, 1),
        winner_team=winner,
        saver_name=names_by_id.get(computed.get("RepSaverPlayerID")),
        players=players,
    )


def _matchup(players: list[PlayerResult]) -> str:
    teams: dict[int, str] = {}
    for p in sorted(players, key=lambda x: x.team):
        teams[p.team] = teams.get(p.team, "") + (p.race[:1] or "?")
    return "v".join("".join(sorted(v)) for v in teams.values())
