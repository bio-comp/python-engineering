"""Two Markdown views and a paginated PDF from one validated table model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

from python_engineering.reporting import REPORT_GENERATOR_VERSION
from python_engineering.reporting.analysis import Analysis
from python_engineering.reporting.models import Run


@dataclass(frozen=True)
class TableSpec:
    title: str
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    widths: tuple[float, ...]


def fmt(value: float | int | None, precision: int = 3) -> str:
    if value is None:
        return "NOT MEASURED"
    if isinstance(value, int):
        return str(value)
    return f"{value:,.{precision}f}"


def _metrics_table(analysis: Analysis) -> TableSpec:
    b, c = analysis.baseline, analysis.candidate
    rows = []
    for label, field in (
        ("Recorded observation rows", "recorded_rows"),
        ("Measured rows", "measured_rows"),
        ("Diagnostic rows", "detection_rows"),
        ("True positives", "tp"),
        ("False positives", "fp"),
        ("True negatives", "tn"),
        ("False negatives", "fn"),
        ("Precision", "precision"),
        ("Recall", "recall"),
        ("Specificity", "specificity"),
        ("Accuracy", "accuracy"),
        ("Duration observations", "duration_count"),
        ("Median duration (ms)", "median_duration_ms"),
    ):
        rows.append((label, fmt(getattr(b, field)), fmt(getattr(c, field))))
    return TableSpec(
        "Measured outcomes: distinct condition-level observations",
        ("Metric / denominator", "Baseline", "Candidate"),
        tuple(rows),
        (0.50, 0.25, 0.25),
    )


def report_tables(run: Run, analysis: Analysis) -> tuple[TableSpec, ...]:
    env = run.environment
    condition = TableSpec(
        "Exact experimental conditions",
        ("Aspect", "Baseline", "Candidate"),
        (
            ("Tool identity", run.baseline.upstream_identity, run.candidate.upstream_identity),
            ("Version", run.baseline.version, run.candidate.version),
            ("Configuration", run.baseline.configuration, run.candidate.configuration),
        ),
        (0.23, 0.385, 0.385),
    )
    environment = TableSpec(
        "Observed execution provenance",
        ("Attribute", "Exact value"),
        tuple(
            (key, value)
            for key, value in (
                ("Python", f"{env.python_implementation} {env.python_version}"),
                ("Interpreter executable", env.interpreter_executable),
                ("uv", env.uv_version),
                ("Operating system", f"{env.os_name} {env.os_release} ({env.architecture})"),
                ("Runtime / CI runner", f"{env.runtime_identity}; {env.ci_runner}"),
                ("Repository / branch", f"{env.repository} / {env.branch}"),
                ("Git commit", env.commit_sha),
                ("Fixture revision", env.fixture_revision),
                ("Lockfile SHA-256", env.lockfile_sha256),
                ("pyproject.toml SHA-256", env.pyproject_sha256),
                ("Harness / generator", f"{env.harness_version} / {env.generator_version}"),
                (
                    "Tool versions",
                    "; ".join(f"{k}={v}" for k, v in sorted(env.tool_versions.items()))
                    or "NOT MEASURED",
                ),
                (
                    "Dependencies",
                    "; ".join(f"{k}={v}" for k, v in sorted(env.dependency_versions.items()))
                    or "NOT MEASURED",
                ),
                ("Hardware", env.hardware),
                (
                    "Selected environment",
                    "; ".join(f"{k}={v}" for k, v in sorted(env.selected_environment.items()))
                    or "NOT MEASURED",
                ),
                ("Seeds", ", ".join(map(str, env.random_seeds)) or "NOT APPLICABLE"),
                ("Model / permissions", f"{env.model_identity}; {env.agent_permissions}"),
                ("Prompt revision", env.prompt_revision),
                ("Source retrieval time", env.source_retrieved_at),
            )
        ),
        (0.26, 0.74),
    )
    paired = TableSpec(
        "Paired evidence (description, not an IID inferential claim)",
        ("Measure", "Observed"),
        (
            ("Matched case/repetition/seed pairs", str(analysis.paired.matched_detection_pairs)),
            ("Baseline-only correct", str(analysis.paired.baseline_only_correct)),
            ("Candidate-only correct", str(analysis.paired.candidate_only_correct)),
            ("Both correct", str(analysis.paired.both_correct)),
            ("Both wrong", str(analysis.paired.both_wrong)),
            (
                "Candidate - baseline accuracy",
                fmt(analysis.paired.candidate_minus_baseline_accuracy),
            ),
            ("Candidate-only true-positive detections", str(analysis.paired.unique_true_positives)),
        ),
        (0.70, 0.30),
    )
    score = TableSpec(
        "Criterion-level rubric outcomes (no inferred adoption)",
        ("ID / dimension", "Metric / scope", "Value / n", "0-4 score / evidence"),
        tuple(
            (
                f"{c.criterion_id}: {c.dimension}",
                f"{c.metric} / {c.condition_id}",
                f"{fmt(c.value)} / {c.denominator}",
                f"{fmt(c.score)} / {c.evidence_grade}; {c.state.value}",
            )
            for c in analysis.criteria
        )
        or (("No prespecified criteria", "NOT MEASURED", "-", "NOT MEASURED"),),
        (0.26, 0.22, 0.18, 0.34),
    )
    gates = TableSpec(
        "Noncompensatory acceptance gates",
        ("Gate", "Outcome", "Requirement / supporting evidence"),
        tuple(
            (
                gate.gate_id,
                "PASS" if gate.passed else "FAIL" if gate.passed is False else "UNKNOWN",
                (
                    f"{gate.requirement}; receipts: "
                    f"{', '.join(gate.evidence_ids) or 'NONE'}; {gate.note}"
                ),
            )
            for gate in run.gates
        )
        or (("NONE", "UNKNOWN", "No gate evidence supplied"),),
        (0.18, 0.16, 0.66),
    )
    observations = TableSpec(
        "Raw observation ledger (each finding traces to a receipt)",
        (
            "Observation / case",
            "Condition / repetition",
            "State",
            "Oracle / outcome",
            "Time ms / evidence",
        ),
        tuple(
            (
                f"{o.observation_id} / {o.case_id}",
                f"{o.condition_id} / {o.repetition} / seed={o.seed}",
                o.state.value,
                f"{o.expected_defect} / {o.detected_defect}",
                f"{fmt(o.duration_ms)} / {o.evidence_id}",
            )
            for o in run.observations
        )
        or (("NONE", "-", "NOT MEASURED", "-", "-"),),
        (0.22, 0.21, 0.18, 0.18, 0.21),
    )
    evidence = TableSpec(
        "Evidence receipts and independent/source strength",
        ("Receipt", "Strength", "Identity / locator / note"),
        tuple(
            (e.evidence_id, e.grade.value, f"{e.source}; {e.locator}; {e.note}")
            for e in run.evidence
        )
        or (("NONE", "NOT MEASURED", "No evidence supplied"),),
        (0.15, 0.22, 0.63),
    )
    independent = any(e.grade.value == "independently_reproduced" for e in run.evidence)
    measured = analysis.baseline.measured_rows + analysis.candidate.measured_rows
    checklist = TableSpec(
        "Standard experimental evidence checklist",
        ("Control", "Assessment", "Scope / caveat"),
        (
            (
                "Protocol and hypotheses",
                "DECLARED",
                (
                    "Identity, revision and prespecified criteria are provided; "
                    "provenance must be audited"
                ),
            ),
            (
                "Execution provenance",
                "DECLARED",
                (
                    "Interpreter, exact versions, hashes, commands, branch and commit "
                    "supplied; not externally attested"
                ),
            ),
            (
                "Raw measurements",
                "SYNTHETIC"
                if run.synthetic_demonstration
                else ("PRESENT" if measured else "NOT MEASURED"),
                "Measured rows: " + str(measured),
            ),
            (
                "Paired baseline/candidate",
                "PRESENT" if analysis.paired.matched_detection_pairs else "INSUFFICIENT",
                "Matched case/repetition/seed pairs: "
                + str(analysis.paired.matched_detection_pairs),
            ),
            (
                "Prespecified anchored scoring",
                "PRESENT" if run.criteria else "NOT MEASURED",
                "No composite score is inferred",
            ),
            (
                "False positive and negative review",
                "PRESENT" if analysis.candidate.detection_rows else "NOT MEASURED",
                "Requires independently labeled representative corpus to generalize",
            ),
            (
                "Noncompensatory gates",
                analysis.essential_gate_state,
                "Missing/failed gates override any favorable score",
            ),
            (
                "Independent reproduction",
                "PRESENT" if independent and not run.synthetic_demonstration else "NOT MEASURED",
                "Local synthetic checks do not establish efficacy",
            ),
            (
                "Interpretation / limitations",
                "DECLARED",
                "Human-supplied interpretation remains a snapshot, not a Drive decision",
            ),
            (
                "Report reproducibility",
                "GENERATED",
                "Inspect manifest.json SHA-256 entries; printed reports are versioned snapshots",
            ),
        ),
        (0.26, 0.21, 0.53),
    )
    commands = TableSpec(
        "Exact reproduction commands as recorded by the run",
        ("Sequence", "Command"),
        tuple((str(i), command) for i, command in enumerate(env.commands, 1)),
        (0.12, 0.88),
    )
    rubric = TableSpec(
        "Prespecified 0-4 anchors (scores require actual metrics)",
        ("Criterion", "Anchors 0 / 1 / 2 / 3 / 4"),
        tuple(
            (c.criterion_id, " | ".join(f"{n}: {a}" for n, a in enumerate(c.anchors)))
            for c in run.criteria
        )
        or (("NONE", "NOT MEASURED"),),
        (0.18, 0.82),
    )
    return (
        condition,
        environment,
        _metrics_table(analysis),
        paired,
        gates,
        score,
        rubric,
        observations,
        evidence,
        checklist,
        commands,
    )


def _md_cell(cell: str) -> str:
    return cell.replace("|", r"\|").replace("\n", " ").replace("\r", " ")


def _markdown_table(table: TableSpec) -> str:
    header = "| " + " | ".join(map(_md_cell, table.headers)) + " |"
    rule = "| " + " | ".join("---" for _ in table.headers) + " |"
    rows = ["| " + " | ".join(_md_cell(v) for v in row) + " |" for row in table.rows]
    return "\n".join((f"### {table.title}", "", header, rule, *rows, ""))


def render_markdown(run: Run, analysis: Analysis, *, detailed: bool) -> str:
    e = run.experiment
    banner = (
        "**SYNTHETIC DEMONSTRATION - NOT EMPIRICAL TOOL EVIDENCE**"
        if run.synthetic_demonstration
        else ("**EVIDENCE SNAPSHOT - DO NOT INFER QUALIFICATION OR ADOPTION**")
    )
    lines = [
        f"# {e.title}",
        "",
        banner,
        "",
        (
            f"Experiment **{e.experiment_id}** / protocol "
            f"**{e.protocol_revision}** / run **{e.run_id}**"
        ),
        "",
        f"Execution: **{e.executed_at.isoformat()}** | Study status: **{e.status.value}**",
        "",
        f"**Question:** {e.research_question}",
        "",
        f"**Hypothesis:** {e.hypothesis}",
        "",
        f"**Prespecified decision criteria:** {e.prespecified_criteria}",
        "",
        f"**Source-reported interpretation:** {run.interpretation.summary}",
        "",
        f"**Essential gates:** {analysis.essential_gate_state}",
        "",
        f"**Disposition (recorded, not generated):** {run.interpretation.disposition}",
        "",
        f"**Applicability:** {run.interpretation.applicability}",
        "",
        f"**Statistical scope:** {analysis.statistical_scope}",
        "",
        "## Key measured results",
        "",
        _markdown_table(_metrics_table(analysis)),
        _markdown_table(report_tables(run, analysis)[3]),
        "## Limitations",
        "",
        *[f"- {x}" for x in run.interpretation.limitations],
        "",
        f"**Next qualification step:** {run.interpretation.proposed_next_step}",
        "",
    ]
    if detailed:
        lines += ["## Complete evidence and reproducibility record", ""]
        for table in report_tables(run, analysis):
            lines.extend([_markdown_table(table), ""])
        lines += [
            "## Reproduction and governance boundary",
            "",
            (
                f"Reporting generator: {REPORT_GENERATOR_VERSION}; "
                f"rubric revision: {run.rubric_revision}; schema {run.schema_version}."
            ),
            "",
            (
                "The run JSON is the frozen input. This report is a generated snapshot, "
                "not the Google Drive research canonical."
            ),
            "",
            (
                "A passing gate alone cannot authorize tool adoption; false-positive, "
                "generalization, and independent-review requirements remain."
            ),
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def render_pdf(run: Run, analysis: Analysis, target: Path) -> None:
    """Vector/selectable PDF with controlled-width, wrapped, repeated-header tables."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        CondPageBreak,
        HRFlowable,
        LongTable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        TableStyle,
    )

    navy = colors.HexColor("#15314F")
    teal = colors.HexColor("#096F7D")
    slate = colors.HexColor("#425569")
    pale = colors.HexColor("#EAF1F5")
    line = colors.HexColor("#D7E2E9")
    white = colors.white
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ResearchTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=27,
        textColor=navy,
        spaceAfter=12,
        alignment=TA_LEFT,
    )
    label_style = ParagraphStyle(
        "ResearchKicker",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.4,
        leading=12,
        textColor=teal,
        spaceAfter=9,
    )
    heading_style = ParagraphStyle(
        "ResearchHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.2,
        leading=16,
        textColor=navy,
        spaceBefore=17,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ResearchBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.0,
        leading=13.5,
        textColor=slate,
        spaceAfter=8,
        allowWidows=0,
        allowOrphans=0,
        splitLongWords=1,
    )
    cell_style = ParagraphStyle(
        "ResearchCell",
        parent=body_style,
        fontSize=7.6,
        leading=10.5,
        spaceAfter=0,
        wordWrap="CJK",
        splitLongWords=1,
    )
    header_style = ParagraphStyle(
        "ResearchTableHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        fontSize=7.7,
        leading=10.7,
        textColor=white,
    )
    doc = SimpleDocTemplate(
        str(target),
        pagesize=letter,
        leftMargin=48,
        rightMargin=48,
        topMargin=50,
        bottomMargin=46,
        title=f"{run.experiment.experiment_id} evaluation report",
        author="Python Engineering Laboratory",
        pageCompression=1,
        invariant=1,
    )
    content_width = letter[0] - 96

    def plain(value: str) -> str:
        return xml_escape(value).replace("\n", " ")

    def paragraph(label: str, value: str) -> Paragraph:
        return Paragraph(f"<b>{plain(label)}:</b> {plain(value)}", body_style)

    def page_footer(canvas: object, d: object) -> None:
        # Narrow dynamic canvas bridge; ReportLab owns the canvas protocol.
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus.doctemplate import BaseDocTemplate

        assert isinstance(canvas, Canvas)
        assert isinstance(d, BaseDocTemplate)
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(48, 39, letter[0] - 48, 39)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(slate)
        canvas.drawString(
            48,
            27,
            (
                f"{run.experiment.experiment_id} / {run.experiment.run_id}  |  "
                f"rubric {run.rubric_revision}"
            ),
        )
        canvas.drawRightString(
            letter[0] - 48, 27, f"Page {d.page}  |  report {REPORT_GENERATOR_VERSION}"
        )
        canvas.restoreState()

    def build_table(spec: TableSpec) -> LongTable:
        rows: list[list[Paragraph]] = [[Paragraph(plain(h), header_style) for h in spec.headers]]
        for row_index, row in enumerate(spec.rows):
            cells = []
            for col_index, value in enumerate(row):
                content = plain(value)
                if (
                    spec.title.startswith("Evidence receipts")
                    and col_index == 2
                    and row_index < len(run.evidence)
                ):
                    source = run.evidence[row_index].source
                    parsed = urlparse(source)
                    if parsed.scheme == "https" and parsed.netloc and not parsed.username:
                        href = xml_escape(source, {'"': "&quot;"})
                        content = f'<link href="{href}" color="#096F7D">{content}</link>'
                cells.append(Paragraph(content, cell_style))
            rows.append(cells)
        widths = [content_width * part for part in spec.widths]
        table = LongTable(
            rows,
            colWidths=widths,
            repeatRows=1,
            hAlign="LEFT",
            splitByRow=1,
            spaceAfter=10,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
                    ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.2, teal),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, line),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, pale]),
                ]
            )
        )
        return table

    e = run.experiment
    story = [
        Paragraph("PYTHON ENGINEERING  /  EVIDENCE SNAPSHOT", label_style),
        Paragraph(plain(e.title), title_style),
        HRFlowable(width="100%", thickness=1.4, color=teal, spaceAfter=18),
        paragraph("Run", f"{e.experiment_id} / {e.run_id} / protocol {e.protocol_revision}"),
        paragraph("Date", e.executed_at.isoformat()),
        paragraph("Study status", e.status.value),
        paragraph("Interpretation", run.interpretation.summary),
        paragraph("Essential gates", analysis.essential_gate_state),
        paragraph("Recorded disposition", run.interpretation.disposition),
        paragraph("Applicability", run.interpretation.applicability),
        paragraph("Evidence limitation", "; ".join(run.interpretation.limitations)),
        Spacer(1, 15),
        Paragraph(
            "SYNTHETIC DATA: NOT A REAL TOOL RESULT"
            if run.synthetic_demonstration
            else "SOURCE-BOUNDED SNAPSHOT: NO AUTOMATIC ADOPTION DECISION",
            ParagraphStyle("Caution", parent=label_style, fontSize=10.5, leading=14),
        ),
        Paragraph("Measured outcomes", heading_style),
        build_table(_metrics_table(analysis)),
        PageBreak(),
        Paragraph("Design and environment", title_style),
        paragraph("Research question", e.research_question),
        paragraph("Hypothesis", e.hypothesis),
        paragraph("Prespecified criteria", e.prespecified_criteria),
        build_table(report_tables(run, analysis)[0]),
        build_table(report_tables(run, analysis)[1]),
        PageBreak(),
        Paragraph("Evidence and scoring", title_style),
    ]
    for spec in report_tables(run, analysis)[2:]:
        # Reserve room for both the heading and at least one table header/data row.
        # A KeepTogether around the heading alone produces orphaned section titles.
        story.append(CondPageBreak(110))
        story.append(Paragraph(plain(spec.title), heading_style))
        story.append(build_table(spec))
    story += [
        Paragraph("Interpretation and boundaries", heading_style),
        paragraph("Descriptive statistics", analysis.statistical_scope),
        paragraph("Next step", run.interpretation.proposed_next_step),
        paragraph(
            "Governance",
            (
                "Generated versioned evidence snapshot only; Google Drive retains "
                "experiment protocols, decisions, practices and source qualification."
            ),
        ),
    ]
    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
