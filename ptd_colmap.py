# ptd_colmap.py — Estagio 3: Col-map via LLM
# Identifica colunas semanticas (servico, produto, area, data) usando LLM
# Registra decisao + confianca por tabela (rastreabilidade)
# Parte de S1 (Operacoes) do pipeline PTD-BR v2

import json
import logging
import os
from dataclasses import dataclass

from ptd_extracao import TabelaExtraida

logger = logging.getLogger("ptd_colmap")

PROMPT_TEMPLATE = """Voce esta analisando uma tabela de um Plano de Transformacao Digital (PTD)
do governo federal brasileiro. Identifique qual coluna corresponde a cada campo semantico.

Cabecalhos da tabela: {headers}

Retorne APENAS JSON valido:
{{
  "servico": "nome_coluna ou null",
  "produto": "nome_coluna ou null",
  "area": "nome_coluna ou null",
  "data_prevista": "nome_coluna ou null",
  "confianca": 0.0
}}

Se confianca < 0.7, inclua "motivo_incerteza".
"""


@dataclass
class ColMapResult:
    """Resultado do mapeamento de colunas por LLM."""
    mapping: dict[str, str | None]  # campo_semantico -> nome_coluna
    confianca: float
    fonte: str  # "llm_haiku", "llm_sonnet", "heuristica_fallback"
    motivo_incerteza: str | None = None


def mapear_colunas_llm(tabela: TabelaExtraida) -> ColMapResult:
    """Usa LLM para mapear colunas da tabela a campos semanticos.
    
    Fallback: heuristica simples se LLM nao disponivel.
    """
    if not tabela.headers:
        return ColMapResult(
            mapping={"servico": None, "produto": None, "area": None, "data_prevista": None},
            confianca=0.0,
            fonte="sem_headers",
        )

    # Tentar LLM
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return _colmap_via_anthropic(tabela.headers, api_key)

    # Fallback heuristica (limitada — documentada como causa raiz #1)
    logger.warning("ANTHROPIC_API_KEY nao definida — usando heuristica fallback (limitada)")
    return _colmap_heuristica(tabela.headers)


def _colmap_via_anthropic(headers: list[str], api_key: str) -> ColMapResult:
    """Chama Anthropic API (Haiku) para col_map."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        prompt = PROMPT_TEMPLATE.format(headers=json.dumps(headers, ensure_ascii=False))

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Extrair JSON da resposta
        if "```" in text:
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()

        result = json.loads(text)
        confianca = result.pop("confianca", 0.5)
        motivo = result.pop("motivo_incerteza", None)

        return ColMapResult(
            mapping={
                "servico": result.get("servico"),
                "produto": result.get("produto"),
                "area": result.get("area"),
                "data_prevista": result.get("data_prevista"),
            },
            confianca=confianca,
            fonte="llm_haiku",
            motivo_incerteza=motivo,
        )

    except Exception as e:
        logger.error("LLM col_map falhou: %s — fallback heuristica", e)
        return _colmap_heuristica(headers)


def _colmap_heuristica(headers: list[str]) -> ColMapResult:
    """Heuristica simples. LIMITADA — ver Analise Falacia 3."""
    mapping = {"servico": None, "produto": None, "area": None, "data_prevista": None}
    h_lower = {h: h.lower() for h in headers}

    for h, low in h_lower.items():
        if any(k in low for k in ("servico", "serviço", "entrega", "acao", "ação", "meta", "atividade")):
            if not mapping["servico"]:
                mapping["servico"] = h
        elif any(k in low for k in ("produto", "product")):
            if not mapping["produto"]:
                mapping["produto"] = h
        elif any(k in low for k in ("area", "área", "unidade", "setor")):
            if not mapping["area"]:
                mapping["area"] = h
        elif any(k in low for k in ("data", "prazo", "previs")):
            if not mapping["data_prevista"]:
                mapping["data_prevista"] = h

    matched = sum(1 for v in mapping.values() if v is not None)
    return ColMapResult(
        mapping=mapping,
        confianca=matched / 4.0,
        fonte="heuristica_fallback",
        motivo_incerteza="LLM indisponivel — heuristica limitada (Falacia 3)" if matched < 3 else None,
    )


def aplicar_colmap(tabela: TabelaExtraida, colmap: ColMapResult) -> list[dict]:
    """Aplica col_map a cada linha da tabela. Retorna lista de dicts com proveniencia."""
    if tabela.is_risk:
        return []  # Tabelas de risco filtradas

    linhas = []
    for linha_idx, row in enumerate(tabela.rows):
        # Mapear celulas aos campos semanticos
        header_to_idx = {h: i for i, h in enumerate(tabela.headers)}
        registro = {
            "sigla": tabela.sigla,
            "servico": "",
            "produto": "",
            "area": "",
            "data_prevista": "",
            "proveniencia": {
                "pdf_sha256": tabela.pdf_sha256,
                "pdf_filename": tabela.pdf_filename,
                "pagina": tabela.pagina,
                "tabela_idx": tabela.tabela_idx,
                "linha_idx": linha_idx,
                "raw_text": " | ".join(row),
                "col_map_aplicado": colmap.mapping,
                "col_map_confianca": colmap.confianca,
                "col_map_fonte": colmap.fonte,
                "bbox": tabela.bbox,
            },
        }

        for campo, col_name in colmap.mapping.items():
            if col_name and col_name in header_to_idx:
                idx = header_to_idx[col_name]
                if idx < len(row):
                    registro[campo] = row[idx].strip()

        linhas.append(registro)

    return linhas
