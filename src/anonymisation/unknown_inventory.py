#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  8 07:21:07 2026

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

OUTPUT_FILE = ANONYMISED_DIR / "document_inventory_v3.csv"


# ============================================================
# KNOWN FOLDERS
# ============================================================

KNOWN_FOLDERS = {
    "empfehlungen": "Empfehlungen",
    "visitendokumentation": "Visitendokumentation",
    "medikationsplan": "Medikationsplan",
}


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_document(file, patient_folder):
    """
    Classify a document using the following priority:

    1. Temporary Word file
    2. Existing document folder
    3. Filename
    4. Unknown
    """

    filename = file.name
    filename_lower = filename.lower()

    relative_path = file.relative_to(patient_folder)
    parent_folders = relative_path.parts[:-1]

    # --------------------------------------------------------
    # 1. Temporary Word files
    # --------------------------------------------------------

    if filename.startswith("~$"):
        return "Temporary", "Microsoft Word temporary file"

    # --------------------------------------------------------
    # 2. Existing known folder
    # --------------------------------------------------------

    for folder in parent_folders:

        folder_lower = folder.lower()

        if folder_lower in KNOWN_FOLDERS:
            return (
                KNOWN_FOLDERS[folder_lower],
                f"Existing folder: {folder}"
            )

    # --------------------------------------------------------
    # 3. Filename-based classification
    # --------------------------------------------------------

    if "empfehlungen" in filename_lower:
        return (
            "Empfehlungen",
            "Filename: Empfehlungen"
        )

    if "pfehlungen" in filename_lower:
        return (
            "Empfehlungen",
            "Filename: truncated Empfehlungen"
        )

    if "visitendokumentation" in filename_lower:
        return (
            "Visitendokumentation",
            "Filename: Visitendokumentation"
        )

    if "visitendokumentatio" in filename_lower:
        return (
            "Visitendokumentation",
            "Filename: truncated Visitendokumentation"
        )

    if "medikationsplan" in filename_lower:
        return (
            "Medikationsplan",
            "Filename: Medikationsplan"
        )

    # --------------------------------------------------------
    # 4. Unknown
    # --------------------------------------------------------

    return (
        "Unknown",
        "No known folder or filename pattern"
    )


# ============================================================
# MAIN
# ============================================================

def create_inventory():

    patient_folders = sorted(
        folder
        for folder in ANONYMISED_DIR.iterdir()
        if folder.is_dir()
        and folder.name.lower().startswith("patient_")
    )

    rows = []

    for patient_folder in patient_folders:

        for file in patient_folder.rglob("*.docx"):

            classification, reason = classify_document(
                file,
                patient_folder
            )

            relative_path = file.relative_to(
                patient_folder
            )

            rows.append(
                {
                    "Patient": patient_folder.name,
                    "Filename": file.name,
                    "RelativePath": str(relative_path),
                    "Classification": classification,
                    "Reason": reason,
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
            "Classification",
            "Reason",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    # ========================================================
    # SUMMARY
    # ========================================================

    counts = {}

    for row in rows:

        classification = row["Classification"]

        counts[classification] = (
            counts.get(classification, 0) + 1
        )

    patients_by_classification = {}

    for row in rows:

        patient = row["Patient"]
        classification = row["Classification"]

        if patient not in patients_by_classification:
            patients_by_classification[patient] = set()

        patients_by_classification[patient].add(
            classification
        )

    patients_with_unknown = sum(
        "Unknown" in classifications
        for classifications
        in patients_by_classification.values()
    )

    patients_with_temporary = sum(
        "Temporary" in classifications
        for classifications
        in patients_by_classification.values()
    )

    print()
    print("=" * 60)
    print("DOCUMENT INVENTORY V3")
    print("=" * 60)

    print(
        f"Patient folders: {len(patient_folders)}"
    )

    print()

    print("DOCUMENT COUNTS")
    print("-" * 60)

    for classification in [
        "Empfehlungen",
        "Visitendokumentation",
        "Medikationsplan",
        "Temporary",
        "Unknown",
    ]:

        print(
            f"{classification:25} "
            f"{counts.get(classification, 0)}"
        )

    print()

    print("PATIENT COUNTS")
    print("-" * 60)

    print(
        f"Patients with unknown files:   "
        f"{patients_with_unknown}"
    )

    print(
        f"Patients with temporary files: "
        f"{patients_with_temporary}"
    )

    print()

    print(
        f"Inventory saved to:\n{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    create_inventory()