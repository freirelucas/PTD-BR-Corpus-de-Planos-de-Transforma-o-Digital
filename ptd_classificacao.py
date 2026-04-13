# ptd_classificacao.py — Estagio 4: Classificacao semantica
# Aho-Corasick com spaceless matching (tolerante a palavras grudadas)
# Corrigido com base em descobertas factuais (2026-04-13)

import json
import logging
from pathlib import Path

import ahocorasick

from ptd_constants import detectar_eixo
from ptd_utils import spaceless

logger = logging.getLogger("ptd_classificacao")

CONFIG_DIR = Path("config")


def _carregar_vocabulario() -> list[str]:
    """Carrega produtos canonicos de config/produtos_sgd_v23.json."""
    path = CONFIG_DIR / "produtos_sgd_v23.json"
    data = json.loads(path.read_text())
    return data["produtos"]


def _build_automaton(termos: list[str]) -> ahocorasick.Automaton:
    """Constroi automaton Aho-Corasick com chaves spaceless.

    Cada termo e normalizado via spaceless() (remove espacos + acentos + casefold).
    Isso torna o matching tolerante a palavras grudadas:
    'ferramentade avaliação' e 'ferramenta de avaliacao' → mesma chave.
    """
    A = ahocorasick.Automaton()
    for termo in sorted(termos, key=len, reverse=True):
        key = spaceless(termo)
        A.add_word(key, termo)
    A.make_automaton()
    return A


def classificar_linhas(linhas: list[dict]) -> list[dict]:
    """Classifica cada linha: produto via Aho-Corasick spaceless, eixo via regex.

    Modifica linhas in-place e retorna.
    """
    vocab = _carregar_vocabulario()
    automaton = _build_automaton(vocab)

    for linha in linhas:
        servico = linha.get("servico", "")
        produto_campo = linha.get("produto", "")
        texto_busca = spaceless(f"{servico} {produto_campo}")

        # Aho-Corasick spaceless: primeiro match
        produto_match = None
        for _, termo in automaton.iter(texto_busca):
            produto_match = termo
            break

        if produto_match:
            linha["produto"] = produto_match

        # Eixo: detectar via regex no texto original (precisa de acentos)
        eixo = detectar_eixo(f"{servico} {produto_campo}")
        linha["eixo"] = eixo

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
