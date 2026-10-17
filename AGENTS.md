# Instruções para agentes de IA

Projeto: base de dados e rankings da liga ESPN Fantasy NBA "Basquetobol Teorico Diplos" (pontos). Leia o `README.md` primeiro.

- Para perguntas sobre elencos, use `data/elencos_atuais.csv` (não precisa de API nem de cookies). Valores em fantasy points (FP) por jogo, salvo colunas marcadas como total.
- Para atualizar os dados, rode os scripts na ordem da tabela do README. Exigem `.env` com `ESPN_S2` e `SWID` do usuário.
- Nunca leia, imprima, commite ou envie o conteúdo do `.env`.
- Regras de negócio estão no README (Metodologia). Mudanças de fórmula ficam em `rankings.py` e `calibrate_teto.py`.
- Posições: `POSITION` em `config.py`. Temporada: `SEASON = 2027` significa 2026-27.
- Depois de mudar código, rode `python rankings.py && python export_csv.py && python make_report.py` e confira se o PDF gera sem erro.
