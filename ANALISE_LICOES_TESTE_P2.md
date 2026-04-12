# PTD-BR v2 — Analise de Licoes (Parte 2/2)

*Continuacao de [ANALISE_LICOES_TESTE_P1.md](ANALISE_LICOES_TESTE_P1.md)*

---

## 6. Causa raiz #1: col_map heuristico

Ref: [Briefing, III-A1]; [Briefing, Parte II]

| Orgao | Header real (col "servico") | col_map_ok no teste |
|-------|---------------------------|-------------------|
| AGU | "Entrega" | ~61% |
| INCRA | "Meta" | 0% |
| FUNAI | "Acao" | ~34% |
| MEC | "Descricao da Atividade" | ~0% |
| MD | "Produto/Servico" | ~40% |

Tentativas fracassadas: `col_keys_extra.json` por sigla (nao escalou), watcher ajustando thresholds (sintoma), expansao automatica de keywords (termos errados).

**Solucao (do Briefing Parte II):**
```
Voce esta analisando uma tabela de um Plano de Transformacao Digital (PTD)
do governo federal. Identifique qual coluna corresponde a cada campo semantico.
Cabecalhos da tabela: {headers}
Retorne JSON:
{"servico": "col ou null", "produto": "col ou null", "area": "col ou null",
 "data_prevista": "col ou null", "confianca": 0.0-1.0}
Se confianca < 0.7, inclua "motivo_incerteza".
```
Custo: ~$0.0025/tabela. ~$1 total p/ 90 orgaos. A decisao do LLM deve ser registrada por linha (ver modelo de proveniencia na P1).

---

## 7. Problemas tecnicos por orgao

### col_map (LLM resolve)
| Orgao | col_map_ok | Problema | Ref |
|-------|-----------|---------|-----|
| INCRA | 0% | Headers "Acao, Meta, Entrega" | III-A1 |
| ANS-PLANO | ~30% | Tabela risco misturada | III-A2 |
| MDA-DOCUME | ~20% | Sigla truncada + risco | III-A5 |

### OCR
| Orgao | Problema | Solucao | Ref |
|-------|---------|---------|-----|
| MEC | 80% NaN, PDFs escaneados | OCR 400 DPI | III-A4 |
| MD (parcial) | Tabelas como imagem | OCR 300 DPI | III-A4 |

Deteccao: `nan_ratio = 1 - (len(text) / expected_chars) > 0.8` → re-OCR. Config: `{'DEFAULT': {'dpi': 300, 'psm': 6, 'lang': 'por'}, 'MEC': {'dpi': 400}}`.

### Vocabulario (dominio especifico)
| Orgao | pct_ok | Dominio ausente |
|-------|--------|----------------|
| MD | ~40% | Militar/defesa |
| FUNAI | 34.5% | Povos indigenas |
| ITI | 45.9% | ICP-Brasil/certificacao |
| AGU | 61.5% | Juridico/consultoria |

### Eixo contaminado
PGFN: token "SAJ/IA" (pag 8) contamina E3 em 21 linhas E1. Fix: deteccao stateless por linha. Regra: orgao com E3 > 10 registros → verificar manualmente. [Briefing, III-A3]

### Siglas fantasma (excluir sempre) [Briefing, III-A5]
`ABNT-NBR-1`, `ASSINADO`, `21`, `MDA-DOCUME`, `MDA-ANEXO-`. Regras: len < 3 → excluir; contem digito → excluir (exceto lista branca).

---

## 8. Checklist operacional

Adaptado de [Briefing, Parte IV].

### Antes do 1o run
- [ ] `produtos_sgd_v23.json` carregado
- [ ] `is_risk_table()` testada
- [ ] LLM col_map testado com 3 tabelas reais
- [ ] Kill switch (`max_pdfs`, `max_orgaos`)
- [ ] Sensor (`ptd_run_summary.json`) implementado
- [ ] Proveniencia ativa (SHA + page + table_idx + raw_text + col_map_decision)
- [ ] Blocklist siglas fantasma ativa

### Pos-1o run — verificar
- [ ] Quantos orgaos >= 1 linha?
- [ ] col_map_ok_rate > 80%?
- [ ] Top 10 frases nao matchadas?
- [ ] Orgaos com pct_ok = 0%?
- [ ] Siglas fantasma presentes?
- [ ] Proveniencia funcional? (20 linhas aleatorias vs PDF)

### Criterios MVP vs S5

| Metrica | MVP | S5 (final) |
|---------|-----|-----------|
| Orgaos | >= 80 | >= 95% |
| pct_ok (ground truth) | >= 80% | >= 90% |
| col_map_ok_rate | >= 90% | >= 95% |
| sem_produto_pct | <= 15% | <= 10% |
| Siglas fantasma | 0 | 0 |

---

## 9. Artefatos a migrar

### Copiar intacto
| Artefato | Path no teste | Destino |
|----------|--------------|---------|
| Vocabulario | `config/produtos_sgd_v23.json` | `config/` |
| Correcoes eixo | `config/correcoes_eixo.json` | `config/` |
| `_is_risk_table()` | `ptd_pipeline_v30.py` | pipeline v2 |
| `is_image_pdf()` | `ptd_pipeline_v30.py` | pipeline v2 |
| OCR config | `ptd_ocr_fallback.py` | pipeline v2 |
| Prompt col_map | Briefing Parte II | CLAUDE.md |
| Blocklist siglas | Briefing III-A5 | config |

### Adaptar
`ptd_constants.py` (manter eixos/regex, ajustar paths). `ptd_healthcheck.py` (novo repo).

### Referencia (nao copiar)
`watcher.yml` (anti-padrao), `VSM_CLAUDE_SPINOFF.md` (teorico), `meta_learning.py` (slope — se S3 for necessario).

---

## 10. Balanco e proximos passos

| Dimensao | Estado |
|----------|--------|
| S1 (Pipeline) | 0% codigo. Artefatos prontos no teste |
| S2 (Config) | 70% — vocab e correcoes prontos, falta migrar |
| S3* (Auditoria) | 30% — schema documentado, nada implementado |
| S5 (Identidade) | 95% — definido no Briefing. pct_ok>=90%, cobertura>=95%, deadline 2026-07-01 |
| Ground truth | **Nao existe — Bloqueador #1** |

### Roadmap

```
P0 [AGORA]     Pushear esta analise ← feito
P1 [Semana 1]  Migrar config/ + detector risco + blocklist
P2 [Sem 1-2]   S1 minimo: 4 estagios lineares, 1 orgao end-to-end
P3 [Sem 2]     S3* desde inicio: run_summary + proveniencia completa
P4 [Sem 2-3]   Ground truth: 500 linhas (5 orgaos x 100) validadas
P5 [Sem 3-4]   Avaliar Docling MCP vs library
P6 [Sem 4-8]   Escalar 80+ orgaos, pct_ok>=80%
P7 [Sem 8-12]  Refinamento → pct_ok>=90%, cobertura>=95%
```

### Gates
P1→P2: artefatos migrados + CLAUDE.md criado | P2→P3: S1 roda em 1 orgao | P3→P4: proveniencia funcional (20 linhas) | P4→P5: ground truth existe | P5→P6: decisao MCP/lib | P6→P7: 80+ orgaos com pct_ok>=80%

---

*Fonte: [`NOVA_SESSAO_BRIEFING.md`](https://github.com/freirelucas/ptd-br-corpus-de-planos-de-transforma-o-digital/blob/main/NOVA_SESSAO_BRIEFING.md) (426 linhas) + [`teste`](https://github.com/freirelucas/teste/tree/claude/setup-docling-pipeline-g11gg) (150+ commits, 28+ arquivos).*
