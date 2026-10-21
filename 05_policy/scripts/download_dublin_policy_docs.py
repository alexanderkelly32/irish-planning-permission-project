import csv
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[2]
REFUSAL_CASES = ROOT / "03_refusal" / "current" / "refusal_reasons_cases_master.csv"
POLICY_ROOT = ROOT / "05_policy"
DOWNLOAD_ROOT = POLICY_ROOT / "documents" / "downloaded"
SOURCE_DATA_ROOT = POLICY_ROOT / "source_data"

DUBLIN_COUNCILS = [
    "Dublin City Council",
    "Dun Laoghaire Rathdown County Council",
    "Fingal County Council",
    "South Dublin County Council",
]

DOCS = [
    {
        "authority": "Dublin City Council",
        "document_label": "Dublin City Development Plan 2016-2022 Volume 1 Written Statement",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement",
        "url": "https://www.dublincity.ie/sites/default/files/2020-08/written-statement-volume-1.pdf",
        "relative_path": "Dublin_City_Council/Dublin_City_Development_Plan_2016_2022_Volume_1_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Dublin City Council",
        "document_label": "Dublin City Development Plan 2022-2028 Final Volume 1 Written Statement",
        "coverage_start_year": 2022,
        "coverage_end_year": 2028,
        "document_type": "written_statement",
        "url": "https://www.dublincity.ie/sites/default/files/2022-12/Final%20Vol%201%20Written%20Statement.pdf",
        "relative_path": "Dublin_City_Council/Dublin_City_Development_Plan_2022_2028_Volume_1_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2004-2010 Written Statement",
        "coverage_start_year": 2004,
        "coverage_end_year": 2010,
        "document_type": "written_statement",
        "url": "https://www.dlrcoco.ie/sites/dlrcoco/files/atoms/files/written_statement_2004.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2004_2010_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2010-2016 Written Statement",
        "coverage_start_year": 2010,
        "coverage_end_year": 2016,
        "document_type": "written_statement",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp_2010_written_statement.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2010_2016_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Cover and Contents",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cover_and_contents.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Cover_and_Contents.pdf",
        "note": "DLR's 2016-2022 plan is exposed as separate PDFs rather than one consolidated written statement file.",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 1",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section1.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_1.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 2",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section2.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_2.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 3",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section3.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_3.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 4",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section4.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_4.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 6",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section6.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_6.pdf",
        "note": "Section 5 did not resolve to a public PDF during download verification.",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 7",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section7.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_7.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 8",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section8.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_8.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 9",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section9.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_9.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Section 10",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement_section",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/cdp2016_section10.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Section_10.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 1",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix1.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_1.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 2",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix2.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_2.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 3",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix3.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_3.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 4",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix4.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_4.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 5",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix5.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_5.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 7",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix7.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_7.pdf",
        "note": "Appendix numbers 6, 9, 10, 12 and 17 did not resolve to public PDFs during verification.",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 8",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix8.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_8.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 11",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix11.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_11.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 13",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix13.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_13.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 14",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix14.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_14.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 15",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix15.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_15.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2016-2022 Appendix 16",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "appendix",
        "url": "https://www.dlrcoco.ie/sites/default/files/atoms/files/appendix16.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2016_2022_Appendix_16.pdf",
        "note": "",
    },
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "document_label": "Dun Laoghaire-Rathdown County Development Plan 2022-2028 Written Statement",
        "coverage_start_year": 2022,
        "coverage_end_year": 2028,
        "document_type": "written_statement",
        "url": "https://www.dlrcoco.ie/sites/dlrcoco/files/atoms/files/written_statement.pdf",
        "relative_path": "Dun_Laoghaire_Rathdown_County_Council/DLR_County_Development_Plan_2022_2028_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Fingal County Council",
        "document_label": "Fingal Development Plan 2005-2011 Written Statement Full Version",
        "coverage_start_year": 2005,
        "coverage_end_year": 2011,
        "document_type": "written_statement",
        "url": "https://www.fingal.ie/sites/default/files/2019-03/Fingal%20Development%20Written%20Statement%20Full%20Version.pdf",
        "relative_path": "Fingal_County_Council/Fingal_Development_Plan_2005_2011_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Fingal County Council",
        "document_label": "Fingal Development Plan 2011-2017 Written Statement",
        "coverage_start_year": 2011,
        "coverage_end_year": 2017,
        "document_type": "written_statement",
        "url": "https://www.fingal.ie/sites/default/files/2019-03/Written%20Statement%202011%20-%202017%20%2828%20MB%29_compressed_compressed%20%281%29.pdf",
        "relative_path": "Fingal_County_Council/Fingal_Development_Plan_2011_2017_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Fingal County Council",
        "document_label": "Fingal Development Plan 2017-2023 Written Statement",
        "coverage_start_year": 2017,
        "coverage_end_year": 2023,
        "document_type": "written_statement",
        "url": "https://www.fingal.ie/sites/default/files/2019-03/Fingal%20Development%20Plan%202017-2023%20-%20Written%20Statement_compressed_compressed.pdf",
        "relative_path": "Fingal_County_Council/Fingal_Development_Plan_2017_2023_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "Fingal County Council",
        "document_label": "Fingal Development Plan 2023-2029 Written Statement",
        "coverage_start_year": 2023,
        "coverage_end_year": 2029,
        "document_type": "written_statement",
        "url": "https://www.fingal.ie/sites/default/files/2023-10/Fingal%20Development%20Plan%2030.08.23_V4_WEB.pdf",
        "relative_path": "Fingal_County_Council/Fingal_Development_Plan_2023_2029_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "South Dublin County Council",
        "document_label": "South Dublin County Development Plan 2004-2010",
        "coverage_start_year": 2004,
        "coverage_end_year": 2010,
        "document_type": "written_statement",
        "url": "https://www.sdcc.ie/en/download-it/publications/development-plan-2004-2010.pdf",
        "relative_path": "South_Dublin_County_Council/South_Dublin_County_Development_Plan_2004_2010.pdf",
        "note": "No earlier South Dublin plan PDF was discoverable on the current SDCC public site.",
    },
    {
        "authority": "South Dublin County Council",
        "document_label": "South Dublin County Development Plan 2010-2016 Written Statement Including Variations 1 and 2",
        "coverage_start_year": 2010,
        "coverage_end_year": 2016,
        "document_type": "written_statement",
        "url": "https://www.sdcc.ie/en/download-it/editor/development-plan-written-statement-2010-2016-including-variations-1-2.pdf",
        "relative_path": "South_Dublin_County_Council/South_Dublin_County_Development_Plan_2010_2016_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "South Dublin County Council",
        "document_label": "South Dublin County Council Development Plan 2016-2022 Written Statement",
        "coverage_start_year": 2016,
        "coverage_end_year": 2022,
        "document_type": "written_statement",
        "url": "https://www.sdcc.ie/en/download-it/publications/south-dublin-county-council-development-plan-2016-2022-written-statement.pdf",
        "relative_path": "South_Dublin_County_Council/South_Dublin_County_Development_Plan_2016_2022_Written_Statement.pdf",
        "note": "",
    },
    {
        "authority": "South Dublin County Council",
        "document_label": "South Dublin County Development Plan 2022-2028 Written Statement",
        "coverage_start_year": 2022,
        "coverage_end_year": 2028,
        "document_type": "written_statement",
        "url": "https://www.sdcc.ie/en/devplan2022/adopted-plan/county-development-plan-written-statement/county-development-plan-written-statement1.pdf",
        "relative_path": "South_Dublin_County_Council/South_Dublin_County_Development_Plan_2022_2028_Written_Statement.pdf",
        "note": "",
    },
]

GAPS = [
    {
        "authority": "Dun Laoghaire Rathdown County Council",
        "gap_start_year": 2002,
        "gap_end_year": 2003,
        "note": "Earliest refusal reasons are from 2002. A pre-2004 DLR county development plan PDF was not located on the current public site.",
    },
    {
        "authority": "South Dublin County Council",
        "gap_start_year": 1995,
        "gap_end_year": 2003,
        "note": "Earliest refusal reasons are from 1995. The current SDCC public site exposes the development plan archive from 2004 onward; no pre-2004 plan PDF was found.",
    },
]


def normalise_relative_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin("https://placeholder.local", url).replace("https://placeholder.local", "")


def get_refusal_spans():
    csv.field_size_limit(min(sys.maxsize, 2**31 - 1))
    spans = {}
    with REFUSAL_CASES.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            council = row["council"]
            if council not in DUBLIN_COUNCILS:
                continue
            try:
                reason_count = int(row["reason_count"] or "0")
            except ValueError:
                reason_count = 0
            if reason_count <= 0:
                continue
            decision_date = (row["decision_date"] or "")[:10]
            if not decision_date:
                continue
            existing = spans.get(council)
            payload = {
                "date": decision_date,
                "application_number": row["application_number"],
            }
            if existing is None:
                spans[council] = {"earliest": payload, "latest": payload}
                continue
            if decision_date < existing["earliest"]["date"]:
                existing["earliest"] = payload
            if decision_date > existing["latest"]["date"]:
                existing["latest"] = payload
    return spans


def download_file(session: requests.Session, url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower():
            raise RuntimeError(f"Expected PDF but got {content_type or 'unknown content type'} for {url}")
        with dest.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)


def main():
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    SOURCE_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    refusal_spans = get_refusal_spans()
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"

    manifest_rows = []
    for doc in DOCS:
        rel_path = Path(doc["relative_path"])
        dest = DOWNLOAD_ROOT / rel_path
        status = "downloaded"
        error = ""
        try:
            download_file(session, doc["url"], dest)
        except Exception as exc:
            status = "download_failed"
            error = str(exc)
        span = refusal_spans.get(doc["authority"], {})
        manifest_rows.append(
            {
                "authority": doc["authority"],
                "earliest_refusal_reason_date": span.get("earliest", {}).get("date", ""),
                "earliest_application_number": span.get("earliest", {}).get("application_number", ""),
                "latest_refusal_reason_date": span.get("latest", {}).get("date", ""),
                "document_label": doc["document_label"],
                "coverage_start_year": doc["coverage_start_year"],
                "coverage_end_year": doc["coverage_end_year"],
                "document_type": doc["document_type"],
                "source_url": doc["url"],
                "relative_file": str(Path("documents") / "downloaded" / rel_path).replace("\\", "/"),
                "status": status,
                "note": doc["note"] or error,
            }
        )

    for gap in GAPS:
        span = refusal_spans.get(gap["authority"], {})
        manifest_rows.append(
            {
                "authority": gap["authority"],
                "earliest_refusal_reason_date": span.get("earliest", {}).get("date", ""),
                "earliest_application_number": span.get("earliest", {}).get("application_number", ""),
                "latest_refusal_reason_date": span.get("latest", {}).get("date", ""),
                "document_label": f"Archive gap {gap['gap_start_year']}-{gap['gap_end_year']}",
                "coverage_start_year": gap["gap_start_year"],
                "coverage_end_year": gap["gap_end_year"],
                "document_type": "gap",
                "source_url": "",
                "relative_file": "",
                "status": "missing_public_source",
                "note": gap["note"],
            }
        )

    fieldnames = [
        "authority",
        "earliest_refusal_reason_date",
        "earliest_application_number",
        "latest_refusal_reason_date",
        "document_label",
        "coverage_start_year",
        "coverage_end_year",
        "document_type",
        "source_url",
        "relative_file",
        "status",
        "note",
    ]
    manifest_path = SOURCE_DATA_ROOT / "dublin_policy_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)


if __name__ == "__main__":
    main()
