"""Rankings da liga: power rank, starting five por posição, depth, teto e projeção de temporada.

Valor atual do jogador (fantasy points por jogo, scoring da liga):
  - com média anterior e projeção: 80% média anterior + 20% projeção
  - só projeção (rookies): projeção
  - só média anterior: média anterior
  - sem nenhum dado: fica de fora (sinalizado)
  - OUT / INJURY_RESERVE / SUSPENSION: 0 no valor atual (a projeção de temporada segue contando)

Teto (potencial desta temporada, em fantasy points por jogo):
  Calibrado com dados (calibrate_teto.py -> data/teto_params.json): projeção atual do ESPN
  multiplicada pelo percentil 80 de (real / projeção) do nível do jogador na temporada passada.
  Níveis: top 50, 51-150 e 151+ no ranking de projeções. Rookies: multiplicador da turma de
  rookies da temporada passada; top-2 do draft (ROOKIE_TOP) usam o percentil 90.
  Sem teto_params.json, usa multiplicadores de fallback (1.03 / 1.10 / 1.15; rookies 1.10 / 1.25).

Starting five: uma vaga por posição (PG, SG, SF, PF, C). Cada jogador pode ocupar qualquer vaga para a
qual é elegível no ESPN (eligibleSlots; ex.: um PF/C pode ser o C). A escolha maximiza a soma total do
valor atual entre as combinações válidas. Se uma vaga não tiver elegível saudável, ela vai para o melhor
disponível (marcado com *).
Depth: próximos 8 melhores saudáveis fora do starting five.

Uso:
    python rankings.py
Gera data/rankings.md e data/player_values.csv. Usa só a biblioteca padrão.
"""
import csv
import json
from collections import defaultdict

from config import DATA_DIR, POSITION, ELIGIBLE_SLOT

W_PREV, W_PROJ = 0.8, 0.2
OUT_STATUSES = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
SLOTS = ["PG", "SG", "SF", "PF", "C"]

# Rookies do NewJeans com pick top-2 do draft da NBA 2026 (ajustar se necessário).
ROOKIE_TOP = {"AJ Dybantsa", "Darryn Peterson"}  # picks 1 e 2 do draft 2026 (ajustar se necessário)


def load_teto_params():
    p = DATA_DIR / "teto_params.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


TETO = load_teto_params()


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def teto_fp(name, prev, pj):
    if prev is None and pj is None:
        return None
    if TETO:
        if prev is None:  # rookie sem histórico
            return pj * (TETO["rookie_top"] if name in ROOKIE_TOP else TETO["rookie_default"])
        base = pj if pj is not None else prev
        e1, e2 = TETO["edges"]
        m = TETO["mults"][0] if base >= e1 else TETO["mults"][1] if base >= e2 else TETO["mults"][2]
        return base * m
    # fallback sem calibração
    if prev is None:
        return pj * (1.25 if name in ROOKIE_TOP else 1.10)
    base = max(x for x in (prev, pj) if x is not None)
    return base * (1.03 if base >= 50 else 1.10 if base >= 35 else 1.15)


def load():
    proj = {r["espn_player_id"]: r for r in csv.DictReader(open(DATA_DIR / "espn_projections.csv", encoding="utf-8"))}
    base = {r["player_name"]: r for r in csv.DictReader(open(DATA_DIR / "players_base.csv", encoding="utf-8"))}
    players = []
    for r in csv.DictReader(open(DATA_DIR / "rosters.csv", encoding="utf-8")):
        p = proj.get(r["espn_player_id"], {})
        prev, pj = f(p.get("actual_avg_fp_prev")), f(p.get("proj_avg_fp"))
        proj_total = f(p.get("proj_total"))
        age = f(base.get(r["player_name"], {}).get("2526_AGE"))
        name = r["player_name"]
        status = r["injury_status"]
        slots = {int(x) for x in r.get("eligible_slots", "").split("|") if x}
        elegiveis = [ELIGIBLE_SLOT[s] for s in sorted(slots) if s in ELIGIBLE_SLOT]
        out = status in OUT_STATUSES

        if prev is not None and pj is not None:
            value, src = W_PREV * prev + W_PROJ * pj, "80/20"
        elif pj is not None:
            value, src = pj, "só projeção"
        elif prev is not None:
            value, src = prev, "só média anterior"
        else:
            value, src = None, "sem dado"

        ceiling = teto_fp(name, prev, pj)

        players.append({
            "owner": r["owner"], "team_name": r["team_name"], "player_name": name,
            "position": POSITION.get(int(r["position_id"]), r["position"]) if r.get("position_id") else r["position"], "injury_status": status, "age": age or "",
            "posicoes_elegiveis": "/".join(elegiveis), "_elegiveis": set(elegiveis),
            "prev_fp": prev if prev is not None else "", "proj_fp": pj if pj is not None else "",
            "proj_total_season": proj_total if proj_total is not None else "",
            "value": round(value, 2) if value is not None else "",
            "fonte_valor": src,
            "value_atual": 0.0 if out else (round(value, 2) if value is not None else 0.0),
            "teto": round(ceiling, 2) if ceiling is not None else "",
            "saudavel": not out,
        })
    return players


def best_five(ps, top_n=8):
    """Melhor combinação de 5 titulares (uma vaga por posição, jogador elegível e saudável).

    Enumera as combinações entre os top_n elegíveis de cada vaga e fica com a de maior soma.
    Vaga sem nenhum elegível saudável (ou sem combinação possível) recebe o melhor disponível (*).
    """
    healthy = sorted([p for p in ps if p["saudavel"]], key=lambda x: x["value_atual"], reverse=True)
    cands = {s: [p for p in healthy if s in p["_elegiveis"]][:top_n] for s in SLOTS}
    SKIP_PENALTY = 1000.0  # deixar vaga vazia só se não houver alternativa

    best = {"score": None, "pick": None}

    def rec(i, used, score, pick):
        if i == len(SLOTS):
            if best["score"] is None or score > best["score"]:
                best["score"], best["pick"] = score, dict(pick)
            return
        slot = SLOTS[i]
        opts = [p for p in cands[slot] if p["player_name"] not in used]
        if not opts:
            rec(i + 1, used, score - SKIP_PENALTY, pick)
            return
        for p in opts:
            pick[slot] = p
            rec(i + 1, used | {p["player_name"]}, score + p["value_atual"], pick)
            del pick[slot]

    rec(0, frozenset(), 0.0, {})
    chosen = best["pick"] or {}

    used = {p["player_name"] for p in chosen.values()}
    lineup = {}
    for slot in SLOTS:
        if slot in chosen:
            lineup[slot] = (chosen[slot], False)
    for slot in SLOTS:
        if slot not in lineup:
            pick = next((p for p in healthy if p["player_name"] not in used), None)
            if pick:
                lineup[slot] = (pick, True)
                used.add(pick["player_name"])
    depth = [p for p in healthy if p["player_name"] not in used][:8]
    return lineup, depth


def team_table(players):
    teams = defaultdict(list)
    for p in players:
        teams[p["team_name"]].append(p)
    rows = []
    for t, ps in teams.items():
        ps_sorted = sorted(ps, key=lambda x: x["value_atual"], reverse=True)
        lineup, depth = best_five(ps)
        five_total = sum(p["value_atual"] for p, _ in lineup.values())
        ceil10 = sorted([x["teto"] for x in ps if x["teto"] != ""], reverse=True)[:10]
        rows.append({
            "time": t, "dono": ps[0]["owner"],
            "power": round(sum(x["value_atual"] for x in ps_sorted[:10]), 1),
            "starting_five": round(five_total, 1),
            "depth": round(sum(x["value_atual"] for x in depth), 1),
            "teto_time": round(sum(ceil10), 1),
            "proj_temporada": round(sum(x["proj_total_season"] for x in ps if x["proj_total_season"] != ""), 0),
            "lineup": " / ".join(
                f"{slot}: {p['player_name']}{'*' if fb else ''}" for slot, (p, fb) in lineup.items()),
        })
    return rows


def md_table(title, rows, key, cols):
    rows = sorted(rows, key=lambda r: r[key], reverse=True)
    out = [f"## {title}", "", "| # | " + " | ".join(c[1] for c in cols) + " |",
           "|---|" + "---|" * len(cols)]
    for i, r in enumerate(rows, 1):
        out.append(f"| {i} | " + " | ".join(str(r[c[0]]) for c in cols) + " |")
    return "\n".join(out) + "\n"


def main():
    players = load()
    teams = team_table(players)

    cols = [k for k in players[0].keys() if not k.startswith("_")]
    with open(DATA_DIR / "player_values.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(players)

    md = ["# Rankings da liga", ""]
    md.append(md_table("Power rank (valor atual, 10 melhores)", teams, "power",
                       [("time", "Time"), ("dono", "Dono"), ("power", "Power")]))
    md.append(md_table("Projeção de temporada (soma das projeções ESPN, inclui lesionados)", teams,
                       "proj_temporada", [("time", "Time"), ("dono", "Dono"), ("proj_temporada", "Total")]))
    md.append(md_table("Melhor starting five (uma vaga por posição)", teams, "starting_five",
                       [("time", "Time"), ("dono", "Dono"), ("starting_five", "Starting five")]))
    md.append(md_table("Melhor depth (8 seguintes saudáveis)", teams, "depth",
                       [("time", "Time"), ("dono", "Dono"), ("depth", "Depth")]))
    md.append(md_table("Maior teto (melhor cenário, 10 maiores)", teams, "teto_time",
                       [("time", "Time"), ("dono", "Dono"), ("teto_time", "Teto")]))
    md.append("## Starting five por time (* = posição preenchida com fallback)\n")
    for t in sorted(teams, key=lambda x: x["starting_five"], reverse=True):
        md.append(f"- **{t['time']}** ({t['starting_five']}): {t['lineup']}")
    md.append("")
    top_teto = sorted([p for p in players if p["teto"] != ""], key=lambda p: p["teto"], reverse=True)[:15]
    md.append(md_table("Top 15 jogadores por teto", top_teto, "teto",
                       [("player_name", "Jogador"), ("team_name", "Time"), ("teto", "Teto")]))
    sem = [p for p in players if p["fonte_valor"] == "sem dado"]
    if sem:
        md.append("## Sem dado (fora do cálculo)\n")
        md += [f"- {p['player_name']} ({p['team_name']})" for p in sem]

    (DATA_DIR / "rankings.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
