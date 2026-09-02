#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  8 07:05:08 2026

@author: administrator
"""

from pathlib import Path
import csv


# ============================================================
# CONFIGURATION
# ============================================================

ANONYMISED_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/anonymised"
)

OUTPUT_FILE = ANONYMISED_DIR / "unmatched_documents.csv"


# ============================================================
# KNOWN DOCUMENT TYPES
# ============================================================

KEYWORDS = {
    "Empfehlungen",
    "Medikationsplan",
    "Visitendokumentation",
}


# ============================================================
# MAIN
# ============================================================

def create_unmatched_inventory():

    patient_folders = sorted(
        folder
        for folder in ANONYMISED_DIR.iterdir()
        if folder.is_dir()
        and folder.name.lower().startswith("patient_")
    )

    unmatched = []

    for patient_folder in patient_folders:

        for file in patient_folder.rglob("*.docx"):

            # Ignore files already inside categorized folders
            relative_path = file.relative_to(patient_folder)

            parent_folders = relative_path.parts[:-1]

            if any(
                folder in KEYWORDS
                for folder in parent_folders
            ):
                continue

            filename_lower = file.name.lower()

            # Check whether filename contains a known keyword
            matched = any(
                keyword.lower() in filename_lower
                for keyword in KEYWORDS
            )

            if not matched:

                unmatched.append(
                    {
                        "Patient": patient_folder.name,
                        "Filename": file.name,
                        "RelativePath": str(relative_path),
                    }
                )

    # ========================================================
    # WRITE CSV
    # ========================================================

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        fieldnames = [
            "Patient",
            "Filename",
            "RelativePath",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(unmatched)

    # ========================================================
    # SUMMARY
    # ========================================================

    patients_with_unmatched = len(
        set(row["Patient"] for row in unmatched)
    )

    print("=" * 60)
    print("UNMATCHED DOCUMENTS")
    print("=" * 60)

    print(
        f"Unmatched documents: {len(unmatched)}"
    )

    print(
        f"Patients affected:   {patients_with_unmatched}"
    )

    print()
    print(
        f"Saved to:\n{OUTPUT_FILE}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    create_unmatched_inventory()