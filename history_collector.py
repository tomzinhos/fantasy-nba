"""Histórico da liga no ESPN: classificação final, campanha e dono de cada time por temporada.

Liga a franquia ao DONO (member id do ESPN), porque os nomes dos times mudam
(ex.: Ajej's Ball Hustlers -> Little River Hustlers; Best Estimated -> Thanos).

Uso:
    python history_collector.py
Gera data/historico.csv (uma linha por time e temporada) e data/historico_donos.csv (resumo por dono).
Requer ESPN_S2 e SWID no .env. Só lê dados.
"""
import csv
import os
from collections import defaultdict

import requests
from dotenv import load_dotenv

from config import LEAGUE_ID, SEASON, DATA_DIR

load_dotenv()
HIST = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/leagueHistory/{LEAGUE_ID}"
FIRST_SEASON = 2015  # busca para trás até aqui; temporadas inexistentes são ignoradas


def label(season_id: int) -> str:
    return f"{season_id - 1}-{str(season_id)[2:]}"


def main():
    s = requests.Session()
    s.cookies.set("espn_s2", os.getenv("ESPN_S2"), domain=".espn.com")
    s.cookies.set("SWID", os.getenv("SWID"), domain=".espn.com")
    current = {}  # dono ou co-dono -> time atual
    cur = s.get(f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{SEASON}/segments/0/leagues/{LEAGUE_ID}",
                params=[("view", "mTeam")], timeout=30).json()
    cur_members = {m["id"]: f'{m.get("firstName", "")} {m.get("lastName", "")}'.strip() for m in cur.get("members", [])}
    for t in cur.get("teams", []):
        for i, o in enumerate(t.get("owners", [])):
            current[cur_members.get(o, o)] = t.get("name", "") + ("" if i == 0 else " (co-dono)")

    rows = []
    for yr in range(FIRST_SEASON, SEASON):
        r = s.get(HIST, params=[("seasonId", yr), ("view", "mTeam")], timeout=30)
        if r.status_code != 200:
            continue
        data = r.json()
        data = data[0] if isinstance(data, list) and data else data
        if not data or not data.get("teams"):
            continue
        members = {m["id"]: f'{m.get("firstName", "")} {m.get("lastName", "")}'.strip() for m in data.get("members", [])}
        n = len(data["teams"])
        for t in data["teams"]:
            rec = t.get("record", {}).get("overall", {})
            owners = [members.get(o, o) for o in t.get("owners", [])]
            rows.append({
                "temporada": label(yr), "season_id": yr, "n_times": n,
                "time": t.get("name") or f'{t.get("location", "")} {t.get("nickname", "")}'.strip(),
                "dono": owners[0] if owners else "", "co_donos": " / ".join(owners[1:]),
                "posicao_final": t.get("rankCalculatedFinal"), "seed": t.get("playoffSeed"),
                "vitorias": rec.get("wins"), "derrotas": rec.get("losses"), "empates": rec.get("ties"),
                "pontos_pro": rec.get("pointsFor"), "pontos_contra": rec.get("pointsAgainst"),
                "time_atual_do_dono": current.get(owners[0], "") if owners else "",
            })
    rows.sort(key=lambda r: (r["season_id"], r["posicao_final"] or 99))
    with open(DATA_DIR / "historico.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by = defaultdict(list)
    for r in rows:
        by[r["dono"]].append(r)
        if r["co_donos"]:
            for c in r["co_donos"].split(" / "):
                by[c].append(dict(r, co=True))
    summ = []
    for dono, lst in by.items():
        own = [r for r in lst if not r.get("co")]
        fin = [r["posicao_final"] for r in lst]
        w_, l_ = sum(r["vitorias"] for r in own), sum(r["derrotas"] for r in own)
        summ.append({
            "dono": dono, "time_atual": current.get(dono, "(fora da liga)"),
            "temporadas": len(lst), "titulos": sum(1 for p in fin if p == 1), "finais": sum(1 for p in fin if p <= 2),
            "top3": sum(1 for p in fin if p <= 3), "melhor_final": min(fin), "media_final": round(sum(fin) / len(fin), 1),
            "campanha_regular": f"{w_}-{l_}", "aproveitamento": round(w_ / (w_ + l_), 3) if (w_ + l_) else "",
            "trajetoria": " | ".join(f'{r["temporada"]}: {r["posicao_final"]}º ({r["time"]}{", co-dono" if r.get("co") else ""})' for r in lst),
        })
    summ.sort(key=lambda r: (-r["titulos"], -r["finais"], -r["top3"], r["media_final"]))
    with open(DATA_DIR / "historico_donos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys()))
        w.writeheader()
        w.writerows(summ)
    print(f"historico.csv: {len(rows)} linhas | historico_donos.csv: {len(summ)} donos")
    for r in summ:
        print(f'{r["dono"]:<34} {r["time_atual"]:<26} títulos {r["titulos"]} finais {r["finais"]} top3 {r["top3"]} média {r["media_final"]}  | {r["trajetoria"]}')


if __name__ == "__main__":
    main()
