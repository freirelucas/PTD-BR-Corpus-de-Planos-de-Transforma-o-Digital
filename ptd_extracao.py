# ptd_extracao.py — Estagio 2: Extracao de tabelas de PDFs
# Docling com deteccao automatica de PDF nativo vs escaneado
# Tesseract OCR para PDFs-imagem, texto nativo para os demais
# Pos-processamento: normalize_cell_text (fix grudados + strip artefatos)
# Corrigido com base em descobertas factuais (2026-04-13)

import logging
from dataclasses import dataclass
from pathlib import Path

from ptd_utils import is_risk_table, normalize_cell_text, pdf_has_native_text

logger = logging.getLogger("ptd_extracao")


@dataclass
class TabelaExtraida:
    """Uma tabela extraida de um PDF, com proveniencia completa."""
    sigla: str
    pdf_sha256: str
    pdf_filename: str
    pagina: int
    tabela_idx: int
    headers: list[str]
    rows: list[list[str]]
    bbox: dict | None = None
    charspan: tuple[int, int] | None = None
    is_risk: bool = False


def _build_converter(filepath: str):
    """Constroi DocumentConverter com OCR adequado ao tipo de PDF.

    - PDF com texto nativo: OCR desligado (mais rapido, sem artefatos)
    - PDF escaneado (imagem): Tesseract CLI com lang=por
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat

    native = pdf_has_native_text(filepath)
    pipeline_opts = PdfPipelineOptions()

    if native:
        pipeline_opts.do_ocr = False
        logger.info("PDF nativo detectado — OCR desligado")
    else:
        from docling.datamodel.pipeline_options import TesseractCliOcrOptions
        pipeline_opts.do_ocr = True
        pipeline_opts.ocr_options = TesseractCliOcrOptions(
            lang=["por"],
            force_full_page_ocr=True,
        )
        logger.info("PDF escaneado detectado — Tesseract OCR ativado")

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts),
        }
    )


def extrair_tabelas_pdf(
    filepath: str,
    sha256: str,
    sigla: str,
) -> list[TabelaExtraida]:
    """Extrai tabelas de um PDF usando Docling.

    Detecta automaticamente PDF nativo vs escaneado.
    Aplica normalize_cell_text em todo texto de celula.
    """
    path = Path(filepath)
    logger.info("Extraindo: %s (%s)", path.name, sigla)

    try:
        converter = _build_converter(str(path))
        result = converter.convert(str(path))
    except Exception as e:
        logger.error("Docling falhou em %s: %s", path.name, e)
        return []

    doc = result.document
    tabelas = []

    for item_idx, item in enumerate(doc.tables):
        # Proveniencia
        page_no = 0
        bbox_dict = None
        charspan_val = None

        if item.prov:
            prov = item.prov[0]
            page_no = getattr(prov, "page_no", 0)
            if prov.bbox:
                b = prov.bbox
                bbox_dict = {"l": b.l, "t": b.t, "r": b.r, "b": b.b}
            charspan_val = getattr(prov, "charspan", None)

        # Extrair headers e rows via table_cells
        table_data = getattr(item, "data", None)
        if not table_data or not table_data.table_cells:
            continue

        cells = table_data.table_cells
        max_row = max(c.start_row_offset_idx for c in cells)

        headers = []
        rows = []

        for row_idx in range(max_row + 1):
            row_cells = sorted(
                [c for c in cells if c.start_row_offset_idx == row_idx],
                key=lambda c: c.start_col_offset_idx,
            )
            texts = [normalize_cell_text(c.text) if c.text else "" for c in row_cells]

            if row_idx == 0:
                headers = texts
            else:
                rows.append(texts)

        risk = is_risk_table(headers)
        if risk:
            logger.debug("Tabela de risco (pag %d, idx %d)", page_no, item_idx)

        tabelas.append(TabelaExtraida(
            sigla=sigla,
            pdf_sha256=sha256,
            pdf_filename=path.name,
            pagina=page_no,
            tabela_idx=item_idx,
            headers=headers,
            rows=rows,
            bbox=bbox_dict,
            charspan=charspan_val,
            is_risk=risk,
        ))

    logger.info("Extraidas %d tabelas de %s (%d risco)",
                len(tabelas), path.name, sum(1 for t in tabelas if t.is_risk))
    return tabelas
