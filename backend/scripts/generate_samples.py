"""Sample documents committed to the repository.

A demo that starts with "first find yourself a shipping contract" is a demo
nobody runs.
"""

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parents[2] / "data" / "samples"
SEED = 7
TODAY = date(2026, 9, 22)

CONTRACT_CLAUSES = [
    (
        "1. Scope of Agreement",
        [
            "This Master Supply Agreement governs the purchase of goods described in any purchase "
            "order issued under it. The Supplier shall deliver the goods in accordance with the "
            "agreed Incoterms 2020 rules stated on each purchase order.",
        ],
    ),
    (
        "2. Delivery Terms",
        [
            "Delivery shall be made to the destination named on the purchase order. Title and risk "
            "pass in accordance with the stated Incoterm.",
            "The Supplier shall notify the Buyer within 24 hours of becoming aware of any event "
            "likely to delay a shipment by more than two working days.",
        ],
    ),
    (
        "3. Lead Times",
        [
            "Standard lead time for ocean freight is 35 calendar days from the "
            "date of the purchase order. Air freight lead time is 7 calendar days.",
        ],
    ),
    (
        "4. Service Levels",
        [
            "The Supplier shall maintain an on-time delivery rate of not less than 95 percent "
            "measured over any rolling three month period.",
        ],
    ),
    (
        "4.1 Measurement",
        [
            "On-time means arrival at the destination on or before the estimated time of arrival "
            "confirmed at the time of booking.",
        ],
    ),
    (
        "4.2 Late Delivery",
        [
            "Where a shipment arrives after the confirmed estimated time of arrival, the Supplier "
            "shall pay a penalty of 2 percent of the shipment value for each complete week of "
            "delay, capped at 10 percent of the value of the affected purchase order.",
            "The penalty in this clause is the Buyer's sole financial remedy for late delivery and "
            "does not apply where the delay is caused by an event under clause 7.",
        ],
    ),
    (
        "5. Quality and Inspection",
        [
            "The Buyer may inspect goods within 10 working days of arrival and reject any goods "
            "that do not conform to the specification.",
        ],
    ),
    (
        "6. Payment",
        [
            "Payment terms are 60 days from the date of a valid invoice. Invoices shall quote the "
            "purchase order number and the shipment reference.",
        ],
    ),
    (
        "7. Force Majeure",
        [
            "Neither party is liable for failure to perform caused by an event beyond its "
            "reasonable control, including port closure, strike, or natural disaster, provided "
            "the affected party notifies the other within five working days.",
        ],
    ),
    (
        "8. Term and Termination",
        [
            "This Agreement runs for 24 months from the effective date and renews automatically "
            "for successive 12 month periods unless either party gives 90 days notice.",
        ],
    ),
]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=16, spaceAfter=14),
        "heading": ParagraphStyle("h", parent=base["Heading2"], fontSize=11, spaceBefore=10),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=9.5, leading=14),
    }


def write_contract(path: Path, buyer: str, supplier: str, number: str) -> None:
    style = _styles()
    story = [
        Paragraph("Master Supply Agreement", style["title"]),
        Paragraph(
            f"Agreement number {number}, between {buyer} (the Buyer) and {supplier} "
            f"(the Supplier), effective {TODAY - timedelta(days=400)}.",
            style["body"],
        ),
        Spacer(1, 8 * mm),
    ]
    for heading, paragraphs in CONTRACT_CLAUSES:
        story.append(Paragraph(heading, style["heading"]))
        for text in paragraphs:
            story.append(Paragraph(text, style["body"]))
    SimpleDocTemplate(str(path), pagesize=A4, title=f"MSA {number}").build(story)


def write_invoice(path: Path, supplier: str, number: str) -> None:
    style = _styles()
    rows = [["Line", "Description", "Qty", "Unit USD", "Total USD"]]
    total = 0.0
    for i, (desc, qty, unit) in enumerate(
        [
            ("Bearing assembly 6204", 1200, 3.45),
            ("Steel bracket M8", 4000, 0.92),
            ("Packaging, export grade", 40, 18.0),
        ],
        start=1,
    ):
        line = qty * unit
        total += line
        rows.append([str(i), desc, str(qty), f"{unit:.2f}", f"{line:,.2f}"])
    rows.append(["", "", "", "Total", f"{total:,.2f}"])

    table = Table(rows, colWidths=[15 * mm, 70 * mm, 20 * mm, 25 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, "#888888"),
                ("BACKGROUND", (0, 0), (-1, 0), "#eeeeee"),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    SimpleDocTemplate(str(path), pagesize=A4, title=f"Invoice {number}").build(
        [
            Paragraph(f"Commercial Invoice {number}", style["title"]),
            Paragraph(f"Supplier: {supplier}", style["body"]),
            Paragraph(f"Invoice date: {TODAY - timedelta(days=30)}", style["body"]),
            Spacer(1, 6 * mm),
            table,
        ]
    )


def write_manifest(path: Path, rows: int, lanes: list[tuple[str, str]], dirty: int) -> None:
    rng = random.Random(SEED)  # noqa: S311 - sample data
    # Deliberately non-obvious headers: real manifests never use our field names.
    headers = [
        "Ref No",
        "Vendor",
        "POL",
        "POD",
        "Mode",
        "Incoterms",
        "Cartons",
        "Invoice Value",
        "Gross Weight",
        "ETA",
        "Actual Arrival",
    ]

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for i in range(rows):
            origin, dest = rng.choice(lanes)
            eta = TODAY - timedelta(days=rng.randint(-30, 240))
            late = rng.random() < 0.25
            ata = eta + timedelta(days=rng.randint(1, 14) if late else -rng.randint(0, 2))
            writer.writerow(
                [
                    f"{origin}{dest}-MF-{i + 1:04d}",
                    rng.choice(
                        ["Shenzhen Precision Parts", "Hanoi Textile Group", "Osaka Bearings"]
                    ),
                    origin,
                    dest,
                    rng.choice(["FCL", "Air", "Truck"]),
                    rng.choice(["FOB", "CIF", "DAP"]),
                    rng.randint(10, 900),
                    f"{rng.randint(4000, 300000):,}",
                    rng.randint(80, 22000),
                    eta.strftime("%d/%m/%Y"),
                    ata.strftime("%d/%m/%Y") if ata <= TODAY else "",
                ]
            )
        # A few rows the file gets wrong, because real ones always do.
        for i in range(dirty):
            writer.writerow(
                [
                    f"BAD-{i}",
                    "Unknown Vendor",
                    "",
                    "DE",
                    "FCL",
                    "FOB",
                    "N/A",
                    "n/a",
                    "",
                    "not a date",
                    "",
                ]
            )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    write_contract(
        OUT / "contract_acme_supply_2026.pdf",
        "Acme Logistics",
        "Shenzhen Precision Parts",
        "MSA-2026-001",
    )
    write_contract(
        OUT / "contract_globex_framework_2026.pdf",
        "Globex Manufacturing",
        "Taipei Semiconductors",
        "MSA-2026-014",
    )
    write_invoice(OUT / "invoice_acme_INV-2026-0412.pdf", "Osaka Bearings", "INV-2026-0412")
    write_manifest(OUT / "manifest_acme_q1.csv", 42, [("CN", "DE"), ("VN", "NL"), ("JP", "US")], 3)
    write_manifest(OUT / "manifest_globex_q1.csv", 38, [("TW", "US"), ("DE", "FR")], 2)

    for path in sorted(OUT.iterdir()):
        if path.name != ".gitkeep":
            print(f"  {path.name:<42} {path.stat().st_size / 1024:6.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
