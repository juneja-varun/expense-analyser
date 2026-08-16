"""The default category tree a new household starts with.

Tuned for Indian spending patterns — UPI-heavy, with categories most Indian
households actually use (domestic help, festivals, EMIs) rather than a
translated US taxonomy.

Users can rename, add and reorder freely. This is a starting point, not a
schema: the aim is that a first statement upload lands mostly in sensible
buckets so the app is useful before anyone configures anything.

Shape: (name, is_income, colour, [children]) — at most three levels deep.
"""

from __future__ import annotations

from typing import TypeAlias

CategorySpec: TypeAlias = tuple[str, list["CategorySpec"]]

# Palette is deliberately muted and distinguishable in both light and dark
# themes; charts pick these up directly.
DEFAULT_TAXONOMY: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
    (
        "Food & Dining",
        "#c2703d",
        [
            ("Groceries", ["Supermarket", "Local Kirana", "Online Grocery"]),
            ("Eating Out", ["Restaurants", "Cafes", "Food Delivery"]),
        ],
    ),
    (
        "Transport",
        "#3d7ac2",
        [
            ("Fuel", []),
            ("Cabs & Autos", []),
            ("Public Transport", ["Metro", "Bus", "Train"]),
            ("Vehicle", ["Servicing", "Insurance", "Parking & Tolls"]),
        ],
    ),
    (
        "Housing",
        "#7a5dc2",
        [
            ("Rent", []),
            ("Maintenance", []),
            ("Utilities", ["Electricity", "Water", "Gas", "Internet & Mobile"]),
            ("Domestic Help", []),
        ],
    ),
    (
        "Shopping",
        "#c23d7a",
        [
            ("Clothing", []),
            ("Electronics", []),
            ("Home & Furniture", []),
            ("Online Marketplaces", []),
        ],
    ),
    (
        "Health",
        "#3dc28a",
        [
            ("Doctor & Hospital", []),
            ("Pharmacy", []),
            ("Insurance", []),
            ("Fitness", []),
        ],
    ),
    (
        "Entertainment",
        "#c2a03d",
        [
            ("Subscriptions", ["Streaming", "Music", "News"]),
            ("Movies & Events", []),
            ("Travel & Holidays", ["Flights", "Hotels", "Activities"]),
        ],
    ),
    (
        "Financial",
        "#5d8ac2",
        [
            ("EMI & Loan Repayment", []),
            ("Investments", ["Mutual Funds", "Stocks", "Fixed Deposits", "Gold"]),
            ("Insurance Premiums", []),
            ("Taxes", []),
            ("Bank Charges", []),
            ("Credit Card Payment", []),
        ],
    ),
    (
        "Personal",
        "#c25d5d",
        [
            ("Education", []),
            ("Gifts & Donations", []),
            ("Festivals", []),
            ("Family Support", []),
            ("Grooming", []),
        ],
    ),
    ("Cash Withdrawal", "#8a8a80", []),
    ("Transfers", "#6b8a9e", [("To Own Accounts", []), ("To People", [])]),
    ("Uncategorised", "#9e9e94", []),
]

INCOME_TAXONOMY: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
    (
        "Income",
        "#2f8f5b",
        [
            ("Salary", []),
            ("Business & Freelance", []),
            ("Interest & Dividends", []),
            ("Refunds & Cashback", []),
            ("Rental Income", []),
            ("Other Income", []),
        ],
    ),
]

UNCATEGORISED_NAME = "Uncategorised"
"""Where transactions land when no rule matches. Always present, never deleted."""
