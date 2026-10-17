# Fantasy NBA (ESPN) — base de dados e rankings

Coleta local dos elencos da liga ESPN e stats da NBA para gerar rankings
(power rank, starting five, depth, teto).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencha ESPN_S2 e SWID
```

Cookies: no navegador, logado no ESPN Fantasy, abra DevTools > Application >
Cookies > fantasy.espn.com e copie `espn_s2` e `SWID`.

## Rodar

```bash
python espn_collector.py   # gera data/rosters.csv e data/draft.csv
python nba_stats.py        # gera data/nba_player_stats.csv
```

## Pontos em aberto (validar na primeira execução)

- `SEASON` em `config.py`: confirmar o ano que o ESPN usa para 2026-27.
- Mapeamento de posições (`POSITION` em `espn_collector.py`): conferir com um jogador conhecido.
- Os campos do JSON do ESPN podem variar; se o CSV sair vazio ou com `None`, o problema está no parser.

## Privacidade

Cookies e `.env` nunca vão para o repositório (estão no `.gitignore`).
