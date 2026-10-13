"""SQLite 저장소"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .replay import GameResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id          INTEGER PRIMARY KEY,
    file_hash   TEXT NOT NULL UNIQUE,
    file_path   TEXT NOT NULL,
    start_time  TEXT,
    map_name    TEXT,
    title       TEXT,
    game_type   TEXT,
    matchup     TEXT,
    length_sec  REAL,
    winner_team INTEGER,
    saver_name  TEXT,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS players (
    id           INTEGER PRIMARY KEY,
    game_id      INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id    INTEGER NOT NULL,
    name         TEXT NOT NULL,
    race         TEXT NOT NULL,
    team         INTEGER NOT NULL,
    won          INTEGER,
    apm          INTEGER,
    eapm         INTEGER,
    last_cmd_sec REAL,
    left_sec     REAL,
    metrics      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_players_name ON players(name);
CREATE INDEX IF NOT EXISTS ix_players_game ON players(game_id);
CREATE TABLE IF NOT EXISTS failed_files (
    file_hash TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    error     TEXT
);
"""


@dataclass
class PlayerRow:
    game_id: int
    name: str
    race: str
    team: int
    won: bool | None
    apm: int
    eapm: int
    last_cmd_sec: float | None
    left_sec: float | None
    metrics: dict


@dataclass
class GameRow:
    id: int
    start_time: str
    map_name: str
    matchup: str
    length_sec: float
    winner_team: int | None
    file_path: str
    players: list[PlayerRow]

    def player(self, name: str) -> PlayerRow | None:
        return next((p for p in self.players if p.name == name), None)


class Database:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------ 저장

    def has_hash(self, file_hash: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM games WHERE file_hash = ? UNION SELECT 1 FROM failed_files WHERE file_hash = ?",
            (file_hash, file_hash))
        return cur.fetchone() is not None

    def insert_game(self, g: GameResult) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO games (file_hash, file_path, start_time, map_name, title, game_type, matchup,"
                " length_sec, winner_team, saver_name) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (g.file_hash, g.file_path, g.start_time, g.map_name, g.title, g.game_type, g.matchup,
                 g.length_sec, g.winner_team, g.saver_name))
            game_id = cur.lastrowid
            self.conn.executemany(
                "INSERT INTO players (game_id, player_id, name, race, team, won, apm, eapm, last_cmd_sec,"
                " left_sec, metrics) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(game_id, p.player_id, p.name, p.race, p.team,
                  None if p.won is None else int(p.won), p.apm, p.eapm, p.last_cmd_sec, p.left_sec,
                  json.dumps(p.metrics)) for p in g.players])
        return game_id

    def failed_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM failed_files").fetchone()[0]

    def clear_failed(self, error_like: str | None = None) -> int:
        """실패 기록 삭제 → 다음 import 때 재시도. error_like 지정 시 해당 문구가 포함된 것만"""
        with self.conn:
            if error_like:
                cur = self.conn.execute("DELETE FROM failed_files WHERE error LIKE ?", (f"%{error_like}%",))
            else:
                cur = self.conn.execute("DELETE FROM failed_files")
        return cur.rowcount

    def mark_failed(self, file_hash: str, path: str, error: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO failed_files VALUES (?,?,?)", (file_hash, path, error))

    # ------------------------------------------------------------ 조회

    def _players_for(self, game_ids: list[int]) -> dict[int, list[PlayerRow]]:
        if not game_ids:
            return {}
        marks = ",".join("?" * len(game_ids))
        rows = self.conn.execute(f"SELECT * FROM players WHERE game_id IN ({marks}) ORDER BY team, id", game_ids)
        out: dict[int, list[PlayerRow]] = {}
        for r in rows:
            out.setdefault(r["game_id"], []).append(PlayerRow(
                game_id=r["game_id"], name=r["name"], race=r["race"], team=r["team"],
                won=None if r["won"] is None else bool(r["won"]), apm=r["apm"], eapm=r["eapm"],
                last_cmd_sec=r["last_cmd_sec"], left_sec=r["left_sec"], metrics=json.loads(r["metrics"])))
        return out

    def games(self, map_keywords: list[str] | None = None) -> list[GameRow]:
        rows = self.conn.execute("SELECT * FROM games ORDER BY start_time").fetchall()
        if map_keywords:
            kws = [k.lower() for k in map_keywords]
            rows = [r for r in rows if any(k in (r["map_name"] or "").lower() for k in kws)]
        players = self._players_for([r["id"] for r in rows])
        return [GameRow(id=r["id"], start_time=r["start_time"], map_name=r["map_name"], matchup=r["matchup"],
                        length_sec=r["length_sec"], winner_team=r["winner_team"], file_path=r["file_path"],
                        players=players.get(r["id"], [])) for r in rows]

    def game(self, game_id: int) -> GameRow | None:
        r = self.conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if not r:
            return None
        return GameRow(id=r["id"], start_time=r["start_time"], map_name=r["map_name"], matchup=r["matchup"],
                       length_sec=r["length_sec"], winner_team=r["winner_team"], file_path=r["file_path"],
                       players=self._players_for([r["id"]]).get(r["id"], []))

    def last_game_id(self) -> int | None:
        r = self.conn.execute("SELECT id FROM games ORDER BY start_time DESC, id DESC LIMIT 1").fetchone()
        return r["id"] if r else None
