#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Aug  3 08:30:52 2026

@author: administrator
"""

from pathlib import Path
import re
import csv
import shutil


# ==========================
# CONFIGURATION
# ==========================

RAW_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/raw"
)

ANON_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/anonymised"
)

mapping_dir = Path(r"/Users/administrator/Documents/Μεταπτυχιακό/Thesis")

MAPPING_FILE = mapping_dir / "patient_folder_mapping.csv"

DRY_RUN = False   # Change to False after checking


# Matches folders like:
# AB1234567
# DO7240009425
PATIENT_PATTERN = re.compile(r"^[A-Za-z]{2}\d+$")


# ==========================
# CREATE OUTPUT FOLDER
# ==========================

ANON_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ==========================
# COPY AND RENAME
# ==========================

mapping = []

patient_counter = 1


for folder in sorted(RAW_DIR.iterdir()):

    if not folder.is_dir():
        continue

    if not PATIENT_PATTERN.match(folder.name):
        continue


    patient_id = f"Patient_{patient_counter:04d}"

    destination = ANON_DIR / patient_id


    print(
        f"{folder.name}  -->  {destination.name}"
    )


    mapping.append(
        [
            folder.name,
            patient_id
        ]
    )


    if not DRY_RUN:

        if destination.exists():
            raise FileExistsError(
                f"{destination} already exists"
            )

        shutil.copytree(
            folder,
            destination
        )


    patient_counter += 1



# ==========================
# SAVE MAPPING
# ==========================

with open(
    MAPPING_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.writer(f)

    writer.writerow(
        [
            "OriginalFolder",
            "AnonymisedFolder"
        ]
    )

    writer.writerows(mapping)



print()
print(
    f"Found {len(mapping)} patient folders"
)

if DRY_RUN:
    print(
        "DRY RUN: Nothing copied"
    )
else:
    print(
        "Copy completed"
    )