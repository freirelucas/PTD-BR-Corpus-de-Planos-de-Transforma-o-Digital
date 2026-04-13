# ptd_utils.py — Utilidades reutilizaveis do pipeline PTD-BR v2
# Migrado de: ptd_pipeline_v30.py + descobertas Docling (2026-04-13)

import re
from unicodedata import normalize, category

# -- Pos-processamento de texto extraido --


def fix_glued_words(text: str) -> str:
    """Insere espaco entre minuscula e maiuscula (daQualidade → da Qualidade).

    Cobre 100% dos grudados [a-z][A-Z] encontrados em PDFs nativos (ANAC)
    e escaneados (AGU). Sem falsos positivos observados.
    """
    return re.sub(r"([a-záéíóúãõç])([A-ZÁÉÍÓÚÃÕÇ])", r"\1 \2", text)


def clean_ocr_artifacts(text: str) -> str:
    """Remove pipes de borda de celula e espacos extras (artefatos Tesseract)."""
    text = text.strip("| ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_cell_text(text: str) -> str:
    """Pipeline completo de limpeza para texto de celula de tabela.

    Ordem: strip artefatos OCR → corrigir grudados.
    Nao usa dicionario — so regex deterministico.
    """
    if not text:
        return ""
    text = clean_ocr_artifacts(text)
    text = fix_glued_words(text)
    return text


def spaceless(text: str) -> str:
    """Remove espacos e acentos para matching tolerante a grudados.

    'Integração à ferramenta de avaliação' e 'Integracaoaferramentadeavaliacao'
    ficam ambos 'integracaoaferramentadeavaliacao' → match exato.
    """
    nfd = normalize("NFD", text)
    stripped = "".join(c for c in nfd if category(c) != "Mn")
    return re.sub(r"\s+", "", stripped).casefold()


def pdf_has_native_text(filepath: str, min_chars: int = 50) -> bool:
    """Detecta se PDF tem texto nativo (True) ou e imagem pura (False).

    Usa pypdfium2 para extrair texto sem OCR. Se qualquer pagina tem
    mais que min_chars, considera nativo.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(filepath)
    for i in range(len(pdf)):
        text = pdf[i].get_textpage().get_text_range()
        if len(text) > min_chars:
            return True
    return False


# -- Detector de tabela de risco [Briefing III-A2] --
RISK_MARKERS = {"risco", "probabilidade", "impacto", "severidade", "mitigacao", "ameaca"}


def is_risk_table(headers: list[str]) -> bool:
    """Retorna True se headers indicam tabela de risco (>= 2 marcadores)."""
    normalized = {h.lower().strip() for h in headers}
    return len(normalized & RISK_MARKERS) >= 2


# -- Config OCR por sigla (legacy — mantido para compatibilidade) --
OCR_CONFIG = {
    "DEFAULT": {"dpi": 300, "psm": 6, "lang": "por"},
}


# -- Blocklist de siglas fantasma [Briefing III-A5] --
SIGLAS_EXCLUIR = {"ABNT-NBR-1", "ASSINADO", "21", "MDA-DOCUME", "MDA-ANEXO-"}
_PAT_SIGLA_INVALIDA = re.compile(r"^.{0,2}$|[0-9]")


def is_sigla_valida(sigla: str, lista_branca: set[str] | None = None) -> bool:
    """Valida sigla: >= 3 chars, sem digitos (exceto lista branca), nao na blocklist."""
    if sigla in SIGLAS_EXCLUIR:
        return False
    if lista_branca and sigla in lista_branca:
        return True
    return not bool(_PAT_SIGLA_INVALIDA.match(sigla))
