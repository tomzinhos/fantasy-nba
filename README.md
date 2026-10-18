# Basquetobol Teorico Diplos: Fantasy NBA (ESPN)

Base de dados e rankings da liga **Basquetobol Teorico Diplos** (ESPN Fantasy Basketball, pontos, draft de 17/10/2026).
Tudo roda no seu computador. Nenhum passo usa API paga.

O resultado mais fácil de ver é o PDF: [`reports/Basquetobol_Teorico_Diplos_preseason.pdf`](reports/Basquetobol_Teorico_Diplos_preseason.pdf)
(5 rankings + uma página por time com pontos fortes e frágeis).

## Escolha o seu caminho

| Você quer... | Caminho | Precisa de conta/cookie ESPN? |
|---|---|---|
| Só ver ou analisar os elencos | **A. CSV pronto** | Não |
| Atualizar os dados (lesões, trocas) e refazer os rankings | **B. Rodar o pipeline** | Sim (só leitura, é o seu login) |
| Analisar com a sua IA preferida (ChatGPT, Claude, Gemini, etc.) | **C. Usar com IA** | Não, se usar o CSV |

## A. CSV pronto (sem API, sem cookie)

Arquivo: [`data/elencos_atuais.csv`](data/elencos_atuais.csv), com os 156 jogadores draftados (12 times × 13).
Abre direto no Excel, Google Sheets ou Python (`pandas.read_csv`).

| Coluna | Significado |
|---|---|
| `time`, `conferencia`, `dono` | Time, conferência (East ou West) e dono na liga |
| `jogador`, `posicao`, `idade` | Posição padrão do ESPN (PG, SG, SF, PF, C) |
| `posicoes_elegiveis` | Todas as posições em que o jogador pode ser escalado no ESPN (ex.: `SF/PF/F`) |
| `status_lesao` | `ACTIVE`, `DAY_TO_DAY`, `OUT`, `INJURY_RESERVE`... |
| `pick_draft` | Pick geral no draft (1 a 156) |
| `fp_jogo_2025_26` | Média real de fantasy points por jogo na temporada passada |
| `fp_jogo_proj_2026_27` | Projeção do ESPN, em FP por jogo |
| `fp_total_proj_2026_27` | Projeção do ESPN para a temporada inteira |
| `valor_atual` | 80% média real + 20% projeção, com peso menor para quem jogou menos de 41 jogos (rookies e quem não jogou: só projeção). `OUT` vale 0 |
| `teto` | Melhor cenário realista, em FP por jogo (veja Metodologia) |
| `saudavel` | `False` para quem está `OUT`, em IR ou suspenso |
| `espn_player_id` | ID do jogador no ESPN |

Campos vazios significam "sem dado" (por exemplo, rookie sem histórico).
O CSV é uma foto de 17/10/2026. Para atualizar, use o caminho B.

## B. Rodar o pipeline completo

Requisitos: Python 3.9 ou mais novo e git.

```bash
git clone https://github.com/tomzinhos/fantasy-nba.git
cd fantasy-nba
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Abra o `.env` e preencha `ESPN_S2` e `SWID` com os **seus** cookies (a liga é privada, então o ESPN exige login):

1. Entre em `fantasy.espn.com` logado.
2. DevTools (F12) > Application (Chrome) ou Storage (Firefox) > Cookies > `fantasy.espn.com`.
3. Copie o valor de `espn_s2` e de `SWID` (o SWID vem com as chaves `{...}`).

O `.env` fica só no seu computador (está no `.gitignore`). **Nunca** compartilhe esses cookies: eles dão acesso à sua conta.

Rodar tudo:

```bash
python espn_collector.py && python nba_stats.py && python espn_projections.py
python build_base.py && python calibrate_teto.py && python rankings.py
python export_csv.py
python make_report.py
python history_collector.py   # só precisa rodar uma vez por temporada
```

| # | Script | O que faz | Saída (`data/`) |
|---|---|---|---|
| 1 | `espn_collector.py` | Rosters (com posições elegíveis), lesões, draft, times com conferência e agenda | `rosters.csv`, `draft.csv`, `teams.csv`, `schedule.csv` |
| 2 | `nba_stats.py` | Médias por jogo da NBA (2024-25, 2025-26, pré-temporada 2026-27) | `nba_player_stats.csv` |
| 3 | `espn_projections.py` | Projeção ESPN 2026-27 e média real 2025-26 em FP | `espn_projections.csv` |
| 4 | `build_base.py` | Junta rosters e stats da NBA por nome | `players_base.csv` |
| 5 | `calibrate_teto.py` | Calibra o teto (real ÷ projeção da temporada passada, por nível) | `teto_params.json`, `teto_calibration.md` |
| 6 | `rankings.py` | Power rank, projeção, starting five, depth e teto | `rankings.md`, `player_values.csv` |
| 7 | `export_csv.py` | CSV amigável dos elencos | `elencos_atuais.csv` |
| 8 | `make_report.py` | PDF com rankings e uma página por time | `reports/*.pdf` |
| 9 | `history_collector.py` | Histórico da liga por temporada (classificação final, campanha), ligado ao dono de cada time | `historico.csv`, `historico_donos.csv` |

Os confrontos ficam em `data/schedule.csv` (20 semanas, 6 jogos por semana). As conferências ficam em `data/teams.csv`.

Usando outra liga? Troque `LEAGUE_ID` em `config.py` (o número que aparece na URL da liga).

## C. Usar com a sua IA

Nenhum código é específico de uma IA. Duas formas:

- **Sem instalar nada:** baixe `data/elencos_atuais.csv` (e, se quiser, `data/rankings.md` ou o PDF), anexe na IA que preferir e pergunte.
  Exemplos: "qual time tem o melhor banco?", "sugira uma troca justa entre o time X e o time Y", "quem são os waiver pickups mais valiosos para o meu time?".
- **Com um agente de código** (Claude Code, Codex, Cursor, Gemini CLI...): abra a pasta do repositório. O arquivo [`AGENTS.md`](AGENTS.md) explica o projeto para o agente, que pode rodar o pipeline por você.

## Compartilhar este repositório

O repositório é do Tom. Duas opções:

1. **Privado + convidar amigos** (recomendado): no GitHub, `Settings > Collaborators > Add people`. Quem aceitar o convite consegue clonar. Cada um usa o **próprio** `.env`.
2. **Público:** `Settings > General > Danger Zone > Change visibility`. Qualquer um pode clonar ou dar fork. Antes de publicar, confirme que nenhum cookie foi commitado (`git log -p | grep -i espn_s2` não deve achar valores) e lembre que os nomes dos donos e o draft ficam visíveis a todos.

Para quem só vai ler: basta o PDF e o CSV, e dá para mandar esses dois arquivos direto, sem GitHub.

Quem quiser propor melhorias: fork, branch, pull request.

## Histórico da liga

`data/historico.csv` traz a classificação final e a campanha de cada time desde 2023-24 (primeira temporada disponível no ESPN).
Os nomes dos times mudam, então a franquia é seguida pelo **dono**: `data/historico_donos.csv` resume títulos, finais, pódios e trajetória de cada um.
Exemplos: Ajej's Ball Hustlers virou Little River Hustlers; Best Estimated virou Thanos; Pinetrees' Bulldogs e LOUD viraram Pinetrees' Dachshunds.

## Metodologia (resumo)

- **Valor atual** (FP por jogo, scoring da liga): 80% média real 2025-26 + 20% projeção ESPN 2026-27, se o jogador fez 41+ jogos. Com menos jogos, o peso da média cai proporcionalmente (16 jogos: 31%); sem jogos na temporada passada, vale só a projeção. Rookies usam a projeção. `OUT`, `INJURY_RESERVE` e `SUSPENSION` valem 0; `DAY_TO_DAY` conta como saudável.
- **Power rank:** soma dos 10 melhores valores do elenco.
- **Starting five:** uma vaga por posição (PG, SG, SF, PF, C). Cada jogador pode ocupar qualquer vaga para a qual é elegível no ESPN (um PF que também é C pode ser o C). A escolha é a combinação saudável de maior soma. Se uma vaga não tiver elegível saudável, entra o melhor disponível (marcado com `*`).
- **Depth:** os 8 melhores saudáveis fora do starting five.
- **Conferências e playoffs:** 12 times em duas conferências de 6 (East e West), 20 semanas regulares e 4 times nos playoffs.
- **Teto:** projeção ESPN × percentil 80 de (real ÷ projeção) do nível do jogador na temporada passada (top 50, 51-150, 151+). Rookies usam a turma de rookies de 2025-26 (até 24 anos); os dois primeiros picks do draft usam o percentil 90. O teto do time soma os 10 maiores.
- **Projeção de temporada:** soma das projeções totais do ESPN (inclui lesionados).
- **Rating (PDF):** média das posições nos 5 rankings; 4 melhores Overweight, 4 do meio Equal-weight, 4 últimos Underweight.

## Pontos validados

- `SEASON = 2027` em `config.py`: o ESPN usa o ano de término da temporada (projeções em `2027`, resultados reais em `2026`).
- Posições (`POSITION` em `config.py`): `1 = PG`, `2 = SG`, `3 = SF`, `4 = PF`, `5 = C`, conferido com jogadores conhecidos. Os ids 0, 6 e 7 nunca apareceram.
- Parser do ESPN: 156 jogadores e 156 picks, 12 times de 13 jogadores, sem campos vazios.
- Casamento ESPN × NBA por nome: 156 de 156.

## Limitações conhecidas

- A projeção do ESPN foi otimista na temporada passada (mediana de real ÷ projeção entre 0,94 e 0,98 nos três níveis). Os valores usam a projeção como ela vem.
- A posição vem do `defaultPositionId`; a elegibilidade múltipla do ESPN (ex.: PG/SG) não é usada.
- Aday Mara não tem projeção nem histórico e fica com valor 0.
- A amostra de rookies para calibrar o teto é pequena (21 jogadores).
- Os cookies do ESPN expiram de tempos em tempos; se o coletor der erro 401, pegue-os de novo.
