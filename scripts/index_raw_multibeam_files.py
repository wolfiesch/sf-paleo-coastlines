#!/usr/bin/env python3
"""Build a file-level index for raw multibeam survey files."""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PALEO_PUBLIC = ROOT / "public" / "data" / "paleo-coastlines"
EXTERNAL_CANDIDATES = PALEO_PUBLIC / "external_bathymetry_candidates.json"
OUT_JSON = PALEO_PUBLIC / "raw_multibeam_file_index.json"
OUT_MD = ROOT / "docs" / "raw-multibeam-file-index.md"
DEFAULT_REPORT_DIR = ROOT / "data" / "paleo-coastlines" / "raw-sonar-probe"

SURVEY_PAGES = {
    "NA080": "https://www.ngdc.noaa.gov/ships/nautilus/NA080_mb.html",
    "NA085": "https://www.ngdc.noaa.gov/ships/nautilus/NA085_mb.html",
    "NA107": "https://www.ngdc.noaa.gov/ships/nautilus/NA107_mb.html",
}

RAW_EXTENSIONS = (
    ".all.mb58.gz",
    ".mb58.gz",
    ".all.gz",
    ".gsf.mb121.gz",
)


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


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_links(url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(fetch_text(url))
    return [urllib.parse.urljoin(url, link) for link in parser.links]


def raw_links(page_url: str) -> list[str]:
    return [
        link for link in parse_links(page_url)
        if urllib.parse.urlparse(link).path.lower().endswith(RAW_EXTENSIONS)
    ]


def bounds_overlap(a: list[float] | None, b: list[float] | None) -> bool:
    if not a or not b:
        return False
    aw, asouth, ae, anorth = a
    bw, bsouth, be, bnorth = b
    return not (ae < bw or be < aw or anorth < bsouth or bnorth < asouth)


def bounds_from_stats(stats: dict[str, Any] | None) -> list[float] | None:
    if not stats:
        return None
    required = ["minLon", "minLat", "maxLon", "maxLat"]
    if any(key not in stats for key in required):
        return None
    return [float(stats["minLon"]), float(stats["minLat"]), float(stats["maxLon"]), float(stats["maxLat"])]


def load_gap_cells() -> list[dict[str, Any]]:
    payload = json.loads(EXTERNAL_CANDIDATES.read_text())
    return [
        {
            "cellId": cell["cellId"],
            "bounds": cell["bounds"],
            "center": cell["center"],
        }
        for cell in payload.get("auditedCells", [])
    ]


def collect_reports(report_dir: Path, extra_reports: list[Path]) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for path in list(report_dir.glob("**/*sample-report.json")) + extra_reports:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        url = data.get("url")
        if not url:
            continue
        reports[url] = {
            "surveyId": data.get("surveyId"),
            "url": url,
            "bounds": bounds_from_stats(data.get("stats")),
            "stats": data.get("stats"),
            "gridPath": data.get("gridPath"),
            "algorithm": data.get("algorithm"),
            "gridSize": data.get("gridSize"),
            "reportPath": str(path),
        }
    return reports


def summarize(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_survey: dict[str, dict[str, Any]] = {}
    for entry in entries:
        survey = entry["surveyId"]
        summary = by_survey.setdefault(survey, {
            "surveyId": survey,
            "rawFileCount": 0,
            "indexedFileCount": 0,
            "targetOverlapCount": 0,
            "targetCells": set(),
        })
        summary["rawFileCount"] += 1
        if entry.get("bounds"):
            summary["indexedFileCount"] += 1
        if entry.get("overlappingGapCells"):
            summary["targetOverlapCount"] += 1
            summary["targetCells"].update(cell["cellId"] for cell in entry["overlappingGapCells"])
    rows = []
    for summary in by_survey.values():
        copy = dict(summary)
        copy["targetCells"] = sorted(copy["targetCells"])
        rows.append(copy)
    return sorted(rows, key=lambda item: item["surveyId"])


def build_index(surveys: list[str], report_dir: Path, extra_reports: list[Path]) -> dict[str, Any]:
    gap_cells = load_gap_cells()
    reports = collect_reports(report_dir, extra_reports)
    entries = []
    for survey in surveys:
        page = SURVEY_PAGES[survey]
        for url in raw_links(page):
            report = reports.get(url)
            bounds = report.get("bounds") if report else None
            overlapping = [
                cell for cell in gap_cells
                if bounds_overlap(bounds, cell["bounds"])
            ]
            entries.append({
                "surveyId": survey,
                "fileName": Path(urllib.parse.urlparse(url).path).name,
                "url": url,
                "bounds": bounds,
                "overlappingGapCells": overlapping,
                "indexed": bool(bounds),
                "sourceReport": report.get("reportPath") if report else None,
                "gridPath": report.get("gridPath") if report else None,
                "pointStats": report.get("stats") if report else None,
            })
    return {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "plainEnglishPurpose": (
            "List raw sonar files by survey and record which files have proven bounds "
            "that overlap weak map cells."
        ),
        "surveys": surveys,
        "gapCells": gap_cells,
        "summary": summarize(entries),
        "files": entries,
    }


def write_markdown(index: dict[str, Any], path: Path) -> None:
    rows = [
        "# Raw Multibeam File Index",
        "",
        "This file is generated by `python3 scripts/index_raw_multibeam_files.py`.",
        "",
        "Plain English: this index helps us avoid downloading and gridding huge raw sonar files that do not actually touch the weak map cells.",
        "",
        "## Survey Summary",
        "",
        "| Survey | Raw files listed | Files with proven bounds | Files overlapping weak cells | Weak cells touched |",
        "|---|---:|---:|---:|---|",
    ]
    for summary in index["summary"]:
        rows.append(
            f"| {summary['surveyId']} | {summary['rawFileCount']} | "
            f"{summary['indexedFileCount']} | {summary['targetOverlapCount']} | "
            f"{', '.join(summary['targetCells']) or '-'} |"
        )
    rows.extend([
        "",
        "## Indexed Target Files",
        "",
        "| Survey | File | Overlapping weak cells | Bounds | Points |",
        "|---|---|---|---|---:|",
    ])
    target_files = [entry for entry in index["files"] if entry.get("overlappingGapCells")]
    for entry in target_files:
        bounds = entry["bounds"]
        bounds_text = (
            f"`{bounds[0]:.6f}, {bounds[1]:.6f}, {bounds[2]:.6f}, {bounds[3]:.6f}`"
            if bounds else "-"
        )
        point_stats = entry.get("pointStats") or {}
        points = point_stats.get("unthinnedValidPointCount") or point_stats.get("validPointCount") or 0
        cells = ", ".join(cell["cellId"] for cell in entry["overlappingGapCells"])
        rows.append(f"| {entry['surveyId']} | `{entry['fileName']}` | {cells} | {bounds_text} | {points:,} |")
    if not target_files:
        rows.append("| - | - | - | - | 0 |")
    rows.extend([
        "",
        "## Next Step",
        "",
        "Index more files before production gridding. For large surveys like `NA107` and `NA080`, the first raw file is not enough evidence; we need file-level bounds for each likely target file.",
        "",
    ])
    path.write_text("\n".join(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a file-level raw multibeam index.")
    parser.add_argument("--survey", action="append", choices=sorted(SURVEY_PAGES), help="Survey to index. Can be repeated.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--extra-report", action="append", type=Path, default=[])
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()

    surveys = args.survey or ["NA085", "NA107", "NA080"]
    index = build_index(surveys, args.report_dir, args.extra_report)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(index, indent=2) + "\n")
    write_markdown(index, args.out_md)
    print(json.dumps(index["summary"], indent=2))


if __name__ == "__main__":
    main()
