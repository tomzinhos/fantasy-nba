# Basquetobol Teorico Diplos — Fantasy NBA (ESPN)

Base de dados e rankings da liga ESPN Fantasy Basketball (pontos), construída com dados do ESPN e da NBA.
Tudo roda local; nenhum passo consome créditos de API paga.

## Pipeline

| # | Script | O que faz | Saída (`data/`) |
|---|---|---|---|
| 1 | `espn_collector.py` | Rosters, lesões e draft da liga | `rosters.csv`, `draft.csv` |
| 2 | `nba_stats.py` | Médias por jogo da NBA (2024-25, 2025-26 e pré-temporada 2026-27) | `nba_player_stats.csv` |
| 3 | `espn_projections.py` | Projeção ESPN 2026-27 e média real 2025-26, em fantasy points | `espn_projections.csv` |
| 4 | `build_base.py` | Junta rosters + stats da NBA (casamento por nome normalizado) | `players_base.csv` |
| 5 | `calibrate_teto.py` | Calibra o teto: real ÷ projeção ESPN da temporada passada, por nível | `teto_params.json`, `teto_calibration.md` |
| 6 | `rankings.py` | Power rank, projeção de temporada, starting five, depth e teto | `rankings.md`, `player_values.csv` |
| 7 | `make_report.py` | Relatório em PDF com os rankings e uma página por time | `reports/*.pdf` |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Depois abra o `.env` e preencha `ESPN_S2` e `SWID`. Para pegar os dois: no navegador logado em `fantasy.espn.com`,
abra o DevTools > Application > Cookies > `fantasy.espn.com` e copie os valores.
O `.env` está no `.gitignore` e nunca vai para o repositório.

## Atualizar tudo

```bash
python espn_collector.py && python nba_stats.py && python espn_projections.py
python build_base.py && python calibrate_teto.py && python rankings.py
python make_report.py
```

## Metodologia (resumo)

- **Valor atual** (fantasy points por jogo, scoring da liga): 80% média real 2025-26 + 20% projeção ESPN 2026-27.
  Rookies usam a projeção. Jogadores `OUT`/`INJURY_RESERVE` valem 0 no valor atual; `DAY_TO_DAY` conta como saudável.
- **Power rank**: soma dos 10 melhores valores do elenco.
- **Starting five**: uma vaga por posição (PG, SG, SF, PF, C) com o melhor saudável daquela posição; se faltar, cai para o melhor disponível (marcado com `*`).
- **Depth**: os 8 melhores saudáveis fora do starting five.
- **Teto**: projeção ESPN × percentil 80 de (real ÷ projeção) do nível do jogador na temporada passada
  (top 50, 51-150, 151+ do ranking de projeções). Rookies usam a turma de rookies de 2025-26 (até 24 anos); top-2 do draft usam o percentil 90.
- **Projeção de temporada**: soma das projeções totais do ESPN (inclui lesionados).

## Pontos validados

- `SEASON = 2027` em `config.py`: o ESPN usa o ano de término da temporada (a API devolve projeções em `2027` e resultados reais em `2026`).
- Posições (`POSITION` em `config.py`): `1 = PG`, `2 = SG`, `3 = SF`, `4 = PF`, `5 = C`, conferido com jogadores conhecidos. Os ids 0, 6 e 7 não apareceram.
- Parser do ESPN: 156 jogadores e 156 picks, 12 times de 13 jogadores, sem campos vazios.
- Casamento ESPN × NBA por nome: 156 de 156.

## Limitações conhecidas

- A projeção do ESPN foi otimista na temporada passada (mediana de real ÷ projeção entre 0,94 e 0,98 nos três níveis). Os valores usam a projeção como ela vem.
- A posição vem do `defaultPositionId`; a elegibilidade múltipla do ESPN (ex.: PG/SG) não é usada.
- Aday Mara não tem projeção nem histórico e fica fora do cálculo.
- A amostra de rookies para calibrar o teto é pequena (21 jogadores).
