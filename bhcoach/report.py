"""HTML 리포트 생성 (외부 리소스 없는 단일 파일)"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from .analysis import (is_eliminated_early, player_profile, prescriptions, win_loss_compare)
from .db import GameRow
from .metrics import COUNT_EVENTS, FIRST_EVENTS, LABELS, fmt_time

RACE_KO = {"Protoss": "프로토스", "Zerg": "저그", "Terran": "테란"}

# 상대 프로필 표에 노출할 핵심 지표
PROFILE_KEYS = {
    "Zerg": ["pool", "hatch2", "lair", "spire", "mutal", "hydra_den", "lurker", "creep@5"],
    "Protoss": ["forge", "cannon", "gateway", "stargate", "corsair", "robo", "reaver", "cannon@5"],
    "Terran": ["barracks", "factory", "starport", "cc2"],
}

CSS = """
:root { --bg:#f7f7f8; --card:#fff; --fg:#1d1d1f; --muted:#6b6b76; --line:#e3e3e8;
        --warn:#c2410c; --warn-bg:#fff4ed; --info:#1d4ed8; --info-bg:#eff4ff; --good:#15803d; --good-bg:#eefbf2;
        --me:#fff7cc; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#141417; --card:#1e1e23; --fg:#ececf1; --muted:#9a9aa6; --line:#33333b;
          --warn:#fb923c; --warn-bg:#2b1d14; --info:#93b4ff; --info-bg:#161e33; --good:#4ade80; --good-bg:#122419;
          --me:#3a3418; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.55 "Malgun Gothic","Apple SD Gothic Neo",sans-serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:17px; margin:28px 0 10px; }
.sub { color:var(--muted); margin-bottom:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:10px; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }
th { color:var(--muted); font-weight:600; font-size:12px; }
tr.me td { background:var(--me); font-weight:600; }
.win { color:var(--good); font-weight:700; } .lose { color:var(--warn); font-weight:700; }
.advice { border-left:4px solid; }
.advice.warn { border-color:var(--warn); background:var(--warn-bg); }
.advice.info { border-color:var(--info); background:var(--info-bg); }
.advice.good { border-color:var(--good); background:var(--good-bg); }
.advice b { display:block; margin-bottom:2px; }
.muted { color:var(--muted); } .small { font-size:12px; }
"""


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")


def _result(won: bool | None) -> str:
    if won is None:
        return "<span class='muted'>?</span>"
    return "<span class='win'>승</span>" if won else "<span class='lose'>패</span>"


def _table(headers: list[str], rows: list[list[str]], row_classes: list[str] | None = None) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for i, r in enumerate(rows):
        cls = f" class='{row_classes[i]}'" if row_classes and row_classes[i] else ""
        body += f"<tr{cls}>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _metric_keys(race: str) -> list[str]:
    return [k for k, _, _ in FIRST_EVENTS.get(race, [])] + [k for k, _, _ in COUNT_EVENTS.get(race, [])]


def _metric_cell(p_metrics: dict, key: str) -> str:
    v = p_metrics.get(key)
    if "@" in key:
        return "-" if v is None else str(v)
    return fmt_time(v)


def game_report(game: GameRow, history: list[GameRow], me: str, min_compare: int) -> str:
    my = game.player(me)
    parts: list[str] = []

    when = game.start_time.replace("T", " ").replace("Z", " UTC")
    parts.append(f"<h1>{escape(game.map_name)} · {escape(game.matchup)}</h1>")
    parts.append(f"<div class='sub'>{escape(when)} · 경기 시간 {fmt_time(game.length_sec)}"
                 f" · 누적 {len(history)}판 · 내 결과 {_result(my.won if my else None)}</div>")

    # 1) 처방
    parts.append("<h2>이번 판 처방</h2>")
    for a in prescriptions(game, history, me):
        parts.append(f"<div class='card advice {a.level}'><b>{escape(a.title)}</b>{escape(a.detail)}</div>")

    # 2) 참가자
    rows, classes = [], []
    for p in sorted(game.players, key=lambda x: (x.team, x.name)):
        activity = fmt_time(p.last_cmd_sec)
        if is_eliminated_early(p, game):
            activity += " <span class='lose small'>초반 탈락</span>"
        rows.append([str(p.team), escape(p.name), RACE_KO.get(p.race, p.race), _result(p.won),
                     str(p.apm), str(p.eapm), activity])
        classes.append("me" if p.name == me else "")
    parts.append("<h2>참가자</h2><div class='card'>"
                 + _table(["팀", "플레이어", "종족", "결과", "APM", "EAPM", "마지막 명령"], rows, classes) + "</div>")

    # 3) 종족별 빌드 타임라인 (팀별로 묶어서)
    for race in ("Protoss", "Zerg", "Terran"):
        ps = [p for p in game.players if p.race == race]
        if not ps:
            continue
        keys = _metric_keys(race)
        rows = [[escape(p.name), _result(p.won)] + [_metric_cell(p.metrics, k) for k in keys]
                for p in sorted(ps, key=lambda x: (x.team, x.name))]
        classes = ["me" if p.name == me else "" for p in sorted(ps, key=lambda x: (x.team, x.name))]
        parts.append(f"<h2>{RACE_KO[race]} 빌드 타임라인</h2><div class='card'>"
                     + _table(["플레이어", "결과"] + [LABELS[k] for k in keys], rows, classes)
                     + "<div class='small muted'>명령 기준 시각입니다. 자원 부족으로 실패한 건설 지시도 포함될 수 있습니다.</div></div>")

    # 4) 상대 프로필 (이번 판 이전 기록 기준)
    if my:
        past = [g for g in history if g.id != game.id and g.start_time <= game.start_time]
        enemies = [p for p in game.players if p.team != my.team]
        for race in ("Zerg", "Protoss", "Terran"):
            group = [e for e in enemies if e.race == race]
            if not group:
                continue
            keys = PROFILE_KEYS[race]
            rows = []
            for e in group:
                prof = player_profile(past, e.name).get(race)
                if not prof:
                    rows.append([escape(e.name), "0", "-"] + ["-"] * len(keys) + (["-"] if race == "Zerg" else []))
                    continue
                wr = "-" if prof.win_rate is None else f"{prof.win_rate * 100:.0f}%"
                cells = [prof.stat(k).display() if prof.stat(k) else "-" for k in keys]
                extra = [f"{prof.early_pool}/{prof.games}"] if race == "Zerg" else []
                rows.append([escape(e.name), str(prof.games), wr] + cells + extra)
            headers = ["상대", "과거 판수", "승률"] + [LABELS[k] for k in keys] + (["1분내 풀"] if race == "Zerg" else [])
            parts.append(f"<h2>상대 프로필 ({RACE_KO[race]}) — 과거 기록 중앙값</h2><div class='card'>"
                         + _table(headers, rows) + "</div>")

    # 5) 승/패 비교
    if my:
        vs = {p.race for p in game.players if p.team != my.team}
        if len(vs) == 1:
            vs_race = vs.pop()
            n, cmp_rows = win_loss_compare(history, my.race, vs_race)
            title = f"<h2>{RACE_KO.get(my.race, my.race)} 승/패 비교 (vs {RACE_KO.get(vs_race, vs_race)})</h2>"
            if n < min_compare:
                parts.append(title + f"<div class='card muted'>데이터 수집 중: {n}/{min_compare}판. "
                             "판수가 모이면 이긴 판과 진 판의 빌드 차이를 보여줍니다.</div>")
            else:
                rows = []
                for r in cmp_rows:
                    diff = "" if r.diff_sec is None else (f"진 판이 {fmt_time(abs(r.diff_sec))} "
                                                         + ("늦음" if r.diff_sec > 0 else "빠름"))
                    rows.append([r.label, r.win, r.lose, diff])
                parts.append(title + f"<div class='card'>"
                             + _table(["지표", "이긴 판 중앙값", "진 판 중앙값", "차이"], rows)
                             + f"<div class='small muted'>{n}판 기준 · 팀원 포함 · 초반 탈락자 제외</div></div>")

    parts.append(f"<div class='small muted' style='margin-top:24px'>생성 {datetime.now():%Y-%m-%d %H:%M} · "
                 f"{escape(Path(game.file_path).name)}</div>")
    return _page(f"빅헌터 리포트 #{game.id}", "".join(parts))


def profile_report(history: list[GameRow], name: str) -> str:
    profiles = player_profile(history, name)
    parts = [f"<h1>{escape(name)} 프로필</h1>",
             f"<div class='sub'>빅헌터 기록 {sum(p.games for p in profiles.values())}판</div>"]
    if not profiles:
        parts.append("<div class='card muted'>기록이 없습니다.</div>")
    for race, prof in profiles.items():
        wr = "-" if prof.win_rate is None else f"{prof.win_rate * 100:.0f}%"
        summary = f"{prof.games}판 · {prof.wins}승 {prof.losses}패 · 승률 {wr}"
        if race == "Zerg":
            summary += f" · 1분 내 풀 {prof.early_pool}회"
        rows = [[s.label, s.display(), f"{s.seen}/{s.total}"] for s in prof.stats]
        parts.append(f"<h2>{RACE_KO.get(race, race)}</h2><div class='card'><div class='sub'>{summary}</div>"
                     + _table(["지표", "중앙값", "등장"], rows) + "</div>")
    return _page(f"{name} 프로필", "".join(parts))


def write(html: str, out_dir: str, filename: str) -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / filename
    target.write_text(html, encoding="utf-8")
    return target
