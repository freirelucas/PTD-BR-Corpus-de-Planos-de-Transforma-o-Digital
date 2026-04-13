# Descobertas Factuais — Exploracao Docling (AGU)

Data: 2026-04-13
PDF testado: AGU — Anexo de Entregas PTD 2025-2027 (538 KB, 2 paginas)

## 1. Natureza do PDF

O PDF da AGU e **imagem pura** (escaneado). pypdfium2 retorna 0 chars de texto nativo.
Toda extracao depende 100% de OCR.

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

## 3. Estrutura das 3 tabelas

| Tabela | Pagina | Rows x Cols | Colunas | Conteudo |
|--------|--------|-------------|---------|----------|
| 0 | 1 | 18x5 | Servico/Acao, Produto, Eixo, Area Responsavel, DtPactuada | Entregas pactuadas (principal) |
| 1 | 2 | 6x4 | sem header (PPSI ciclos) | Continuacao entregas PPSI |
| 2 | 2 | 11x5 | Servico/Acao, Produto, Eixo, Area Responsavel, DtEntrega | Entregas ja realizadas (historico) |

**Nota:** Tabela 1 nao tem header — colunas sao indices 0-3. Parece ser continuacao da tabela 0 (mesma estrutura mas sem cabecalho).

## 4. Problema critico: OCR e espacos

### RapidOCR (padrao do Docling)

Texto vem **sem espacos entre palavras**:

```
'ReverdescricaodetodososservicosdaAGUnoportalgov.br'
'ServicosDigitaiseMethoriadaQualidade'
'Integracaoaferramentadeavaliacaodasatisfacao dosusuarios'
```

- Aho-Corasick impossivel (busca "Integracao a ferramenta" nao acha "Integracaoaferramenta")
- LLM col_map recebe lixo
- Sem acentos

### Tesseract OCR (via TesseractCliOcrOptions)

Texto vem **com espacos e acentos**:

```
'Resolver pendência decorrente do protesto de títulos das autarquias e fundações públicas federais'
'Integração à ferramenta de avaliação da satisfação dos usuários'
'Serviços Digitais e Melhoria da Qualidade'
```

**Mas com problemas residuais:**
- Rows 0-1 truncadas/cortadas (primeira linha da tabela perde texto)
- Pipes `|` vazando de bordas de celula no OCR
- DtPactuada frequentemente vazia
- Algumas celulas com lixo de OCR ("enmncuo", "ETeeeeoeeoeeoe—")
- Area Responsavel as vezes truncada ("SG" em vez de "SGE")

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

## 6. Opcoes de OCR disponiveis no Docling

```
EasyOcrOptions
RapidOcrOptions        ← padrao, texto grudado
TesseractOcrOptions    ← binding Python
TesseractCliOcrOptions ← CLI, melhor resultado
OcrAutoOptions
OcrMacOptions
KserveV2OcrOptions
```

## 7. Implicacoes para o pipeline

### O que funciona
- `doc.tables` como lista
- `table.export_to_dataframe()` para converter tabela em DataFrame
- `table.prov[0].page_no` para localizacao
- `table.data.table_cells` para acesso granular
- Headers detectados via `cell.column_header == True`
- Tesseract OCR produz texto legivel com espacos

### O que precisa de correcao no ptd_extracao.py
1. **Remover referencia a `doc.main_text`** — nao existe
2. **Usar Tesseract** em vez de RapidOCR padrao
3. **Pos-processamento de texto:**
   - Strip de pipes `|` no inicio/fim do texto de celulas
   - Merge de linhas truncadas (rows 0-1 podem ser continuacao)
   - Limpeza de lixo OCR
4. **Tratar tabela sem header** (tabela 1) como continuacao da tabela anterior
5. **DtPactuada** pode precisar de extracao separada (coluna estreita, OCR falha)

### O que NAO funciona para Aho-Corasick
Mesmo com Tesseract, o texto de Produto vem como:
- "Integração à ferramenta de avaliação da satisfação dos usuários"
- "Disponibilização em Acesso Digital"
- "Integração ao Login Único"

Estes sao nomes reais de produtos SGD — Aho-Corasick pode funcionar se:
- O dicionario usar formas com acento
- Matching usar normalize(NFD) + casefold para comparacao fuzzy

## 8. Proximos passos

1. [ ] Testar PDF de outro orgao (verificar se texto grudado e so AGU ou generalizado)
2. [ ] Notebook 02: testar col_map LLM com headers reais
3. [ ] Corrigir ptd_extracao.py com base nestas descobertas
4. [ ] Implementar pos-processamento (strip pipes, merge rows)
5. [ ] Testar Aho-Corasick com texto Tesseract normalizado
