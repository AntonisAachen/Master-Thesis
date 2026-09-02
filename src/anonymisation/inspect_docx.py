#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 13 07:07:19 2026

@author: administrator
"""

from pathlib import Path
from docx import Document


# CHANGE THIS to one actual patient folder
PATIENT_FOLDER = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/data/test_anonymisation_output/Patient_0006"
)


for file in PATIENT_FOLDER.rglob("*.docx"):

    if file.name.startswith("~$"):
        continue

    print()
    print("=" * 80)
    print("FILE:")
    print(file)
    print("=" * 80)

    try:
        doc = Document(file)

        print("\n--- PARAGRAPHS ---")

        for i, paragraph in enumerate(doc.paragraphs):

            text = paragraph.text.strip()

            if text:
                print(f"[P{i}] {text}")

        print("\n--- TABLES ---")

        for table_number, table in enumerate(doc.tables):

            print(f"\nTABLE {table_number}")

            for row_number, row in enumerate(table.rows):

                cells = [
                    cell.text.replace("\n", " | ")
                    for cell in row.cells
                ]

                print(
                    f"Row {row_number}: {cells}"
                )

        print("\n--- HEADERS ---")

        for section_number, section in enumerate(
            doc.sections
        ):

            print(
                f"\nSection {section_number}"
            )

            for paragraph in section.header.paragraphs:

                if paragraph.text.strip():

                    print(
                        paragraph.text
                    )

            for table in section.header.tables:

                for row in table.rows:

                    print(
                        [
                            cell.text
                            for cell in row.cells
                        ]
                    )

        print("\n--- FOOTERS ---")

        for section in doc.sections:

            for paragraph in section.footer.paragraphs:

                if paragraph.text.strip():

                    print(
                        paragraph.text
                    )

    except Exception as e:

        print(
            f"ERROR: {e}"
        )