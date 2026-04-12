# PTD-BR v2 — Analise de Licoes do Repositorio `teste`

**Data:** 2026-04-12 | **Fonte:** [`NOVA_SESSAO_BRIEFING.md`](https://github.com/freirelucas/ptd-br-corpus-de-planos-de-transforma-o-digital/blob/main/NOVA_SESSAO_BRIEFING.md) + [`CLAUDE.md` do teste](https://github.com/freirelucas/teste/blob/claude/setup-docling-pipeline-g11gg/CLAUDE.md)

> Este documento **analisa** os fontes acima. Nao os substitui. Convencao: `[Briefing, III-A1]` = NOVA_SESSAO_BRIEFING.md, Parte III, secao A1.

---

## 1. Resumo Executivo

O repo `teste` (branch `claude/setup-docling-pipeline-g11gg`) construiu um pipeline de extracao dos **Planos de Transformacao Digital (PTD)** do governo federal. Em ~213 iteracoes/150+ commits: 59 orgaos, 18.396 entregas, classificacao Aho-Corasick (74 produtos), watcher autonomo (GitHub Actions a cada 5 min), governanca VSM 3 niveis.

**Resultado:** pct_ok ~75% (meta 90%). Watcher preso em loop vazio nas ultimas 34 iteracoes. **Causa raiz:** col_map heuristico (75% do ruido) nunca corrigido — 213 iteracoes de ajuste parametrico em vez de 1 chamada LLM/tabela.

---

## 2. O que deu certo — reutilizar

| Artefato | Fonte no teste | Por que funciona |
|---|---|---|
| Vocabulario canonico (74 termos) | [`config/produtos_sgd_v23.json`](https://github.com/freirelucas/teste/blob/claude/setup-docling-pipeline-g11gg/config/produtos_sgd_v23.json) | Aho-Corasick O(n), deterministico, auditavel |
| Dedup SHA-256 | `ptd_pipeline_v30.py` | Idempotencia entre runs |
| `_is_risk_table()` | `ptd_pipeline_v30.py` | Filtra tabelas de risco (>=2 de: risco, probabilidade, impacto, severidade, mitigacao, ameaca) |
| Sensor S3* | `gerar_relatorio.py` → `ptd_run_summary.json` | Separacao sensor/atuador |
| `top_unmatched_phrases` | no run_summary | Diz **o que** falta (>=50: add vocab, >=20: revisar, >=5: acumular) [Briefing, III-B4] |
| Per-sigla decomposition | `por_orgao` no run_summary | Acao cirurgica por orgao |
| Prompt LLM col_map | [Briefing, Parte II] | Resolve causa raiz #1 por ~$0.0025/tabela |
| `ptd_constants.py` | [teste](https://github.com/freirelucas/teste/blob/claude/setup-docling-pipeline-g11gg/ptd_constants.py) | Fonte unica de verdade (eixos, regex) |
| CLAUDE.md | [teste](https://github.com/freirelucas/teste/blob/claude/setup-docling-pipeline-g11gg/CLAUDE.md) | Onboarding IA instantaneo |
| Dual license + CITATION.cff | teste | Publicacao academica pronta |

---

## 3. O que deu errado — 6 falacias + 1 anti-padrao

> Ref teorica: Stafford Beer, "Brain of the Firm" (1972); Philipp Enderle, "Your AI Agents Need an Org Chart" (dev.to, 2025)

**Nota VSM:** O teste nomeava etapas do pipeline como S1-S4 ("S1 Coleta, S2 Extracao..."). Errado. O pipeline **inteiro** e S1 (Operacoes). S2-S5 sao funcoes de controle *sobre* S1. Esta analise usa Beer/Enderle correto.

### F1: Complexidade como fim em si
Ref: [CLAUDE.md, VSM]; [VSM_CLAUDE_SPINOFF.md, 25KB]. Ergueu S1-S5 + recursao 3 niveis antes de S1 funcionar. Codigo de governanca > codigo de extracao. **Licao:** S1 robusto primeiro.

### F2: Otimizacao sem ground truth
Ref: [Briefing, III-E2]. 213 iteracoes otimizando `pct_ok` (metrica interna). `gerar_validacao_manual.py` veio na iteracao ~150+. S3* verificava reports, nao artefatos. **Licao:** 500 linhas validadas por humano antes de loop.

### F3: Heuristica onde LLM resolve
Ref: [Briefing, III-A1]. col_map com keywords fixas: INCRA 0%, FUNAI 34%, MEC ~0%. Custo: 213 iter x 5min CI = ~17h. LLM: ~$1 total p/ 90 orgaos. **Licao:** LLM p/ estrutura ambigua, automata p/ semantica.

### F4: Loop sem kill switch
Ref: [CLAUDE.md, .trigger_debug]. Watcher rodou 100+ iter antes de max_iteration. Ultimas 34: "fix para 0 orgaos zerados" com N_ZERO=0. **Licao:** Kill switch antes do 1o run autonomo.

### F5: Expansao de vocab sem curacao
Ref: [Briefing, III-B4]. Watcher adicionou nomes de pessoas ao vocabulario canonico. S2 corrompido por S3. **Licao:** S2 curado por humano; S3 sugere, nao executa.

### F6: Escopo divergente
Multiplos projetos no mesmo repo, branches divergentes. S5 ambiguo → S1 diverge. **Licao:** Um repo, uma missao, um S5.

### Anti-padrao: watcher auto-referente
Ref: [CLAUDE.md, Loop cibernetico]. S3 commitava fix → disparava S1 → S3* lia mesmo resultado → S3 aplicava mesmo fix. Sem diff temporal. **Licao:** S3* verifica artefatos. S3 compara deltas.

---

## 4. Rastreabilidade extracao ↔ origem

Ref: [Briefing, I]; `ptd_pipeline_v30.py`

**Teste tinha:** pdf_sha256 + pagina. **Faltava:** tabela_idx, linha_idx, raw_text, col_map_decision, bbox.

**Docling ja fornece nativamente:** `ProvenanceItem` (page_no + bbox + charspan), `TableCell` (coordenadas), `TableData` (geometria). O teste descartava `prov` e `bbox`. Custo zero de preservar.

Modelo por linha:
```json
{"corpus_row_id": 4217, "sigla": "INCRA", "servico": "Georreferenciamento",
 "proveniencia": {"pdf_sha256": "a1b2...", "pagina": 8, "tabela_idx": 2,
  "linha_idx": 5, "raw_text": "Georreferenciamento | Meta | 31/12/2025",
  "col_map_aplicado": {"Acao": "servico"}, "col_map_confianca": 0.85}}
```

**Docling MCP** (`docling-mcp`): alternativa que unifica extracao + col_map. Config: `{"mcpServers": {"docling": {"command": "uvx", "args": ["--from=docling-mcp", "docling-mcp-server"]}}}`. Decisao adiada ate piloto com 5 orgaos.

---

## 5. VSM corrigido (Beer/Enderle)

```
S1 — OPERACOES (pipeline inteiro, 4 estagios):
  1-Coleta  2-Extracao(Docling/OCR)  3-Col_map(LLM)  4-Classificacao(Aho-Corasick)

S2 — COORDENACAO (regras laterais): config/ (vocab, correcoes, org_meta)
S3 — OTIMIZACAO: NAO antes de ground truth
S3* — AUDITORIA (desde o inicio): ptd_run_summary.json + top_unmatched
S4 — INTELIGENCIA (futuro): monitorar portal gov.br
S5 — IDENTIDADE (estatico): pct_ok>=90%, cobertura>=95%, deadline 2026-07-01
```

Ordem: S1 → S3* → S5(existe) → S2(migrar) → S3(pos-ground truth) → S4(futuro)

---

*Continua em [ANALISE_LICOES_TESTE_P2.md](ANALISE_LICOES_TESTE_P2.md) — secoes 6-11*
