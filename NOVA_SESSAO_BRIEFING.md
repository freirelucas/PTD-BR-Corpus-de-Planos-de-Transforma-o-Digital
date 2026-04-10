# PTD-BR — Briefing para Nova Sessão
## S5 Estático + Apêndice de Aprendizados Acumulados

**Data de geração:** 2026-04-10  
**Iterações anteriores:** ~213 (branch `claude/setup-docling-pipeline-g11gg`) + ~20 (reinício)  
**Status:** Projeto reiniciado em novo repositório — este documento é o passaporte de memória

---

## PARTE I — S5 ESTÁTICO (Política e Identidade do Sistema)

> S5 é a razão de existir. Não muda por iteração. Define o que nunca se negocia.

### Missão (uma frase)

Extrair e estruturar automaticamente os **Planos de Trabalho Departamental (PTD)** dos órgãos do Governo Federal Brasileiro, produzindo um corpus analítico com entregas, produtos, eixos EFGD e riscos — com cobertura ≥ 95% dos órgãos e qualidade ≥ 90% das linhas.

### Fonte normativa

- **Portal**: gov.br — Estratégia Federal de Governo Digital (EFGD)
- **Portaria de referência**: SGD/MGI nº 6.618/2024
- **Escopo**: ~130 PDFs de ~90 órgãos do Poder Executivo Federal
- **Ciclo**: PTD 2025 (dados publicados em 2025, coletados em 2026)

### Critérios S5 (não-negociáveis, mensuráveis)

| Critério | Valor-alvo | Inegociável? |
|---------|-----------|-------------|
| `pct_ok` global | ≥ 90% | Sim |
| Cobertura documental | ≥ 95% órgãos com extração | Sim |
| `sem_produto_pct` | ≤ 10% | Sim |
| `col_map_ok_rate` | ≥ 95% | Sim |
| Preservação de corpus | ≥ 98% registros não-nulos | Sim |
| Deadline | 2026-07-01 (prazo novo) | Sim |

### Campos obrigatórios no corpus final

Cada linha do corpus deve conter:

```
sigla          — identificador do órgão (ex: AGU, IBGE, FUNAI)
servico        — descrição da entrega/ação
produto        — produto EFGD correspondente (vocabulário canônico)
eixo           — eixo EFGD (1 a 6)
area           — área responsável (quando disponível)
data_prevista  — prazo (quando disponível)
parse_flag     — ok | sem_produto | sem_servico | ruido | vazio
pdf_sha256     — hash do PDF fonte (rastreabilidade)
pagina         — página de origem
```

### Produtos canônicos obrigatórios (presentes em todo órgão)

Todo órgão deve ter pelo menos uma linha com cada um destes produtos:

1. `Implementação do PPSI`
2. `Auto-avaliação, análise de lacunas e planejamento do PPSI`
3. `Implementação das recomendações do autodiagnóstico de qualidade`
4. `Realização de Autodiagnóstico de Qualidade`

Se algum órgão não tiver estes produtos → falha de extração, não ausência do órgão.

### Os 6 Eixos EFGD (vocabulário oficial)

| Eixo | Nome | Palavras-chave principais |
|------|------|--------------------------|
| 1 | Centrado no Cidadão e Inclusivo | cidadão, inclusiv, serviços digitais, unificação de canais |
| 2 | Integrado e Colaborativo | integrad, colaborat, interoperab, barramento, ecossistema |
| 3 | Inteligente e Inovador | inteligent, inovad, governança de dados, gestão de dados |
| 4 | Confiável e Seguro | confiável, segur, privacidade, PPSI, LGPD |
| 5 | Transparente, Aberto e Participativo | transpar, dados abertos, LAI, controle social |
| 6 | Eficiente e Sustentável | eficien, sustent, desburocrat, simplifica, moderniza |

---

## PARTE II — ARQUITETURA RECOMENDADA (novo projeto)

> A arquitetura anterior falhou por complexidade autorreferencial. Esta é lean e linear.

### Pipeline em 4 estágios

```
[S1] Coleta
  Portal gov.br → scraping de URLs de PTD
  Download PDFs → raw_pdfs/
  Deduplicação por hash SHA256

[S2] Extração
  Docling → PDFs com texto nativo (maioria)
  Tesseract/pytesseract → PDFs-imagem (OCR fallback)
  Critério: página com >80% NaN text = imagem → OCR

[S3] Col-map via LLM  ← MUDANÇA CRÍTICA em relação ao projeto anterior
  Prompt para Haiku/Flash identificar: qual coluna é serviço? produto? área? data?
  Retorno JSON estruturado por tabela
  Elimina 80% do ruído do projeto anterior

[S4] Classificação semântica
  Aho-Corasick contra vocabulário canônico (produtos_sgd_v23.json)
  Regex de eixos por palavras-chave
  parse_flag por linha
```

### Por que LLM no col-map?

O **col_map heurístico** foi a causa raiz de 75% do ruído no projeto anterior. Cada órgão usa headers diferentes:

| Órgão | Header real (coluna "serviço") |
|-------|-------------------------------|
| AGU | "Entrega" |
| INCRA | "Meta" |
| FUNAI | "Ação" |
| MEC | "Descrição da Atividade" |
| MD | "Produto/Serviço" |

Um LLM de baixo custo (Haiku: ~$0.0025/1K tokens) resolve isso com 1 chamada por tabela.
213 iterações de heurística frágil custaram mais do que isso.

---

## PARTE III — APÊNDICE DE APRENDIZADOS (213+ iterações)

### A. Falhas fundamentais identificadas

#### A1. col_map heurístico — causa raiz #1

**O problema:** A função que detecta qual coluna do PDF é "serviço/produto/área/data" usava keywords fixas (`col_keys`). Cada órgão usa terminologia diferente. INCRA tem "Meta" onde deveria estar "Entrega". MEC tem "Descrição da Atividade".

**Tentativas fracassadas:**
- `col_keys_extra.json`: overrides manuais por sigla → não escalou
- Loop de 213 iterações ajustando thresholds → ajustou sintoma, não causa

**Solução correta:** LLM identifica headers na primeira passagem. Zero heurística.

---

#### A2. Tabelas de risco extraídas como entregas — causa raiz #2

**O problema:** Muitos PDFs têm tabela de riscos E tabela de entregas. O pipeline não distinguia. Resultado: registros de "Risco de Segurança da Informação" eram classificados como entregas.

**Siglas afetadas:** ANS-PLANO, MDA-DOCUME, INCRA, MD.

**Fix implementado no projeto anterior (funciona):**
```python
def _is_risk_table(headers: list[str]) -> bool:
    RISK_MARKERS = {"risco", "probabilidade", "impacto", "severidade", "mitigação", "ameaça"}
    return len(set(h.lower() for h in headers) & RISK_MARKERS) >= 2
```
**Levar para o novo projeto — funciona.**

---

#### A3. State machine de eixo contamina registros — bug de design

**O problema:** Detecção de eixo usava estado persistente entre linhas. Um token forte ("SAJ/IA" → E3) persistia incorretamente pelas 21 linhas seguintes.

**Caso documentado:** PGFN — página 8, linha 1 "SAJ/IA" contamina E3 em serviços de certidão/dívida ativa (que são E1).

**Fix:** Detectar eixo por linha independentemente. Estado persistente só se linha não tiver nenhum indicador.

**Regra de auditoria:** Qualquer órgão com E3 > 10 registros → verificar manualmente se são AI genuínos ou contaminação.

---

#### A4. OCR sem calibração por DPI — problema MEC e similares

**O problema:** PDFs-imagem escaneados em baixa qualidade. Tesseract padrão (72 DPI) produz 80% NaN.

**Fix que funcionou:** 300 DPI mínimo para PDFs identificados como imagem. Detecção: `texto_extraido / total_chars < 0.2`.

**Siglas que precisam de OCR:** MEC (93 registros, ~80% NaN), algumas páginas de MD, FUNAI.

---

#### A5. Siglas fantasma na extração

**O problema:** Artefatos de extração criavam "siglas" inválidas no corpus.

**Lista para filtrar (excluir sempre):**
- `ABNT-NBR-1` — norma técnica, não órgão federal
- `ASSINADO` — linha de assinatura de PDF
- `21` — prefixo de nome de arquivo extraído como sigla
- `MDA-DOCUME`, `MDA-ANEXO-` — sigla truncada por bug de extração (regex quebrado)
- Qualquer sigla com < 3 caracteres
- Qualquer sigla com dígito (exceto lista branca explícita)

---

### B. O que funcionou bem (levar para o novo projeto)

#### B1. Aho-Corasick para classificação semântica

Rápido, determinístico, auditável. Com vocabulário correto, classifica milhares de linhas em <1s. Manter exatamente como está.

**Arquivo:** `config/produtos_sgd_v23.json` (74 termos, ordem importa — mais específico primeiro)

---

#### B2. Deduplicação por SHA256

Garante idempotência. PDF baixado duas vezes → mesmo hash → não reprocessa. Crítico para pipelines que rodam múltiplas vezes.

---

#### B3. Sensor independente (ptd_run_summary.json)

O `gerar_relatorio.py` produz um JSON legível por IA com métricas reais. Isso funcionou bem: o watcher lia o JSON e tomava decisões. **Separar sensor de atuador é design correto.**

Schema mínimo para o novo projeto:
```json
{
  "gerado_em": "ISO8601",
  "pct_ok": 73.2,
  "sem_produto_pct": 24.3,
  "col_map_ok_rate": 80.0,
  "orgaos_processados": 65,
  "orgaos_zero_rows": 4,
  "top_unmatched_phrases": [
    {"frase": "Projetos Especiais", "count": 115},
    {"frase": "Segurança e Privacidade", "count": 78}
  ],
  "por_orgao": {
    "AGU": {"pct_ok": 61.5, "n_rows": 130, "parse_flags": {...}},
    "MEC": {"pct_ok": 0.0, "n_rows": 93, "problema": "ocr"}
  }
}
```

---

#### B4. `top_unmatched_phrases` como sinal de ação

As frases mais frequentes sem match no vocabulário canônico dizem **exatamente o que expandir**. Regra operacional:

- Frase com count ≥ 50 → adicionar ao vocabulário canônico imediatamente
- Frase com count ≥ 20 → revisar se é produto, eixo ou ruído
- Frase com count ≥ 5 → acumular para próximo ciclo

---

#### B5. Per-sigla decomposition

Tratar cada órgão como unidade autônoma de diagnóstico. `por_orgao` no run_summary com `pct_ok`, `n_rows`, `problema` por sigla permite ação cirúrgica.

---

#### B6. _is_risk_table() — detector de tabela de risco

Funciona. Previne extração de tabelas erradas. Ver código em `ptd_pipeline_v30.py`.

---

### C. Vocabulário canônico — estado atual

**74 produtos canônicos** em `config/produtos_sgd_v23.json`. Cobrem a maioria dos órgãos.

**Lacunas identificadas (frases não matchadas de alta frequência):**

| Frase | Count | Ação recomendada |
|-------|-------|-----------------|
| Projetos Especiais | 115 | Adicionar como produto canônico |
| Segurança e Privacidade | 78 | Mapear para Eixo 4 / produto PPSI |
| Governança e Gestão de Dados | 75 | Adicionar como produto (subeixo E3) |
| Integração à ferramenta de avaliação | 61 | col_keys por sigla, não vocab |
| Serviços Digitais e Melhoria da... | 58 | Truncamento — regex mais largo |
| Transformação Digital dos Serviços | 44 | Adicionar como produto |

---

### D. Órgãos por estratégia de solução

#### D1. Precisam de vocabulário expandido
| Órgão | pct_ok atual | Problema |
|-------|-------------|---------|
| MD | ~40% | Vocabulário militar/defesa ausente |
| FUNAI | 34.5% | Vocabulário de povos indígenas ausente |
| ITI | 45.9% | Vocabulário ICP-Brasil e certificação digital ausente |
| AGU | 61.5% | Vocabulário jurídico/consultoria ausente |
| SGPR | 73.3% | Terminologia Secretaria-Geral específica |

**Ação:** Adicionar ao vocabulário canônico. Extrair top_unmatched de cada um.

#### D2. Precisam de col_map corrigido
| Órgão | col_map_ok | Problema |
|-------|-----------|---------|
| INCRA | 0% | Headers "Ação, Meta, Entrega" não reconhecidos |
| ANS-PLANO | ~30% | Tabela de risco misclassificada como entregas |
| MDA-DOCUME | ~20% | Idem + sigla truncada no processo de extração |

**Ação:** LLM col_map resolve INCRA e similares automaticamente.

#### D3. Precisam de OCR melhorado
| Órgão | Problema |
|-------|---------|
| MEC | 93 registros, ~80% NaN — PDFs escaneados em baixa qualidade |
| Parte de MD | Páginas de tabelas como imagem |

**Ação:** Re-OCR com 300 DPI mínimo. Detecção: `nan_ratio > 0.8` na página.

---

### E. Lições de design de sistema

#### E1. Complexidade autorreferencial mata

O projeto anterior construiu S1, S2, S3, S3*, S4, S5, recursão de 3 níveis, VSM spinoff, Claude hooks — e chegou a 73% de pct_ok após 213 iterações. A complexidade virou um fim em si.

**Princípio para o novo projeto:** Adicionar complexidade apenas quando a simples falhar comprovadamente. Começar com pipeline linear. Adicionar sensor. Adicionar classificação. Medir. Só aí decidir se precisa de loop.

#### E2. Ground truth é insubstituível

213 iterações de refinamento autônomo sem validação humana. O sistema aprendeu a se otimizar, não a acertar. A interface de validação manual (gerar_validacao_manual.py) veio tarde.

**Para o novo projeto:** Criar amostra de ground truth (500 linhas validadas manualmente) **antes** de qualquer loop autônomo. Medir contra ground truth, não apenas pct_ok interno.

#### E3. O sinal `top_unmatched_phrases` é o mais valioso

É o único sinal que diz diretamente O QUE o sistema não sabe. Todo o resto (slope, pct_ok, col_map_ok) diz que existe problema. Só o top_unmatched diz onde está.

#### E4. Separar sensor de atuador desde o início

`ptd_run_summary.json` (sensor independente) vs watcher (atuador) foi o design correto. O problema foi implementar tarde. No novo projeto: primeiro o sensor, depois qualquer automação.

#### E5. Loop autônomo requer kill switch óbvio

O loop autônomo rodou mesmo quando não devia. O mecanismo de parada (max_iteration) veio depois de 100+ iterações. No novo projeto: kill switch antes do primeiro run autônomo.

---

## PARTE IV — CHECKLIST PARA NOVA SESSÃO

### Antes de rodar o pipeline

- [ ] Vocabulário canônico carregado (`produtos_sgd_v23.json`)
- [ ] Regras de eixo testadas contra 10 exemplos conhecidos
- [ ] `_is_risk_table()` implementada e testada
- [ ] LLM col_map implementado e testado com 3 tabelas reais
- [ ] Kill switch implementado (max_pdfs, max_orgaos, flag de parada)
- [ ] Sensor de diagnóstico implementado (run_summary.json ou equivalente)

### Primeiro run — verificar

- [ ] Cobertura: quantos órgãos extraíram ≥ 1 linha?
- [ ] col_map_ok_rate: > 80%?
- [ ] Quais são as top 10 frases não matchadas?
- [ ] Quais órgãos têm pct_ok = 0%? (problema de OCR ou col_map)
- [ ] Quais órgãos estão gerando siglas fantasma?

### Critério de sucesso mínimo (MVP)

- ≥ 80 órgãos processados (de ~90 esperados)
- pct_ok ≥ 80% global
- col_map_ok_rate ≥ 90%
- Nenhuma sigla fantasma no corpus

---

## APÊNDICE — REFERÊNCIAS TÉCNICAS

### Configurações que funcionam

**OCR Tesseract para PDFs-imagem:**
```python
OCR_CONFIG = {
    'DEFAULT': {'dpi': 300, 'psm': 6, 'lang': 'por'},
    'MEC': {'dpi': 400, 'psm': 6, 'lang': 'por'},  # PDFs muito ruins
}
```

**Detecção de PDF-imagem:**
```python
def is_image_pdf(text_extracted: str, total_chars_expected: int) -> bool:
    if total_chars_expected == 0:
        return True
    nan_ratio = 1 - (len(text_extracted.strip()) / total_chars_expected)
    return nan_ratio > 0.8
```

**Detector de tabela de risco:**
```python
RISK_MARKERS = {"risco", "probabilidade", "impacto", "severidade", "mitigação", "ameaça"}

def is_risk_table(headers: list[str]) -> bool:
    normalized = {h.lower().strip() for h in headers}
    return len(normalized & RISK_MARKERS) >= 2
```

**Prompt LLM para col_map (exemplo Haiku):**
```
Você está analisando uma tabela de um Plano de Trabalho Departamental (PTD) do governo federal.
Identifique qual coluna corresponde a cada campo semântico.

Cabeçalhos da tabela: {headers}

Retorne JSON:
{
  "servico": "nome_coluna ou null",
  "produto": "nome_coluna ou null",
  "area": "nome_coluna ou null",
  "data_prevista": "nome_coluna ou null",
  "confianca": 0.0 a 1.0
}

Se confianca < 0.7, inclua "motivo_incerteza".
```

### Siglas e suas particularidades documentadas

| Sigla | Problema | Solução |
|-------|---------|---------|
| INCRA | col_map 0% — headers "Ação/Meta/Entrega" | LLM col_map |
| MEC | 80% NaN — scanned PDF | OCR 400 DPI |
| MD | Vocab militar ausente | Expandir vocabulário |
| FUNAI | Vocab indígena ausente | Expandir vocabulário |
| ITI | Vocab ICP-Brasil ausente | Expandir vocabulário |
| AGU | Vocab jurídico ausente | Expandir vocabulário |
| PGFN | State machine E3 contamina E1 | Detecção de eixo stateless |
| ANS-PLANO | Tabela de risco extraída | _is_risk_table() |
| MDA-DOCUME | Sigla truncada + tabela risco | Regex sigla + _is_risk_table() |
| ABNT-NBR-1 | Não é órgão federal | Excluir sempre |

---

*Documento gerado em 2026-04-10 para portabilidade entre sessões.*  
*Projeto anterior: `freirelucas/teste` branch `claude/setup-docling-pipeline-g11gg`.*  
*Vocabulário canônico: `config/produtos_sgd_v23.json` — levar para o novo projeto.*
