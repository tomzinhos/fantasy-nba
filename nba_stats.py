"""Médias da temporada por jogador via nba_api (gratuito, sem créditos).

Uso:
    python nba_stats.py
Gera data/nba_player_stats.csv com médias por jogo.
"""
import time
import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats

from config import NBA_SEASON, DATA_DIR


def fetch_player_stats() -> pd.DataFrame:
    stats = leaguedashplayerstats.LeagueDashPlayerStats(
        season=NBA_SEASON,
        per_mode_detailed="PerGame",
        timeout=60,
    )
    time.sleep(1)  # educado com o endpoint público
    df = stats.get_data_frames()[0]
    cols = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN",
            "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG_PCT", "FT_PCT"]
    return df[cols]


def main():
    DATA_DIR.mkdir(exist_ok=True)
    df = fetch_player_stats()
    out = DATA_DIR / "nba_player_stats.csv"
    df.to_csv(out, index=False)
    print(f"nba_player_stats.csv: {len(df)} jogadores")


if __name__ == "__main__":
    main()
