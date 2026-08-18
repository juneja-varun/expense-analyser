"""Generate the synthetic ICICI savings statement fixture.

Modelled on a real statement's *layout* — the wrapped particulars column, the
brought-forward row, the single-amount rows — with entirely invented data.
Generating rather than anonymising is what docs/anonymising-statements.md
recommends wherever the shape can be recreated, and here it can.

Run from `backend/`:
    poetry run python apps/parsers/banks/icici_bank/tests/make_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

rl_config.invariant = 1  # byte-reproducible output

FIXTURE = Path(__file__).parent / "fixtures" / "icici_savings_2026_07.pdf"

HEADER = [
    "ICICI Bank Limited",
    "MR TEST USER",
    "1 TEST STREET",
    "TEST CITY - INDIA - 000000",
    "Your Base Branch : TEST BRANCH, ICICI BANK LTD.",
    "Dial your Bank (Toll-free) 1800 0000 000",
    "",
    "STATEMENT SUMMARY for Customer ID: XXXXX0000 in INR as on July 31, 2026.",
    "Summary Balance",
    "Savings Account Balance 3,31,727.45",
    "Fixed Deposit Balance (Not Linked) 0.00",
    "TOTAL 3,31,727.45",
    "Page 1 of 2 M-00000000-00000",
    "",
    "ACCOUNT DETAILS - INR",
    "ACCOUNT HOLDERS : MR TEST USER",
    "ACCOUNT TYPE ACCOUNT BALANCE (I) NOMINATION",
    "Savings A/c XXXXXXXX0136 3,31,727.45 Registered",
    "TOTAL 3,31,727.45",
    "Statement of Transactions in Savings Account XXXXXXXX0136 in INR for the period "
    "July 01, 2026 - July 31, 2026",
    "DATE MODE PARTICULARS DEPOSITS WITHDRAWALS BALANCE",
]

# The wrapping is the point: merchant name above the row, reference tail below,
# and the particulars sometimes inline on the row itself.
BODY = [
    "01-07-2026 B/F 3,35,678.35",
    "Amazon Pay Groceries",
    "UPI/Amazon Pay/amazonpaygroce/You are pa/AXIS",
    "01-07-2026 691.00 3,34,987.35",
    "BANK/000000000000/APL000000000000000000000000000",
    "000/",
    "Amazon India",
    "02-07-2026 UPI/Amazon Ind/amazon@yapl/You are pa/YES BANK 1,649.00 3,33,338.35",
    "L/000000000000/APY000000000000000000000000000000/",
    "Test Digital Services Pvt Ltd",
    "UPI/Test Digital/testrecharge@o/UPI/AXIS",
    "03-07-2026 350.90 3,32,987.45",
    "BANK/000000000000/ICI000000000000000000000000000",
    "000/",
    "TEST RESTAURANT",
    "UPI/TEST RESTAURANT/testrest.000000/Payment By/HDFC",
    "03-07-2026 1,260.00 3,31,727.45",
    "BANK/000000000000/ICI000000000000000000000000000",
    "000/",
    "SALARY TESTCORP PVT LTD",
    "NEFT-TESTCORP-000000000",
    "05-07-2026 1,25,000.00 4,56,727.45",
    "TEST REFUND",
    "06-07-2026 UPI/TEST REFUND/refund@testbank/Refund/ICICI BANK 1,299.00 4,58,026.45",
    "This is a computer generated statement and does not require signature.",
    "Page 2 of 2 M-00000000-00000",
]


def build() -> Path:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(FIXTURE), pagesize=A4, invariant=1)
    pdf.setTitle("Synthetic ICICI savings statement fixture")
    pdf.setAuthor("expense-analyser test fixtures")
    pdf.setSubject("Synthetic test data - not a real statement")

    _, height = A4
    y = height - 40
    pdf.setFont("Helvetica", 8)
    for line in HEADER + BODY:
        pdf.drawString(30, y, line)
        y -= 11
        if y < 40:
            pdf.showPage()
            pdf.setFont("Helvetica", 8)
            y = height - 40
    pdf.showPage()
    pdf.save()
    return FIXTURE


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({path.stat().st_size} bytes)")
