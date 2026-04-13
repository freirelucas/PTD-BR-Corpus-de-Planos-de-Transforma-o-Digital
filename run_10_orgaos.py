#!/usr/bin/env python3
"""Roda extracao + classificacao em todos os PDFs da pasta pdfs/.
Exporta CSV + JSON summary."""

import csv
import json
import hashlib
import logging
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ptd_extracao import extrair_tabelas_pdf
from ptd_classificacao import classificar_linhas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-16s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_10")

PDF_DIR = Path("pdfs")
OUT_DIR = Path("output")

# Palavras-chave que indicam tabela de entregas
_ENTREGAS_KEYWORDS = {"servico", "servi\u00e7o", "acao", "a\u00e7\u00e3o", "produto", "entrega"}


def _encontrar_tabela_entregas(tabelas):
    """Encontra a tabela principal de entregas pactuadas.

    Heuristica: tabela com mais rows cujos headers contem palavras de entregas.
    Fallback: tabela com mais rows.
    """
    candidatas = []
    for t in tabelas:
        h_lower = " ".join(h.lower() for h in t.headers)
        score = sum(1 for kw in _ENTREGAS_KEYWORDS if kw in h_lower)
        if score >= 2 and len(t.rows) >= 2:
            candidatas.append((score, len(t.rows), t))

    if candidatas:
        candidatas.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidatas[0][2]

    # Fallback: tabela com mais rows (e pelo menos 3)
    validas = [t for t in tabelas if len(t.rows) >= 3]
    if validas:
        return max(validas, key=lambda t: len(t.rows))
    return tabelas[0] if tabelas else None


def _mapear_colunas(headers):
    """Mapeia headers a campos semanticos por keywords."""
    col_map = {}
    for i, h in enumerate(headers):
        hl = h.lower()
        if any(k in hl for k in ("servico", "servi\u00e7o", "acao", "a\u00e7\u00e3o")) and "servico" not in col_map:
            col_map["servico"] = i
        elif any(k in hl for k in ("produto",)) and "produto" not in col_map:
            col_map["produto"] = i
        elif any(k in hl for k in ("eixo",)) and "eixo" not in col_map:
            col_map["eixo"] = i
        elif any(k in hl for k in ("area", "\u00e1rea", "responsavel", "respons\u00e1vel")) and "area" not in col_map:
            col_map["area"] = i
        elif any(k in hl for k in ("data", "dt", "prazo", "pactuada", "entrega")) and "data" not in col_map:
            col_map["data"] = i

    if not col_map:
        for i, field in enumerate(["servico", "produto", "eixo", "area", "data"]):
            if i < len(headers):
                col_map[field] = i

    return col_map


def _get_col(row, idx):
    if idx is not None and idx < len(row):
        return row[idx]
    return ""


OUT_DIR.mkdir(exist_ok=True)

SIGLA_MAP = {
    "agu_entregas.pdf": "AGU",
    "anac_entregas.pdf": "ANAC",
    "abin_entregas.pdf": "ABIN",
    "aeb_entregas.pdf": "AEB",
    "ana_entregas.pdf": "ANA",
    "anatel_entregas.pdf": "ANATEL",
    "anvisa_entregas.pdf": "ANVISA",
    "bcb_entregas.pdf": "BCB",
    "cgu_entregas.pdf": "CGU",
    "aneel_entregas.pdf": "ANEEL",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def main():
    t0 = time.time()
    todas_linhas = []
    erros = []

    for pdf_file in sorted(PDF_DIR.glob("*.pdf")):
        sigla = SIGLA_MAP.get(pdf_file.name, pdf_file.stem.split("_")[0].upper())
        sha = sha256_file(pdf_file)

        logger.info(">>> %s (%s)", sigla, pdf_file.name)

        try:
            tabelas = extrair_tabelas_pdf(
                filepath=str(pdf_file),
                sha256=sha,
                sigla=sigla,
            )
        except Exception as e:
            logger.error("FALHA %s: %s", sigla, e)
            erros.append({"sigla": sigla, "erro": str(e)})
            continue

        if not tabelas:
            logger.warning("%s: 0 tabelas extraidas", sigla)
            erros.append({"sigla": sigla, "erro": "0 tabelas"})
            continue

        t_principal = _encontrar_tabela_entregas(tabelas)
        if not t_principal:
            logger.warning("%s: nenhuma tabela de entregas encontrada", sigla)
            erros.append({"sigla": sigla, "erro": "nenhuma tabela de entregas"})
            continue

        col_map = _mapear_colunas(t_principal.headers)

        for row_idx, row in enumerate(t_principal.rows):
            linhas_dict = {
                "sigla": sigla,
                "servico": _get_col(row, col_map.get("servico")),
                "produto": _get_col(row, col_map.get("produto")),
                "eixo_raw": _get_col(row, col_map.get("eixo")),
                "area": _get_col(row, col_map.get("area")),
                "data_prevista": _get_col(row, col_map.get("data")),
                "pdf_filename": pdf_file.name,
                "pagina": t_principal.pagina,
                "tabela_idx": t_principal.tabela_idx,
                "linha_idx": row_idx,
                "n_tabelas_pdf": len(tabelas),
            }
            todas_linhas.append(linhas_dict)

    logger.info("=== CLASSIFICANDO %d linhas ===", len(todas_linhas))
    todas_linhas = classificar_linhas(todas_linhas)

    csv_path = OUT_DIR / "ptd_corpus_v2.csv"
    fieldnames = [
        "sigla", "servico", "produto", "produto_classificado",
        "eixo_raw", "eixo_classificado", "area", "data_prevista",
        "parse_flag", "pdf_filename", "pagina",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(todas_linhas)

    logger.info("CSV salvo: %s (%d linhas)", csv_path, len(todas_linhas))

    flags = Counter(l["parse_flag"] for l in todas_linhas)
    total = len(todas_linhas)
    n_ok = flags.get("ok", 0)

    por_orgao = defaultdict(lambda: {"n_rows": 0, "n_ok": 0, "flags": Counter()})
    for l in todas_linhas:
        s = l["sigla"]
        por_orgao[s]["n_rows"] += 1
        por_orgao[s]["flags"][l["parse_flag"]] += 1
        if l["parse_flag"] == "ok":
            por_orgao[s]["n_ok"] += 1

    summary = {
        "total_linhas": total,
        "pct_ok": round(n_ok / total * 100, 1) if total else 0,
        "parse_flags": dict(flags),
        "orgaos_processados": len(por_orgao),
        "tempo_segundos": round(time.time() - t0, 1),
        "erros": erros,
        "por_orgao": {
            s: {
                "n_rows": d["n_rows"],
                "pct_ok": round(d["n_ok"] / d["n_rows"] * 100, 1) if d["n_rows"] else 0,
                "flags": dict(d["flags"]),
            }
            for s, d in sorted(por_orgao.items())
        },
    }

    summary_path = OUT_DIR / "ptd_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n" + "=" * 65)
    print(f"  RESULTADO: {n_ok}/{total} ok ({summary['pct_ok']}%)")
    print(f"  Orgaos: {len(por_orgao)} | Tempo: {summary['tempo_segundos']}s")
    print("=" * 65)
    print(f"  {'SIGLA':<10} {'ROWS':>5} {'OK':>5} {'%OK':>6}  FLAGS")
    print(f"  {'-'*10} {'-'*5} {'-'*5} {'-'*6}  {'-'*20}")
    for s, d in sorted(por_orgao.items()):
        pct = round(d["n_ok"] / d["n_rows"] * 100) if d["n_rows"] else 0
        print(f"  {s:<10} {d['n_rows']:>5} {d['n_ok']:>5} {pct:>5}%  {dict(d['flags'])}")

    if erros:
        print(f"\n  ERROS ({len(erros)}):")
        for e in erros:
            print(f"    {e['sigla']}: {e['erro']}")

    print()


if __name__ == "__main__":
    main()
