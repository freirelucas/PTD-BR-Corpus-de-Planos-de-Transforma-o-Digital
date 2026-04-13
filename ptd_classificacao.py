# ptd_classificacao.py — Estagio 4: Classificacao semantica
# Spaceless substring matching (tolerante a palavras grudadas)
# Corrigido com base em descobertas factuais (2026-04-13):
# - spaceless() em vez de .lower() → tolera "ferramentade", "daQualidade"
# - Sem dependencia de ahocorasick (mesmo resultado com substring match)
# - Testado: ANAC 89% ok, AGU 78% ok

import json
import logging
from pathlib import Path

from ptd_constants import detectar_eixo
from ptd_utils import spaceless

logger = logging.getLogger("ptd_classificacao")

CONFIG_DIR = Path("config")


def _carregar_vocabulario() -> list[str]:
    """Carrega produtos canonicos de config/produtos_sgd_v23.json."""
    path = CONFIG_DIR / "produtos_sgd_v23.json"
    data = json.loads(path.read_text())
    return data["produtos"]


def _build_spaceless_index(termos: list[str]) -> list[tuple[str, str]]:
    """Constroi indice spaceless ordenado por tamanho desc.

    Retorna [(chave_spaceless, forma_canonica), ...].
    Mais longo primeiro = match mais especifico tem prioridade.
    """
    pares = [(spaceless(t), t) for t in termos]
    # Deduplica (alguns termos viram a mesma chave spaceless)
    vistos = set()
    unicos = []
    for k, v in pares:
        if k not in vistos:
            vistos.add(k)
            unicos.append((k, v))
    return sorted(unicos, key=lambda p: len(p[0]), reverse=True)


def classificar_linhas(linhas: list[dict]) -> list[dict]:
    """Classifica cada linha: produto via spaceless matching, eixo via regex."""
    vocab = _carregar_vocabulario()
    indice = _build_spaceless_index(vocab)

    for linha in linhas:
        servico = linha.get("servico", "")
        produto_campo = linha.get("produto", "")
        texto_original = f"{servico} {produto_campo}"
        texto_sl = spaceless(texto_original)

        # Spaceless substring matching (mais longo primeiro)
        produto_match = None
        for chave, canonico in indice:
            if chave in texto_sl:
                produto_match = canonico
                break

        if produto_match:
            linha["produto_classificado"] = produto_match

        # Eixo: regex — inclui coluna eixo_raw do PDF quando disponivel
        eixo_raw = linha.get("eixo_raw", "")
        texto_eixo = f"{texto_original} {eixo_raw}"
        eixo = detectar_eixo(texto_eixo)
        linha["eixo_classificado"] = eixo

        linha["parse_flag"] = _determinar_flag(linha, produto_match)

    n_ok = sum(1 for l in linhas if l["parse_flag"] == "ok")
    n_total = len(linhas)
    pct = (n_ok / n_total * 100) if n_total else 0
    logger.info("Classificacao: %d/%d ok (%.1f%%)", n_ok, n_total, pct)

    return linhas


def _determinar_flag(linha: dict, produto_match: str | None) -> str:
    """Determina parse_flag para uma linha."""
    servico = linha.get("servico", "").strip()

    if not servico and not produto_match:
        return "vazio"
    if not servico:
        return "sem_servico"
    if not produto_match:
        return "sem_produto"
    if len(servico) < 5:
        return "ruido"
    return "ok"
