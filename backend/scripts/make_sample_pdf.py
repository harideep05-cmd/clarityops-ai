"""Generate a fully synthetic handbook for repeatable demos; contains no real company data."""

from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

POLICIES = [
    (
        "Leave Policy",
        [
            "Employees receive 12 casual leave days per calendar year.",
            "Casual leave does not carry forward into the next calendar year.",
            "Submit planned casual leave requests in the staff portal at least 2 working days in advance. Your reporting manager must approve the request.",
            "For an unexpected absence, notify your reporting manager before 10:00 AM on the first day of absence.",
        ],
    ),
    (
        "Expense Policy",
        [
            "Employees must submit expense claims with itemized receipts within 14 calendar days of the expense.",
            "An individual expense above INR 5,000 requires written manager approval before purchase.",
            "Finance processes approved claims within 10 business days after receiving complete receipts and approvals.",
            "Personal purchases are not reimbursable. Do not include personal items in a business expense claim.",
        ],
    ),
    (
        "Sales Handover SOP",
        [
            "After a customer signs a contract, the account owner must create a handover ticket for Customer Success within 1 working day.",
            "The handover ticket must include the signed scope, primary customer contact, promised delivery dates, and any agreed exclusions.",
            "Customer Success schedules an internal handover before inviting the customer to the kickoff meeting.",
        ],
    ),
    (
        "IT Security Policy",
        [
            "Multi-factor authentication is required for all company email and document accounts.",
            "Report a lost company laptop to the IT service desk immediately. Include the asset tag and the last known location.",
            "Never share account passwords or multi-factor authentication codes with anyone, including people claiming to be IT staff.",
            "Store internal company documents only in the approved company document workspace.",
        ],
    ),
    (
        "New Employee Onboarding",
        [
            "The People Operations team assigns each new employee an onboarding buddy before their first day.",
            "On the first working day, new employees complete account setup with IT and review the employee handbook with their manager.",
            "Managers schedule a role expectations discussion during the first working week.",
        ],
    ),
]


def make_pdf(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, file in [("Vera", "Vera.ttf"), ("VeraBold", "VeraBd.ttf"), ("VeraItalic", "VeraIt.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
    for name in ["Normal", "BodyText", "Title", "Heading2", "Italic"]:
        styles[name].fontName = "Vera"
    styles["Title"].fontName = "VeraBold"
    styles["Heading2"].fontName = "VeraBold"
    styles["Italic"].fontName = "VeraItalic"
    styles["BodyText"].fontSize = 11
    styles["BodyText"].leading = 17
    story = []
    for i, (title, paragraphs) in enumerate(POLICIES):
        if i:
            story.append(PageBreak())
        story.extend(
            [
                Paragraph("MERIDIAN WORKS", styles["Heading2"]),
                Paragraph("Synthetic company handbook - demonstration fixture", styles["BodyText"]),
                Spacer(1, 32),
                Paragraph(title, styles["Title"]),
                Spacer(1, 20),
            ]
        )
        for paragraph in paragraphs:
            story.extend([Paragraph(paragraph, styles["BodyText"]), Spacer(1, 15)])
        story.extend(
            [
                Spacer(1, 24),
                Paragraph(
                    "These fictional policies are test data. They are not advice or policies of any real employer.",
                    styles["Italic"],
                ),
            ]
        )

    def footer(canvas, doc):
        canvas.setFont("Vera", 9)
        canvas.setFillColor(colors.HexColor("#526075"))
        canvas.drawString(48, 35, "ClarityOps AI | Synthetic test material")
        canvas.drawRightString(A4[0] - 48, 35, f"Page {doc.page}")

    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=48,
        leftMargin=48,
        topMargin=50,
        bottomMargin=55,
        title="Meridian Works - Synthetic Company Handbook",
        author="ClarityOps AI",
        invariant=1,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return path


if __name__ == "__main__":
    result = make_pdf(Path(__file__).resolve().parents[2] / "samples" / "Meridian_Works_Handbook.pdf")
    print("Created synthetic sample:", result.name)
