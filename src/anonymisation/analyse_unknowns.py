#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  8 07:31:01 2026

@author: administrator
"""

from pathlib import Path
import csv
import re
from collections import Counter


# ============================================================
# CONFIGURATION
# ============================================================

ANONYMISED_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/anonymised"
)

INPUT_FILE = ANONYMISED_DIR / "document_inventory_v3.csv"

OUTPUT_FILE = ANONYMISED_DIR / "unknown_analysis.csv"


# ============================================================
# NORMALISE FILENAME
# ============================================================

def normalise_filename(filename):
    """
    Create a simplified representation of a filename
    so that similar filenames can be grouped together.
    """

    name = filename

    # Remove .docx
    name = re.sub(
        r"\.docx$",
        "",
        name,
        flags=re.IGNORECASE
    )

    # Remove obvious patient identifiers / IDs
    name = re.sub(
        r"\b[A-Z]{2,3}\d{6,}\b",
        "<ID>",
        name
    )

    # Remove dates
    name = re.sub(
        r"\b\d{4}[-_]\d{2}[-_]\d{2}\b",
        "<DATE>",
        name
    )

    # Replace numbers
    name = re.sub(
        r"\b\d+\b",
        "<NUM>",
        name
    )

    # Remove KW numbers
    name = re.sub(
        r"KW\d+",
        "KW<NUM>",
        name,
        flags=re.IGNORECASE
    )

    # Replace underscores and hyphens with spaces
    name = re.sub(
        r"[_-]+",
        " ",
        name
    )

    # Normalize whitespace
    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name.strip()


# ============================================================
# MAIN
# ============================================================

def analyse_unknowns():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Could not find:\n{INPUT_FILE}"
        )

    unknown_files = []

    # --------------------------------------------------------
    # Read inventory
    # --------------------------------------------------------

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            if row["Classification"] == "Unknown":

                unknown_files.append(row)

    # --------------------------------------------------------
    # Group normalized names
    # --------------------------------------------------------

    groups = Counter()

    for row in unknown_files:

        normalized = normalise_filename(
            row["Filename"]
        )

        groups[normalized] += 1

    # --------------------------------------------------------
    # Write analysis
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "Count",
                "Normalized pattern"
            ]
        )

        for pattern, count in groups.most_common():

            writer.writerow(
                [
                    count,
                    pattern
                ]
            )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("UNKNOWN DOCUMENT ANALYSIS")
    print("=" * 60)

    print(
        f"Unknown documents: {len(unknown_files)}"
    )

    print(
        f"Unique filename patterns: {len(groups)}"
    )

    print()

    print(
        "Most common patterns:"
    )

    print("-" * 60)

    for pattern, count in groups.most_common(30):

        print(
            f"{count:4}  {pattern}"
        )

    print()

    print(
        f"Detailed analysis saved to:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    analyse_unknowns()