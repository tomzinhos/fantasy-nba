"""Configuração da liga. Cookies ficam no .env, nunca aqui."""
from pathlib import Path

LEAGUE_ID = 440479407
SEASON = 2027  # temporada 2026-27 usa o ano de término no ESPN; confirmar na primeira execução
NBA_SEASONS = ["2024-25", "2025-26"]  # temporadas regulares usadas como insumo
NBA_PRESEASON = "2026-27"  # pré-temporada atual (pode vir vazia até os jogos começarem)
DATA_DIR = Path(__file__).parent / "data"

# defaultPositionId do ESPN -> posição. Confirmado com jogadores conhecidos (ids 0, 6 e 7 não apareceram).
POSITION = {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"}

# eligibleSlots do ESPN -> posição que o slot representa (ids 7 a 10 não foram decodificados e são ignorados).
ELIGIBLE_SLOT = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F"}
