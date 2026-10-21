"""v4 pre-submission review report: branded, dated, methodology-cited PDF.

Generated with fpdf2 (pure-Python, vendored). The report turns one scoring
run into a defensible artifact a consultant can put in front of a client:
headline result with the calibration range, the model's track record, the
comparable cases by name, the development-plan crosswalk, the site evidence
and the wording analysis - all with the sensitivity disclaimer on every page.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRODUCT = "Planning Intelligence"
TITLE = "Pre-Submission Planning Risk Review"

INK = (24, 30, 40)
NAVY = (21, 42, 74)
ACCENT = (0, 105, 92)
RED = (192, 57, 43)
GREEN = (30, 132, 73)
AMBER = (180, 120, 0)
LIGHT = (238, 241, 246)
MID = (200, 206, 216)


def _latin(text: object) -> str:
    value = str(text if text is not None else "")
    value = (
        value.replace("\u2018", "'").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2013", "-").replace("\u2014", "-").replace("\u2022", "-").replace("\u00b2", "2")
        .replace("\u2264", "<=").replace("\u2265", ">=").replace("\u00d7", "x").replace("\u2026", "...")
    )
    return "".join(ch if ord(ch) < 256 else "?" for ch in value)


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class ReviewReport:
    def __init__(self) -> None:
        try:
            from fpdf import FPDF
        except ModuleNotFoundError:
            import sys as _sys

            _sys.path.insert(0, str(ROOT / ".vendor"))
            from fpdf import FPDF

        self.pdf = FPDF(format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=18)
        self.pdf.set_margins(14, 14, 14)

    def _header(self, scheme_label: str) -> None:
        pdf = self.pdf
        pdf.set_fill_color(*NAVY)
        pdf.rect(0, 0, 210, 22, style="F")
        pdf.set_fill_color(*ACCENT)
        pdf.rect(0, 22, 210, 1.2, style="F")
        pdf.set_xy(14, 6)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 6, f"{PRODUCT}  |  {TITLE}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(210, 220, 235)
        pdf.cell(0, 5, _latin(scheme_label), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*INK)

    def _footer(self) -> None:
        pdf = self.pdf
        pdf.set_y(-16)
        pdf.set_draw_color(*MID)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(120, 128, 140)
        pdf.cell(0, 4, "Model-attributed sensitivity statements built from historical rates - not guaranteed outcomes and not planning advice.", new_x="LMARGIN", new_y="NEXT")
        stamp = datetime.now().strftime("%d %b %Y %H:%M")
        pdf.cell(90, 4, f"Generated {stamp}  |  {PRODUCT} - {TITLE}")
        pdf.cell(0, 4, f"Page {pdf.page_no()}/{{nb}}", align="R")
        pdf.set_text_color(*INK)

    def _section(self, title: str) -> None:
        pdf = self.pdf
        if pdf.get_y() > 250:
            pdf.add_page()
        pdf.ln(4)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.cell(0, 6.5, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*INK)
        pdf.ln(2)

    def _kv(self, pairs: list[tuple[str, str]]) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "", 9)
        for label, value in pairs:
            x = pdf.get_x()
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(46, 5.2, _latin(label))
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5.2, _latin(value), new_x="LMARGIN", new_y="NEXT")

    def _body(self, text: str, size: float = 9, colour: tuple | None = None, indent: int = 0) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "", size)
        if colour:
            pdf.set_text_color(*colour)
        pdf.set_x(14 + indent)
        pdf.multi_cell(0, 5.0, _latin(text), new_x="LMARGIN", new_y="NEXT")
        if colour:
            pdf.set_text_color(*INK)

    def _bullet(self, text: str, colour: tuple | None = None) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "", 9)
        if colour:
            pdf.set_text_color(*colour)
        pdf.set_x(18)
        pdf.multi_cell(0, 5.0, f"- {_latin(text)}", new_x="LMARGIN", new_y="NEXT")
        if colour:
            pdf.set_text_color(*INK)

    def _table(self, headers: list[str], rows: list[list[str]], widths: list[float], size: float = 7.5, colour_rows: list[tuple | None] | None = None) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "B", size)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        for header, width in zip(headers, widths):
            pdf.cell(width, 5.6, _latin(header), border=1, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", size)
        pdf.set_text_color(*INK)
        for row_index, row in enumerate(rows):
            colour = colour_rows[row_index] if colour_rows else None
            if colour:
                pdf.set_text_color(*colour)
            if pdf.get_y() > 268:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", size)
                pdf.set_fill_color(*NAVY)
                pdf.set_text_color(255, 255, 255)
                for header, width in zip(headers, widths):
                    pdf.cell(width, 5.6, _latin(header), border=1, fill=True)
                pdf.ln()
                pdf.set_font("Helvetica", "", size)
                pdf.set_text_color(*INK)
                if colour:
                    pdf.set_text_color(*colour)
            pdf.set_fill_color(*LIGHT) if row_index % 2 == 0 else None
            for cell, width in zip(row, widths):
                pdf.cell(width, 5.4, _latin(cell), border=1, fill=(row_index % 2 == 0))
            pdf.ln()
            if colour:
                pdf.set_text_color(*INK)

    def build(
        self,
        scheme_label: str,
        proposal: dict,
        score: dict,
        digest: dict,
        confidence: dict,
        calibration: dict | None,
        precedents: dict,
        objectives: dict,
        site: dict,
        brief: dict | None = None,
        override: dict | None = None,
    ) -> bytes:
        pdf = self.pdf
        pdf.add_page()

        self._header(scheme_label)
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*NAVY)
        pdf.cell(0, 8, _latin(scheme_label))
        pdf.set_text_color(*INK)
        pdf.ln(10)

        risk = score["refusal_probability"]
        band = score["risk_band"].upper()
        band_colour = GREEN if band == "LOW" else (AMBER if band == "MEDIUM" else RED)
        pdf.set_fill_color(*LIGHT)
        pdf.rect(14, pdf.get_y(), 182, 26, style="F")
        pdf.set_xy(18, pdf.get_y() + 3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(60, 6, "Estimated refusal probability")
        pdf.set_xy(18, pdf.get_y() + 7)
        pdf.set_font("Helvetica", "B", 24)
        pdf.set_text_color(*band_colour)
        pdf.cell(60, 11, f"{risk * 100:.0f}%")
        pdf.set_text_color(*INK)
        pdf.set_xy(84, pdf.get_y() - 13)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(50, 6, f"Risk band: {band}")
        if calibration:
            pdf.set_xy(84, pdf.get_y() + 6.5)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(
                0, 5,
                _latin(
                    f"Calibration: schemes scored in the {calibration['band']} band historically refused "
                    f"at {calibration['observed_rate'] * 100:.0f}% (95% CI {calibration['ci_lo'] * 100:.0f}-{calibration['ci_hi'] * 100:.0f}%, n={calibration['n']})."
                ),
            )
        specialised = confidence.get("specialised")
        if specialised:
            pdf.set_xy(18, pdf.get_y() + 9)
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*AMBER)
            pdf.multi_cell(
                0, 5,
                _latin(
                    f"Specialised scheme disclosure: senior-living/care schemes historically refuse at "
                    f"{specialised['observed_rate_pre2024'] * 100:.0f}% (n={specialised['n']}); "
                    f"the general score shown above is the model output and the specialised prior-adjusted figure is "
                    f"{specialised['specialised_prior_adjusted'] * 100:.0f}%."
                ),
            )
            pdf.set_text_color(*INK)
        pdf.ln(30)

        self._section("1. Scheme")
        self._kv([
            ("Planning authority", proposal.get("authority") or "-"),
            ("Application type", precedents.get("summary", {}).get("bucket", "-")),
            ("Description", proposal.get("description") or "-"),
            ("Residential units", f"{proposal.get('units') or '-'}"),
            ("Site area", f"{proposal.get('site_area_sqm') or '-'} m2"),
            ("Floor area", f"{proposal.get('floor_area_sqm') or '-'} m2"),
            ("Submission year", str(proposal.get("submission_year") or "-")),
        ])
        if site.get("coordinates", {}).get("itm_easting") is not None:
            self._kv([("ITM coordinates", f"E {site['coordinates']['itm_easting']:.0f} / N {site['coordinates']['itm_northing']:.0f}")])

        self._section("2. What drives this score")
        if digest.get("summary"):
            self._body(digest["summary"])
        for factor in digest.get("factors", []):
            self._bullet(factor["text"])

        self._section("3. Confidence and fallbacks")
        for note in confidence.get("confidence_notes", []):
            self._bullet(note, colour=AMBER if "Few recent precedents" in note else None)
        if confidence.get("fallbacks"):
            self._body("Inputs the model approximated:", size=8.5)
            for fallback in confidence["fallbacks"]:
                self._bullet(fallback)

        self._section("4. The closest past applications")
        summary = precedents.get("summary", {})
        if summary.get("retrieved"):
            self._body(
                f"The {summary.get('retrieved')} closest past applications, matched on wording, unit count, density, council and "
                f"recency - decided applications received in the last 5 years only ({summary.get('pool')} on file for this scheme "
                f"type, {summary.get('same_council_count')} in {proposal.get('authority')}). "
                f"Of these, {summary.get('refused_count')} were refused and {summary.get('granted_count')} granted."
            )
            pdf.ln(1)
            rows: list[list[str]] = []
            colours: list[tuple | None] = []
            for item in precedents.get("precedents", [])[:20]:
                rows.append([
                    item["application_number"],
                    _latin(item["council"])[:22],
                    item["received_date"],
                    item["decision_date"] or "-",
                    "-" if item["units"] is None else f"{item['units']:.0f}",
                    item["outcome"],
                    item["wording_label"],
                ])
                colours.append(RED if item["outcome"] == "Refused" else GREEN)
            self._table(["App ref", "Council", "Received", "Decision", "Units", "Outcome", "Wording"], rows,
                        [24, 36, 24, 24, 14, 20, 20], size=7.5, colour_rows=colours)
            pdf.ln(1)
            self._body("Inspector rationale (refused cases with extracted reasons):", size=8.5)
            for item in precedents.get("precedents", [])[:20]:
                if item["outcome"] == "Refused" and item.get("rationale"):
                    self._bullet(f"{item['application_number']} ({item.get('rationale_label') or item.get('rationale_tag')}): {item['rationale']}", colour=RED)

        self._section("6. Development plan crosswalk")
        obj_summary = objectives.get("summary")
        if obj_summary:
            self._body(
                f"Plan in force: {_latin(obj_summary.get('plan_document'))} ({obj_summary.get('plan_period')}) "
                f"- {obj_summary.get('objective_count')} objectives, {obj_summary.get('mention_count')} mentions. "
                f"Addressed in your description text: {obj_summary.get('addressed')}; not addressed: {obj_summary.get('open')}"
                + (f"; site-flagged: {obj_summary.get('flagged')}" if obj_summary.get("flagged") else "")
                + (" (nearest plan used - no plan period matched the submission year)." if obj_summary.get("fallback_used") else ".")
            )
            rows = []
            for item in objectives.get("objectives", [])[:120]:
                status = {"addressed": "Addressed", "open": "Open", "flag": "FLAG"}[item["status"]]
                rows.append([item["code"], _latin(item["title"])[:88], item["theme_label"], status])
            colour_rows = []
            for item in objectives.get("objectives", [])[:120]:
                colour_rows.append(GREEN if item["status"] == "addressed" else (RED if item["status"] == "flag" else None))
            self._table(["Code", "Objective", "Theme", "Status"], rows, [18, 112, 32, 22], size=6.5, colour_rows=colour_rows)
            if obj_summary.get("objective_count", 0) > 120:
                self._body(f"(Showing the 120 most-cited of {obj_summary.get('objective_count')} objectives.)", size=8)

        self._section("6. Site evidence")
        flood = site.get("flood")
        if flood:
            status_text = "IN MAPPED FLOOD ZONE" if flood["flood_any"] else "No mapped flood-zone hit"
            self._bullet(
                f"Flood: {status_text} (nearest fluvial zone {flood['nearest_fluvial_m']:.0f} m, nearest coastal zone {flood['nearest_coastal_m']:.0f} m).",
                colour=RED if flood["flood_any"] else GREEN,
            )
        small_area = site.get("small_area")
        if small_area:
            self._bullet(
                f"Census small area: {small_area.get('urban_area_name') or small_area.get('nuts3')}, "
                f"{small_area.get('pop_density_per_sqkm'):.0f} people/km2, owner-occupied {small_area.get('owner_share'):.0f}%, "
                f"private rent {small_area.get('private_rent_share'):.0f}%."
            )
        rates = site.get("nearby_rates", {})
        if rates.get("within_1km"):
            self._bullet(
                f"Local track record: {rates['within_1km']['recent_24m_count']} applications within 1km in the last 24 months, "
                f"{rates['within_1km']['recent_24m_refusal_rate'] * 100:.0f}% refused; "
                f"within 3km: {rates['within_3km']['recent_24m_count']} applications, {rates['within_3km']['recent_24m_refusal_rate'] * 100:.0f}% refused."
            )
        zoning = site.get("zoning")
        if zoning and zoning.get("status") == "ok":
            self._bullet(f"Zoning: {zoning.get('zone')} - {_latin(zoning.get('zone_description') or '')} ({zoning.get('plan_period')})")
        elif zoning:
            self._bullet(f"Zoning: {_latin(zoning.get('note') or 'not available')}")

        self._section("7. Risk register and unknowns")
        if brief:
            register = brief.get("register") or []
            self._body(
                "Severities are derived only from data the project holds; where no data exists the row is marked "
                "UNVERIFIED with a confirm-action, never an invented severity."
            )
            pdf.ln(1)
            order = {"high": 0, "medium": 1, "low": 2, "unverified": 3}
            register_rows = []
            register_colours = []
            severity_colour = {"high": RED, "medium": AMBER, "low": GREEN, "unverified": None}
            for row in sorted(register, key=lambda r: order[r["severity"]]):
                register_rows.append([
                    row["severity"].upper(),
                    _latin(row["issue"])[:44],
                    _latin(row["evidence"])[:86],
                    _latin(row["mitigation"])[:60],
                    _latin(row["owner"]),
                ])
                register_colours.append(severity_colour[row["severity"]])
            self._table(["Sev", "Issue", "Evidence", "Mitigation", "Owner"], register_rows, [20, 46, 60, 40, 28], size=6.5, colour_rows=register_colours)
            next_actions = brief.get("next_actions") or []
            if next_actions:
                pdf.ln(1)
                self._body("Next actions by owner:", size=8.5)
                for action in next_actions[:14]:
                    self._bullet(f"[{action['severity']}] ({action['owner']}) {action['issue']} - {action['action']}", colour=RED if action["severity"] in ("high", "medium") else None)
        else:
            self._body("Risk register not included in this build.")

        self._section("8. Evidence quality")
        if brief and brief.get("evidence_quality"):
            for stamp in brief["evidence_quality"]:
                self._bullet(f"{stamp['input']} [{stamp['status']}]: {stamp['stamp']}")
        else:
            self._body("Evidence-quality stamps not included in this build.")

        if override:
            self._section("9. Planner note (override)")
            self._body(
                f"Recorded by {override.get('planner_name') or 'planner'} on {override.get('created_at', '')[:16]}: "
                f"{override.get('target')} set from {override.get('original_value')} to {override.get('override_value')}."
            )
            self._body(f"Rationale: {override.get('rationale')}")
            self._body("The model value remains unchanged in the scoring log; the override is an explicit professional judgment on the record.")

        return bytes(pdf.output())


def build_report_pdf(**kwargs) -> bytes:
    report = ReviewReport()
    return report.build(**kwargs)
