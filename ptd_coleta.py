# ptd_coleta.py — Estagio 1: Coleta
# Scraping gov.br + download PDFs + SHA-256 dedup
# Parte de S1 (Operacoes) do pipeline PTD-BR v2

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ptd_constants import PORTAL_BASE, DIR_RAW

logger = logging.getLogger("ptd_coleta")

MANIFEST_PATH = DIR_RAW / "download_manifest.json"


def _sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scrape_pdf_urls(portal_url: str = PORTAL_BASE) -> list[dict]:
    """Scrape portal gov.br e retorna lista de {url, sigla_inferida}."""
    logger.info("Scraping %s", portal_url)
    resp = requests.get(portal_url, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    pdfs = []
    for a in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
        href = a["href"]
        url = urljoin(portal_url, href)
        filename = Path(href).name
        # Inferir sigla do nome do arquivo (ex: PTD_AGU_2025.pdf -> AGU)
        m = re.search(r"PTD[_-]([A-Z]{2,10})", filename, re.I)
        sigla = m.group(1).upper() if m else filename.replace(".pdf", "").upper()
        pdfs.append({"url": url, "filename": filename, "sigla": sigla})

    logger.info("Encontrados %d PDFs", len(pdfs))
    return pdfs


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def _save_manifest(manifest: dict):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def download_pdfs(
    pdf_list: list[dict],
    max_pdfs: int | None = None,
    force: bool = False,
) -> list[dict]:
    """Baixa PDFs com dedup SHA-256. Retorna lista de {filepath, sha256, sigla, url}."""
    DIR_RAW.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    downloaded = []

    for i, pdf_info in enumerate(pdf_list):
        if max_pdfs and i >= max_pdfs:
            logger.info("max_pdfs=%d atingido, parando", max_pdfs)
            break

        filepath = DIR_RAW / pdf_info["filename"]

        # Dedup: se arquivo existe e hash conhecido, skip
        if not force and filepath.exists() and str(filepath) in manifest:
            sha = manifest[str(filepath)]["sha256"]
            logger.debug("Skip (dedup): %s [%s]", filepath.name, sha[:12])
            downloaded.append({
                "filepath": str(filepath),
                "sha256": sha,
                "sigla": pdf_info["sigla"],
                "url": pdf_info["url"],
                "cached": True,
            })
            continue

        # Download
        logger.info("Baixando %s", pdf_info["url"])
        try:
            resp = requests.get(pdf_info["url"], timeout=120)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Falha ao baixar %s: %s", pdf_info["url"], e)
            continue

        filepath.write_bytes(resp.content)
        sha = _sha256(filepath)

        # Sanity: arquivo muito pequeno provavelmente nao e PDF valido
        if filepath.stat().st_size < 1024:
            logger.warning("PDF suspeito (< 1KB): %s", filepath.name)

        manifest[str(filepath)] = {
            "sha256": sha,
            "sigla": pdf_info["sigla"],
            "url": pdf_info["url"],
            "size_bytes": filepath.stat().st_size,
        }
        downloaded.append({
            "filepath": str(filepath),
            "sha256": sha,
            "sigla": pdf_info["sigla"],
            "url": pdf_info["url"],
            "cached": False,
        })

        time.sleep(0.5)  # Cortesia ao servidor

    _save_manifest(manifest)
    logger.info("Coleta: %d PDFs (%d novos)", len(downloaded),
                sum(1 for d in downloaded if not d["cached"]))
    return downloaded
