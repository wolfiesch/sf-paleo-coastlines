#!/usr/bin/env python3
"""Check whether candidate multibeam surveys are easy or hard to process."""

from __future__ import annotations

import json
import re
import shutil
import urllib.parse
import urllib.request
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PALEO_DIR = ROOT / "public" / "data" / "paleo-coastlines"
EXTERNAL_CANDIDATES = PALEO_DIR / "external_bathymetry_candidates.json"
OUT_JSON = PALEO_DIR / "multibeam_processing_feasibility.json"
OUT_MD = ROOT / "docs" / "multibeam-processing-feasibility.md"

MULTIBEAM_PAGE_ROOT = "https://www.ngdc.noaa.gov/ships"
DATA_ROOT = "https://data.ngdc.noaa.gov/platforms/ocean/ships"
PRODUCT_QUERY_URL = "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_datasets/MapServer/0/query"
PAGE_TEXT_CACHE: dict[str, str] = {}
PAGE_LINK_CACHE: dict[str, list[str]] = {}

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
RAW_MULTIBEAM_EXTENSIONS = (
    ".all",
    ".all.gz",
    ".all.mb58.gz",
    ".mb15",
    ".mb21",
    ".mb21.gz",
    ".mb58.gz",
    ".s7k",
    ".s7k.gz",
)

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


def fetch_text(url: str, timeout: int = 8) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def head(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
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
    if url in PAGE_LINK_CACHE:
        return PAGE_LINK_CACHE[url]
    parser = LinkParser()
    try:
        parser.feed(cached_fetch_text(url))
    except Exception:
        return []
    links = [urllib.parse.urljoin(url, link) for link in parser.links]
    PAGE_LINK_CACHE[url] = links
    return links


def cached_fetch_text(url: str) -> str:
    if url not in PAGE_TEXT_CACHE:
        PAGE_TEXT_CACHE[url] = fetch_text(url)
    return PAGE_TEXT_CACHE[url]


def survey_page_summary(page_url: str | None) -> dict[str, Any]:
    if not page_url:
        return {}
    try:
        html = cached_fetch_text(page_url)
    except Exception as error:  # noqa: BLE001 - this is an audit probe.
        return {"pageReadError": str(error)}

    def field(label: str) -> str | None:
        match = re.search(
            rf"<b>{re.escape(label)}:</b></td>\s*<td>(.*?)</td>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        return re.sub(r"<.*?>", "", match.group(1)).strip()

    def numeric(label: str) -> float | None:
        value = field(label)
        if not value:
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        return float(match.group(0)) if match else None

    bounds_values = {
        "west": numeric("Western Extent"),
        "south": numeric("Southern Extent"),
        "east": numeric("Eastern Extent"),
        "north": numeric("Northern Extent"),
    }
    bounds = None
    if all(value is not None for value in bounds_values.values()):
        bounds = [bounds_values["west"], bounds_values["south"], bounds_values["east"], bounds_values["north"]]

    return {
        "ship": field("Ship Name"),
        "sourceOrganization": field("Source Organization"),
        "numberOfFiles": numeric("Number of Files"),
        "bounds": bounds,
    }


def metadata_xml_url(survey_id: str) -> str:
    return f"https://www.ngdc.noaa.gov/metadata/published/NOAA/NESDIS/NGDC/MGG/Multibeam/iso/xml/{survey_id}_Multibeam.xml"


def xml_text(element: ET.Element, path: str) -> str | None:
    namespaces = {
        "gco": "http://www.isotc211.org/2005/gco",
        "gmd": "http://www.isotc211.org/2005/gmd",
    }
    match = element.find(path, namespaces)
    if match is None or match.text is None:
        return None
    return match.text.strip()


def metadata_summary(survey_id: str) -> dict[str, Any]:
    url = metadata_xml_url(survey_id)
    try:
        root = ET.fromstring(fetch_text(url).encode("utf-8"))
    except Exception as error:  # noqa: BLE001 - this is an audit probe.
        return {"url": url, "error": str(error)}

    namespaces = {
        "gco": "http://www.isotc211.org/2005/gco",
        "gmd": "http://www.isotc211.org/2005/gmd",
    }
    bbox = root.find(".//gmd:EX_GeographicBoundingBox", namespaces)
    bounds = None
    if bbox is not None:
        values = {
            "west": xml_text(bbox, "gmd:westBoundLongitude/gco:Decimal"),
            "east": xml_text(bbox, "gmd:eastBoundLongitude/gco:Decimal"),
            "south": xml_text(bbox, "gmd:southBoundLatitude/gco:Decimal"),
            "north": xml_text(bbox, "gmd:northBoundLatitude/gco:Decimal"),
        }
        if all(value is not None for value in values.values()):
            bounds = [float(values["west"]), float(values["south"]), float(values["east"]), float(values["north"])]

    title = xml_text(root, ".//gmd:identificationInfo//gmd:citation//gmd:title/gco:CharacterString")
    vertical = None
    for ref in root.findall(".//gmd:referenceSystemInfo", namespaces):
        title_attr = ref.attrib.get("{http://www.w3.org/1999/xlink}title")
        if title_attr and "Vertical" in title_attr:
            vertical = title_attr
            break

    return {
        "url": url,
        "title": title,
        "bounds": bounds,
        "verticalReference": vertical,
    }


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
    try:
        payload = fetch_json(PRODUCT_QUERY_URL, {
            "f": "json",
            "where": where,
            "outFields": "DATASET_NAME,NGDC_ID,SURVEY_NAME,PLATFORM,SURVEY_YEAR,DOWNLOAD_URL,DATA_TYPE,FILE_COUNT",
            "returnGeometry": "false",
            "resultRecordCount": 50,
        })
    except Exception:
        return []
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


def sample_raw_files(page_url: str | None, limit: int = 2) -> list[dict[str, Any]]:
    if not page_url:
        return []
    links = parse_links(page_url)
    raw_links = [
        link for link in links
        if link.lower().endswith(RAW_MULTIBEAM_EXTENSIONS)
    ]
    samples = []
    for link in raw_links[:limit]:
        samples.append(head(link))
    return samples


def raw_file_inventory(page_url: str | None) -> dict[str, Any]:
    if not page_url:
        return {"count": 0, "extensions": [], "urls": []}
    links = parse_links(page_url)
    raw_links = [
        link for link in links
        if link.lower().endswith(RAW_MULTIBEAM_EXTENSIONS)
    ]
    extensions: dict[str, int] = {}
    for link in raw_links:
        name = urllib.parse.urlparse(link).path.split("/")[-1]
        match = re.search(
            r"(\.all\.mb58\.gz|\.mb58\.gz|\.all\.gz|\.mb21\.gz|\.s7k\.gz|\.mb15|\.mb21|\.all|\.s7k)$",
            name.lower(),
        )
        extension = match.group(1) if match else Path(name).suffix.lower()
        extensions[extension] = extensions.get(extension, 0) + 1
    return {
        "count": len(raw_links),
        "extensions": sorted(extensions.items(), key=lambda item: item[0]),
        "urls": raw_links,
    }


def header_file_samples(page_url: str | None, limit: int = 2) -> list[dict[str, Any]]:
    if not page_url:
        return []
    links = parse_links(page_url)
    header_links = [link for link in links if link.lower().endswith(".hdr")]
    samples = []
    for link in header_links[:limit]:
        sample = head(link)
        try:
            text = fetch_text(link)
        except Exception as error:  # noqa: BLE001 - this is an audit probe.
            text = ""
            sample["readError"] = str(error)
        bounds: dict[str, float] = {}
        vertical = None
        for line in text.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4 and parts[0] == "#":
                key = parts[2]
                if parts[1] == "FILE" and key in {"MINLAT", "MAXLAT", "MINLON", "MAXLON"}:
                    bounds[key] = float(parts[3])
                if parts[1] == "NAVI" and key == "VERTICAL_DATUM":
                    vertical = parts[3]
        if bounds:
            sample["declaredBounds"] = {
                "west": bounds.get("MINLON"),
                "south": bounds.get("MINLAT"),
                "east": bounds.get("MAXLON"),
                "north": bounds.get("MAXLAT"),
            }
        if vertical:
            sample["verticalDatum"] = vertical
        samples.append(sample)
    return samples


def bounds_overlap(a: list[float] | None, b: list[float] | None) -> bool | None:
    if not a or not b:
        return None
    aw, asouth, ae, anorth = a
    bw, bsouth, be, bnorth = b
    return not (ae < bw or be < aw or anorth < bsouth or bnorth < asouth)


def top_multibeam_candidates(limit: int = 10, cell_id: str | None = None) -> list[dict[str, Any]]:
    audit = json.loads(EXTERNAL_CANDIDATES.read_text())
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for cell in audit.get("auditedCells", []):
        if cell_id and cell.get("cellId") != cell_id:
            continue
        for candidate in cell.get("multibeamCandidates", []):
            name = str(candidate.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            copy = dict(candidate)
            copy["firstGapCell"] = cell["cellId"]
            copy["firstGapCenter"] = cell["center"]
            copy["firstGapBounds"] = cell["bounds"]
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


def build_audit(limit: int = 10, cell_id: str | None = None, probe_products: bool = False) -> dict[str, Any]:
    tool_paths = {tool: shutil.which(tool) for tool in RAW_PROCESSING_TOOLS}
    tools_available = all(tool_paths.values())
    candidates = []
    for candidate in top_multibeam_candidates(limit=limit, cell_id=cell_id):
        survey_id = str(candidate["name"])
        platform = candidate.get("platform")
        page = survey_page_url(platform, survey_id) or candidate.get("downloadUrl")
        page_summary = survey_page_summary(page)
        metadata = metadata_summary(survey_id) if probe_products else {}
        records = product_records(survey_id) if probe_products else []
        product_dirs = probe_products_dirs(platform, survey_id) if probe_products else []
        raw_inventory = raw_file_inventory(page)
        raw_samples = sample_raw_files(page)
        status, recommendation = classify(records, product_dirs, raw_samples, tools_available)
        candidates.append({
            "surveyId": survey_id,
            "platform": platform,
            "instrument": candidate.get("instrument"),
            "surveyYear": candidate.get("surveyYear"),
            "firstGapCell": candidate.get("firstGapCell"),
            "firstGapCenter": candidate.get("firstGapCenter"),
            "firstGapBounds": candidate.get("firstGapBounds"),
            "pageUrl": page,
            "pageSummary": page_summary,
            "metadata": metadata,
            "metadataBoundsOverlapFirstGap": bounds_overlap(
                (metadata.get("bounds") or page_summary.get("bounds")),
                candidate.get("firstGapBounds"),
            ),
            "processingStatus": status,
            "recommendation": recommendation,
            "knownCaveat": KNOWN_SURVEY_CAVEATS.get(survey_id),
            "productRecordCount": len(records),
            "productRecords": records[:5],
            "productDirProbes": product_dirs,
            "rawFileCount": raw_inventory["count"],
            "rawFileExtensions": raw_inventory["extensions"],
            "sampleRawFiles": raw_samples,
            "sampleHeaderFiles": header_file_samples(page),
        })

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "plainEnglishPurpose": (
            "Check whether top multibeam candidates have ready-made gridded products "
            "or only raw sonar files that need specialist processing."
        ),
        "rawProcessingTools": tool_paths,
        "rawProcessingToolsAvailable": tools_available,
        "targetCellId": cell_id,
        "productProbesEnabled": probe_products,
        "candidates": candidates,
    }


def write_markdown(audit: dict[str, Any]) -> None:
    tool_text = "available" if audit["rawProcessingToolsAvailable"] else "not installed locally"
    target_text = f" for `{audit['targetCellId']}`" if audit.get("targetCellId") else ""
    lines = [
        "# Multibeam Processing Feasibility",
        "",
        "This file is generated by `python3 scripts/audit_multibeam_processing_feasibility.py`.",
        "",
        f"Raw multibeam processing tools are **{tool_text}**.",
        "",
        f"Plain-English purpose: separate easy gridded-data candidates from raw-sonar candidates{target_text} before we spend time downloading large files.",
        "",
        "## Candidate Feasibility",
        "",
        "| Survey | First gap | Bounds overlap? | Raw files | Year | Instrument | Status | What this means | Caveat |",
        "|---|---|---|---:|---:|---|---|---|---|",
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
        overlap = item.get("metadataBoundsOverlapFirstGap")
        overlap_text = "yes" if overlap is True else "no" if overlap is False else "unknown"
        raw_extensions = ", ".join(f"{ext} x{count}" for ext, count in item.get("rawFileExtensions", [])) or "none found"
        lines.append(
            f"| [{item['surveyId']}]({item['pageUrl']}) | {item['firstGapCell']} "
            f"`{item['firstGapCenter']}` | {overlap_text} | "
            f"{item.get('rawFileCount') or 0} ({raw_extensions}) | {item.get('surveyYear') or ''} | "
            f"{item.get('instrument') or ''} | {item['processingStatus']} | {recommendation} | "
            f"{item.get('knownCaveat') or ''} |"
        )
        raw = item.get("sampleRawFiles") or []
        if raw:
            sample = raw[0]
            size = sample.get("bytes")
            size_text = f"{round(size / 1_000_000, 1)} MB" if size else "unknown size"
            lines.append(f"|  |  |  |  |  |  | sample raw file | {size_text}: `{sample['url']}` |  |")
        headers = item.get("sampleHeaderFiles") or []
        if headers:
            header = headers[0]
            declared = header.get("declaredBounds")
            vertical = header.get("verticalDatum")
            detail = []
            if declared:
                detail.append(f"declared bounds {declared}")
            if vertical:
                detail.append(f"vertical datum {vertical}")
            if detail:
                lines.append(f"|  |  |  |  |  |  | sample header | {'; '.join(detail)} |  |")

    lines.extend([
        "",
        "## How To Read This",
        "",
        "- `easier` means a NOAA product record exists, so we should look for a grid before touching raw sonar.",
        "- `medium` means a products folder exists, but this audit did not yet inspect every file in it.",
        "- `blocked locally` means the survey may be useful, but this Mac currently lacks MB-System tools needed to turn raw sonar into terrain.",
        "- `Bounds overlap?` uses the official NOAA survey rectangle. It is a first screen, not proof that every raw line crosses the exact cell.",
        "",
    ])
    OUT_MD.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether NOAA multibeam candidates are practical to process.")
    parser.add_argument("--cell", help="Only audit candidates from one source-quality gap cell, such as qg-05-12.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum unique multibeam surveys to audit.")
    parser.add_argument("--probe-products", action="store_true", help="Also query slower NOAA product services and products folders.")
    args = parser.parse_args()

    audit = build_audit(limit=args.limit, cell_id=args.cell, probe_products=args.probe_products)
    OUT_JSON.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    write_markdown(audit)
    for item in audit["candidates"]:
        print(f"{item['surveyId']}: {item['processingStatus']} - {item['recommendation']}")


if __name__ == "__main__":
    main()
