"""Calibra o teto (upside) com dados reais do ESPN.

Compara, para a temporada passada (SEASON-1), a projeção do ESPN com o que o jogador
realmente rendeu (fantasy points por jogo, scoring da liga) e mede quanto cada nível
superou a projeção. O teto de cada jogador passa a ser: projeção atual * percentil Q
de (real / projeção) do nível dele.

Níveis (pela posição no ranking de projeções): top 50, 51-150, 151+.
Rookies: turma de rookies da temporada passada (jogadores que estão nas stats da NBA em
2025-26 mas não em 2024-25, com até MAX_ROOKIE_AGE anos, para não contar veterano que voltou
de lesão, como Saddiq Bey). rookie_default = percentil Q; rookie_top = percentil 90.

Só entram jogadores com MIN_GP jogos na temporada passada.

Uso:
    python calibrate_teto.py
Gera data/teto_params.json (lido pelo rankings.py) e data/teto_calibration.md.
Requer ESPN_S2 e SWID no .env. Só lê dados.
"""
import csv
import json
import os
import re
import unicodedata

from config import LEAGUE_ID, SEASON, DATA_DIR

Q = 0.80
Q_TOP = 0.90
MIN_GP = 20
MIN_PROJ = 10.0
TIER_RANKS = (50, 150)
TIER_NAMES = ["Elite (top 50)", "Médio (51-150)", "Baixo (151+)"]
FALLBACK_MULTS = [1.03, 1.10, 1.15]
FALLBACK_ROOKIE = (1.10, 1.25)
MIN_N = 8
MAX_ROOKIE_AGE = 24
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).lower().strip()
    return " ".join(p for p in s.split() if p not in SUFFIXES)


def quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def get_stat(stats, season_id, source):
    for st in stats:
        if (st.get("seasonId") == season_id and st.get("statSourceId") == source
                and st.get("statSplitTypeId") == 0):
            return st
    return None


def compute(players, prev_names, cur_names):
    rookie_names = cur_names - prev_names
    rows, pool_now = [], []
    for p in players:
        pl = p.get("player", {})
        stats = pl.get("stats", [])
        now = get_stat(stats, SEASON, 1)
        if now and (now.get("appliedAverage") or 0) > 0:
            pool_now.append(now["appliedAverage"])
        act, proj = get_stat(stats, SEASON - 1, 0), get_stat(stats, SEASON - 1, 1)
        if not (act and proj):
            continue
        a_avg, a_tot, p_avg = act.get("appliedAverage"), act.get("appliedTotal"), proj.get("appliedAverage")
        if not a_avg or not p_avg or a_avg <= 0 or p_avg <= 0:
            continue
        gp = a_tot / a_avg
        if gp < MIN_GP:
            continue
        rows.append({"name": pl.get("fullName", "?"), "proj": p_avg, "actual": a_avg, "gp": gp,
                     "ratio": a_avg / p_avg, "rookie": norm(pl.get("fullName")) in rookie_names})

    pool_now.sort(reverse=True)
    last = len(pool_now) - 1
    edges = [pool_now[min(TIER_RANKS[0] - 1, last)], pool_now[min(TIER_RANKS[1] - 1, last)]] if pool_now else [50, 35]

    vets = sorted([r for r in rows if not r["rookie"] and r["proj"] >= MIN_PROJ], key=lambda r: r["proj"], reverse=True)
    tiers = [[], [], []]
    for i, r in enumerate(vets, 1):
        t = 0 if i <= TIER_RANKS[0] else 1 if i <= TIER_RANKS[1] else 2
        tiers[t].append(r["ratio"])

    mults, tier_stats = [], []
    for t, rs in enumerate(tiers):
        q = quantile(rs, Q)
        mult = round(max(1.0, q), 3) if len(rs) >= MIN_N and q else FALLBACK_MULTS[t]
        mults.append(mult)
        tier_stats.append({"nome": TIER_NAMES[t], "n": len(rs), "mediana": quantile(rs, 0.5),
                           "p75": quantile(rs, 0.75), "p80": quantile(rs, Q), "p90": quantile(rs, Q_TOP),
                           "bate_proj": (sum(1 for x in rs if x > 1) / len(rs)) if rs else None, "mult": mult})

    rook = [r for r in rows if r["rookie"]]
    rr = [r["ratio"] for r in rook]
    if len(rr) >= 5:
        rd = round(max(1.0, quantile(rr, Q)), 3)
        rt = round(max(rd, quantile(rr, Q_TOP)), 3)
    else:
        rd, rt = FALLBACK_ROOKIE
    params = {"quantile": Q, "edges": [round(e, 2) for e in edges], "mults": mults,
              "rookie_default": rd, "rookie_top": rt, "n_vets": sum(len(t) for t in tiers),
              "n_rookies": len(rook), "calibrado_com_temporada": SEASON - 1}
    return params, tier_stats, rook


def fmt(x):
    return "-" if x is None else f"{x:.3f}"


def report(params, tier_stats, rook):
    L = ["# Calibração do teto", "",
         f"Base: real ÷ projeção ESPN na temporada {SEASON - 1}, jogadores com {MIN_GP}+ jogos. "
         f"Teto = projeção atual × percentil {int(Q * 100)} do nível.", "",
         "| Nível | n | mediana | p75 | p80 | p90 | % que bateu a projeção | multiplicador |",
         "|---|---|---|---|---|---|---|---|"]
    for t in tier_stats:
        pct = "-" if t["bate_proj"] is None else f"{t['bate_proj'] * 100:.0f}%"
        L.append(f"| {t['nome']} | {t['n']} | {fmt(t['mediana'])} | {fmt(t['p75'])} | {fmt(t['p80'])} | "
                 f"{fmt(t['p90'])} | {pct} | **{t['mult']}** |")
    L += ["", f"Cortes de projeção (fantasy points/jogo): elite >= {params['edges'][0]}, médio >= {params['edges'][1]}.",
          "", f"## Rookies da temporada passada (n={params['n_rookies']})", "",
          f"rookie_default (p{int(Q * 100)}) = **{params['rookie_default']}** | rookie_top (p{int(Q_TOP * 100)}) = **{params['rookie_top']}**",
          "", "| Jogador | Projeção | Real | Real ÷ proj |", "|---|---|---|---|"]
    for r in sorted(rook, key=lambda r: r["ratio"], reverse=True):
        L.append(f"| {r['name']} | {r['proj']:.1f} | {r['actual']:.1f} | {r['ratio']:.2f} |")
    return "\n".join(L) + "\n"


def load_nba_names():
    prev, cur = set(), set()
    with open(DATA_DIR / "nba_player_stats.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["season_type"] != "Regular Season":
                continue
            if r["season"] == "2024-25":
                prev.add(norm(r["PLAYER_NAME"]))
            elif r["season"] == "2025-26":
                try:
                    young = float(r["AGE"]) <= MAX_ROOKIE_AGE
                except (TypeError, ValueError):
                    young = True
                if young:
                    cur.add(norm(r["PLAYER_NAME"]))
    return prev, cur


def fetch_players():
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    url = (f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{SEASON}"
           f"/segments/0/leagues/{LEAGUE_ID}")
    s = requests.Session()
    s.cookies.set("espn_s2", os.getenv("ESPN_S2"), domain=".espn.com")
    s.cookies.set("SWID", os.getenv("SWID"), domain=".espn.com")
    filt = {"players": {"limit": 1000, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    r = s.get(url, params={"view": "kona_player_info", "scoringPeriodId": 0},
              headers={"x-fantasy-filter": json.dumps(filt)}, timeout=60)
    r.raise_for_status()
    return r.json().get("players", [])


def main():
    players = fetch_players()
    prev, cur = load_nba_names()
    params, tier_stats, rook = compute(players, prev, cur)
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "teto_params.json").write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
    md = report(params, tier_stats, rook)
    (DATA_DIR / "teto_calibration.md").write_text(md, encoding="utf-8")
    print(f"jogadores lidos: {len(players)}")
    print(md)


if __name__ == "__main__":
    main()
