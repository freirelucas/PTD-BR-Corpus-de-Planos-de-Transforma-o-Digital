# ptd_pipeline.py — Orquestrador S1 + Sensor S3*
# Pipeline linear: Coleta -> Extracao -> Col-map -> Classificacao -> Sensor
# Sem loop autonomo. Kill switch via --max-pdfs e --max-orgaos.

import argparse
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ptd_constants import DIR_DB
from ptd_coleta import scrape_pdf_urls, download_pdfs
from ptd_extracao import extrair_tabelas_pdf
from ptd_colmap import mapear_colunas_llm, aplicar_colmap
from ptd_classificacao import classificar_linhas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-16s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ptd_pipeline")


def run(
    max_pdfs: int | None = None,
    max_orgaos: int | None = None,
    siglas_filtro: list[str] | None = None,
    skip_download: bool = False,
):
    """Executa pipeline completo: 4 estagios + sensor S3*."""

    # === Estagio 1: Coleta ===
    logger.info("=== ESTAGIO 1: COLETA ===")
    if skip_download:
        # Usar PDFs ja baixados
        from ptd_coleta import _load_manifest, DIR_RAW
        manifest = _load_manifest()
        pdf_list = [
            {"filepath": k, "sha256": v["sha256"], "sigla": v["sigla"], "url": v["url"], "cached": True}
            for k, v in manifest.items()
        ]
    else:
        urls = scrape_pdf_urls()
        if siglas_filtro:
            urls = [u for u in urls if u["sigla"] in siglas_filtro]
        pdf_list = download_pdfs(urls, max_pdfs=max_pdfs)

    if max_orgaos:
        siglas_vistas = set()
        filtered = []
        for pdf in pdf_list:
            if pdf["sigla"] not in siglas_vistas:
                if len(siglas_vistas) >= max_orgaos:
                    break
                siglas_vistas.add(pdf["sigla"])
            filtered.append(pdf)
        pdf_list = filtered

    logger.info("Coleta: %d PDFs de %d orgaos",
                len(pdf_list), len({p["sigla"] for p in pdf_list}))

    # === Estagio 2: Extracao ===
    logger.info("=== ESTAGIO 2: EXTRACAO ===")
    todas_tabelas = []
    for pdf in pdf_list:
        tabelas = extrair_tabelas_pdf(
            filepath=pdf["filepath"],
            sha256=pdf["sha256"],
            sigla=pdf["sigla"],
        )
        todas_tabelas.extend(tabelas)

    logger.info("Extracao: %d tabelas (%d risco filtradas)",
                len(todas_tabelas), sum(1 for t in todas_tabelas if t.is_risk))

    # === Estagio 3: Col-map via LLM ===
    logger.info("=== ESTAGIO 3: COL-MAP ===")
    todas_linhas = []
    for tabela in todas_tabelas:
        colmap = mapear_colunas_llm(tabela)
        linhas = aplicar_colmap(tabela, colmap)
        todas_linhas.extend(linhas)

    logger.info("Col-map: %d linhas extraidas", len(todas_linhas))

    # === Estagio 4: Classificacao ===
    logger.info("=== ESTAGIO 4: CLASSIFICACAO ===")
    todas_linhas = classificar_linhas(todas_linhas)

    # === Sensor S3*: ptd_run_summary.json ===
    logger.info("=== S3*: SENSOR ===")
    summary = _gerar_run_summary(todas_linhas)

    DIR_DB.mkdir(parents=True, exist_ok=True)

    # Salvar corpus
    corpus_path = DIR_DB / "ptd_corpus_v2.json"
    corpus_path.write_text(json.dumps(todas_linhas, indent=2, ensure_ascii=False))
    logger.info("Corpus salvo: %s (%d linhas)", corpus_path, len(todas_linhas))

    # Salvar sensor
    summary_path = DIR_DB / "ptd_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info("Sensor S3* salvo: %s", summary_path)

    _imprimir_resumo(summary)
    return summary


def _gerar_run_summary(linhas: list[dict]) -> dict:
    """Gera ptd_run_summary.json — sensor independente S3*."""
    flags = Counter(l.get("parse_flag", "desconhecido") for l in linhas)
    total = len(linhas)
    n_ok = flags.get("ok", 0)

    # Per-sigla
    por_orgao = defaultdict(lambda: {"n_rows": 0, "flags": Counter()})
    unmatched_phrases = Counter()

    for l in linhas:
        sigla = l.get("sigla", "DESCONHECIDO")
        por_orgao[sigla]["n_rows"] += 1
        por_orgao[sigla]["flags"][l.get("parse_flag", "?")] += 1

        if l.get("parse_flag") == "sem_produto":
            servico = l.get("servico", "").strip()
            if servico and len(servico) > 5:
                unmatched_phrases[servico] += 1

    # Formatar por_orgao
    por_orgao_fmt = {}
    for sigla, data in por_orgao.items():
        n = data["n_rows"]
        n_ok_s = data["flags"].get("ok", 0)
        por_orgao_fmt[sigla] = {
            "n_rows": n,
            "pct_ok": round(n_ok_s / n * 100, 1) if n else 0,
            "parse_flags": dict(data["flags"]),
        }

    # Top unmatched
    top_unmatched = [
        {"frase": frase, "count": count}
        for frase, count in unmatched_phrases.most_common(30)
    ]

    # Col-map stats
    fontes = Counter()
    confiancas = []
    for l in linhas:
        prov = l.get("proveniencia", {})
        fontes[prov.get("col_map_fonte", "?")] += 1
        c = prov.get("col_map_confianca")
        if c is not None:
            confiancas.append(c)

    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "total_linhas": total,
        "pct_ok": round(n_ok / total * 100, 1) if total else 0,
        "sem_produto_pct": round(flags.get("sem_produto", 0) / total * 100, 1) if total else 0,
        "parse_flags": dict(flags),
        "orgaos_processados": len(por_orgao),
        "orgaos_zero_rows": [s for s, d in por_orgao_fmt.items() if d["n_rows"] == 0],
        "col_map_fontes": dict(fontes),
        "col_map_confianca_media": round(sum(confiancas) / len(confiancas), 3) if confiancas else 0,
        "top_unmatched_phrases": top_unmatched,
        "por_orgao": por_orgao_fmt,
    }


def _imprimir_resumo(summary: dict):
    logger.info("=" * 60)
    logger.info("RESUMO DO RUN")
    logger.info("  Linhas: %d", summary["total_linhas"])
    logger.info("  pct_ok: %.1f%%", summary["pct_ok"])
    logger.info("  sem_produto: %.1f%%", summary["sem_produto_pct"])
    logger.info("  Orgaos: %d", summary["orgaos_processados"])
    logger.info("  Col-map fontes: %s", summary["col_map_fontes"])
    logger.info("  Col-map confianca media: %.3f", summary["col_map_confianca_media"])
    if summary["top_unmatched_phrases"]:
        logger.info("  Top 5 unmatched:")
        for item in summary["top_unmatched_phrases"][:5]:
            logger.info("    %3d x %s", item["count"], item["frase"])
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PTD-BR Pipeline v2")
    parser.add_argument("--max-pdfs", type=int, default=None, help="Limite de PDFs (kill switch)")
    parser.add_argument("--max-orgaos", type=int, default=None, help="Limite de orgaos (kill switch)")
    parser.add_argument("--siglas", type=str, default=None, help="Filtrar por siglas (ex: AGU,FUNAI,INCRA)")
    parser.add_argument("--skip-download", action="store_true", help="Usar PDFs ja baixados")
    args = parser.parse_args()

    siglas = args.siglas.split(",") if args.siglas else None
    run(
        max_pdfs=args.max_pdfs,
        max_orgaos=args.max_orgaos,
        siglas_filtro=siglas,
        skip_download=args.skip_download,
    )
