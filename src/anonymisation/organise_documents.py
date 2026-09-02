#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  8 06:25:57 2026

@author: administrator
"""

from pathlib import Path
import shutil


# ============================================================
# CONFIGURATION
# ============================================================

ANONYMISED_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/anonymised"
)

# Set to True to see what would happen without moving anything
DRY_RUN = True


# ============================================================
# DOCUMENT TYPE DETECTION
# ============================================================

DOCUMENT_TYPES = {
    "Empfehlungen": "Empfehlungen",
    "Medikationsplan": "Medikationsplan",
    "Visitendokumentation": "Visitendokumentation",
}


def identify_document_type(filename):
    """
    Identify the document type from its filename.

    Returns:
        str or None
    """

    filename_lower = filename.lower()

    for keyword, folder_name in DOCUMENT_TYPES.items():

        if keyword.lower() in filename_lower:
            return folder_name

    return None


# ============================================================
# MAIN
# ============================================================

def organise_documents():

    if not ANONYMISED_DIR.exists():
        raise FileNotFoundError(
            f"Directory does not exist: {ANONYMISED_DIR}"
        )

    total_moved = 0
    total_unmatched = 0

    patient_folders = sorted(
        folder
        for folder in ANONYMISED_DIR.iterdir()
        if folder.is_dir()
        and folder.name.lower().startswith("patient_")
    )

    print(f"Found {len(patient_folders)} patient folders.")
    print()

    # --------------------------------------------------------
    # Process each patient
    # --------------------------------------------------------

    for patient_folder in patient_folders:

        print("=" * 60)
        print(f"Patient: {patient_folder.name}")
        print("=" * 60)

        patient_moved = 0

        # Find DOCX files recursively
        docx_files = list(
            patient_folder.rglob("*.docx")
        )

        for file in docx_files:

            # Skip files that are already inside one of
            # the target folders
            relative_parts = file.relative_to(
                patient_folder
            ).parts

            if any(
                part in DOCUMENT_TYPES.values()
                for part in relative_parts[:-1]
            ):
                continue

            document_type = identify_document_type(
                file.name
            )

            # ------------------------------------------------
            # No matching document type
            # ------------------------------------------------

            if document_type is None:

                print(
                    f"  UNMATCHED: {file.name}"
                )

                total_unmatched += 1
                continue

            # ------------------------------------------------
            # Target folder
            # ------------------------------------------------

            target_folder = (
                patient_folder / document_type
            )

            target_file = (
                target_folder / file.name
            )

            print(
                f"  {file.name}"
            )

            print(
                f"      -> {document_type}/"
            )

            # ------------------------------------------------
            # Move
            # ------------------------------------------------

            if not DRY_RUN:

                target_folder.mkdir(
                    parents=True,
                    exist_ok=True
                )

                # Prevent accidental overwriting
                if target_file.exists():

                    print(
                        f"      WARNING: {target_file} already exists!"
                    )

                    continue

                shutil.move(
                    str(file),
                    str(target_file)
                )

            patient_moved += 1
            total_moved += 1

        print(
            f"  Files moved: {patient_moved}"
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(
        f"Patient folders: {len(patient_folders)}"
    )

    print(
        f"Files to move/moved: {total_moved}"
    )

    print(
        f"Unmatched files: {total_unmatched}"
    )

    if DRY_RUN:

        print()
        print(
            "DRY RUN: No files were moved."
        )

    else:

        print()
        print(
            "Files moved successfully."
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    organise_documents()