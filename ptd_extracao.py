# ptd_extracao.py — Estagio 2: Extracao
# Docling (texto nativo) + Tesseract OCR (fallback imagem)
# Preserva ProvenanceItem completo (page_no + bbox + charspan)
# Parte de S1 (Operacoes) do pipeline PTD-BR v2

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ptd_utils import is_risk_table, is_image_pdf, OCR_CONFIG

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
    # Proveniencia Docling (preservada, nao descartada)
    bbox: dict | None = None  # {"l": float, "t": float, "r": float, "b": float}
    charspan: tuple[int, int] | None = None
    is_risk: bool = False


def extrair_tabelas_pdf(
    filepath: str,
    sha256: str,
    sigla: str,
) -> list[TabelaExtraida]:
    """Extrai tabelas de um PDF usando Docling, com OCR fallback.
    
    Retorna lista de TabelaExtraida com proveniencia completa.
    Filtra tabelas de risco via is_risk_table().
    """
    path = Path(filepath)
    logger.info("Extraindo: %s (%s)", path.name, sigla)

    try:
        from docling.document_converter import DocumentConverter
        converter = DocumentConverter()
        result = converter.convert(str(path))
    except Exception as e:
        logger.error("Docling falhou em %s: %s", path.name, e)
        return []

    tabelas = []
    doc = result.document

    for item_idx, item in enumerate(doc.tables if hasattr(doc, "tables") else []):
        # Proveniencia: extrair page_no e bbox do ProvenanceItem
        page_no = 0
        bbox_dict = None
        charspan_val = None

        if hasattr(item, "prov") and item.prov:
            prov = item.prov[0]
            page_no = prov.page_no if hasattr(prov, "page_no") else 0
            if hasattr(prov, "bbox") and prov.bbox:
                b = prov.bbox
                bbox_dict = {"l": b.l, "t": b.t, "r": b.r, "b": b.b}
            if hasattr(prov, "charspan"):
                charspan_val = prov.charspan

        # Extrair headers e rows da TableData
        table_data = item.data if hasattr(item, "data") else None
        if not table_data:
            continue

        headers = []
        rows = []

        if hasattr(table_data, "table_cells") and table_data.table_cells:
            # Organizar celulas por row
            max_row = max(c.start_row_offset_idx for c in table_data.table_cells)
            for row_idx in range(max_row + 1):
                row_cells = sorted(
                    [c for c in table_data.table_cells if c.start_row_offset_idx == row_idx],
                    key=lambda c: c.start_col_offset_idx,
                )
                texts = [c.text.strip() if c.text else "" for c in row_cells]
                if row_idx == 0:
                    headers = texts
                else:
                    rows.append(texts)

        # Filtrar tabelas de risco
        risk = is_risk_table(headers)
        if risk:
            logger.debug("Tabela de risco detectada (pag %d, idx %d) — marcada", page_no, item_idx)

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

    # OCR fallback: se nenhuma tabela extraida, tentar OCR
    if not tabelas:
        logger.info("Nenhuma tabela Docling em %s — tentando OCR fallback", path.name)
        tabelas = _ocr_fallback(path, sha256, sigla)

    logger.info("Extraidas %d tabelas de %s (%d risco)",
                len(tabelas), path.name, sum(1 for t in tabelas if t.is_risk))
    return tabelas


def _ocr_fallback(path: Path, sha256: str, sigla: str) -> list[TabelaExtraida]:
    """Fallback OCR para PDFs-imagem. Usa config per-sigla."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.warning("pytesseract/pdf2image nao instalados — OCR skip")
        return []

    config = OCR_CONFIG.get(sigla, OCR_CONFIG["DEFAULT"])
    dpi = config["dpi"]
    lang = config["lang"]

    logger.info("OCR fallback: %s com DPI=%d", path.name, dpi)

    try:
        images = convert_from_path(str(path), dpi=dpi)
    except Exception as e:
        logger.error("pdf2image falhou em %s: %s", path.name, e)
        return []

    tabelas = []
    for page_idx, img in enumerate(images):
        text = pytesseract.image_to_string(img, lang=lang)
        if not text.strip():
            continue
        # OCR retorna texto corrido — criar tabela simplificada
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        tabelas.append(TabelaExtraida(
            sigla=sigla,
            pdf_sha256=sha256,
            pdf_filename=path.name,
            pagina=page_idx + 1,
            tabela_idx=0,
            headers=["ocr_text"],
            rows=[[l] for l in lines],
            bbox=None,
            charspan=None,
            is_risk=False,
        ))

    return tabelas
