"""Server-side PDF rendering for NutriCare's daily nutrition record.

The document is deliberately built only from the already-calculated dashboard
summary, meal entries, and daily insights payload. It does not manufacture
clinical findings, food records, or recommendations.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


FOREST = colors.HexColor("#1E3B2B")
DEEP_FOREST = colors.HexColor("#072517")
EMERALD = colors.HexColor("#2F694D")
SAGE = colors.HexColor("#85A590")
OAT = colors.HexColor("#F4EFEB")
OAT_DARK = colors.HexColor("#E2D9CE")
INK = colors.HexColor("#18221E")
MUTED = colors.HexColor("#526059")
TERRACOTTA = colors.HexColor("#C2612D")
SKY = colors.HexColor("#476553")
WHITE = colors.white

MEAL_ORDER = ("breakfast", "lunch", "snacks", "dinner")
MEAL_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "snacks": "Snacks & beverages",
}
MICRO_ROWS = (
    ("Dietary fiber", "fiber_g", "g", False),
    ("Sodium", "sodium_mg", "mg", True),
    ("Potassium", "potassium_mg", "mg", False),
    ("Calcium", "calcium_mg", "mg", False),
    ("Iron", "iron_mg", "mg", False),
)


def _number(value: Any, digits: int = 0) -> str:
    """Format a numeric value for a PDF while handling absent values safely."""
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _safe(value: Any) -> str:
    return escape(str(value or ""))


def _meal_totals(entries: list[dict]) -> dict[str, float]:
    keys = ("kcal", "protein_g", "carbs_g", "fat_g")
    totals = {key: 0.0 for key in keys}
    for entry in entries:
        nutrients = entry.get("nutrients") or {}
        for key in keys:
            try:
                totals[key] += float(nutrients.get(key) or 0)
            except (TypeError, ValueError):
                continue
    return totals


class DailyIntakeChart(Flowable):
    """Four stacked, data-only meal bars for the daily PDF record."""

    chart_height = 182

    def __init__(self, grouped_meals: dict[str, list[dict]]):
        super().__init__()
        self.rows = [(meal, _meal_totals(grouped_meals.get(meal, []))) for meal in MEAL_ORDER]
        self.width = 0
        self.height = self.chart_height

    def wrap(self, available_width, available_height):
        self.width = available_width
        return available_width, self.chart_height

    def draw(self):  # noqa: C901 - drawing coordinates are intentionally local
        canvas = self.canv
        left, right, bottom, top = 34, 12, 35, 23
        plot_w = max(20, self.width - left - right)
        plot_h = self.chart_height - bottom - top
        maximum = max(1.0, *(totals["kcal"] for _, totals in self.rows))

        canvas.saveState()
        canvas.setStrokeColor(OAT_DARK)
        canvas.setLineWidth(0.6)
        for fraction in (0, 0.5, 1):
            y = bottom + plot_h * fraction
            canvas.line(left, y, self.width - right, y)
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 6.5)
            canvas.drawRightString(left - 4, y - 2, f"{round(maximum * fraction):,}")

        colors_for_macro = (("protein_g", 4.0, EMERALD), ("carbs_g", 4.0, SAGE),
                            ("fat_g", 9.0, TERRACOTTA))
        step = plot_w / len(self.rows)
        bar_w = min(42, step * 0.45)
        for index, (meal, totals) in enumerate(self.rows):
            x = left + step * index + (step - bar_w) / 2
            total_kcal = max(0.0, totals["kcal"])
            macro_kcal = sum(max(0.0, totals[key]) * multiplier
                             for key, multiplier, _ in colors_for_macro)
            scale = total_kcal / macro_kcal if macro_kcal > total_kcal and macro_kcal else 1.0
            y = bottom
            for key, multiplier, colour in colors_for_macro:
                energy = max(0.0, totals[key]) * multiplier * scale
                height = plot_h * energy / maximum
                if height:
                    canvas.setFillColor(colour)
                    canvas.rect(x, y, bar_w, height, stroke=0, fill=1)
                    y += height
            remainder = max(0.0, total_kcal - macro_kcal * scale)
            remainder_h = plot_h * remainder / maximum
            if remainder_h:
                canvas.setFillColor(OAT_DARK)
                canvas.rect(x, y, bar_w, remainder_h, stroke=0, fill=1)
            canvas.setStrokeColor(FOREST)
            canvas.setLineWidth(0.5)
            canvas.rect(x, bottom, bar_w, plot_h * total_kcal / maximum, stroke=1, fill=0)
            canvas.setFillColor(INK)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.drawCentredString(x + bar_w / 2, bottom + plot_h * total_kcal / maximum + 5,
                                     f"{round(total_kcal):,}")
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 7)
            canvas.drawCentredString(x + bar_w / 2, 17, MEAL_LABELS[meal].split(" &")[0])

        legend_x = left
        legend = ((EMERALD, "Protein"), (SAGE, "Carbohydrates"), (TERRACOTTA, "Fat"),
                  (OAT_DARK, "Other documented energy"))
        canvas.setFont("Helvetica", 6.5)
        for colour, label in legend:
            canvas.setFillColor(colour)
            canvas.rect(legend_x, self.chart_height - 11, 6, 6, stroke=0, fill=1)
            canvas.setFillColor(MUTED)
            canvas.drawString(legend_x + 9, self.chart_height - 10, label)
            legend_x += 12 + canvas.stringWidth(label, "Helvetica", 6.5)
        canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("NutriCarePdfTitle", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=22, leading=26, textColor=DEEP_FOREST, spaceAfter=4),
        "subtitle": ParagraphStyle("NutriCarePdfSubtitle", parent=base["Normal"], fontSize=9,
                                   leading=13, textColor=MUTED, spaceAfter=12),
        "section": ParagraphStyle("NutriCarePdfSection", parent=base["Heading2"], fontName="Helvetica-Bold",
                                  fontSize=12, leading=15, textColor=DEEP_FOREST, spaceBefore=12,
                                  spaceAfter=7),
        "body": ParagraphStyle("NutriCarePdfBody", parent=base["BodyText"], fontSize=8.5,
                               leading=12, textColor=INK),
        "small": ParagraphStyle("NutriCarePdfSmall", parent=base["BodyText"], fontSize=7.5,
                                leading=10, textColor=MUTED),
        "cell_label": ParagraphStyle("NutriCarePdfCellLabel", parent=base["BodyText"], fontName="Helvetica-Bold",
                                     fontSize=7, leading=9, textColor=MUTED, alignment=TA_CENTER),
        "cell_value": ParagraphStyle("NutriCarePdfCellValue", parent=base["BodyText"], fontName="Helvetica-Bold",
                                     fontSize=13, leading=15, textColor=DEEP_FOREST, alignment=TA_CENTER),
        "right": ParagraphStyle("NutriCarePdfRight", parent=base["BodyText"], fontSize=7.5,
                                leading=10, textColor=MUTED, alignment=TA_RIGHT),
    }


def _page_footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(OAT_DARK)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 13 * mm, width - doc.rightMargin, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 8.5 * mm, "NutriCare daily nutrition record — built only from logged meals and water")
    canvas.drawRightString(width - doc.rightMargin, 8.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _portion(entry: dict) -> str:
    nutrients = entry.get("nutrients") or {}
    grams = _number(nutrients.get("grams"), 0)
    quantity = _number(entry.get("quantity"), 2)
    if entry.get("unit") == "serving":
        food = entry.get("food") or {}
        desc = _safe(food.get("serving_desc") or "serving")
        return f"{quantity} × {desc} ({grams} g)"
    return f"{grams} g"


def build_daily_report_pdf(*, user: dict, day: str, grouped_meals: dict[str, list[dict]],
                           totals: dict, water_ml: int, water_goal_ml: int,
                           targets: dict | None, daily_insights: dict) -> bytes:
    """Build a printable daily report from passed live NutriCare data only."""
    out = BytesIO()
    doc = SimpleDocTemplate(
        out, pagesize=A4, title="NutriCare daily nutrition record",
        author="NutriCare", leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=19 * mm, pageCompression=0,
    )
    styles = _styles()
    story: list[Any] = []
    profile_note = "Personalised targets shown as estimates." if targets else (
        "Profile targets are not configured; no personalised comparisons are shown.")
    story.extend([
        Paragraph("Daily nutrition record", styles["title"]),
        Paragraph(f"For <b>{_safe(user.get('name') or 'Local profile')}</b> · {_safe(day)}<br/>{profile_note}",
                  styles["subtitle"]),
    ])

    summary_cells = [
        ("Calories", f"{_number(totals.get('kcal'))} kcal"),
        ("Protein", f"{_number(totals.get('protein_g'), 1)} g"),
        ("Carbohydrates", f"{_number(totals.get('carbs_g'), 1)} g"),
        ("Fat", f"{_number(totals.get('fat_g'), 1)} g"),
        ("Water", f"{_number(water_ml)} ml"),
    ]
    summary_table = Table([
        [Paragraph(label, styles["cell_label"]) for label, _ in summary_cells],
        [Paragraph(value, styles["cell_value"]) for _, value in summary_cells],
    ], colWidths=[doc.width / len(summary_cells)] * len(summary_cells))
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OAT),
        ("BOX", (0, 0), (-1, -1), 0.5, OAT_DARK),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, OAT_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([summary_table, Spacer(1, 5)])
    if water_goal_ml:
        story.append(Paragraph(
            f"Hydration logged: <b>{_number(water_ml)} ml</b> of <b>{_number(water_goal_ml)} ml</b> selected goal "
            f"({_number(100 * water_ml / water_goal_ml)}%).", styles["small"]))

    story.extend([
        Paragraph("Today's intake graph", styles["section"]),
        Paragraph("Meal bars use documented calories. Colour segments show the calculated energy contribution of protein, carbohydrates, and fat from each logged meal.", styles["small"]),
        DailyIntakeChart(grouped_meals),
    ])

    story.append(Paragraph("Micronutrient snapshot", styles["section"]))
    if targets and targets.get("micro"):
        micro_data = [[
            Paragraph("Nutrient", styles["cell_label"]),
            Paragraph("Logged", styles["cell_label"]),
            Paragraph("Reference", styles["cell_label"]),
            Paragraph("Context", styles["cell_label"]),
        ]]
        for label, key, unit, upper in MICRO_ROWS:
            value = totals.get(key, 0)
            reference = targets["micro"].get(key)
            ratio = 100 * float(value or 0) / float(reference) if reference else 0
            context = "upper limit" if upper else f"{_number(ratio)}% of reference"
            micro_data.append([
                Paragraph(label, styles["body"]),
                Paragraph(f"{_number(value, 1)} {unit}", styles["right"]),
                Paragraph(f"{_number(reference)} {unit}", styles["right"]),
                Paragraph(context, styles["right"]),
            ])
        micro_table = Table(micro_data, colWidths=[doc.width * .32, doc.width * .2, doc.width * .23, doc.width * .25], repeatRows=1)
        micro_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FOREST),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FBF9F5")),
            ("GRID", (0, 0), (-1, -1), 0.35, OAT_DARK),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(micro_table)
    else:
        story.append(Paragraph(
            "Complete age, sex, height, weight, and activity in My Profile to compare logged micronutrients with estimate-based reference targets.",
            styles["body"]))
    story.append(Paragraph(
        "Micronutrients are summed only where documented in the food dataset. A zero can mean no documented micronutrient data for a manual item; it does not prove absence from a food or diet.",
        styles["small"]))

    story.append(Paragraph("Meals logged today", styles["section"]))
    has_meals = False
    for meal in MEAL_ORDER:
        entries = grouped_meals.get(meal, [])
        if not entries:
            continue
        has_meals = True
        meal_total = _meal_totals(entries)
        heading = Paragraph(
            f"<b>{MEAL_LABELS[meal]}</b> · {_number(meal_total['kcal'])} kcal · "
            f"P {_number(meal_total['protein_g'], 1)} g · C {_number(meal_total['carbs_g'], 1)} g · F {_number(meal_total['fat_g'], 1)} g",
            styles["body"])
        table_rows = [[
            Paragraph("Food", styles["cell_label"]), Paragraph("Portion", styles["cell_label"]),
            Paragraph("kcal", styles["cell_label"]), Paragraph("P / C / F (g)", styles["cell_label"]),
        ]]
        for entry in entries:
            nutrients = entry.get("nutrients") or {}
            table_rows.append([
                Paragraph(_safe(entry.get("display_name") or "Custom item"), styles["body"]),
                Paragraph(_portion(entry), styles["small"]),
                Paragraph(_number(nutrients.get("kcal")), styles["right"]),
                Paragraph(
                    f"{_number(nutrients.get('protein_g'), 1)} / {_number(nutrients.get('carbs_g'), 1)} / {_number(nutrients.get('fat_g'), 1)}",
                    styles["right"]),
            ])
        meal_table = Table(table_rows, colWidths=[doc.width * .38, doc.width * .27, doc.width * .12, doc.width * .23], repeatRows=1)
        meal_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF4EC")),
            ("GRID", (0, 0), (-1, -1), 0.35, OAT_DARK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        # Tables may be longer than one page; leave them splittable so every logged
        # meal is included rather than failing an export with a large diary.
        story.extend([heading, Spacer(1, 3), meal_table, Spacer(1, 7)])
    if not has_meals:
        story.append(Paragraph(
            "No meals are logged for this day. This record does not treat an empty log as zero food intake.",
            styles["body"]))

    story.append(Paragraph("Nutrition observations & recommendations", styles["section"]))
    report_insights = daily_insights.get("insights") or []
    if not report_insights:
        story.append(Paragraph("No data-based observations are available yet.", styles["body"]))
    else:
        for item in report_insights:
            lines = [f"<b>{_safe(item.get('title'))}</b>: {_safe(item.get('detail'))}"]
            recommendations = item.get("recommendations") or []
            if recommendations:
                options = "; ".join(
                    f"<b>{_safe(rec.get('name'))}</b> ({_safe(rec.get('contribution'))})"
                    for rec in recommendations
                )
                lines.append(f"Documented food-dataset options: {options}.")
            elif item.get("recommendations_note"):
                lines.append(_safe(item["recommendations_note"]))
            story.append(Paragraph("<br/>".join(lines), styles["body"]))
            story.append(Spacer(1, 5))

    story.append(Spacer(1, 4))
    story.append(Paragraph(_safe(daily_insights.get("disclaimer") or
        "General educational information from your logged records; not medical advice."), styles["small"]))
    if targets and targets.get("estimate_note"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(_safe(targets["estimate_note"]), styles["small"]))

    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return out.getvalue()


def _period_page_footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(OAT_DARK)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 13 * mm, width - doc.rightMargin, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 8.5 * mm,
                      "NutriCare nutrition summary — built only from logged meals and water")
    canvas.drawRightString(width - doc.rightMargin, 8.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_period_report_pdf(*, user: dict, days: int, start_day: str, end_day: str,
                            per_day: list[dict], targets: dict | None) -> bytes:
    """Build a printable, non-clinical summary for a selected report window.

    Days without meal entries remain visible in the table but are not treated as
    zero food intake. The PDF is intentionally a summary rather than a set of
    invented daily meal details.
    """
    out = BytesIO()
    doc = SimpleDocTemplate(
        out, pagesize=A4, title=f"NutriCare {days}-day nutrition summary",
        author="NutriCare", leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=19 * mm, pageCompression=0,
    )
    styles = _styles()
    story: list[Any] = []
    meal_days = [row for row in per_day if row.get("logged_count", 0)]
    keys = ("kcal", "protein_g", "carbs_g", "fat_g")
    totals = {key: sum(float(row.get(key) or 0) for row in per_day) for key in keys}
    water_total = sum(float(row.get("water_ml") or 0) for row in per_day)
    n_meal_days = len(meal_days)
    profile_note = "Personalised targets, where shown, are estimates." if targets else (
        "Profile targets are not configured; no personalised comparisons are shown.")
    story.extend([
        Paragraph(f"Nutrition summary · {days} days", styles["title"]),
        Paragraph(
            f"For <b>{_safe(user.get('name') or 'Local profile')}</b> · "
            f"{_safe(start_day)} to {_safe(end_day)}<br/>{profile_note}", styles["subtitle"]),
    ])

    if n_meal_days:
        summary_cells = [
            ("Meal-log days", f"{n_meal_days} of {days}"),
            ("Average calories", f"{_number(totals['kcal'] / n_meal_days)} kcal"),
            ("Average protein", f"{_number(totals['protein_g'] / n_meal_days, 1)} g"),
            ("Average carbs", f"{_number(totals['carbs_g'] / n_meal_days, 1)} g"),
            ("Average fat", f"{_number(totals['fat_g'] / n_meal_days, 1)} g"),
        ]
        summary_table = Table([
            [Paragraph(label, styles["cell_label"]) for label, _ in summary_cells],
            [Paragraph(value, styles["cell_value"]) for _, value in summary_cells],
        ], colWidths=[doc.width / len(summary_cells)] * len(summary_cells))
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), OAT),
            ("BOX", (0, 0), (-1, -1), 0.5, OAT_DARK),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, OAT_DARK),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([summary_table, Spacer(1, 5)])
        story.append(Paragraph(
            f"Recorded water across this window: <b>{_number(water_total)} ml</b>. "
            "Nutrition averages use days with at least one meal entry.", styles["small"]))
    else:
        story.append(Paragraph(
            "No meal entries are logged in this window. This summary does not treat the absence of a log as zero food intake.",
            styles["body"]))
        if water_total:
            story.append(Paragraph(
                f"Recorded water across this window: <b>{_number(water_total)} ml</b>.", styles["small"]))

    story.append(Paragraph("Recorded daily totals", styles["section"]))
    story.append(Paragraph(
        "Only days with a meal entry display meal energy and macronutrients. A blank day means no meal was recorded, not that no food was eaten.",
        styles["small"]))
    table_rows = [[
        Paragraph("Date", styles["cell_label"]),
        Paragraph("Meal entries", styles["cell_label"]),
        Paragraph("kcal", styles["cell_label"]),
        Paragraph("Protein", styles["cell_label"]),
        Paragraph("Carbs", styles["cell_label"]),
        Paragraph("Fat", styles["cell_label"]),
        Paragraph("Water", styles["cell_label"]),
    ]]
    for row in per_day:
        has_meals = bool(row.get("logged_count", 0))
        table_rows.append([
            Paragraph(_safe(row.get("date")), styles["body"]),
            Paragraph(str(int(row.get("logged_count") or 0)) if has_meals else "—", styles["right"]),
            Paragraph(f"{_number(row.get('kcal'))}" if has_meals else "—", styles["right"]),
            Paragraph(f"{_number(row.get('protein_g'), 1)} g" if has_meals else "—", styles["right"]),
            Paragraph(f"{_number(row.get('carbs_g'), 1)} g" if has_meals else "—", styles["right"]),
            Paragraph(f"{_number(row.get('fat_g'), 1)} g" if has_meals else "—", styles["right"]),
            Paragraph(f"{_number(row.get('water_ml'))} ml", styles["right"]),
        ])
    daily_table = Table(table_rows,
                        colWidths=[doc.width * .19, doc.width * .13, doc.width * .12,
                                   doc.width * .15, doc.width * .15, doc.width * .12,
                                   doc.width * .14], repeatRows=1)
    daily_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FOREST),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FBF9F5")),
        ("GRID", (0, 0), (-1, -1), 0.35, OAT_DARK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(daily_table)
    story.extend([
        Spacer(1, 8),
        Paragraph(
            "This document is a summary of the local records selected above. It is not a medical assessment, diagnosis, or food-safety certification.",
            styles["small"]),
    ])
    if targets and targets.get("estimate_note"):
        story.append(Spacer(1, 3))
        story.append(Paragraph(_safe(targets["estimate_note"]), styles["small"]))

    doc.build(story, onFirstPage=_period_page_footer, onLaterPages=_period_page_footer)
    return out.getvalue()
