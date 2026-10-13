"""누적 데이터 분석: 상대 프로필 / 처방 / 승패 비교"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .db import GameRow, PlayerRow
from .metrics import COUNT_EVENTS, FIRST_EVENTS, LABELS, fmt_time

EARLY_POOL_SEC = 60  # 1분 이내 스포닝풀 = 극초반 러시로 판정


# ---------------------------------------------------------------- 공통

def _values(rows: list[PlayerRow], key: str) -> list[float]:
    return [r.metrics[key] for r in rows if r.metrics.get(key) is not None]


def _median(values: list[float]) -> float | None:
    return median(values) if values else None


def is_eliminated_early(p: PlayerRow, game: GameRow) -> bool:
    """경기 시간의 절반도 안 돼서 명령이 끊긴 경우 (초반 탈락/이탈)"""
    if p.last_cmd_sec is None or game.length_sec <= 0:
        return False
    return p.last_cmd_sec < game.length_sec * 0.5 and game.length_sec - p.last_cmd_sec > 120


# ---------------------------------------------------------------- 플레이어 프로필

@dataclass
class MetricStat:
    key: str
    label: str
    median: float | None
    seen: int          # 해당 지표가 나온 경기 수
    total: int         # 해당 종족으로 플레이한 경기 수
    is_count: bool

    def display(self) -> str:
        if self.median is None:
            return "-"
        return f"{self.median:.1f}" if self.is_count else fmt_time(self.median)


@dataclass
class RaceProfile:
    race: str
    games: int
    wins: int
    losses: int
    stats: list[MetricStat] = field(default_factory=list)
    early_pool: int = 0   # 저그 전용: 1분 이내 풀 횟수

    @property
    def win_rate(self) -> float | None:
        decided = self.wins + self.losses
        return self.wins / decided if decided else None

    def stat(self, key: str) -> MetricStat | None:
        return next((s for s in self.stats if s.key == key), None)


def player_profile(games: list[GameRow], name: str) -> dict[str, RaceProfile]:
    rows_by_race: dict[str, list[PlayerRow]] = {}
    for g in games:
        p = g.player(name)
        if p:
            rows_by_race.setdefault(p.race, []).append(p)

    out: dict[str, RaceProfile] = {}
    for race, rows in rows_by_race.items():
        prof = RaceProfile(race=race, games=len(rows),
                           wins=sum(1 for r in rows if r.won is True),
                           losses=sum(1 for r in rows if r.won is False))
        for key, _, _ in FIRST_EVENTS.get(race, []):
            vals = _values(rows, key)
            prof.stats.append(MetricStat(key, LABELS.get(key, key), _median(vals), len(vals), len(rows), False))
        for key, _, _ in COUNT_EVENTS.get(race, []):
            vals = _values(rows, key)
            prof.stats.append(MetricStat(key, LABELS.get(key, key), _median(vals), len(vals), len(rows), True))
        if race == "Zerg":
            prof.early_pool = sum(1 for v in _values(rows, "pool") if v <= EARLY_POOL_SEC)
        out[race] = prof
    return out


# ---------------------------------------------------------------- 처방 (규칙 기반)

@dataclass
class Advice:
    level: str   # "warn" | "info" | "good"
    title: str
    detail: str


def _team_first(game: GameRow, team: int, key: str) -> tuple[float | None, str | None]:
    """팀 내에서 가장 빠른 지표 값과 그 플레이어"""
    best, who = None, None
    for p in game.players:
        v = p.metrics.get(key)
        if p.team == team and v is not None and (best is None or v < best):
            best, who = v, p.name
    return best, who


def prescriptions(game: GameRow, history: list[GameRow], me: str) -> list[Advice]:
    my = game.player(me)
    if not my:
        return [Advice("info", "내 플레이어를 찾지 못했습니다", f"설정의 my_name({me})을 확인하세요.")]

    advices: list[Advice] = []
    # 이번 경기를 제외한 과거 기록으로만 상대 성향을 판단 (사후 편향 방지)
    past = [g for g in history if g.id != game.id and g.start_time <= game.start_time]
    enemies = [p for p in game.players if p.team != my.team]

    # 1) 초반 탈락 감지
    if is_eliminated_early(my, game):
        advices.append(Advice("warn", f"{fmt_time(my.last_cmd_sec)}에 활동이 끊겼습니다",
                              "초반 러시나 이탈로 경기에서 빠진 것으로 보입니다. 아래 상대 초반 성향을 확인하세요."))

    for e in enemies:
        prof = player_profile(past, e.name).get(e.race)
        if not prof or prof.games < 2:
            continue

        # 2) 극초반 풀 러시 성향
        if e.race == "Zerg" and prof.early_pool >= max(2, prof.games // 2):
            pool = prof.stat("pool")
            detail = (f"과거 {prof.games}판 중 {prof.early_pool}판이 1분 이내 풀 (중앙값 {pool.display()}). "
                      f"이번 판 {e.name}의 풀: {fmt_time(e.metrics.get('pool'))}.")
            if my.race == "Protoss":
                detail += (f" 내 포지 {fmt_time(my.metrics.get('forge'))}, 첫 캐논 {fmt_time(my.metrics.get('cannon'))}"
                           " → 포지 1:00 이전, 캐논 1:30 이전 권장.")
            advices.append(Advice("warn", f"{e.name}: 극초반 러시 성향", detail))

        # 3) 뮤탈 타이밍 vs 우리 팀 첫 커세어
        mutal = prof.stat("mutal")
        if e.race == "Zerg" and mutal and mutal.median is not None and mutal.seen >= 2:
            corsair, who = _team_first(game, my.team, "corsair")
            target = mutal.median - 20
            if corsair is None or corsair > target:
                advices.append(Advice(
                    "warn", f"{e.name}: 뮤탈 대비 필요",
                    f"과거 첫 뮤탈 중앙값 {mutal.display()} ({mutal.seen}/{prof.games}판). "
                    f"이번 판 우리 팀 첫 커세어 {fmt_time(corsair)}{f' ({who})' if who else ''} "
                    f"→ {fmt_time(target)} 이전 커세어 권장."))
            else:
                advices.append(Advice("good", f"{e.name}: 뮤탈 대비 OK",
                                      f"뮤탈 중앙값 {mutal.display()}보다 빠른 {fmt_time(corsair)}에 커세어 ({who})."))

        # 4) 럴커 → 옵저버
        lurker = prof.stat("lurker")
        if e.race == "Zerg" and lurker and lurker.median is not None and lurker.seen >= 2:
            obs, who = _team_first(game, my.team, "observer")
            if obs is None or obs > lurker.median:
                advices.append(Advice(
                    "info", f"{e.name}: 럴커 사용자",
                    f"과거 첫 럴커 중앙값 {lurker.display()} ({lurker.seen}/{prof.games}판). "
                    f"우리 팀 첫 옵저버 {fmt_time(obs)} → 그 전에 옵저버 확보 권장."))

    # 5) 내가 이긴 판 평균 대비 늦은 빌드
    my_prof = player_profile([g for g in past if (p := g.player(me)) and p.won], me).get(my.race)
    if my_prof and my_prof.games >= 3:
        for s in my_prof.stats:
            v = my.metrics.get(s.key)
            if s.is_count or s.median is None or v is None or s.seen < 3:
                continue
            if v - s.median >= 60:
                advices.append(Advice("info", f"{s.label}이(가) 평소보다 늦었습니다",
                                      f"이번 판 {fmt_time(v)} / 내가 이긴 판 중앙값 {s.display()} (+{fmt_time(v - s.median)})."))

    if not advices:
        advices.append(Advice("good", "특이사항 없음", "누적 데이터 기준으로 눈에 띄는 문제가 없습니다."))
    return advices


# ---------------------------------------------------------------- 승/패 비교

@dataclass
class CompareRow:
    label: str
    win: str
    lose: str
    diff_sec: float | None


def win_loss_compare(games: list[GameRow], race: str, vs_race: str) -> tuple[int, list[CompareRow]]:
    """race 쪽 플레이어 전체(팀원 포함)를 승/패로 나눠 지표 중앙값 비교"""
    win_rows, lose_rows, n_games = [], [], 0
    for g in games:
        sides = {p.team: {q.race for q in g.players if q.team == p.team} for p in g.players}
        counted = False
        for p in g.players:
            enemy_races = set().union(*(r for t, r in sides.items() if t != p.team)) if len(sides) > 1 else set()
            if p.race != race or enemy_races != {vs_race} or p.won is None or is_eliminated_early(p, g):
                continue
            (win_rows if p.won else lose_rows).append(p)
            counted = True
        n_games += counted

    out = []
    for key, _, _ in FIRST_EVENTS.get(race, []):
        w, l = _median(_values(win_rows, key)), _median(_values(lose_rows, key))
        out.append(CompareRow(LABELS.get(key, key), fmt_time(w), fmt_time(l),
                              None if w is None or l is None else l - w))
    for key, _, _ in COUNT_EVENTS.get(race, []):
        w, l = _median(_values(win_rows, key)), _median(_values(lose_rows, key))
        out.append(CompareRow(LABELS.get(key, key), "-" if w is None else f"{w:.1f}",
                              "-" if l is None else f"{l:.1f}", None))
    return n_games, out
