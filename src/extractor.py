# -*- coding: utf-8 -*-
"""
Created on Tue May 19 11:38:11 2026

@author: aantonopolos
"""

from pathlib import Path
from docx import Document

import csv
import json
import re


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/"
    "data/anonymised_processed"
)

OUTPUT_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/"
    "data/extracted"
)

JSON_DIR = OUTPUT_DIR / "json"

TEXT_DIR = OUTPUT_DIR / "text"

MANIFEST_FILE = (
    OUTPUT_DIR
    / "dataset_manifest.csv"
)


# ============================================================
# PATTERNS
# ============================================================

PATIENT_PATTERN = re.compile(
    r"Patient_\d{4}"
)


# ============================================================
# HELPERS
# ============================================================

def get_patient_id(file_path):
    """
    Extract Patient_XXXX from the path or filename.
    """

    match = PATIENT_PATTERN.search(
        str(file_path)
    )

    if match:

        return match.group()

    return "UNKNOWN"


def get_document_type(file_path):
    """
    Determine document type from filename/path.
    """

    text = str(file_path).lower()

    if "visitendokumentation" in text:

        return "Visitendokumentation"

    if "empfehlungen" in text:

        return "Empfehlungen"

    if "medikationsplan" in text:

        return "Medikationsplan"

    return "Unknown"


def clean_text(text):
    """
    Basic whitespace normalisation.

    Does NOT alter clinical content.
    """

    if text is None:
        return ""

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# EXTRACT PARAGRAPHS
# ============================================================

def extract_paragraphs(document):
    """
    Extract all non-empty body paragraphs.
    """

    paragraphs = []

    for index, paragraph in enumerate(
        document.paragraphs
    ):

        text = clean_text(
            paragraph.text
        )

        if not text:
            continue

        paragraphs.append(
            {
                "index": index,
                "text": text,
            }
        )

    return paragraphs


# ============================================================
# EXTRACT TABLES
# ============================================================

def extract_tables(document):
    """
    Extract Word tables while preserving rows and cells.
    """

    tables = []

    for table_index, table in enumerate(
        document.tables
    ):

        rows = []

        for row_index, row in enumerate(
            table.rows
        ):

            cells = []

            for cell_index, cell in enumerate(
                row.cells
            ):

                text = clean_text(
                    cell.text
                )

                cells.append(
                    {
                        "column": cell_index,
                        "text": text,
                    }
                )

            rows.append(
                {
                    "row": row_index,
                    "cells": cells,
                }
            )

        tables.append(
            {
                "table_index": table_index,
                "rows": rows,
            }
        )

    return tables


# ============================================================
# EXTRACT HEADER / FOOTER TEXT
# ============================================================

def extract_headers_footers(document):
    """
    Extract remaining text from headers and footers.

    These should already be pseudonymised.
    """

    headers = []
    footers = []

    seen_headers = set()
    seen_footers = set()

    for section_index, section in enumerate(
        document.sections
    ):

        header_parts = [
            section.header,
            section.first_page_header,
            section.even_page_header,
        ]

        footer_parts = [
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        ]

        for part in header_parts:

            texts = []

            for paragraph in part.paragraphs:

                text = clean_text(
                    paragraph.text
                )

                if text:
                    texts.append(
                        text
                    )

            for table in part.tables:

                for row in table.rows:

                    row_text = " | ".join(
                        clean_text(
                            cell.text
                        )
                        for cell in row.cells
                        if clean_text(
                            cell.text
                        )
                    )

                    if row_text:
                        texts.append(
                            row_text
                        )

            combined = clean_text(
                "\n".join(
                    texts
                )
            )

            if (
                combined
                and combined not in seen_headers
            ):

                headers.append(
                    {
                        "section": section_index,
                        "text": combined,
                    }
                )

                seen_headers.add(
                    combined
                )

        for part in footer_parts:

            texts = []

            for paragraph in part.paragraphs:

                text = clean_text(
                    paragraph.text
                )

                if text:
                    texts.append(
                        text
                    )

            for table in part.tables:

                for row in table.rows:

                    row_text = " | ".join(
                        clean_text(
                            cell.text
                        )
                        for cell in row.cells
                        if clean_text(
                            cell.text
                        )
                    )

                    if row_text:
                        texts.append(
                            row_text
                        )

            combined = clean_text(
                "\n".join(
                    texts
                )
            )

            if (
                combined
                and combined not in seen_footers
            ):

                footers.append(
                    {
                        "section": section_index,
                        "text": combined,
                    }
                )

                seen_footers.add(
                    combined
                )

    return headers, footers


# ============================================================
# BUILD PLAIN-TEXT REPRESENTATION
# ============================================================

def build_full_text(
    paragraphs,
    tables,
    headers,
    footers
):
    """
    Build deterministic text representation.

    Tables retain row/cell boundaries using pipes.
    """

    parts = []

    # ========================================================
    # HEADERS
    # ========================================================

    if headers:

        parts.append(
            "=== HEADER ==="
        )

        for header in headers:

            parts.append(
                header["text"]
            )

    # ========================================================
    # BODY PARAGRAPHS
    # ========================================================

    if paragraphs:

        parts.append(
            "=== BODY ==="
        )

        for paragraph in paragraphs:

            parts.append(
                paragraph["text"]
            )

    # ========================================================
    # TABLES
    # ========================================================

    for table in tables:

        parts.append(
            (
                "=== TABLE "
                f"{table['table_index']} ==="
            )
        )

        for row in table["rows"]:

            values = [
                cell["text"]
                for cell
                in row["cells"]
            ]

            parts.append(
                " | ".join(
                    values
                )
            )

    # ========================================================
    # FOOTERS
    # ========================================================

    if footers:

        parts.append(
            "=== FOOTER ==="
        )

        for footer in footers:

            parts.append(
                footer["text"]
            )

    return clean_text(
        "\n".join(
            parts
        )
    )


# ============================================================
# PROCESS SINGLE DOCUMENT
# ============================================================

def extract_document(
    input_file
):
    """
    Convert one DOCX to structured data.
    """

    document = Document(
        input_file
    )

    patient_id = get_patient_id(
        input_file
    )

    document_type = get_document_type(
        input_file
    )

    document_id = (
        input_file.stem
    )

    paragraphs = extract_paragraphs(
        document
    )

    tables = extract_tables(
        document
    )

    (
        headers,
        footers
    ) = extract_headers_footers(
        document
    )

    full_text = build_full_text(
        paragraphs,
        tables,
        headers,
        footers
    )

    data = {
        "patient_id":
            patient_id,

        "document_id":
            document_id,

        "document_type":
            document_type,

        "source_file":
            input_file.name,

        "paragraphs":
            paragraphs,

        "tables":
            tables,

        "headers":
            headers,

        "footers":
            footers,

        "full_text":
            full_text,
    }

    return data


# ============================================================
# PROCESS DATASET
# ============================================================

def process_dataset():

    if not INPUT_DIR.exists():

        raise FileNotFoundError(
            f"Input directory does not exist:\n"
            f"{INPUT_DIR}"
        )

    JSON_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    TEXT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    docx_files = sorted(
        file
        for file in INPUT_DIR.rglob(
            "*.docx"
        )
        if not file.name.startswith(
            "~$"
        )
    )

    print(
        f"Documents found: "
        f"{len(docx_files)}"
    )

    manifest = []

    errors = 0

    # ========================================================
    # DOCUMENT LOOP
    # ========================================================

    for index, input_file in enumerate(
        docx_files,
        start=1
    ):

        try:

            data = extract_document(
                input_file
            )

            patient_id = (
                data[
                    "patient_id"
                ]
            )

            document_id = (
                data[
                    "document_id"
                ]
            )

            document_type = (
                data[
                    "document_type"
                ]
            )

            # =================================================
            # PATIENT-SPECIFIC OUTPUT FOLDERS
            # =================================================

            patient_json_dir = (
                JSON_DIR
                / patient_id
            )

            patient_text_dir = (
                TEXT_DIR
                / patient_id
            )

            patient_json_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            patient_text_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            # =================================================
            # JSON
            # =================================================

            json_file = (
                patient_json_dir
                / f"{document_id}.json"
            )

            with open(
                json_file,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            # =================================================
            # PLAIN TEXT
            # =================================================

            text_file = (
                patient_text_dir
                / f"{document_id}.txt"
            )

            with open(
                text_file,
                "w",
                encoding="utf-8"
            ) as f:

                f.write(
                    data[
                        "full_text"
                    ]
                )

            # =================================================
            # MANIFEST ENTRY
            # =================================================

            manifest.append(
                {
                    "patient_id":
                        patient_id,

                    "document_id":
                        document_id,

                    "document_type":
                        document_type,

                    "source_file":
                        input_file.name,

                    "paragraph_count":
                        len(
                            data[
                                "paragraphs"
                            ]
                        ),

                    "table_count":
                        len(
                            data[
                                "tables"
                            ]
                        ),

                    "character_count":
                        len(
                            data[
                                "full_text"
                            ]
                        ),

                    "word_count":
                        len(
                            data[
                                "full_text"
                            ].split()
                        ),

                    "status":
                        "OK",
                }
            )

        except Exception as error:

            errors += 1

            print(
                f"ERROR in "
                f"{input_file.name}: "
                f"{error}"
            )

            manifest.append(
                {
                    "patient_id":
                        get_patient_id(
                            input_file
                        ),

                    "document_id":
                        input_file.stem,

                    "document_type":
                        get_document_type(
                            input_file
                        ),

                    "source_file":
                        input_file.name,

                    "paragraph_count":
                        0,

                    "table_count":
                        0,

                    "character_count":
                        0,

                    "word_count":
                        0,

                    "status":
                        f"ERROR: {error}",
                }
            )

        # ====================================================
        # QUIET PROGRESS REPORT
        # ====================================================

        if (
            index % 100 == 0
            or index == len(
                docx_files
            )
        ):

            print(
                f"Processed "
                f"{index}/"
                f"{len(docx_files)}"
            )

    # ========================================================
    # WRITE MANIFEST
    # ========================================================

    with open(
        MANIFEST_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        fieldnames = [
            "patient_id",
            "document_id",
            "document_type",
            "source_file",
            "paragraph_count",
            "table_count",
            "character_count",
            "word_count",
            "status",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()

        writer.writerows(
            manifest
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    successful = sum(
        row["status"] == "OK"
        for row in manifest
    )

    patients = {
        row["patient_id"]
        for row in manifest
        if row["patient_id"]
        != "UNKNOWN"
    }

    types = {}

    for row in manifest:

        document_type = (
            row[
                "document_type"
            ]
        )

        types.setdefault(
            document_type,
            0
        )

        types[
            document_type
        ] += 1

    print()
    print("=" * 70)
    print("EXTRACTION FINISHED")
    print("=" * 70)

    print(
        f"Patients: "
        f"{len(patients)}"
    )

    print(
        f"Documents: "
        f"{len(manifest)}"
    )

    print(
        f"Successful: "
        f"{successful}"
    )

    print(
        f"Errors: "
        f"{errors}"
    )

    print()

    print(
        "Document types:"
    )

    for document_type, count in sorted(
        types.items()
    ):

        print(
            f"    "
            f"{document_type}: "
            f"{count}"
        )

    print()

    print(
        f"JSON output:\n"
        f"{JSON_DIR}"
    )

    print()

    print(
        f"Text output:\n"
        f"{TEXT_DIR}"
    )

    print()

    print(
        f"Dataset manifest:\n"
        f"{MANIFEST_FILE}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    process_dataset()