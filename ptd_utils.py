# ptd_utils.py — Utilidades reutilizaveis do repo teste
# Migrado de: ptd_pipeline_v30.py (_is_risk_table, is_image_pdf)
# + blocklist de siglas fantasma (NOVA_SESSAO_BRIEFING.md, III-A5)

import re

# -- Detector de tabela de risco [Briefing III-A2] --
RISK_MARKERS = {"risco", "probabilidade", "impacto", "severidade", "mitigacao", "ameaca"}


def is_risk_table(headers: list[str]) -> bool:
    """Retorna True se headers indicam tabela de risco (>= 2 marcadores)."""
    normalized = {h.lower().strip() for h in headers}
    return len(normalized & RISK_MARKERS) >= 2


# -- Detector de PDF-imagem [Briefing III-A4] --
def is_image_pdf(text_extracted: str, total_chars_expected: int) -> bool:
    """Retorna True se pagina e provavelmente imagem (>80% NaN)."""
    if total_chars_expected == 0:
        return True
    nan_ratio = 1 - (len(text_extracted.strip()) / total_chars_expected)
    return nan_ratio > 0.8


# -- Config OCR por sigla --
OCR_CONFIG = {
    "DEFAULT": {"dpi": 300, "psm": 6, "lang": "por"},
    "MEC": {"dpi": 400, "psm": 6, "lang": "por"},
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
