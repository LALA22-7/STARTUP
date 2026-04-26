"""
PDF Generation Service for Prescriptions
Generates professional prescription PDFs
"""
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

IST = ZoneInfo("Asia/Kolkata")


def sanitize_patient_name(patient_name: str) -> str:
    """
    Sanitize a patient name for use in a PDF filename.

    Rules (per Requirement 8.6):
    - Spaces are replaced with underscores.
    - All non-ASCII-alphanumeric characters (including hyphens, slashes,
      Unicode letters/digits outside [a-zA-Z0-9], etc.) are removed.
    - If the result is empty (e.g. the name contained only unsafe characters),
      the fallback value "patient" is returned.

    Returns a string containing only [a-zA-Z0-9_] characters.
    """
    safe = "".join(
        "_" if ch == " " else ch
        for ch in patient_name
        if ch == " " or (ch.isascii() and ch.isalnum()) or ch == "_"
    ).strip("_")
    return safe or "patient"


def generate_prescription_pdf(
    patient_name: str,
    doctor_name: str,
    date: Optional[datetime] = None,
    medications: Optional[list] = None,
    instructions: str = "",
    clinic_name: str = "City Health Clinic",
    clinic_address: str = "Noida, India",
    clinic_phone: str = "+91-9876543210",
) -> bytes:
    """
    Generate a professional prescription PDF
    
    Args:
        patient_name: Name of the patient
        doctor_name: Name of the prescribing doctor
        date: Date of prescription (defaults to today)
        medications: List of dicts with {name, dose, frequency, duration}
        instructions: Special instructions
        clinic_name: Clinic name
        clinic_address: Clinic address
        clinic_phone: Clinic phone number
    
    Returns:
        PDF bytes
    """
    if date is None:
        date = datetime.now(IST)
    
    if medications is None:
        medications = []
    
    # Create PDF buffer
    buffer = io.BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    
    # Container for PDF elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#0f8b8d"),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=colors.HexColor("#0f8b8d"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=4,
    )
    
    # Header
    elements.append(Paragraph(clinic_name, title_style))
    elements.append(Spacer(1, 0.1 * inch))
    
    # Clinic info
    clinic_info = f"{clinic_address} | {clinic_phone}"
    elements.append(Paragraph(clinic_info, normal_style))
    elements.append(Spacer(1, 0.2 * inch))
    
    # Separator line
    elements.append(Paragraph(
        "<hr/>", normal_style
    ))
    elements.append(Spacer(1, 0.1 * inch))
    
    # Title
    elements.append(Paragraph("PRESCRIPTION", heading_style))
    elements.append(Spacer(1, 0.15 * inch))
    
    # Patient & Doctor info
    patient_info = f"<b>Patient Name:</b> {patient_name}"
    elements.append(Paragraph(patient_info, normal_style))
    
    doctor_info = f"<b>Doctor:</b> Dr. {doctor_name}"
    elements.append(Paragraph(doctor_info, normal_style))
    
    date_str = date.strftime("%d %B %Y")
    date_info = f"<b>Date:</b> {date_str}"
    elements.append(Paragraph(date_info, normal_style))
    
    elements.append(Spacer(1, 0.2 * inch))
    
    # Medications table
    if medications:
        elements.append(Paragraph("MEDICATIONS:", heading_style))
        elements.append(Spacer(1, 0.1 * inch))
        
        # Create medication table
        med_data = [
            ["Medicine", "Dosage", "Frequency", "Duration"],
        ]
        
        for med in medications:
            med_data.append([
                med.get("name", ""),
                med.get("dose", ""),
                med.get("frequency", ""),
                med.get("duration", ""),
            ])
        
        med_table = Table(med_data, colWidths=[2 * inch, 1.2 * inch, 1.2 * inch, 1.1 * inch])
        med_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f8b8d")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
            ("GRID", (0, 0), (-1, -1), 1, colors.grey),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        ]))
        
        elements.append(med_table)
        elements.append(Spacer(1, 0.2 * inch))
    
    # Instructions
    if instructions:
        elements.append(Paragraph("INSTRUCTIONS:", heading_style))
        elements.append(Spacer(1, 0.05 * inch))
        elements.append(Paragraph(instructions, normal_style))
        elements.append(Spacer(1, 0.2 * inch))
    
    # Footer
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph("<hr/>", normal_style))
    elements.append(Spacer(1, 0.05 * inch))
    
    footer_text = (
        "This prescription is valid for 30 days. "
        "For queries, contact us at " + clinic_phone
    )
    elements.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


def generate_clinical_notes_pdf(
    patient_name: str,
    doctor_name: str,
    chief_complaint: str,
    diagnosis: str,
    treatment_plan: str,
    clinic_name: str = "City Health Clinic",
    date: Optional[datetime] = None,
) -> bytes:
    """Generate clinical notes PDF"""
    if date is None:
        date = datetime.now(IST)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#0f8b8d"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=6,
    )
    
    elements.append(Paragraph(clinic_name, heading_style))
    elements.append(Paragraph("CLINICAL NOTES", heading_style))
    elements.append(Spacer(1, 0.1 * inch))
    
    elements.append(Paragraph(f"<b>Patient:</b> {patient_name}", normal_style))
    elements.append(Paragraph(f"<b>Doctor:</b> Dr. {doctor_name}", normal_style))
    elements.append(Paragraph(f"<b>Date:</b> {date.strftime('%d %B %Y')}", normal_style))
    elements.append(Spacer(1, 0.15 * inch))
    
    elements.append(Paragraph("<b>Chief Complaint:</b>", heading_style))
    elements.append(Paragraph(chief_complaint, normal_style))
    elements.append(Spacer(1, 0.1 * inch))
    
    elements.append(Paragraph("<b>Diagnosis:</b>", heading_style))
    elements.append(Paragraph(diagnosis, normal_style))
    elements.append(Spacer(1, 0.1 * inch))
    
    elements.append(Paragraph("<b>Treatment Plan:</b>", heading_style))
    elements.append(Paragraph(treatment_plan, normal_style))
    
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes
