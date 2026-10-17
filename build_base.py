"""Junta rosters da liga (ESPN) com as stats da NBA em data/players_base.csv.

Casamento por nome normalizado (sem acento, pontuação e sufixos).
Jogadores sem par são listados no final para revisão manual.

Uso:
    python build_base.py
Usa apenas a biblioteca padrão.
"""
import csv
import re
import unicodedata
from collections import defaultdict

from config import DATA_DIR

SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
STAT_COLS = ["GP", "MIN", "AGE", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG_PCT"]
SEASON_TAGS = {
    ("2024-25", "Regular Season"): "2425",
    ("2025-26", "Regular Season"): "2526",
    ("2026-27", "Pre Season"): "pre2627",
}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).lower().strip()
    parts = [p for p in s.split() if p not in SUFFIXES]
    return " ".join(parts)


def load_nba():
    by_name = defaultdict(dict)  # nome normalizado -> {tag: linha}
    nba_team = {}
    with open(DATA_DIR / "nba_player_stats.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tag = SEASON_TAGS.get((row["season"], row["season_type"]))
            if not tag:
                continue
            key = norm(row["PLAYER_NAME"])
            by_name[key][tag] = row
            nba_team[key] = row["TEAM_ABBREVIATION"]
    return by_name, nba_team


def main():
    nba, nba_team = load_nba()
    out_rows, unmatched = [], []
    with open(DATA_DIR / "rosters.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = norm(r["player_name"])
            stats = nba.get(key, {})
            row = {
                "owner": r["owner"],
                "team_name": r["team_name"],
                "player_name": r["player_name"],
                "espn_position": r["position"],
                "lineup_slot": r["lineup_slot"],
                "injury_status": r["injury_status"],
                "nba_team": nba_team.get(key, ""),
                "matched": "sim" if stats else "não",
            }
            for tag in SEASON_TAGS.values():
                for col in STAT_COLS:
                    row[f"{tag}_{col}"] = stats.get(tag, {}).get(col, "")
            out_rows.append(row)
            if not stats:
                unmatched.append(f'{r["player_name"]} ({r["team_name"]})')

    out = DATA_DIR / "players_base.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"players_base.csv: {len(out_rows)} jogadores, {len(out_rows) - len(unmatched)} casados")
    if unmatched:
        print("Sem par na NBA:")
        for n in unmatched:
            print("  -", n)


if __name__ == "__main__":
    main()
