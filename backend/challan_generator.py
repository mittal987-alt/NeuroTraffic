"""
TrafficVision AI - E-Challan PDF Generator
------------------------------------------------
Generates official digital traffic violation receipts (E-Challan)
using ReportLab with fine breakdown, camera location, violation type,
recorded speed, plate number, and payment verification.
"""

import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

VIOLATION_FINES = {
    "overspeed": {"title": "Over-Speeding Violation", "fine": 2000, "section": "Sec 183 MV Act"},
    "red_light": {"title": "Red Light Signal Jumping", "fine": 1000, "section": "Sec 184 MV Act"},
    "no_helmet": {"title": "Riding Without Protective Headgear (Helmet)", "fine": 1000, "section": "Sec 129/177 MV Act"},
    "no_seatbelt": {"title": "Driving Without Fastened Seatbelt", "fine": 1000, "section": "Sec 194B MV Act"},
    "wrong_way": {"title": "Driving in Contravention of Flow (Wrong-Way)", "fine": 5000, "section": "Sec 184 MV Act"},
    "lane_departure": {"title": "Improper Lane Discipline / Lane Straddling", "fine": 500, "section": "Sec 177 MV Act"},
    "accident_risk": {"title": "Reckless / Dangerous Driving", "fine": 5000, "section": "Sec 184 MV Act"},
}


def generate_challan_pdf(alert_dict: dict) -> io.BytesIO:
    """
    Generates a PDF E-Challan for a given alert dictionary.
    Returns BytesIO buffer containing PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ChallanTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A365D"),
        alignment=1,  # Center
    )
    subtitle_style = ParagraphStyle(
        "ChallanSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#4A5568"),
        alignment=1,
    )
    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2B6CB0"),
    )
    body_style = ParagraphStyle(
        "BodyTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
    )
    bold_style = ParagraphStyle(
        "BoldTextCustom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1A202C"),
    )

    story = []

    # Header
    story.append(Paragraph("TRAFFIC REGULATION & SURVEILLANCE AUTHORITY", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("AUTOMATED ELECTRONIC TRAFFIC VIOLATION NOTICE (E-CHALLAN)", subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1A365D"), spaceAfter=15))

    # Alert info resolution
    alert_id = alert_dict.get("id", 1001)
    challan_no = f"TRF-CH-{datetime.utcnow().strftime('%Y%m')}-{alert_id:05d}"
    alert_type = alert_dict.get("alert_type", "overspeed").lower()
    violation_meta = VIOLATION_FINES.get(alert_type, {
        "title": alert_dict.get("alert_type", "Traffic Violation").replace("_", " ").title(),
        "fine": 1000,
        "section": "Motor Vehicles Enforcement Act",
    })

    timestamp_str = alert_dict.get("timestamp", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    plate_text = alert_dict.get("plate_text") or "NOT CAPTURED / UNREGISTERED"
    camera_id = alert_dict.get("camera_id", "camera_1")
    speed_kmh = alert_dict.get("speed_kmh")
    speed_display = f"{speed_kmh:.1f} km/h" if speed_kmh else "N/A"
    message = alert_dict.get("message", "Traffic violation logged by AI vision system")

    # Challan Meta Table
    meta_data = [
        [
            Paragraph("<b>Challan Number:</b>", body_style),
            Paragraph(f"<b>{challan_no}</b>", bold_style),
            Paragraph("<b>Issue Date & Time:</b>", body_style),
            Paragraph(timestamp_str, body_style),
        ],
        [
            Paragraph("<b>Camera ID / Junction:</b>", body_style),
            Paragraph(f"{camera_id.upper()} (Smart Sector)", body_style),
            Paragraph("<b>Status:</b>", body_style),
            Paragraph(
                f"<font color='{'#38A169' if alert_dict.get('status') == 'resolved' else '#E53E3E'}'><b>{alert_dict.get('status', 'PENDING').upper()}</b></font>",
                body_style,
            ),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[1.8 * inch, 2.0 * inch, 1.6 * inch, 2.1 * inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EDF2F7")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # Vehicle & Violation Details Section
    story.append(Paragraph("VIOLATION PARTICULARS", section_heading))
    story.append(Spacer(1, 6))

    details_data = [
        [Paragraph("<b>Parameter</b>", bold_style), Paragraph("<b>Recorded Evidentiary Value</b>", bold_style)],
        [Paragraph("Vehicle License Plate (ANPR)", body_style), Paragraph(f"<b>{plate_text}</b>", bold_style)],
        [Paragraph("Detected Offense", body_style), Paragraph(f"<b>{violation_meta['title']}</b>", bold_style)],
        [Paragraph("Statutory Act & Section", body_style), Paragraph(violation_meta["section"], body_style)],
        [Paragraph("Recorded Speed", body_style), Paragraph(speed_display, body_style)],
        [Paragraph("System Offense Description", body_style), Paragraph(message, body_style)],
    ]

    details_table = Table(details_data, colWidths=[2.6 * inch, 4.9 * inch])
    details_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 15))

    # Fine Amount Breakdown
    story.append(Paragraph("PENALTY ASSESSMENT", section_heading))
    story.append(Spacer(1, 6))

    fine_amount = violation_meta["fine"]
    fine_data = [
        [Paragraph("<b>Fee Description</b>", bold_style), Paragraph("<b>Amount (INR)</b>", bold_style)],
        [Paragraph(f"Statutory Penalty: {violation_meta['title']}", body_style), Paragraph(f"₹ {fine_amount:,.2f}", body_style)],
        [Paragraph("Automated Surveillance & Processing Fee", body_style), Paragraph("₹ 50.00", body_style)],
        [Paragraph("<b>TOTAL PAYABLE FINE</b>", bold_style), Paragraph(f"<b>₹ {fine_amount + 50:,.2f}</b>", bold_style)],
    ]
    fine_table = Table(fine_data, colWidths=[5.5 * inch, 2.0 * inch])
    fine_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FEFCBF")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(fine_table)
    story.append(Spacer(1, 20))

    # Notice instructions & Terms
    notice_text = (
        "<b>Notice Instructions:</b><br/>"
        "1. This is a computer-generated electronic traffic notice based on video telemetry & AI vision analysis.<br/>"
        "2. The penalty must be remitted within 15 days of issue to avoid further legal proceedings.<br/>"
        "3. To dispute or view video evidence, log in to the TrafficVision Portal or visit the local traffic management cell."
    )
    story.append(Paragraph(notice_text, body_style))
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=10))

    footer_style = ParagraphStyle(
        "FooterText",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#718096"),
        alignment=1,
    )
    story.append(Paragraph("TrafficVision AI Surveillance Network • Automated Incident ID #" + str(alert_id), footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer
