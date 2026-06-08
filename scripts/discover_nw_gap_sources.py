#!/usr/bin/env python3
"""Discover public NOAA/NCEI sources intersecting the northwest shelf gap."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "public" / "data" / "paleo-coastlines" / "nw_gap_source_candidates.json"
OUT_MD = ROOT / "docs" / "nw-gap-source-candidates.md"

NW_GAP_BOUNDS = [-123.55, 37.95, -123.15, 38.15]

SERVICES = {
    "noaa_ncei_bag": {
        "label": "NOAA/NCEI BAG bathymetry",
        "url": "https://gis.ngdc.noaa.gov/arcgis/rest/services/bag_bathymetry/ImageServer/query",
        "idField": "SurveyID",
        "nameField": "Name",
        "fields": ["SurveyID", "Name", "LowPSActual", "HighPSActual"],
    },
    "noaa_ncei_multibeam_footprints": {
        "label": "NOAA/NCEI multibeam footprints",
        "url": "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_footprints/MapServer/0/query",
        "idField": "SURVEY_ID",
        "nameField": "PLATFORM",
        "fields": ["SURVEY_ID", "PLATFORM", "SURVEY_YEAR", "INSTRUMENT", "DOWNLOAD_URL"],
    },
    "noaa_ncei_multibeam_products": {
        "label": "NOAA/NCEI multibeam products",
        "url": "https://gis.ngdc.noaa.gov/arcgis/rest/services/multibeam_datasets/MapServer/0/query",
        "idField": "NGDC_ID",
        "nameField": "DATASET_NAME",
        "fields": ["NGDC_ID", "DATASET_NAME", "SURVEY_NAME", "PLATFORM", "SURVEY_YEAR", "DOWNLOAD_URL"],
    },
}

KNOWN_LOCAL_SURVEYS = {
    "H11738",
    "H11739",
    "H11965",
    "H12109",
    "H12110",
    "H12111",
    "H12112",
    "H12113",
    "H13334",
    "W00431",
    "W00433",
    "W00442",
    "W00443",
    "W00444",
    "W00477",
    "W00614",
}

BAG_ARCHIVE_ROOT = "https://data.ngdc.noaa.gov/platforms/ocean/nos/coast/W00001-W02000"
BAG_SURVEY_PAGE_ROOT = "https://www.ngdc.noaa.gov/nos/W00001-W02000"


def bag_download_url(survey_id: str, name: str) -> str:
    return f"{BAG_ARCHIVE_ROOT}/{survey_id}/BAG/{urllib.parse.quote(name)}.bag"


def bag_survey_page_url(survey_id: str) -> str:
    return f"{BAG_SURVEY_PAGE_ROOT}/{survey_id}.html"


def parse_content_length(headers: Any) -> int | None:
    value = headers.get("Content-Length")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def probe_download(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {
                "url": url,
                "status": response.status,
                "ok": 200 <= response.status < 400,
                "bytes": parse_content_length(response.headers),
                "contentType": response.headers.get("Content-Type"),
                "probeMethod": "HEAD",
            }
    except HTTPError as error:
        return {
            "url": url,
            "status": error.code,
            "ok": False,
            "bytes": parse_content_length(error.headers),
            "contentType": error.headers.get("Content-Type"),
            "probeMethod": "HEAD",
            "error": error.reason,
        }
    except URLError as error:
        return {
            "url": url,
            "status": None,
            "ok": False,
            "bytes": None,
            "contentType": None,
            "probeMethod": "HEAD",
            "error": str(error.reason),
        }


def enrich_bag_record(record: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(record)
    survey_id = str(record.get("SurveyID") or "").strip()
    name = str(record.get("Name") or "").strip()
    if survey_id and name:
        enriched["downloadUrl"] = bag_download_url(survey_id, name)
        enriched["downloadProbe"] = probe_download(enriched["downloadUrl"])
        enriched["surveyPageUrl"] = bag_survey_page_url(survey_id)
    return enriched


def query_service(service: dict[str, Any]) -> list[dict[str, Any]]:
    params = {
        "f": "json",
        "where": "1=1",
        "geometry": json.dumps({
            "xmin": NW_GAP_BOUNDS[0],
            "ymin": NW_GAP_BOUNDS[1],
            "xmax": NW_GAP_BOUNDS[2],
            "ymax": NW_GAP_BOUNDS[3],
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": ",".join(service["fields"]),
        "returnGeometry": "false",
        "returnDistinctValues": "false",
        "resultRecordCount": "2000",
    }
    url = service["url"] + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=45) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(f"{service['label']} query failed: {payload['error']}")
    return [feature["attributes"] for feature in payload.get("features", [])]


def summarize_records(service_key: str, service: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    id_field = service["idField"]
    name_field = service["nameField"]
    groups: dict[str, dict[str, Any]] = {}
    for record in records:
        if service_key == "noaa_ncei_bag":
            record = enrich_bag_record(record)
        source_id = str(record.get(id_field) or "").strip()
        if not source_id:
            continue
        group = groups.setdefault(source_id, {
            "id": source_id,
            "label": str(record.get(name_field) or source_id),
            "recordCount": 0,
            "sampleRecords": [],
            "alreadyInLocalStack": source_id in KNOWN_LOCAL_SURVEYS,
        })
        group["recordCount"] += 1
        if len(group["sampleRecords"]) < 5:
            group["sampleRecords"].append(record)

    return {
        "service": service_key,
        "label": service["label"],
        "recordCount": len(records),
        "uniqueSourceCount": len(groups),
        "sources": sorted(groups.values(), key=lambda item: (item["alreadyInLocalStack"], item["id"])),
    }


def build_report() -> dict[str, Any]:
    service_summaries = []
    for service_key, service in SERVICES.items():
        records = query_service(service)
        service_summaries.append(summarize_records(service_key, service, records))

    all_sources = [source for service in service_summaries for source in service["sources"]]
    new_source_count = sum(1 for source in all_sources if not source["alreadyInLocalStack"])
    local_source_count = sum(1 for source in all_sources if source["alreadyInLocalStack"])
    new_by_service = {
        service["service"]: sum(1 for source in service["sources"] if not source["alreadyInLocalStack"])
        for service in service_summaries
    }
    local_by_service = {
        service["service"]: sum(1 for source in service["sources"] if source["alreadyInLocalStack"])
        for service in service_summaries
    }
    record_counts = {service["service"]: service["recordCount"] for service in service_summaries}
    bag_summary = next((service for service in service_summaries if service["service"] == "noaa_ncei_bag"), None)
    new_bag_sources = [
        source["id"]
        for source in (bag_summary["sources"] if bag_summary else [])
        if not source["alreadyInLocalStack"]
    ]
    downloadable_bag_source_ids = sorted({
        source["id"]
        for source in (bag_summary["sources"] if bag_summary else [])
        if not source["alreadyInLocalStack"]
        for sample in source["sampleRecords"]
        if sample.get("downloadProbe", {}).get("ok")
    })
    downloadable_bag_files = [
        sample
        for source in (bag_summary["sources"] if bag_summary else [])
        if not source["alreadyInLocalStack"]
        for sample in source["sampleRecords"]
        if sample.get("downloadProbe", {}).get("ok")
    ]
    downloadable_bag_bytes = sum(sample.get("downloadProbe", {}).get("bytes") or 0 for sample in downloadable_bag_files)

    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bounds": NW_GAP_BOUNDS,
        "plainEnglishPurpose": "Find public NOAA/NCEI bathymetry and multibeam candidates intersecting the northwest outer-shelf gap so the next map upgrade can chase real source data.",
        "summary": {
            "serviceCount": len(service_summaries),
            "newCandidateCount": new_source_count,
            "alreadyLocalCandidateCount": local_source_count,
            "newCandidateCountByService": new_by_service,
            "alreadyLocalCandidateCountByService": local_by_service,
            "recordCountByService": record_counts,
            "newBagCandidateIds": new_bag_sources,
            "downloadableNewBagCandidateIds": downloadable_bag_source_ids,
            "downloadableNewBagFileCount": len(downloadable_bag_files),
            "downloadableNewBagBytes": downloadable_bag_bytes,
        },
        "services": service_summaries,
    }


def format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{value} B"


def write_markdown(report: dict[str, Any]) -> None:
    lines = [
        "# Northwest Gap Source Candidates",
        "",
        "This file is generated by `python3 scripts/discover_nw_gap_sources.py`.",
        "",
        "It checks public NOAA/NCEI services against the northwest outer-shelf gap bounds.",
        "",
        f"Bounds: `{report['bounds']}`",
        "",
        "## Summary",
        "",
        f"- New candidate source groups: {report['summary']['newCandidateCount']}",
        f"- Candidate groups already in the local stack: {report['summary']['alreadyLocalCandidateCount']}",
        f"- Downloadable new BAG source groups: {', '.join(report['summary']['downloadableNewBagCandidateIds']) or 'none'}",
        f"- Downloadable new BAG files found: {report['summary']['downloadableNewBagFileCount']}",
        f"- Downloadable new BAG file size: {format_bytes(report['summary']['downloadableNewBagBytes'])}",
        "",
    ]

    for service in report["services"]:
        lines.extend([
            f"## {service['label']}",
            "",
            f"Records returned: {service['recordCount']}",
            f"Unique source groups: {service['uniqueSourceCount']}",
            "",
            "| Source | Status | Records | Sample names / links |",
            "|---|---|---:|---|",
        ])
        for source in service["sources"][:20]:
            status = "already local" if source["alreadyInLocalStack"] else "new candidate"
            samples = []
            sample_limit = 5 if service["service"] == "noaa_ncei_bag" else 3
            for sample in source["sampleRecords"][:sample_limit]:
                name = sample.get("Name") or sample.get("DATASET_NAME") or sample.get("PLATFORM") or source["label"]
                url = sample.get("downloadUrl") or sample.get("DOWNLOAD_URL")
                probe = sample.get("downloadProbe")
                if probe:
                    state = "ok" if probe.get("ok") else f"status {probe.get('status') or 'unknown'}"
                    size = format_bytes(probe.get("bytes"))
                    samples.append(f"[{name}]({url}) ({state}, {size})")
                else:
                    samples.append(f"[{name}]({url})" if url else str(name))
            lines.append(f"| {source['id']} | {status} | {source['recordCount']} | {'; '.join(samples)} |")
        lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines).rstrip() + "\n")


def main() -> None:
    report = build_report()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    write_markdown(report)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
