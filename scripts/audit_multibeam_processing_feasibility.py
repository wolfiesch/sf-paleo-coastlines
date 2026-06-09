#!/usr/bin/env python3
"""Check whether candidate multibeam surveys are easy or hard to process."""

from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"
EXTERNAL_CANDIDATES = PALEO_DIR / "external_bathymetry_candidates.json"
OUT_JSON = PALEO_DIR / "multibeam_processing_feasibility.json"
OUT_MD = ROOT / "docs" / "multibeam-processing-feasibility.md"

MULTIBEAM_PAGE_ROOT = "https://www.ngdc.noaa.gov/ships"
DATA_ROOT = "https://data.ngdc.noaa.gov/platforms/ocean/ships"
PRODUCT_QUERY_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_datasets/MapServer/0/query"

SHIP_SLUGS = {
    "Nautilus": "nautilus",
    "Okeanos Explorer": "okeanos_explorer",
    "NOAA Ship OKEANOS EXPLORER (R337)": "okeanos_explorer",
    "Maurice Ewing": "maurice_ewing",
    "Davidson": "davidson",
    "Melville": "melville",
    "Roger Revelle": "roger_revelle",
    "Marcus G. Langseth": "marcus_g_langseth",
}

RAW_PROCESSING_TOOLS = ["mbinfo", "mbgrid", "mbcopy", "mbdump"]

KNOWN_SURVEY_CAVEATS = {
    "EX0903": (
        "Prior northwest-gap discovery found the ready-made EX0903 50 m grid west of "
        "the current study bounds, so inspect product bounds before adding it."
    ),
    "EX0907": (
        "EX0907 is already in the local terrain stack; current gap coverage audits show "
        "0% valid pixels in sampled weak cells, so more EX0907 work may not fill those holes."
    ),
}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def fetch_text(url: str, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def head(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {
                "url": url,
                "status": response.status,
                "ok": 200 <= response.status < 400,
                "bytes": int(response.headers.get("Content-Length") or 0) or None,
                "contentType": response.headers.get("Content-Type"),
            }
    except Exception as error:  # noqa: BLE001 - this is an audit probe.
        return {"url": url, "status": None, "ok": False, "bytes": None, "error": str(error)}


def parse_links(url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(fetch_text(url))
    return [urllib.parse.urljoin(url, link) for link in parser.links]


def survey_page_url(platform: str | None, survey_id: str) -> str | None:
    slug = SHIP_SLUGS.get(platform or "")
    if not slug:
        return None
    return f"{MULTIBEAM_PAGE_ROOT}/{slug}/{survey_id}_mb.html"


def data_dir_url(platform: str | None, survey_id: str) -> str | None:
    slug = SHIP_SLUGS.get(platform or "")
    if not slug:
        return None
    return f"{DATA_ROOT}/{slug}/{survey_id}/multibeam/data/"


def product_records(survey_id: str) -> list[dict[str, Any]]:
    where = (
        f"SURVEY_NAME = '{survey_id}' OR "
        f"DATASET_NAME LIKE '%{survey_id}%' OR "
        f"NGDC_ID LIKE '%{survey_id}%'"
    )
    payload = fetch_json(PRODUCT_QUERY_URL, {
        "f": "json",
        "where": where,
        "outFields": "DATASET_NAME,NGDC_ID,SURVEY_NAME,PLATFORM,SURVEY_YEAR,DOWNLOAD_URL,DATA_TYPE,FILE_COUNT",
        "returnGeometry": "false",
        "resultRecordCount": 50,
    })
    return [feature.get("attributes", {}) for feature in payload.get("features", [])]


def probe_products_dirs(platform: str | None, survey_id: str) -> list[dict[str, Any]]:
    base = data_dir_url(platform, survey_id)
    if not base:
        return []
    probes = []
    for version in ["version1", "version2", "version3"]:
        url = f"{base}{version}/products/"
        probe = head(url)
        probe["version"] = version
        probes.append(probe)
    return probes


def sample_raw_files(page_url: str | None, limit: int = 5) -> list[dict[str, Any]]:
    if not page_url:
        return []
    links = parse_links(page_url)
    raw_links = [
        link for link in links
        if link.endswith(".mb58.gz") or link.endswith(".all.gz") or link.endswith(".all.mb58.gz")
    ]
    samples = []
    for link in raw_links[:limit]:
        samples.append(head(link))
    return samples


def top_multibeam_candidates(limit: int = 10) -> list[dict[str, Any]]:
    audit = json.loads(EXTERNAL_CANDIDATES.read_text())
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for cell in audit.get("auditedCells", []):
        for candidate in cell.get("multibeamCandidates", []):
            name = str(candidate.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            copy = dict(candidate)
            copy["firstGapCell"] = cell["cellId"]
            copy["firstGapCenter"] = cell["center"]
            candidates.append(copy)
            if len(candidates) >= limit:
                return candidates
    return candidates


def classify(records: list[dict[str, Any]], product_dirs: list[dict[str, Any]], sample_raw: list[dict[str, Any]], tools_available: bool) -> tuple[str, str]:
    if records:
        return "easier", "NOAA product records exist; look for a gridded product before raw processing."
    if any(probe.get("ok") for probe in product_dirs):
        return "medium", "A products directory exists; inspect it for XYZ, GeoTIFF, or NetCDF grids."
    if sample_raw and tools_available:
        return "hard", "Only raw sonar files were found, but local MB-System tools are available."
    if sample_raw:
        return "blocked locally", "Only raw sonar files were found, and MB-System tools are not installed locally."
    return "unknown", "No product records, products directory, or sample raw file was found by this audit."


def build_audit() -> dict[str, Any]:
    tool_paths = {tool: shutil.which(tool) for tool in RAW_PROCESSING_TOOLS}
    tools_available = all(tool_paths.values())
    candidates = []
    for candidate in top_multibeam_candidates():
        survey_id = str(candidate["name"])
        platform = candidate.get("platform")
        page = survey_page_url(platform, survey_id) or candidate.get("downloadUrl")
        records = product_records(survey_id)
        product_dirs = probe_products_dirs(platform, survey_id)
        raw_samples = sample_raw_files(page)
        status, recommendation = classify(records, product_dirs, raw_samples, tools_available)
        candidates.append({
            "surveyId": survey_id,
            "platform": platform,
            "instrument": candidate.get("instrument"),
            "surveyYear": candidate.get("surveyYear"),
            "firstGapCell": candidate.get("firstGapCell"),
            "firstGapCenter": candidate.get("firstGapCenter"),
            "pageUrl": page,
            "processingStatus": status,
            "recommendation": recommendation,
            "knownCaveat": KNOWN_SURVEY_CAVEATS.get(survey_id),
            "productRecordCount": len(records),
            "productRecords": records[:5],
            "productDirProbes": product_dirs,
            "sampleRawFiles": raw_samples,
        })

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "plainEnglishPurpose": (
            "Check whether top multibeam candidates have ready-made gridded products "
            "or only raw sonar files that need specialist processing."
        ),
        "rawProcessingTools": tool_paths,
        "rawProcessingToolsAvailable": tools_available,
        "candidates": candidates,
    }


def write_markdown(audit: dict[str, Any]) -> None:
    tool_text = "available" if audit["rawProcessingToolsAvailable"] else "not installed locally"
    lines = [
        "# Multibeam Processing Feasibility",
        "",
        "This file is generated by `python3 scripts/audit_multibeam_processing_feasibility.py`.",
        "",
        f"Raw multibeam processing tools are **{tool_text}**.",
        "",
        "Plain-English purpose: separate easy gridded-data candidates from raw-sonar candidates before we spend time downloading large files.",
        "",
        "## Candidate Feasibility",
        "",
        "| Survey | First gap | Year | Instrument | Status | What this means | Caveat |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in audit["candidates"]:
        product_names = ", ".join(
            record.get("DATASET_NAME", "")
            for record in item.get("productRecords", [])[:2]
            if record.get("DATASET_NAME")
        )
        recommendation = item["recommendation"]
        if product_names:
            recommendation = f"{recommendation} Product record: {product_names}."
        lines.append(
            f"| [{item['surveyId']}]({item['pageUrl']}) | {item['firstGapCell']} "
            f"`{item['firstGapCenter']}` | {item.get('surveyYear') or ''} | "
            f"{item.get('instrument') or ''} | {item['processingStatus']} | {recommendation} | "
            f"{item.get('knownCaveat') or ''} |"
        )
        raw = item.get("sampleRawFiles") or []
        if raw:
            sample = raw[0]
            size = sample.get("bytes")
            size_text = f"{round(size / 1_000_000, 1)} MB" if size else "unknown size"
            lines.append(f"|  |  |  |  | sample raw file | {size_text}: `{sample['url']}` |  |")

    lines.extend([
        "",
        "## How To Read This",
        "",
        "- `easier` means a NOAA product record exists, so we should look for a grid before touching raw sonar.",
        "- `medium` means a products folder exists, but this audit did not yet inspect every file in it.",
        "- `blocked locally` means the survey may be useful, but this Mac currently lacks MB-System tools needed to turn raw Kongsberg sonar into terrain.",
        "",
    ])
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    audit = build_audit()
    OUT_JSON.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    write_markdown(audit)
    for item in audit["candidates"]:
        print(f"{item['surveyId']}: {item['processingStatus']} - {item['recommendation']}")


if __name__ == "__main__":
    main()
