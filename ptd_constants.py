# ptd_constants.py — PTD-BR v2
# Fonte unica de verdade: eixos EFGD, padroes regex, diretorios
# Migrado de freirelucas/teste (ptd_constants.py), paths ajustados
# IPEA / COGIT / DIEST

from pathlib import Path
import re
from typing import Optional

# -- Diretorios de trabalho --
DIR_ROOT = Path("ptd_corpus")
DIR_RAW = DIR_ROOT / "01_raw_pdfs"
DIR_LOG = DIR_ROOT / "02_logs"
DIR_DB = DIR_ROOT / "03_database"

# -- Portal de coleta --
PORTAL_BASE = (
    "https://www.gov.br/governodigital/pt-br/"
    "estrategias-e-governanca-digital/"
    "planos-de-transformacao-digital"
)

# -- Eixos EFGD (Estrategia Federal de Governo Digital) --
EIXOS: dict[int, str] = {
    1: "Centrado no Cidadao e Inclusivo",
    2: "Integrado e Colaborativo",
    3: "Inteligente e Inovador",
    4: "Confiavel e Seguro",
    5: "Transparente, Aberto e Participativo",
    6: "Eficiente e Sustentavel",
}

# -- Padroes de deteccao por palavras-chave --
_EIXO_PATS: list[tuple[int, re.Pattern]] = [
    (1, re.compile(r"cidad[ao]o|inclusiv|servi[cç]os digitais|unifica[cç][ao]o de canais", re.I)),
    (2, re.compile(
        r"integrad|colaborat|interoperab"
        r"|cooper[ao]|compartilh|cat[aá]logo.*servi[cç]|barramento"
        r"|plataforma.*integr|rede.*compartilh|ecossistema.*digital", re.I)),
    (3, re.compile(r"inteligent|inovad|govern[aâ]n[cç]a.*dados|gest[ao]o.*dados", re.I)),
    (4, re.compile(r"confi[aá]vel|segur|privacidade|ppsi", re.I)),
    (5, re.compile(
        r"transpar(?:en|ên)|aberto|participat|dados abertos"
        r"|lai\b|lei.*acesso.*informa|acesso.*informa[çc][ao]o"
        r"|ouvidoria|controle social|portal.*dados|fiscaliza[çc]", re.I)),
    (6, re.compile(
        r"efici[eê]n|eficient|sustent|desburocrat|simplifica[çc]"
        r"|racionaliz|otimiz|redu[çc][ao]o.*custo|moderniza[çc]"
        r"|digitaliza[çc].*processo|elimina[çc].*papel|automat", re.I)),
]

_PAT_EIXO_NUM = re.compile(r"eixo\s*([1-6])\b|E[-.]([1-6])\b", re.I)


def detectar_eixo(texto: str) -> Optional[int]:
    """Detecta eixo EFGD (1-6) em texto. Tenta numerico, depois keywords."""
    if not texto:
        return None
    m = _PAT_EIXO_NUM.search(texto)
    if m:
        return int(m.group(1) or m.group(2))
    for num, pat in _EIXO_PATS:
        if pat.search(texto):
            return num
    return None
