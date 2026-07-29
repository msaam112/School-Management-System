"""Shared PDF report engine (reportlab) — FR-15.

Every report builder in this file returns raw PDF bytes. Routers call these
and return them via a FastAPI Response with media_type="application/pdf".

This version features a modern, aesthetic design with:
- Realistic rubber‑stamp effect (PASS/FAIL/PAID/UNPAID)
- Faint “SMS” watermark on every page
- Clean, contemporary colour palette
- Enhanced header and footer with subtle decorative touches
- All business logic unchanged
"""

import io
import math
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.graphics.shapes import Drawing, String, Circle, Rect, Group
from reportlab.lib.colors import Color

# ======================================
#   Modern Colour Palette
# ======================================
NAVY = colors.HexColor("#0f172a")        # deep slate
TEAL = colors.HexColor("#0d9488")        # vibrant teal
AMBER = colors.HexColor("#f59e0b")       # warm amber
ROSE = colors.HexColor("#e11d48")        # bold rose
SLATE = colors.HexColor("#f1f5f9")       # light slate
BORDER = colors.HexColor("#cbd5e1")      # soft border
WHITE = colors.white
GREY = colors.HexColor("#475569")

# Report‑type accent mapping
REPORT_ACCENTS = {
    "Student List": TEAL,
    "Attendance": NAVY,
    "Result": ROSE,
    "Fee": AMBER,
    "Default": NAVY,
}

styles = getSampleStyleSheet()
# ----- Paragraph styles -----
TITLE_STYLE = ParagraphStyle("SMSTitle", parent=styles["Heading1"], fontSize=16,
                              textColor=WHITE, spaceAfter=2, fontName="Helvetica-Bold")
SUBTITLE_STYLE = ParagraphStyle("SMSSubtitle", parent=styles["Normal"], fontSize=9,
                                 textColor=WHITE, fontName="Helvetica")
NORMAL = styles["Normal"]
NORMAL_RIGHT = ParagraphStyle("SMSNormalRight", parent=styles["Normal"], alignment=TA_RIGHT)
CENTER = ParagraphStyle("SMSCenter", parent=styles["Normal"], alignment=TA_CENTER)

# ======================================
#   School Logo (Circle with Initials)
# ======================================
def _school_logo_drawing(school_name: str, size=40):
    """Return a circular logo with the school's initials."""
    initials = ''.join(word[0].upper() for word in school_name.split()[:2])
    d = Drawing(size, size)
    d.add(Circle(size/2, size/2, size/2, fillColor=AMBER, strokeColor=WHITE, strokeWidth=1))
    d.add(String(size/2, size/2 - 3, initials,
                 textAnchor="middle", fontSize=size*0.35,
                 fillColor=NAVY, fontName="Helvetica-Bold"))
    return d

# ======================================
#   Header with Logo & Accent Colour
# ======================================
def _header_table(school: dict, report_title: str, accent_color=None):
    """Creative header: logo, school name, report title, and gold bar."""
    if accent_color is None:
        accent_color = NAVY

    name = school.get("name") or "School Management System"
    subtitle_bits = []
    if school.get("address"):
        subtitle_bits.append(school["address"])
    if school.get("emis_code"):
        subtitle_bits.append(f"EMIS: {school['emis_code']}")
    subtitle = "  |  ".join(subtitle_bits)

    logo = _school_logo_drawing(name)
    left_cell = [
        Paragraph(f"<b>{name}</b>", TITLE_STYLE),
        Paragraph(subtitle, SUBTITLE_STYLE)
    ]
    right_cell = Paragraph(f"<b>{report_title}</b>", NORMAL_RIGHT)

    data = [[logo, left_cell, right_cell]]
    t = Table(data, colWidths=[50, 300, 150])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent_color),
        ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        # Gold accent bar at bottom of header
        ("LINEBELOW", (0, 0), (-1, 0), 2, AMBER),
    ]))
    return t

# ======================================
#   Page Setup (Background Watermark + Footer)
# ======================================
def _page_setup(canvas, doc):
    """Draw a faint 'SMS' watermark and footer on every page."""
    canvas.saveState()

    # ---- Watermark ----
    canvas.setFont("Helvetica-Bold", 60)
    canvas.setFillColor(Color(0.1, 0.1, 0.1, alpha=0.06))  # very faint
    canvas.rotate(30)  # diagonal
    canvas.drawCentredString(doc.pagesize[0] * 0.8, doc.pagesize[1] * 0.3, "SMS")

    # ---- Footer ----
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GREY)
    x_start = 20 * mm
    x_end = doc.pagesize[0] - 20 * mm
    y_line = 18 * mm

    # Footer line with double stroke
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(x_start, y_line, x_end, y_line)
    canvas.setLineWidth(1.5)
    canvas.line(x_start, y_line - 2, x_end, y_line - 2)

    # Left: timestamp
    canvas.drawString(x_start, 12 * mm,
                      f"Generated on {datetime.now().strftime('%d %b %Y %H:%M')}")
    # Centre: school name
    canvas.drawCentredString(doc.pagesize[0]/2, 12 * mm, "School Management System")
    # Right: page number
    canvas.drawRightString(x_end, 12 * mm, f"Page {doc.page}")

    canvas.restoreState()

# ======================================
#   Stamp Drawing – Realistic Rubber Stamp
# ======================================
def _stamp_drawing(text, color, size=100, angle=20, opacity=0.4):
    """
    Create a realistic stamp with a thick border, bold text, and a slight shadow.
    """
    from reportlab.lib.colors import Color

    d = Drawing(size * 1.5, size * 1.5)
    cx = size * 0.75
    cy = size * 0.75
    r = size * 0.45

    # Make color with opacity
    if hasattr(color, 'red'):
        color = Color(color.red, color.green, color.blue, alpha=opacity)

    # Outer circle (ring)
    ring = Circle(cx, cy, r, strokeColor=color, strokeWidth=3, fillColor=None)
    # Inner circle (optional)
    # ring2 = Circle(cx, cy, r*0.9, strokeColor=color, strokeWidth=1, fillColor=None)

    # Text inside
    txt = String(cx, cy, text,
                 fontName="Helvetica-Bold", fontSize=size * 0.3,
                 fillColor=color, textAnchor="middle")

    # Group with rotation
    g = Group()
    g.add(ring)
    # g.add(ring2)
    g.add(txt)

    # Rotation around center
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    tx = cx - cx * cos_a + cy * sin_a
    ty = cy - cx * sin_a - cy * cos_a
    g.transform = (cos_a, sin_a, -sin_a, cos_a, tx, ty)

    d.add(g)
    return d

# ======================================
#   Table Style
# ======================================
def _table_style(header_color=None):
    if header_color is None:
        header_color = NAVY
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SLATE]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ])

# ======================================
#   Info Table (light grey background)
# ======================================
def _info_table(data, col_widths=None):
    t = Table(data, colWidths=col_widths or [80, 170, 80, 170])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SLATE),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t

# ======================================
#   Generic Report
# ======================================
def build_generic_report(school: dict, title: str, subtitle: str,
                          headers: list, rows: list, col_widths: list = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=25 * mm,
                             leftMargin=20 * mm, rightMargin=20 * mm)

    accent = REPORT_ACCENTS.get(title.split()[0] if title else "Default", NAVY)
    elements = [_header_table(school, title, accent), Spacer(1, 12)]
    if subtitle:
        elements.append(Paragraph(subtitle, NORMAL))
        elements.append(Spacer(1, 8))

    table_data = [headers] + [[str(c) for c in row] for row in rows]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(_table_style(header_color=accent))
    elements.append(t)

    doc.build(elements, onFirstPage=_page_setup, onLaterPages=_page_setup)
    return buf.getvalue()

# ======================================
#   Attendance Report
# ======================================
def build_attendance_report(school: dict, date: str, class_name: str, section_name: str,
                             rows: list, summary: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=25 * mm,
                             leftMargin=20 * mm, rightMargin=20 * mm)

    accent = REPORT_ACCENTS["Attendance"]
    elements = [_header_table(school, "Attendance Report", accent), Spacer(1, 12)]
    elements.append(Paragraph(f"Class: <b>{class_name}</b> &nbsp;|&nbsp; "
                               f"Section: <b>{section_name}</b> &nbsp;|&nbsp; Date: <b>{date}</b>", NORMAL))
    elements.append(Spacer(1, 10))

    summary_data = [
        ["Total", "Present", "Absent", "Leave"],
        [str(summary.get("total", 0)), str(summary.get("present", 0)),
         str(summary.get("absent", 0)), str(summary.get("leave", 0))]
    ]
    st = Table(summary_data, colWidths=[100, 100, 100, 100])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#22c55e")),  # Present green
        ("BACKGROUND", (2, 1), (2, 1), colors.HexColor("#ef4444")),  # Absent red
        ("BACKGROUND", (3, 1), (3, 1), AMBER),                       # Leave amber
        ("TEXTCOLOR", (1, 1), (1, 1), WHITE),
        ("TEXTCOLOR", (2, 1), (2, 1), WHITE),
        ("TEXTCOLOR", (3, 1), (3, 1), WHITE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("FONTSIZE", (0, 1), (-1, 1), 12),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
    ]))
    elements.append(st)
    elements.append(Spacer(1, 14))

    table_data = [["Roll No", "Student Name", "Status"]] + [[r["roll"], r["name"], r["status"]] for r in rows]
    t = Table(table_data, colWidths=[100, 260, 100], repeatRows=1)
    t.setStyle(_table_style(header_color=accent))
    elements.append(t)

    doc.build(elements, onFirstPage=_page_setup, onLaterPages=_page_setup)
    return buf.getvalue()

# ======================================
#   Result Card (with Stamp & Signatures)
# ======================================
def build_result_card(school: dict, student: dict, exam: dict,
                       subject_rows: list, totals: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=25 * mm,
                             leftMargin=20 * mm, rightMargin=20 * mm)

    accent = REPORT_ACCENTS["Result"]
    elements = [_header_table(school, "Result Card", accent), Spacer(1, 12)]
    elements.append(Paragraph(f"<b>{exam.get('name','Examination')}</b> — {exam.get('exam_date','')}", NORMAL))
    elements.append(Spacer(1, 10))

    info_data = [
        ["Name", student.get("name", ""), "Roll No", student.get("roll_number", "")],
        ["Class", student.get("class_name", ""), "Section", student.get("section_name", "")],
        ["Admission ID", student.get("admission_id", ""), "Status", student.get("status", "")],
    ]
    elements.append(_info_table(info_data))
    elements.append(Spacer(1, 14))

    table_data = [["Subject", "Obtained", "Total", "Percentage", "Grade", "Result"]] + [
        [r["subject"], r["obtained"], r["total"], f"{r['percentage']:.1f}%", r["grade"], r["pass_fail"]]
        for r in subject_rows]
    t = Table(table_data, colWidths=[160, 70, 70, 80, 60, 60], repeatRows=1)
    t.setStyle(_table_style(header_color=accent))
    elements.append(t)
    elements.append(Spacer(1, 14))

    totals_data = [[f"TOTAL: {totals['obtained']:.0f} / {totals['total']:.0f}",
                     f"PERCENTAGE: {totals['percentage']:.1f}%",
                     f"GRADE: {totals['grade']}"]]
    tt = Table(totals_data, colWidths=[167, 167, 166])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(tt)
    elements.append(Spacer(1, 10))

    # Overall result (coloured)
    result_color = colors.HexColor("#22c55e") if totals["pass_fail"] == "Pass" else colors.HexColor("#ef4444")
    result_style = ParagraphStyle("ResultStyle", parent=styles["Heading2"], textColor=result_color)
    elements.append(Paragraph(f"Overall Result: {totals['pass_fail']}", result_style))

    # Stamp (with realistic look)
    stamp_text = "PASS" if totals["pass_fail"] == "Pass" else "FAIL"
    stamp_color = colors.HexColor("#22c55e") if totals["pass_fail"] == "Pass" else colors.HexColor("#ef4444")
    stamp = _stamp_drawing(stamp_text, stamp_color, size=60, angle=15, opacity=0.35)
    elements.append(Spacer(1, 10))
    elements.append(stamp)

    # Teacher's Remark
    if totals.get("remark"):
        elements.append(Spacer(1, 16))
        elements.append(Paragraph("<b>Teacher's Remark:</b>", NORMAL))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(totals["remark"], NORMAL))

    # Signature lines
    elements.append(Spacer(1, 20))
    sig_data = [["", ""], ["Signature of Teacher", "Signature of Principal"]]
    sig_table = Table(sig_data, colWidths=[250, 250])
    sig_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 1, NAVY),
        ("LINEABOVE", (1, 0), (1, 0), 1, NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(sig_table)

    doc.build(elements, onFirstPage=_page_setup, onLaterPages=_page_setup)
    return buf.getvalue()

# ======================================
#   Fee Challan (with Stamp & Signatures)
# ======================================
def build_fee_challan(school: dict, student: dict, challan: dict,
                       breakdown: list, manual_fees: list, total: float) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=25 * mm,
                             leftMargin=20 * mm, rightMargin=20 * mm)

    accent = REPORT_ACCENTS["Fee"]
    elements = [_header_table(school, "Fee Challan", accent), Spacer(1, 12)]
    elements.append(Paragraph(f"Challan ID: <b>{challan['id']}</b> &nbsp;|&nbsp; "
                               f"Month/Year: <b>{challan['month']}/{challan['year']}</b>", NORMAL))
    elements.append(Spacer(1, 10))

    info_data = [
        ["Student", student.get("name", ""), "Roll No", student.get("roll_number", "")],
        ["Class", student.get("class_name", ""), "Section", student.get("section_name", "")],
        ["Issue Date", challan.get("issue_date", ""), "Due Date", challan.get("due_date", "")],
    ]
    elements.append(_info_table(info_data))
    elements.append(Spacer(1, 14))

    rows = [[b["label"], f"Rs. {b['amount']:.0f}"] for b in breakdown]
    for mf in manual_fees:
        label = mf["charge_type"] + (f" ({mf['description']})" if mf.get("description") else "")
        rows.append([label, f"Rs. {mf['amount']:.0f}"])
    table_data = [["Particulars", "Amount"]] + rows
    t = Table(table_data, colWidths=[380, 120], repeatRows=1)
    t.setStyle(_table_style(header_color=accent))
    elements.append(t)
    elements.append(Spacer(1, 10))

    total_data = [[f"TOTAL PAYABLE: Rs. {total:.0f}", f"Status: {challan['status']}"]]
    tt = Table(total_data, colWidths=[250, 250])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(tt)

    # Stamp (PAID/UNPAID)
    if challan['status'] in ("Paid", "Unpaid"):
        stamp_text = "PAID" if challan['status'] == "Paid" else "UNPAID"
        stamp_color = colors.HexColor("#22c55e") if challan['status'] == "Paid" else colors.HexColor("#ef4444")
        stamp = _stamp_drawing(stamp_text, stamp_color, size=70, angle=15, opacity=0.25)
        elements.append(stamp)

    # Signature lines
    elements.append(Spacer(1, 20))
    sig_data = [["", ""], ["Student's Signature", "Authorized Signature"]]
    sig_table = Table(sig_data, colWidths=[250, 250])
    sig_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 1, NAVY),
        ("LINEABOVE", (1, 0), (1, 0), 1, NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(sig_table)

    doc.build(elements, onFirstPage=_page_setup, onLaterPages=_page_setup)
    return buf.getvalue()