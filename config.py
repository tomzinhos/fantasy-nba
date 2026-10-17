"""Configuração da liga. Cookies ficam no .env, nunca aqui."""
from pathlib import Path

LEAGUE_ID = 440479407
SEASON = 2027  # temporada 2026-27 usa o ano de término no ESPN; confirmar na primeira execução
NBA_SEASON = "2026-27"  # formato usado pelo nba_api
DATA_DIR = Path(__file__).parent / "data"
