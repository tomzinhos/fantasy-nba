"""Coleta do ESPN, por jogador da liga:
- projeção de fantasy points da temporada atual (SEASON), por jogo e total
- média real de fantasy points na temporada anterior (SEASON - 1), no scoring da liga

Gera data/espn_projections.csv. Só lê dados; não altera nada na liga.
Uso:
    python espn_projections.py
Requer ESPN_S2 e SWID no .env.
"""
import csv
import json
import os

import requests
from dotenv import load_dotenv

from config import LEAGUE_ID, SEASON, DATA_DIR

load_dotenv()

URL = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{SEASON}"
    f"/segments/0/leagues/{LEAGUE_ID}"
)
SOURCE_ACTUAL = 0
SOURCE_PROJECTED = 1
SPLIT_SEASON = 0  # total da temporada (não é split de mês, semana etc.)


def roster_ids() -> list[int]:
    with open(DATA_DIR / "rosters.csv", newline="", encoding="utf-8") as f:
        return sorted({int(r["espn_player_id"]) for r in csv.DictReader(f) if r["espn_player_id"]})


def pick(stats, season_id, source):
    for st in stats:
        if (st.get("seasonId") == season_id and st.get("statSourceId") == source
                and st.get("statSplitTypeId") == SPLIT_SEASON):
            return st
    return None


def main():
    s = requests.Session()
    s.cookies.set("espn_s2", os.getenv("ESPN_S2"), domain=".espn.com")
    s.cookies.set("SWID", os.getenv("SWID"), domain=".espn.com")

    ids = roster_ids()
    filt = {"players": {"limit": 1000, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    r = s.get(URL, params={"view": "kona_player_info", "scoringPeriodId": 0},
              headers={"x-fantasy-filter": json.dumps(filt)}, timeout=60)
    r.raise_for_status()
    players = r.json().get("players", [])
    wanted = set(ids)

    rows = []
    for p in players:
        pl = p.get("player", {})
        if pl.get("id") not in wanted:
            continue
        stats = pl.get("stats", [])
        proj = pick(stats, SEASON, SOURCE_PROJECTED)
        act = pick(stats, SEASON - 1, SOURCE_ACTUAL)
        rows.append({
            "espn_player_id": pl.get("id"),
            "player_name": pl.get("fullName"),
            "proj_total": proj.get("appliedTotal") if proj else "",
            "proj_avg_fp": round(proj.get("appliedAverage"), 2) if proj else "",
            "actual_total_prev": act.get("appliedTotal") if act else "",
            "actual_avg_fp_prev": round(act.get("appliedAverage"), 2) if act else "",
        })

    DATA_DIR.mkdir(exist_ok=True)
    out = DATA_DIR / "espn_projections.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["espn_player_id"])
        w.writeheader()
        w.writerows(rows)

    sem_proj = sum(1 for r_ in rows if r_["proj_avg_fp"] == "")
    sem_hist = sum(1 for r_ in rows if r_["actual_avg_fp_prev"] == "")
    faltando = len(wanted) - len(rows)
    print(f"espn_projections.csv: {len(rows)} jogadores | sem projeção: {sem_proj} | sem histórico: {sem_hist} | não retornados pela API: {faltando}")


if __name__ == "__main__":
    main()
