# Descobertas Factuais — Exploracao Docling

Data: 2026-04-13
PDFs testados:
- AGU — Anexo de Entregas PTD 2025-2027 (538 KB, 2 paginas, **imagem pura**)
- ANAC — Anexo de Entregas PTD 2025-2026 (220 KB, 1 pagina, **texto nativo**)

## 1. Natureza dos PDFs

| Orgao | Texto nativo? | Chars pypdfium2 | OCR necessario? |
|-------|--------------|-----------------|-----------------|
| AGU | NAO (imagem pura) | 0 | Sim (100%) |
| ANAC | SIM | 22.395 | Nao |

**Conclusao:** Alguns orgaos enviam PDF escaneado, outros enviam PDF com texto nativo.
O pipeline precisa funcionar com ambos.

## 2. API Docling — Mapa Real

```
doc.tables          → list[TableItem], len=3
doc.texts           → list[TextItem], len=14
doc.pages           → dict, len=2
doc.pictures        → list[PictureItem], len=1
doc.body            → GroupItem
doc.iterate_items() → gera (item, level) com tipos:
                      SectionHeaderItem(3), TextItem(2), TableItem(3), PictureItem(1)
doc.main_text       → NAO EXISTE (nosso ptd_extracao.py assumia que existia)
doc.export_to_markdown() → existe
doc.export_to_html()     → existe
```

### TableItem

```
table.data                → TableData
table.data.table_cells    → list[TableCell], 95 cells para tabela 0
table.data.num_rows       → 19
table.data.num_cols       → 5
table.prov                → list[ProvenanceItem]
table.prov[0].page_no     → 1
table.prov[0].bbox        → BoundingBox com coord_origin=BOTTOMLEFT
table.export_to_dataframe() → funciona! (deprecation warning sem arg doc)
table.export_to_markdown()  → funciona
table.export_to_html()      → funciona
```

### TableCell

```
cell.text                    → str (conteudo da celula)
cell.start_row_offset_idx    → int
cell.end_row_offset_idx      → int
cell.start_col_offset_idx    → int
cell.end_col_offset_idx      → int
cell.column_header           → bool
cell.row_header              → bool
cell.row_span                → int
cell.col_span                → int
cell.bbox                    → BoundingBox
```

## 3. Estrutura das tabelas

### AGU (3 tabelas)

| Tabela | Pagina | Rows x Cols | Colunas | Conteudo |
|--------|--------|-------------|---------|----------|
| 0 | 1 | 18x5 | Servico/Acao, Produto, Eixo, Area Responsavel, DtPactuada | Entregas pactuadas (principal) |
| 1 | 2 | 6x4 | sem header (PPSI ciclos) | Continuacao entregas PPSI |
| 2 | 2 | 11x5 | Servico/Acao, Produto, Eixo, Area Responsavel, DtEntrega | Entregas ja realizadas (historico) |

### ANAC (3 tabelas)

| Tabela | Pagina | Rows x Cols | Colunas | Conteudo |
|--------|--------|-------------|---------|----------|
| 0 | 1 | 54x5 | Servico/Acao, Produto, Eixo, Area Responsavel, DtPactuada | Entregas pactuadas |
| 1 | 1 | 72x5 | Servico/Acao, **Produto Eixo** (fundidos!), "", Area Responsavel, DtEntrega | Entregas realizadas |
| 2 | 1 | 1x3 | (assinaturas) | Nao relevante |

**Nota:** Tabela 1 da ANAC tem colunas "Produto" e "Eixo" fundidas num unico header "Produto Eixo".

## 4. Problema critico: texto com palavras grudadas

### Causa raiz

O problema **NAO e do OCR**. Testamos com:
- RapidOCR (padrao): texto grudado SEM acentos
- Tesseract CLI: texto COM acentos mas ainda com grudados residuais
- OCR desligado (ANAC, texto nativo): **mesmo problema de grudados**

A causa e o **layout do proprio PDF**: glifos sem espaco entre si. Isso acontece tanto em PDFs escaneados (AGU) quanto em PDFs nativos (ANAC).

### Padrao dos grudados

Os grudados sao **sistematicos e previsiveis** — sempre em pontos especificos:

| Padrao | Exemplo | Correcao |
|--------|---------|----------|
| `[a-z][A-Z]` | "daQualidade" | "da Qualidade" |
| `[a-z][A-Z]` | "eDados" | "e Dados" |
| `[a-z][A-Z]` | "emAcesso" | "em Acesso" |
| `[a-z][A-Z]` | "ferramentade" | → nao pega (ambas minusculas) |

### Quantificacao (ANAC, Tabela 0, 54 rows)

- **63%** das rows tem pelo menos 1 palavra grudada
- **2%** das rows tem overflow entre celulas (texto de uma coluna vaza para outra)
- Grudados concentrados na coluna **Eixo** ("daQualidade", "eDados")
- Overflow so em servicos com nome muito longo (Row 1)

### RapidOCR vs Tesseract (AGU, PDF escaneado)

| Aspecto | RapidOCR | Tesseract |
|---------|----------|-----------|
| Espacos entre palavras | Quase nenhum | Bom (maioria) |
| Acentos | Nenhum | Sim |
| Pipes nas celulas | Nao | Sim (|) |
| DtPactuada | Presente | Vazia |
| Lixo OCR | Pouco ("sensnsos") | Algum ("enmncuo") |
| Primeira row | OK (grudada) | Truncada ("er") |

**Decisao: usar Tesseract para PDFs escaneados** — texto muito superior apesar de artefatos residuais.

## 5. Configuracao Docling para Tesseract

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
from docling.datamodel.base_models import InputFormat

ocr_opts = TesseractCliOcrOptions(
    lang=["por"],
    force_full_page_ocr=True
)

pipeline_opts = PdfPipelineOptions()
pipeline_opts.do_ocr = True
pipeline_opts.ocr_options = ocr_opts

converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
    }
)
```

**Requisito de sistema:** `tesseract-ocr` e `tesseract-ocr-por` devem estar instalados.

Para PDFs com texto nativo (como ANAC), o OCR pode ser desligado:
```python
pipeline_opts.do_ocr = False
```

## 6. Estrategia de pos-processamento

### Passo 1: Corrigir palavras grudadas (regex)
```python
import re
def fix_glued_words(text: str) -> str:
    # Insere espaco entre minuscula e maiuscula
    return re.sub(r'([a-záéíóúãõç])([A-ZÁÉÍÓÚÃÕÇ])', r'\1 \2', text)
```

### Passo 2: Strip de artefatos OCR
```python
def clean_ocr_artifacts(text: str) -> str:
    text = text.strip('| ')           # pipes de borda
    text = re.sub(r'\s+', ' ', text)  # espacos multiplos
    return text.strip()
```

### Passo 3: Normalizar nomes de Eixo/Produto SGD
Usar dicionario de formas canonicas para corrigir variantes:
```python
EIXOS_CANONICOS = {
    "servicos digitais e melhoria da qualidade": "Serviços Digitais e Melhoria da Qualidade",
    "unificacao de canais digitais": "Unificação de Canais Digitais",
    "governanca e gestao de dados": "Governança e Gestão de Dados",
    "seguranca e privacidade": "Segurança e Privacidade",
}
```

### Passo 4: Detectar e classificar tipo de PDF
```python
import pypdfium2 as pdfium

def pdf_has_native_text(path: str) -> bool:
    pdf = pdfium.PdfDocument(path)
    for i in range(len(pdf)):
        text = pdf[i].get_textpage().get_text_range()
        if len(text) > 50:
            return True
    return False
```

## 7. Opcoes de OCR disponiveis no Docling

```
EasyOcrOptions
RapidOcrOptions        ← padrao, texto grudado sem acentos
TesseractOcrOptions    ← binding Python
TesseractCliOcrOptions ← CLI, melhor resultado para PT-BR
OcrAutoOptions
OcrMacOptions
KserveV2OcrOptions
```

## 8. Implicacoes para o pipeline

### O que funciona
- `doc.tables` como lista
- `table.export_to_dataframe()` para converter tabela em DataFrame
- `table.prov[0].page_no` para localizacao
- `table.data.table_cells` para acesso granular
- Headers detectados via `cell.column_header == True`
- Tesseract OCR produz texto legivel para PDFs escaneados

### O que precisa de correcao no ptd_extracao.py
1. **Remover referencia a `doc.main_text`** — nao existe
2. **Detectar tipo de PDF** (nativo vs escaneado) e ajustar OCR
3. **Usar Tesseract** para PDFs escaneados
4. **Pos-processamento de texto** (fix_glued_words + clean_ocr_artifacts)
5. **Tratar headers fundidos** (ex: "Produto Eixo" da ANAC tabela 1)
6. **Tratar tabela sem header** (ex: AGU tabela 1) como continuacao

### Aho-Corasick: viavel com pos-processamento
Apos fix_glued_words + normalizacao, os nomes de Produto ficam legiveis:
- "Integração à ferramenta de avaliação da satisfação dos usuários"
- "Disponibilização em Acesso Digital"
- "Integração ao Login Único"
- "Migração de Serviço para Plataforma Unificada"

Aho-Corasick pode funcionar se:
- Dicionario usar formas com acento (ou normalizar ambos para casefold+NFD)
- Matching tolerar variantes menores

## 9. Proximos passos

1. [x] Testar PDF de outro orgao → ANAC testado, problema confirmado como generalizado
2. [ ] Implementar pos-processamento (fix_glued_words + clean_ocr_artifacts)
3. [ ] Corrigir ptd_extracao.py com base nestas descobertas
4. [ ] Notebook 02: testar col_map LLM com headers reais pos-processados
5. [ ] Testar Aho-Corasick com texto normalizado
6. [ ] Testar com 3o orgao para validar generalizacao
