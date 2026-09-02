#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  8 06:48:37 2026

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

OUTPUT_FILE = ANONYMISED_DIR / "patient_inventory_v2.csv"


# ============================================================
# DOCUMENT CLASSIFICATION
# ============================================================

def classify_document(filename):
    """
    Classify a DOCX based on its filename.

    Returns:
        (classification, reason)
    """

    filename_lower = filename.lower()

    # --------------------------------------------------------
    # Temporary Microsoft Word files
    # --------------------------------------------------------

    if filename.startswith("~$"):
        return "Temporary", "Word temporary/lock file"

    # --------------------------------------------------------
    # Empfehlungen
    # --------------------------------------------------------

    if "empfehlungen" in filename_lower:
        return "Empfehlungen", "Exact keyword"

    # Common truncated form:
    # ~$pfehlungen... is handled as temporary above,
    # but pfehlungen... without ~$ is still likely
    # to be an abbreviated Empfehlungen filename.

    if "pfehlungen" in filename_lower:
        return "Empfehlungen", "Truncated keyword"

    # --------------------------------------------------------
    # Visitendokumentation
    # --------------------------------------------------------

    if "visitendokumentation" in filename_lower:
        return "Visitendokumentation", "Exact keyword"

    if "visitendokumentatio" in filename_lower:
        return "Visitendokumentation", "Truncated keyword"

    # --------------------------------------------------------
    # Medikationsplan
    # --------------------------------------------------------

    if "medikationsplan" in filename_lower:
        return "Medikationsplan", "Exact keyword"

    # --------------------------------------------------------
    # Unknown
    # --------------------------------------------------------

    return "Unknown", "No known keyword"


# ============================================================
# CREATE INVENTORY
# ============================================================

def create_inventory():

    if not ANONYMISED_DIR.exists():
        raise FileNotFoundError(
            f"Directory does not exist:\n{ANONYMISED_DIR}"
        )

    patient_folders = sorted(
        folder
        for folder in ANONYMISED_DIR.iterdir()
        if folder.is_dir()
        and folder.name.lower().startswith("patient_")
    )

    print(
        f"Found {len(patient_folders)} patient folders."
    )
    print()

    inventory = []

    # ========================================================
    # PROCESS PATIENTS
    # ========================================================

    for patient_folder in patient_folders:

        # Counts
        empfehlungen_count = 0
        visitendokumentation_count = 0
        medikationsplan_count = 0
        temporary_count = 0
        unknown_count = 0

        # ----------------------------------------------------
        # Find all DOCX files
        # ----------------------------------------------------

        docx_files = list(
            patient_folder.rglob("*.docx")
        )

        for file in docx_files:

            # Check if already organized
            relative_path = file.relative_to(
                patient_folder
            )

            parent_folders = relative_path.parts[:-1]

            # ------------------------------------------------
            # Already categorized folders
            # ------------------------------------------------

            if "Empfehlungen" in parent_folders:
                empfehlungen_count += 1
                continue

            if "Visitendokumentation" in parent_folders:
                visitendokumentation_count += 1
                continue

            if "Medikationsplan" in parent_folders:
                medikationsplan_count += 1
                continue

            # ------------------------------------------------
            # Classify filename
            # ------------------------------------------------

            classification, reason = classify_document(
                file.name
            )

            if classification == "Empfehlungen":
                empfehlungen_count += 1

            elif classification == "Visitendokumentation":
                visitendokumentation_count += 1

            elif classification == "Medikationsplan":
                medikationsplan_count += 1

            elif classification == "Temporary":
                temporary_count += 1

            elif classification == "Unknown":
                unknown_count += 1

            # ------------------------------------------------
            # Store individual file information
            # ------------------------------------------------

            inventory.append(
                {
                    "Patient": patient_folder.name,
                    "Filename": file.name,
                    "RelativePath": str(relative_path),
                    "Classification": classification,
                    "Reason": reason,
                }
            )

        # ====================================================
        # Patient-level inclusion
        # ====================================================

        include_patient = (
            empfehlungen_count > 0
            and visitendokumentation_count > 0
        )

        # Add patient summary row
        inventory.append(
            {
                "Patient": patient_folder.name,
                "Filename": "__PATIENT_SUMMARY__",
                "RelativePath": "",
                "Classification": "PATIENT_SUMMARY",
                "Reason": (
                    f"Empfehlungen={empfehlungen_count}; "
                    f"Visitendokumentation="
                    f"{visitendokumentation_count}; "
                    f"Medikationsplan="
                    f"{medikationsplan_count}; "
                    f"Temporary={temporary_count}; "
                    f"Unknown={unknown_count}; "
                    f"Include="
                    f"{'YES' if include_patient else 'NO'}"
                ),
            }
        )

    # ========================================================
    # WRITE FILE-LEVEL INVENTORY
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
        writer.writerows(inventory)

    # ========================================================
    # CREATE PATIENT SUMMARY
    # ========================================================

    patient_summary = {}

    for row in inventory:

        patient = row["Patient"]

        if patient not in patient_summary:

            patient_summary[patient] = {
                "Empfehlungen": 0,
                "Visitendokumentation": 0,
                "Medikationsplan": 0,
                "Temporary": 0,
                "Unknown": 0,
            }

        classification = row["Classification"]

        if classification in patient_summary[patient]:

            patient_summary[patient][classification] += 1

    # ========================================================
    # SUMMARY STATISTICS
    # ========================================================

    total_patients = len(patient_summary)

    included_patients = 0
    patients_with_unknown = 0
    patients_with_temporary = 0

    for patient, counts in patient_summary.items():

        if (
            counts["Empfehlungen"] > 0
            and counts["Visitendokumentation"] > 0
        ):
            included_patients += 1

        if counts["Unknown"] > 0:
            patients_with_unknown += 1

        if counts["Temporary"] > 0:
            patients_with_temporary += 1

    excluded_patients = (
        total_patients - included_patients
    )

    # ========================================================
    # PRINT SUMMARY
    # ========================================================

    print("=" * 60)
    print("PATIENT INVENTORY V2")
    print("=" * 60)

    print(
        f"Total patients:                 "
        f"{total_patients}"
    )

    print(
        f"Patients with both required:    "
        f"{included_patients}"
    )

    print(
        f"Patients excluded:              "
        f"{excluded_patients}"
    )

    print(
        f"Patients with unknown files:    "
        f"{patients_with_unknown}"
    )

    print(
        f"Patients with temporary files:  "
        f"{patients_with_temporary}"
    )

    print()

    print(
        f"Detailed inventory saved to:"
    )

    print(
        OUTPUT_FILE
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    create_inventory()