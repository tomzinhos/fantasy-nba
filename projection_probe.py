"""Teste: verifica se o ESPN expõe projeções de fantasy points por jogador.

Só lê dados. Não grava nada na liga.
Uso:
    python projection_probe.py
"""
import json
import os
import requests
from dotenv import load_dotenv

from config import LEAGUE_ID, SEASON

load_dotenv()

URL = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{SEASON}"
    f"/segments/0/leagues/{LEAGUE_ID}"
)
TARGETS = {"Nikola Jokic", "Jayson Tatum", "Payton Pritchard", "Chet Holmgren"}


def main():
    s = requests.Session()
    s.cookies.set("espn_s2", os.getenv("ESPN_S2"), domain=".espn.com")
    s.cookies.set("SWID", os.getenv("SWID"), domain=".espn.com")
    filt = {"players": {"limit": 1000, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    r = s.get(URL, params={"view": "kona_player_info", "scoringPeriodId": 0},
              headers={"x-fantasy-filter": json.dumps(filt)}, timeout=60)
    r.raise_for_status()
    players = r.json().get("players", [])
    print(f"jogadores retornados: {len(players)}")
    for p in players:
        pl = p.get("player", {})
        name = pl.get("fullName")
        if name not in TARGETS:
            continue
        print(f"\n== {name} (id {pl.get('id')}) ==")
        print("chaves do jogador:", sorted(pl.keys())[:40])
        for st in pl.get("stats", []):
            print({k: st.get(k) for k in ["seasonId", "scoringPeriodId", "statSourceId",
                                          "statSplitTypeId", "appliedTotal", "appliedAverage"]})


if __name__ == "__main__":
    main()
