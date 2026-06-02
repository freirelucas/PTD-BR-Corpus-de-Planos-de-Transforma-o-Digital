# CLAUDE.md — PTD-BR Corpus v2

Guia para assistentes IA trabalhando neste repositorio.

## Missao (S5)

Extrair e estruturar os **Planos de Transformacao Digital (PTD)** dos orgaos do Governo Federal Brasileiro, produzindo um corpus analitico com entregas, produtos, eixos EFGD e riscos.

| Meta S5 | Valor |
|---------|-------|
| pct_ok global | >= 90% (ground truth) |
| Cobertura documental | >= 95% orgaos |
| sem_produto_pct | <= 10% |
| col_map_ok_rate | >= 95% |
| Deadline | 2026-07-01 |

Fonte normativa: Portaria SGD/MGI 6.618/2024. Escopo: ~130 PDFs de ~90 orgaos, ciclo PTD 2025.

## Arquitetura VSM (Beer/Enderle)

> Os sistemas VSM nao sao etapas de pipeline. Sao funcoes de controle que coexistem.

```
S1 — OPERACOES (pipeline em 4 estagios):
  Estagio 1: Coleta (scraping gov.br + download + SHA-256 dedup)
  Estagio 2: Extracao (Docling texto nativo + Tesseract OCR fallback)
  Estagio 3: Col-map via LLM (Haiku identifica colunas -> JSON)
  Estagio 4: Classificacao semantica (Aho-Corasick + regex eixos + parse_flag)

S2 — COORDENACAO (regras laterais, curadas por humano):
  config/produtos_sgd_v23.json — vocabulario canonico (64 termos)
  config/correcoes_eixo.json — correcoes de eixo (auditoria manual)

S3* — AUDITORIA (implementar desde o inicio):
  ptd_run_summary.json — sensor independente
  top_unmatched_phrases — sinal de acao direta

S5 — IDENTIDADE: metas acima. Inegociaveis.
S3 (Otimizacao): NAO antes de ground truth.
S4 (Inteligencia): Futuro.
```

## Estrutura de arquivos

| Arquivo | Papel |
|---------|-------|
| `ptd_constants.py` | Fonte unica: eixos EFGD, regex, dirs, detectar_eixo() |
| `ptd_utils.py` | Utilidades: is_risk_table(), is_image_pdf(), blocklist siglas |
| `config/produtos_sgd_v23.json` | Vocabulario canonico Aho-Corasick (S2) |
| `config/correcoes_eixo.json` | Regras de correcao de eixo (S2) |
| `NOVA_SESSAO_BRIEFING.md` | Passaporte de memoria do repo teste (426 linhas) |
| `ANALISE_LICOES_TESTE_P1.md` | Analise: acertos, falacias, VSM, rastreabilidade |
| `ANALISE_LICOES_TESTE_P2.md` | Analise: causa raiz, orgaos, checklist, roadmap |

## Convencoes

- Prefixo `ptd_`: todos os scripts e outputs
- Constantes compartilhadas: importar de `ptd_constants.py`, nunca redefinir
- Config S2: curada por humano. Automacao sugere, nao executa
- Proveniencia: toda linha do corpus deve ter pdf_sha256 + pagina + tabela_idx + raw_text + col_map_decision

## Campos obrigatorios no corpus final

```
sigla, servico, produto, eixo, area, data_prevista,
parse_flag (ok|sem_produto|sem_servico|ruido|vazio),
pdf_sha256, pagina, tabela_idx, linha_idx, raw_text,
col_map_aplicado, col_map_confianca, col_map_fonte
```

## Produtos PPSI mandatorios (todo orgao deve ter)

1. Implementacao do PPSI
2. Auto-avaliacao, analise de lacunas e planejamento do PPSI
3. Implementacao das recomendacoes do autodiagnostico de qualidade
4. Realizacao de Autodiagnostico de Qualidade

Ausencia = falha de extracao, nao ausencia do orgao.

## Orgaos problematicos (diagnosticados no teste)

| Orgao | Problema | Estrategia |
|-------|---------|-----------|
| INCRA | col_map 0% | LLM col_map |
| MEC | 80% NaN (PDF-imagem) | OCR 400 DPI |
| MD | Vocab militar ausente | Expandir S2 |
| FUNAI | Vocab indigena ausente | Expandir S2 |
| ITI | Vocab ICP-Brasil ausente | Expandir S2 |
| AGU | Vocab juridico ausente | Expandir S2 |
| PGFN | Eixo E3 contamina E1 | Deteccao stateless |
| ANS-PLANO | Tabela risco misturada | is_risk_table() |

## Estado atual

- **Passo:** P1 concluido (artefatos migrados)
- **Proximo:** P2 — construir S1 minimo (1 orgao end-to-end)
- **Bloqueador:** Ground truth nao existe (Passo 4)

## Historico

- Repo anterior: `freirelucas/teste`, branch `claude/setup-docling-pipeline-g11gg`
- 213 iteracoes, pct_ok ~75%, meta 90%. Nao convergiu.
- Causa raiz: col_map heuristico (75% do ruido). Solucao: LLM.
- Analise completa: `ANALISE_LICOES_TESTE_P1.md` + `P2.md`
