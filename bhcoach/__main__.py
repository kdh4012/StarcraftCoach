"""CLI 진입점: python -m bhcoach <명령>"""
from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from pathlib import Path

from .config import CONFIG_PATH, Config
from .db import Database
from .importer import import_folder, watch_folder
from .report import game_report, profile_report, write

log = logging.getLogger("bhcoach")


def _make_game_report(cfg: Config, db: Database, game_id: int, open_it: bool) -> Path | None:
    game = db.game(game_id)
    if not game:
        log.error("경기 #%d 없음", game_id)
        return None
    if not any(k.lower() in (game.map_name or "").lower() for k in cfg.map_keywords):
        log.info("빅헌터가 아닌 경기라 리포트 생략: #%d %s", game_id, game.map_name)
        return None

    history = db.games(cfg.map_keywords)
    html = game_report(game, history, cfg.my_name, cfg.min_games_for_compare)
    path = write(html, cfg.report_dir, f"game_{game_id:05d}.html")
    log.info("리포트: %s", path.resolve())
    if open_it:
        webbrowser.open(path.resolve().as_uri())
    return path


def cmd_init(cfg: Config, _: argparse.Namespace) -> int:
    if CONFIG_PATH.exists():
        log.info("이미 존재: %s", CONFIG_PATH.resolve())
    else:
        cfg.save()
        log.info("생성: %s (my_name, replay_dir 확인 필요)", CONFIG_PATH.resolve())
    return 0


def cmd_import(cfg: Config, args: argparse.Namespace) -> int:
    folder = Path(args.folder or cfg.replay_dir)
    if not folder.is_dir():
        log.error("폴더 없음: %s", folder)
        return 1
    db = Database(cfg.db_path)
    try:
        ids = import_folder(db, cfg.screp_path, folder)
        log.info("신규 %d판 저장 (빅헌터 누적 %d판)", len(ids), len(db.games(cfg.map_keywords)))
    finally:
        db.close()
    return 0


def cmd_watch(cfg: Config, _: argparse.Namespace) -> int:
    folder = Path(cfg.replay_dir)
    if not folder.is_dir():
        log.error("폴더 없음: %s (config.json의 replay_dir 확인)", folder)
        return 1
    db = Database(cfg.db_path)
    try:
        import_folder(db, cfg.screp_path, folder)  # 꺼져 있던 동안 쌓인 리플레이 먼저 반영
        watch_folder(db, cfg.screp_path, folder, cfg.watch_interval_sec,
                     lambda gid: _make_game_report(cfg, db, gid, cfg.open_browser))
    except KeyboardInterrupt:
        log.info("감시 종료")
    finally:
        db.close()
    return 0


def cmd_report(cfg: Config, args: argparse.Namespace) -> int:
    db = Database(cfg.db_path)
    try:
        game_id = args.game or db.last_game_id()
        if game_id is None:
            log.error("저장된 경기가 없습니다. 먼저 import 하세요.")
            return 1
        return 0 if _make_game_report(cfg, db, game_id, not args.no_open) else 1
    finally:
        db.close()


def cmd_profile(cfg: Config, args: argparse.Namespace) -> int:
    db = Database(cfg.db_path)
    try:
        html = profile_report(db.games(cfg.map_keywords), args.name)
        safe = "".join(ch if ch.isalnum() else "_" for ch in args.name)
        path = write(html, cfg.report_dir, f"profile_{safe}.html")
        log.info("프로필: %s", path.resolve())
        if not args.no_open:
            webbrowser.open(path.resolve().as_uri())
    finally:
        db.close()
    return 0


def cmd_list(cfg: Config, args: argparse.Namespace) -> int:
    db = Database(cfg.db_path)
    try:
        games = db.games(cfg.map_keywords)[-args.n:]
        for g in games:
            me = g.player(cfg.my_name)
            res = "-" if not me or me.won is None else ("승" if me.won else "패")
            print(f"#{g.id:<5} {g.start_time[:16].replace('T', ' ')}  {g.matchup:<10} {res}  {g.map_name}")
    finally:
        db.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(prog="bhcoach", description="빅헌터 개인 코치")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="config.json 생성")
    p = sub.add_parser("import", help="리플레이 폴더 일괄 가져오기")
    p.add_argument("folder", nargs="?", help="기본값: config의 replay_dir")
    sub.add_parser("watch", help="리플레이 폴더 감시 → 경기 종료 시 자동 리포트")
    p = sub.add_parser("report", help="경기 리포트 생성")
    p.add_argument("--game", type=int, help="경기 번호 (기본: 가장 최근)")
    p.add_argument("--no-open", action="store_true")
    p = sub.add_parser("profile", help="플레이어 프로필")
    p.add_argument("name")
    p.add_argument("--no-open", action="store_true")
    p = sub.add_parser("list", help="최근 빅헌터 경기 목록")
    p.add_argument("-n", type=int, default=20)

    args = parser.parse_args(argv)
    cfg = Config.load()
    handlers = {"init": cmd_init, "import": cmd_import, "watch": cmd_watch,
                "report": cmd_report, "profile": cmd_profile, "list": cmd_list}
    return handlers[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
