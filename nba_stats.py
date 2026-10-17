"""Médias por jogo via nba_api (gratuito, sem créditos).

Puxa temporadas regulares (NBA_SEASONS) e a pré-temporada (NBA_PRESEASON)
e junta tudo em data/nba_player_stats.csv, com colunas `season` e `season_type`.

Uso:
    python nba_stats.py
"""
import time
import pandas as pd
from nba_api.stats.endpoints import leaguedashplayerstats

from config import NBA_SEASONS, NBA_PRESEASON, DATA_DIR

COLS = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN",
        "PTS", "REB", "AST", "STL", "BLK", "TOV", "FG3M", "FG_PCT", "FT_PCT"]


def fetch(season: str, season_type: str) -> pd.DataFrame:
    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season=season,
            season_type_all_star=season_type,
            per_mode_detailed="PerGame",
            timeout=60,
        )
        time.sleep(1)  # educado com o endpoint público
        df = stats.get_data_frames()[0]
    except Exception as e:
        print(f"[aviso] {season} / {season_type}: sem dados ({type(e).__name__})")
        return pd.DataFrame()
    if df.empty:
        return df
    out = df[COLS].copy()
    out.insert(0, "season", season)
    out.insert(1, "season_type", season_type)
    return out


def main():
    DATA_DIR.mkdir(exist_ok=True)
    frames = []
    for s in NBA_SEASONS:
        frames.append(fetch(s, "Regular Season"))
    frames.append(fetch(NBA_PRESEASON, "Pre Season"))
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise SystemExit("Nenhuma temporada retornou dados. Verifique a conexão com stats.nba.com.")
    df = pd.concat(frames, ignore_index=True)
    out = DATA_DIR / "nba_player_stats.csv"
    df.to_csv(out, index=False)
    print(df.groupby(["season", "season_type"]).size().to_string())
    print(f"nba_player_stats.csv: {len(df)} linhas")


if __name__ == "__main__":
    main()
