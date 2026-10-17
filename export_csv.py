"""Gera data/elencos_atuais.csv: uma linha por jogador draftado, sem precisar de API nem de cookies.

Junta rosters.csv + draft.csv + player_values.csv (todos gerados pelos outros scripts).
Uso: python export_csv.py
"""
import csv
from config import DATA_DIR


def read(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    rosters = read("rosters.csv")
    picks = {r["espn_player_id"]: r for r in read("draft.csv")}
    vals = {(r["team_name"], r["player_name"]): r for r in read("player_values.csv")}
    cols = ["time", "dono", "jogador", "posicao", "idade", "status_lesao", "pick_draft", "fp_jogo_2025_26",
            "fp_jogo_proj_2026_27", "fp_total_proj_2026_27", "valor_atual", "teto", "saudavel", "espn_player_id"]
    out = []
    for r in rosters:
        v = vals.get((r["team_name"], r["player_name"]), {})
        pk = picks.get(r["espn_player_id"], {})
        out.append({
            "time": r["team_name"], "dono": r["owner"], "jogador": r["player_name"], "posicao": v.get("position") or r["position"],
            "idade": (v.get("age") or "").replace(".0", ""), "status_lesao": r["injury_status"], "pick_draft": pk.get("overall_pick", ""),
            "fp_jogo_2025_26": v.get("prev_fp", ""), "fp_jogo_proj_2026_27": v.get("proj_fp", ""),
            "fp_total_proj_2026_27": v.get("proj_total_season", ""), "valor_atual": v.get("value_atual", ""),
            "teto": v.get("teto", ""), "saudavel": v.get("saudavel", ""), "espn_player_id": r["espn_player_id"],
        })
    out.sort(key=lambda x: (x["time"], -(float(x["valor_atual"]) if x["valor_atual"] else -1)))
    path = DATA_DIR / "elencos_atuais.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print("%d jogadores -> %s" % (len(out), path))


if __name__ == "__main__":
    main()
