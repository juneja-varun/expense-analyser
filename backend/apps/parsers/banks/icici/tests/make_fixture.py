"""Generate the synthetic ICICI credit-card statement fixture.

The fixture is committed, so you only need this if you are changing what the
fixture contains. Run it from `backend/`:

    poetry run python apps/parsers/banks/icici/tests/make_fixture.py

Everything in here is invented. Generating a fixture is safer than anonymising
a real statement — there is nothing to miss, and it is the approach
docs/anonymising-statements.md recommends wherever the layout can be recreated.
"""

from __future__ import annotations

from pathlib import Path

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Byte-for-byte reproducible output. Without this reportlab stamps the current
# time into the PDF, so regenerating the fixture would produce a spurious diff
# every time — and the timestamp would trip the fixture privacy scanner.
rl_config.invariant = 1

FIXTURE = Path(__file__).parent / "fixtures" / "icici_credit_card_2024_04.pdf"

# Column x-positions chosen so extracted text keeps the columns separated.
X_DATE, X_DETAIL, X_AMOUNT = 40, 110, 480

HEADER_LINES = [
    "ICICI Bank Limited",
    "Credit Card Statement",
    "",
    "MR TEST USER",
    "1 TEST STREET",
    "TEST CITY 000000",
    "",
    "Card Number: XXXX XXXX XXXX 4321",
    "Statement Period: 05/03/2024 to 04/04/2024",
    "Statement Date: 04/04/2024",
    "Payment Due Date: 22/04/2024",
    "Total Amount Due: 18,450.75",
    "Minimum Amount Due: 950.00",
    "Credit Limit: 2,00,000.00",
    "Available Credit Limit: 1,81,549.25",
    "",
]

TRANSACTIONS = [
    ("06/03/2024", "SWIGGY BANGALORE IN", "675.50"),
    ("08/03/2024", "AMAZON PAY INDIA PVT MUMBAI IN", "2,499.00"),
    ("11/03/2024", "IRCTC RAIL CONNECT NEW DELHI IN", "1,845.00"),
    ("14/03/2024", "BIGBASKET BANGALORE IN", "3,210.75"),
    ("16/03/2024", "REFUND AMAZON PAY INDIA PVT", "1,299.00 CR"),
    ("19/03/2024", "INDIAN OIL CORP TEST CITY IN", "2,000.00"),
    ("22/03/2024", "PAYMENT RECEIVED - THANK YOU", "12,000.00 CR"),
    ("25/03/2024", "NETFLIX COM MUMBAI IN", "649.00"),
    ("28/03/2024", "TEST CITY METRO RAIL IN", "300.00"),
    ("01/04/2024", "MYNTRA DESIGNS BANGALORE IN", "4,570.50"),
    ("03/04/2024", "FINANCE CHARGES", "0.00"),
]

FOOTER_LINES = [
    "",
    "Please pay by the due date to avoid finance charges.",
    "This is a computer generated statement and does not require a signature.",
    "ICICI Bank Customer Care: 1800 000 0000",
]


def build() -> Path:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(FIXTURE), pagesize=A4, invariant=1)
    # Metadata otherwise picks up the generating machine's user name.
    pdf.setTitle("Synthetic ICICI credit card statement fixture")
    pdf.setAuthor("expense-analyser test fixtures")
    pdf.setSubject("Synthetic test data — not a real statement")

    _, height = A4
    y = height - 50

    pdf.setFont("Helvetica", 9)
    for line in HEADER_LINES:
        pdf.drawString(X_DATE, y, line)
        y -= 14

    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(X_DATE, y, "Date")
    pdf.drawString(X_DETAIL, y, "Transaction Details")
    pdf.drawString(X_AMOUNT, y, "Amount (in Rs)")
    y -= 16

    pdf.setFont("Helvetica", 9)
    for txn_date, detail, amount in TRANSACTIONS:
        pdf.drawString(X_DATE, y, txn_date)
        pdf.drawString(X_DETAIL, y, detail)
        pdf.drawString(X_AMOUNT, y, amount)
        y -= 14

    for line in FOOTER_LINES:
        pdf.drawString(X_DATE, y, line)
        y -= 14

    pdf.showPage()
    pdf.save()
    return FIXTURE


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({path.stat().st_size} bytes)")
