"""Downloadable views of a stored run. JSON retains the complete machine record."""

import csv
from io import BytesIO, StringIO
import json
from xml.sax.saxutils import escape


def _csv(fields, rows):
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _cell(row.get(field)) for field in fields})
    return stream.getvalue().encode("utf-8")


def _cell(value):
    if isinstance(value, (dict, list, tuple, bool)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    # Keep cells literal when a spreadsheet opens user-provided data.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def trace_csv(report):
    fields = ("sequence", "name", "kind", "method", "status", "started_utc", "duration_ms",
              "input_keys", "output_keys", "error_code", "json_pointer")
    rows = (step | {"input_keys": list(step["inputs"]), "output_keys": list(step["outputs"] or {}),
                    "error_code": (step["error"] or {}).get("code"),
                    "json_pointer": f"/calculation_trace/{index}"}
            for index, step in enumerate(report["calculation_trace"]))
    return _csv(fields, rows)


def segments_csv(report):
    fields = ("platform", "option_id", "phase", "kind", "start_cell", "end_cell", "horizontal_m", "surface_m", "rise_m",
              "duration_s", "gross_energy_j", "supply_j", "mean_discharge_w", "remaining_j_after_supply",
              "power_and_reserve_passed")
    publication = next((step["outputs"] for step in report["calculation_trace"]
                        if step["name"] == "result.publish" and step["status"] == "completed"), {})
    rows = ({"platform": platform, **row, "supply_j": (row["battery_phase"] or {}).get("supply_j")}
            for platform, result in publication.get("platforms", {}).items() for row in result["segments"])
    return _csv(fields, rows)


def pdf_summary(report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, topMargin=48, bottomMargin=45,
                            leftMargin=46, rightMargin=46, title="Return Window run report")
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#162835")
    styles["Heading2"].textColor = colors.HexColor("#245561")
    story = []

    def line(value, style="BodyText"):
        clean = "".join(char if char.isprintable() else " " for char in str(value))
        story.append(Paragraph(escape(clean), styles[style]))

    line("Return Window run report", "Title")
    line(f"{report['kind'].replace('_', ' ').capitalize()} / {report['status']}", "Heading2")
    line(f"Report {report['report_id']} | Request {report['request_id']}")
    line(f"Recorded {report['started_utc']} | Revision {report['revision'] if report['revision'] is not None else 'unassigned'}")
    result = report["result"] or {}
    provenance = report["provenance"]
    if classification := provenance.get("classification", result.get("classification")):
        line(f"Classification {classification}")
    if "scope" in provenance:
        line(provenance["scope"])
    if report["error"] is not None:
        line(f"{report['error']['code']} / {report['error']['message']}")
    if report["request"].get("objective"):
        line(f"Objective  {report['request']['objective']}")
    if "time_utc" in result:
        line(f"Mission time {result['time_utc']} | Remaining {result['remaining_s']} s | Reserve {result['reserve_s']} s")
    platforms = {name: result[name] for name in ("human", "rover") if name in result}
    if "marswalk" in result:
        platforms[result["marswalk"]["platform"]] = result["marswalk"]
    if not platforms and result and report["kind"] == "fixture_plan":
        line("Route and constraints", "Heading2")
        line(f"{result['status']} | Recommendation {result['recommendation'] or 'withheld'}")
        line(f"Time budget {result['remaining_s']} s | Reserve {result['reserve_s']} s")
        if result["direct_return"] is not None:
            line(f"Direct return {result['direct_return']['seconds']:.1f} s | Margin {result['return_margin_s']:.1f} s")
        for option in result["science"]:
            decision = "feasible" if option["feasible"] else "withheld"
            margin_s = "unknown" if option["margin_s"] is None else f"{option['margin_s']:.1f} s"
            line(f"{option['id']} | {decision} | Time margin {margin_s}")
    if result and report["kind"] == "cell_ranking":
        line("Cell ranking", "Heading2")
        counts = result["counts"]
        line(f"Direct {counts['direct_cells']} | Partial {counts['partial_cells']} | Thematic {counts['thematic_cells']}")
        line(f"Areas returned {len(result['areas'])} | Abstained {result['abstain']}")
        line(f"Ranking pack {result['pack']['version']} | SHA-256 {result['pack']['sha256']}")
    for platform, plan in platforms.items():
        line(f"{platform.capitalize()} route and constraints", "Heading2")
        line(f"{plan['status']} | Recommendation {plan['recommendation'] or 'withheld'} "
             f"| Pareto front {', '.join(plan['pareto_front']) or 'empty'}")
        for option in plan["candidates"]:
            margin = option["margin_s"]
            text = "unknown" if margin is None else f"{margin:.1f} s"
            ledger = option["energy_ledger"]
            if ledger and ledger["total_use"] is not None:
                text += f" | Gross energy {ledger['total_use'] / 3600:.2f} Wh"
            line(f"{option['id']} | Time margin {text}")
            if "envelope_class" in option and option["envelope_class"] is not None:
                line(f"Crew reserve classification {option['envelope_class']}")
            for gate in option["constraints"]:
                line(f"{gate['rule']} / {gate['outcome']} / {gate['reason']}")
    if platforms:
        line("Assumptions and limits", "Heading2")
        limits = list(dict.fromkeys(note for plan in platforms.values() for note in plan["assumptions"]))
        # Integrated human consumables and walkback supersede these base-planner defaults.
        if "tradeoff" in result:
            limits = [note for note in limits if not note.startswith(("Only crew time", "Rover walkback uses", "Historical weather"))]
            limits.extend(result["tradeoff"]["limits"])
        for note in limits:
            line(note)
    line("Calculation trace", "Heading2")
    if not report["calculation_trace"]:
        line("No calculation stages recorded.")
    for step in report["calculation_trace"]:
        elapsed = "" if step["duration_ms"] is None else f" / {step['duration_ms']:.1f} ms"
        line(f"{step['sequence']}  {step['name']} / {step['status']}{elapsed} | {step['method']}")
    artifacts = [(key, value["sha256"]) for key, value in provenance.items()
                 if isinstance(value, dict) and "sha256" in value]
    if artifacts:
        line("Dataset and model provenance", "Heading2")
        for name, digest in artifacts:
            line(f"{name.replace('_', ' ')}")
            line(f"SHA-256 {digest}")

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#50616A"))
        canvas.drawString(46, 27, f"Return Window  /  {report['report_id']}")
        canvas.drawRightString(A4[0] - 46, 27, f"Page {document.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
