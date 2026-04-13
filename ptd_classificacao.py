# ptd_classificacao.py — Estagio 4: Classificacao semantica
# Aho-Corasick contra vocabulario canonico + regex eixos + parse_flag
# Parte de S1 (Operacoes) do pipeline PTD-BR v2

import json
import logging
from pathlib import Path

import ahocorasick

from ptd_constants import detectar_eixo

logger = logging.getLogger("ptd_classificacao")

CONFIG_DIR = Path("config")


def _carregar_vocabulario() -> list[str]:
    """Carrega produtos canonicos de config/produtos_sgd_v23.json."""
    path = CONFIG_DIR / "produtos_sgd_v23.json"
    data = json.loads(path.read_text())
    return data["produtos"]


def _build_automaton(termos: list[str]) -> ahocorasick.Automaton:
    """Constroi automaton Aho-Corasick. Termos mais longos primeiro."""
    A = ahocorasick.Automaton()
    for termo in sorted(termos, key=len, reverse=True):
        A.add_word(termo.lower(), termo)
    A.make_automaton()
    return A


def classificar_linhas(linhas: list[dict]) -> list[dict]:
    """Classifica cada linha: produto via Aho-Corasick, eixo via regex, parse_flag.
    
    Modifica linhas in-place e retorna.
    """
    vocab = _carregar_vocabulario()
    automaton = _build_automaton(vocab)

    for linha in linhas:
        servico = linha.get("servico", "")
        produto_campo = linha.get("produto", "")
        texto_busca = f"{servico} {produto_campo}".lower()

        # Aho-Corasick: primeiro match (mais especifico por ordem)
        produto_match = None
        for _, termo in automaton.iter(texto_busca):
            produto_match = termo
            break  # Primeiro match = mais especifico (ordem por tamanho desc)

        if produto_match:
            linha["produto"] = produto_match

        # Eixo: detectar via regex (stateless por linha — fix PGFN)
        eixo = detectar_eixo(texto_busca)
        linha["eixo"] = eixo

        # Parse flag
        linha["parse_flag"] = _determinar_flag(linha, produto_match)

    n_ok = sum(1 for l in linhas if l["parse_flag"] == "ok")
    n_total = len(linhas)
    pct = (n_ok / n_total * 100) if n_total else 0
    logger.info("Classificacao: %d/%d ok (%.1f%%)", n_ok, n_total, pct)

    return linhas


def _determinar_flag(linha: dict, produto_match: str | None) -> str:
    """Determina parse_flag para uma linha."""
    servico = linha.get("servico", "").strip()
    produto = produto_match

    if not servico and not produto:
        return "vazio"
    if not servico:
        return "sem_servico"
    if not produto:
        return "sem_produto"
    # Detectar ruido: linhas muito curtas ou que parecem headers/footers
    if len(servico) < 5:
        return "ruido"
    return "ok"
