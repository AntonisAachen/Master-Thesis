#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Aug  8 07:45:38 2026

@author: administrator
"""

from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

ANONYMISED_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/anonymised"
)

# First run with True to preview
DRY_RUN = False


# ============================================================
# MAIN
# ============================================================

def remove_temp_files():

    temp_files = []

    # Find all Word temporary files
    for file in ANONYMISED_DIR.rglob("~$*.docx"):

        if file.is_file():
            temp_files.append(file)

    print("=" * 60)
    print("TEMPORARY WORD FILES")
    print("=" * 60)

    print(
        f"Found {len(temp_files)} temporary files."
    )

    print()

    # Show files
    for file in temp_files:

        print(
            file.relative_to(ANONYMISED_DIR)
        )

    # --------------------------------------------------------
    # Delete
    # --------------------------------------------------------

    if DRY_RUN:

        print()
        print("DRY RUN: No files were deleted.")

    else:

        deleted = 0

        for file in temp_files:

            try:

                file.unlink()
                deleted += 1

            except OSError as e:

                print(
                    f"ERROR deleting {file}: {e}"
                )

        print()
        print(
            f"Deleted {deleted} temporary files."
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    remove_temp_files()