"""리플레이 폴더 스캔 / 감시"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path

from .db import Database
from .replay import ReplayParseError, file_hash, parse_replay

log = logging.getLogger(__name__)


def import_file(db: Database, screp_path: str, path: Path) -> int | None:
    """새 리플레이면 저장 후 game_id 반환, 이미 있거나 실패하면 None"""
    try:
        h = file_hash(path)
    except OSError as e:
        log.warning("읽기 실패 %s: %s", path, e)
        return None
    if db.has_hash(h):
        return None

    try:
        game = parse_replay(screp_path, path)
    except ReplayParseError as e:
        log.warning("파싱 실패 %s: %s", path.name, e)
        db.mark_failed(h, str(path), str(e))
        return None

    game_id = db.insert_game(game)
    log.info("저장 #%d %s (%s, %s)", game_id, path.name, game.map_name, game.matchup)
    return game_id


def import_folder(db: Database, screp_path: str, folder: Path) -> list[int]:
    files = sorted(folder.rglob("*.rep"), key=lambda p: p.stat().st_mtime)
    log.info("%s 에서 리플레이 %d개 발견", folder, len(files))
    failed_before = db.failed_count()
    new_ids = []
    for i, f in enumerate(files, 1):
        gid = import_file(db, screp_path, f)
        if gid:
            new_ids.append(gid)
        if i % 100 == 0:
            log.info("진행 %d/%d (신규 %d)", i, len(files), len(new_ids))

    failed_now = db.failed_count()
    log.info("결과: 신규 %d / 이번 실패 %d / 실패 기록 누적 %d (재시도: import --retry-failed)",
             len(new_ids), failed_now - failed_before, failed_now)
    return new_ids


def watch_folder(db: Database, screp_path: str, folder: Path, interval: float,
                 on_new_game: Callable[[int], None]) -> None:
    """폴링 방식 감시 (추가 라이브러리 없이 동작, LastReplay.rep 덮어쓰기도 감지)"""
    mtimes: dict[Path, float] = {p: p.stat().st_mtime for p in folder.rglob("*.rep")}
    log.info("감시 시작: %s (%.0f초 간격, Ctrl+C로 종료)", folder, interval)

    while True:
        time.sleep(interval)
        for p in folder.rglob("*.rep"):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtimes.get(p) == mtime:
                continue
            mtimes[p] = mtime
            # 게임 종료 직후 파일 쓰기가 끝나지 않았을 수 있으므로 잠시 대기
            time.sleep(1.0)
            gid = import_file(db, screp_path, p)
            if gid:
                on_new_game(gid)
