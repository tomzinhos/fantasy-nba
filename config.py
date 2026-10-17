"""Configuração da liga. Cookies ficam no .env, nunca aqui."""
from pathlib import Path

LEAGUE_ID = 440479407
SEASON = 2027  # temporada 2026-27 usa o ano de término no ESPN; confirmar na primeira execução
NBA_SEASONS = ["2024-25", "2025-26"]  # temporadas regulares usadas como insumo
NBA_PRESEASON = "2026-27"  # pré-temporada atual (pode vir vazia até os jogos começarem)
DATA_DIR = Path(__file__).parent / "data"
