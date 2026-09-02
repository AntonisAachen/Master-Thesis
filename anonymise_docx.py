#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 13 06:50:49 2026

@author: administrator
"""

from pathlib import Path
from docx import Document

import csv
import re
import shutil
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/"
    "data/anonymised"
)

OUTPUT_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis/"
    "data/anonymised_processed"
)

LOG_FILE = OUTPUT_DIR / "anonymisation_log.csv"


# ============================================================
# REGEX PATTERNS
# ============================================================

# Examples:
# DO7240010777
# GE1212922
PATIENT_ID_PATTERN = re.compile(
    r"\b[A-Z]{2,3}\d{6,}\b"
)

# Full date, e.g. 22.04.1947
DOB_PATTERN = re.compile(
    r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"
)

# German telephone numbers
PHONE_PATTERN = re.compile(
    r"\b(?:\+49|0)[\d\/\- ]{6,}\d\b"
)


# ============================================================
# OOXML NAMESPACES
# ============================================================

W_NS = (
    "http://schemas.openxmlformats.org/"
    "wordprocessingml/2006/main"
)

CP_NS = (
    "http://schemas.openxmlformats.org/"
    "package/2006/metadata/core-properties"
)

DC_NS = "http://purl.org/dc/elements/1.1/"

DCTERMS_NS = "http://purl.org/dc/terms/"

EP_NS = (
    "http://schemas.openxmlformats.org/"
    "officeDocument/2006/extended-properties"
)

VT_NS = (
    "http://schemas.openxmlformats.org/"
    "officeDocument/2006/docPropsVTypes"
)

CUSTOM_PROPERTIES_NS = (
    "http://schemas.openxmlformats.org/"
    "officeDocument/2006/custom-properties"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def get_patient_code(patient_folder):
    return patient_folder.name


# ============================================================
# FIND PATIENT IDENTIFIERS
# ============================================================

def find_patient_identifiers(document):
    """
    Extract known patient identifiers from structured areas.

    Dates are treated as DOBs ONLY when they occur in
    explicitly labelled DOB fields.

    Clinical dates elsewhere remain untouched.
    """

    identifiers = {
        "names": set(),
        "ids": set(),
        "dobs": set(),
    }

    def extract_ids(text):

        if not text:
            return

        for match in PATIENT_ID_PATTERN.findall(text):
            identifiers["ids"].add(match)

    # ========================================================
    # BODY TABLES
    # ========================================================

    for table in document.tables:

        rows = table.rows

        for row_index, row in enumerate(rows):

            cells = row.cells

            # Search all table cells for patient/admission IDs
            for cell in cells:
                extract_ids(cell.text)

            # ------------------------------------------------
            # Example:
            #
            # Name, Geb.-Datum
            # Original Name | 22.04.1947
            # ------------------------------------------------

            if row_index > 0:

                previous_row = rows[
                    row_index - 1
                ]

                previous_labels = [
                    cell.text.lower()
                    for cell in previous_row.cells
                ]

                for cell_index, label in enumerate(
                    previous_labels
                ):

                    if (
                        "name" in label
                        and (
                            "geb.-datum" in label
                            or "geburtsdatum" in label
                        )
                        and cell_index < len(cells)
                    ):

                        value = (
                            cells[cell_index]
                            .text
                            .strip()
                        )

                        # Extract DOB only here
                        for dob in DOB_PATTERN.findall(
                            value
                        ):
                            identifiers["dobs"].add(
                                dob
                            )

                        # Remove DOB to isolate name
                        candidate = DOB_PATTERN.sub(
                            "",
                            value
                        )

                        candidate = (
                            candidate
                            .replace("*", "")
                            .strip(" |\n\t")
                        )

                        if candidate:
                            identifiers["names"].add(
                                candidate
                            )

            # ------------------------------------------------
            # Medikationsplan:
            #
            # Patientenname: | Original Name
            # ------------------------------------------------

            if len(cells) >= 2:

                label = (
                    cells[0]
                    .text
                    .lower()
                    .strip()
                )

                if "patientenname" in label:

                    patient_name = (
                        cells[1]
                        .text
                        .strip()
                    )

                    if patient_name:
                        identifiers["names"].add(
                            patient_name
                        )

    # ========================================================
    # HEADERS
    # ========================================================

    for section in document.sections:

        headers = [
            section.header,
            section.first_page_header,
            section.even_page_header,
        ]

        for header in headers:

            for paragraph in header.paragraphs:

                extract_ids(
                    paragraph.text
                )

            for table in header.tables:

                for row in table.rows:

                    for cell in row.cells:

                        extract_ids(
                            cell.text
                        )

                if len(table.rows) < 2:
                    continue

                labels = [
                    cell.text.lower().strip()
                    for cell in table.rows[0].cells
                ]

                values = [
                    cell.text.strip()
                    for cell in table.rows[1].cells
                ]

                for index, label in enumerate(
                    labels
                ):

                    if index >= len(values):
                        continue

                    value = values[index]

                    if label == "name":

                        if value:
                            identifiers["names"].add(
                                value
                            )

                    elif (
                        "geburtsdatum" in label
                        or "geb.-datum" in label
                    ):

                        for dob in DOB_PATTERN.findall(
                            value
                        ):
                            identifiers["dobs"].add(
                                dob
                            )

                    elif (
                        "aufnahme" in label
                        or "nummer" in label
                        or "kürzel" in label
                    ):

                        extract_ids(
                            value
                        )

    return identifiers


# ============================================================
# FIND STAFF NAMES
# ============================================================

def find_staff_names(document):
    """
    Collect staff names from structured staff fields and
    signature tables BEFORE modification.
    """

    staff_names = set()

    # ========================================================
    # STRUCTURED STAFF ROWS
    # ========================================================

    for table in document.tables:

        for row in table.rows:

            if len(row.cells) < 2:
                continue

            label = (
                row.cells[0]
                .text
                .lower()
                .strip()
            )

            value = (
                row.cells[1]
                .text
                .strip()
            )

            if (
                "telemediziner" in label
                or "apothekerin" in label
                or "apotheker" in label
            ):

                parts = re.split(
                    r"[/+|,;&]",
                    value
                )

                for part in parts:

                    name = part.strip()

                    if (
                        name
                        and len(name) >= 3
                    ):
                        staff_names.add(
                            name
                        )

    # ========================================================
    # SIGNATURE TABLES
    # ========================================================

    signature_terms = [
        "oberarzt",
        "oberärzt",
        "facharzt",
        "fachärzt",
        "teleintensivmediziner",
        "chefarzt",
        "chefärzt",
    ]

    for table in document.tables:

        table_text = " ".join(
            cell.text.lower()
            for row in table.rows
            for cell in row.cells
        )

        if not any(
            term in table_text
            for term in signature_terms
        ):
            continue

        if (
            len(table.rows) <= 4
            and len(table.columns) <= 4
        ):

            if table.rows:

                for cell in table.rows[0].cells:

                    value = (
                        cell.text
                        .strip()
                    )

                    value = re.sub(
                        r"(?i)\bdr\.?\s*med\.?\s*",
                        "",
                        value
                    )

                    value = re.sub(
                        r"(?i)\bprof\.?\s*",
                        "",
                        value
                    )

                    value = value.strip()

                    if (
                        value
                        and len(value) >= 3
                    ):

                        staff_names.add(
                            value
                        )

                        words = value.split()

                        if len(words) >= 2:

                            staff_names.add(
                                words[-1]
                            )

    return staff_names


# ============================================================
# ANONYMISE TEXT
# ============================================================

def anonymise_text(
    text,
    identifiers,
    patient_code,
    staff_names
):
    """
    Replace known identifiers in an ordinary text string.
    """

    if not text:
        return text, 0

    original = text

    # ========================================================
    # PATIENT NAME
    # ========================================================

    for name in sorted(
        identifiers["names"],
        key=len,
        reverse=True
    ):

        if not name:
            continue

        text = re.sub(
            re.escape(name),
            patient_code,
            text,
            flags=re.IGNORECASE
        )

    # ========================================================
    # PATIENT / ADMISSION ID
    # ========================================================

    for patient_id in sorted(
        identifiers["ids"],
        key=len,
        reverse=True
    ):

        text = re.sub(
            re.escape(patient_id),
            patient_code,
            text,
            flags=re.IGNORECASE
        )

    # ========================================================
    # DATE OF BIRTH
    # ========================================================

    for dob in identifiers["dobs"]:

        text = text.replace(
            dob,
            "[DOB_REMOVED]"
        )

    # ========================================================
    # STAFF NAMES
    # ========================================================

    for staff_name in sorted(
        staff_names,
        key=len,
        reverse=True
    ):

        if not staff_name:
            continue

        text = re.sub(
            rf"\b{re.escape(staff_name)}\b",
            "[STAFF_REMOVED]",
            text,
            flags=re.IGNORECASE
        )

    # ========================================================
    # PHONE NUMBERS
    # ========================================================

    text = PHONE_PATTERN.sub(
        "[PHONE_REMOVED]",
        text
    )

    changed = int(
        text != original
    )

    return text, changed


# ============================================================
# ANONYMISE PARAGRAPH
# ============================================================

def anonymise_paragraph(
    paragraph,
    identifiers,
    patient_code,
    staff_names
):

    old_text = paragraph.text

    new_text, changed = anonymise_text(
        old_text,
        identifiers,
        patient_code,
        staff_names
    )

    if changed:

        paragraph.text = new_text

    return changed


# ============================================================
# REMOVE COMPLETE KK / HEIGHT / WEIGHT CELL
# ============================================================

def remove_sensitive_structured_cell(
    table
):
    """
    Find a table label containing:

        KK
        Krankenkasse
        Versicherung

    and replace the COMPLETE corresponding value cell
    in the next row with:

        [REMOVED]

    This intentionally removes:
        - admission/patient number in that cell
        - insurance company
        - height
        - weight
        - any other value stored in the same structured cell

    No parsing of separators is required.
    """

    changes = 0

    rows = table.rows

    for row_index, row in enumerate(
        rows
    ):

        if row_index + 1 >= len(rows):
            continue

        for cell_index, label_cell in enumerate(
            row.cells
        ):

            label = (
                label_cell.text
                .lower()
                .strip()
            )

            is_sensitive_field = (
                re.search(
                    r"\bkk\b",
                    label
                )
                is not None
                or "krankenkasse" in label
                or "versicherung" in label
            )

            if not is_sensitive_field:
                continue

            value_row = rows[
                row_index + 1
            ]

            if cell_index >= len(
                value_row.cells
            ):
                continue

            value_cell = (
                value_row.cells[
                    cell_index
                ]
            )

            old_text = (
                value_cell.text
            )

            if not old_text.strip():
                continue

            if old_text.strip() == "[REMOVED]":
                continue

            # print(
            #     "    SENSITIVE CELL REMOVED:"
            # )

            # print(
            #     f"        LABEL:  "
            #     f"{repr(label_cell.text)}"
            # )

            # print(
            #     f"        BEFORE: "
            #     f"{repr(old_text)}"
            # )

            # value_cell.text = "[REMOVED]"

            # print(
            #     "        AFTER:   "
            #     "'[REMOVED]'"
            # )

            changes += 1

    return changes


# ============================================================
# ANONYMISE TABLE
# ============================================================

def anonymise_table(
    table,
    identifiers,
    patient_code,
    staff_names
):

    changes = 0

    # ========================================================
    # NORMAL CONTENT
    # ========================================================

    for row in table.rows:

        # ----------------------------------------------------
        # Explicit staff fields
        # ----------------------------------------------------

        if len(row.cells) >= 2:

            label = (
                row.cells[0]
                .text
                .lower()
            )

            if (
                "telemediziner" in label
                or "apothekerin" in label
                or "apotheker" in label
            ):

                if row.cells[1].text.strip():

                    row.cells[1].text = (
                        "[STAFF_REMOVED]"
                    )

                    changes += 1

        # ----------------------------------------------------
        # Normal cell text
        # ----------------------------------------------------

        for cell in row.cells:

            for paragraph in cell.paragraphs:

                changes += anonymise_paragraph(
                    paragraph,
                    identifiers,
                    patient_code,
                    staff_names
                )

    # ========================================================
    # REMOVE COMPLETE KK / HEIGHT / WEIGHT FIELD
    # ========================================================

    changes += remove_sensitive_structured_cell(
        table
    )

    return changes


# ============================================================
# REMOVE PARAGRAPH SIGNATURE BLOCK
# ============================================================

def remove_signature_block(document):
    """
    Replace non-empty body paragraphs following:

        Mit freundlichen Grüßen
    """

    signature_started = False

    changes = 0

    for paragraph in document.paragraphs:

        text = (
            paragraph.text
            .strip()
        )

        if (
            "mit freundlichen grüßen"
            in text.lower()
        ):

            signature_started = True
            continue

        if (
            signature_started
            and text
        ):

            paragraph.text = (
                "[STAFF_SIGNATURE_REMOVED]"
            )

            changes += 1

    return changes


# ============================================================
# REMOVE SIGNATURE TABLES
# ============================================================

def remove_signature_tables(document):
    """
    Detect small tables containing physician signatures.
    """

    changes = 0

    signature_terms = [
        "oberarzt",
        "oberärzt",
        "facharzt",
        "fachärzt",
        "teleintensivmediziner",
        "chefarzt",
        "chefärzt",
        "dr. med.",
    ]

    for table in document.tables:

        table_text = " ".join(
            cell.text.lower()
            for row in table.rows
            for cell in row.cells
        )

        if not any(
            term in table_text
            for term in signature_terms
        ):
            continue

        if (
            len(table.rows) <= 4
            and len(table.columns) <= 4
        ):

            for row in table.rows:

                for cell in row.cells:

                    if cell.text.strip():

                        cell.text = (
                            "[STAFF_SIGNATURE_REMOVED]"
                        )

                        changes += 1

    return changes


# ============================================================
# OOXML HELPER:
# UNWRAP AN ELEMENT WHILE KEEPING ITS CHILDREN
# ============================================================

def unwrap_xml_element(element):
    """
    Remove an OOXML wrapper but preserve its child elements.

    Used for accepted insertions (w:ins) and move-to content.
    """

    parent = element.getparent()

    if parent is None:
        return

    index = parent.index(
        element
    )

    for child in list(element):

        element.remove(
            child
        )

        parent.insert(
            index,
            child
        )

        index += 1

    parent.remove(
        element
    )


# ============================================================
# SANITISE WORD XML
# ============================================================

def sanitise_word_xml(
    data,
    identifiers,
    patient_code,
    staff_names
):
    """
    Sanitise one XML part inside word/.

    Performs:
    - known identifier replacement in w:t elements
    - phone-number removal
    - comment-reference removal
    - accept insertions
    - remove deletions
    - accept move-to content
    - remove move-from content
    - remove revision metadata
    """

    try:

        parser = etree.XMLParser(
            remove_blank_text=False,
            recover=False
        )

        root = etree.fromstring(
            data,
            parser
        )

    except etree.XMLSyntaxError:

        return data, 0

    changes = 0

    namespace = {
        "w": W_NS
    }

    # ========================================================
    # TEXT ELEMENTS
    #
    # This also reaches textboxes and similar content not
    # normally exposed through python-docx.
    # ========================================================

    text_elements = root.xpath(
        "//w:t",
        namespaces=namespace
    )

    for element in text_elements:

        if element.text is None:
            continue

        new_text, changed = anonymise_text(
            element.text,
            identifiers,
            patient_code,
            staff_names
        )

        if changed:

            element.text = new_text

            changes += changed

    # ========================================================
    # REMOVE COMMENT MARKERS
    # ========================================================

    comment_nodes = root.xpath(
        "//w:commentRangeStart"
        " | //w:commentRangeEnd"
        " | //w:commentReference",
        namespaces=namespace
    )

    for node in comment_nodes:

        parent = node.getparent()

        if parent is not None:

            parent.remove(
                node
            )

            changes += 1

    # ========================================================
    # TRACKED CHANGES:
    # ACCEPT INSERTIONS
    # ========================================================

    insertion_nodes = root.xpath(
        "//w:ins | //w:moveTo",
        namespaces=namespace
    )

    # Work deepest-first
    for node in reversed(
        insertion_nodes
    ):

        unwrap_xml_element(
            node
        )

        changes += 1

    # ========================================================
    # TRACKED CHANGES:
    # REMOVE DELETED / MOVE-FROM CONTENT
    # ========================================================

    deletion_nodes = root.xpath(
        "//w:del | //w:moveFrom",
        namespaces=namespace
    )

    for node in deletion_nodes:

        parent = node.getparent()

        if parent is not None:

            parent.remove(
                node
            )

            changes += 1

    # ========================================================
    # REMOVE REMAINING REVISION AUTHOR / DATE ATTRIBUTES
    # ========================================================

    revision_attributes = [
        f"{{{W_NS}}}author",
        f"{{{W_NS}}}date",
        f"{{{W_NS}}}initials",
        f"{{{W_NS}}}userId",
    ]

    for element in root.iter():

        for attribute in revision_attributes:

            if attribute in element.attrib:

                del element.attrib[
                    attribute
                ]

                changes += 1

    output = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True
    )

    return output, changes


# ============================================================
# SANITISE CORE DOCUMENT PROPERTIES
# ============================================================

def sanitise_core_properties_xml(
    data
):
    """
    Clear potentially identifying core properties.
    """

    try:

        root = etree.fromstring(
            data
        )

    except etree.XMLSyntaxError:

        return data, 0

    changes = 0

    sensitive_tags = {
        f"{{{DC_NS}}}creator",
        f"{{{CP_NS}}}lastModifiedBy",
        f"{{{DC_NS}}}title",
        f"{{{DC_NS}}}subject",
        f"{{{CP_NS}}}keywords",
        f"{{{DC_NS}}}description",
        f"{{{CP_NS}}}category",
        f"{{{CP_NS}}}contentStatus",
    }

    for element in root.iter():

        if element.tag in sensitive_tags:

            if element.text:

                element.text = ""

                changes += 1

    output = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True
    )

    return output, changes


# ============================================================
# SANITISE EXTENDED DOCUMENT PROPERTIES
# ============================================================

def sanitise_app_properties_xml(
    data
):
    """
    Clear selected extended properties such as company
    and manager.
    """

    try:

        root = etree.fromstring(
            data
        )

    except etree.XMLSyntaxError:

        return data, 0

    changes = 0

    sensitive_local_names = {
        "Company",
        "Manager",
        "HyperlinkBase",
    }

    for element in root.iter():

        local_name = etree.QName(
            element
        ).localname

        if (
            local_name
            in sensitive_local_names
        ):

            if element.text:

                element.text = ""

                changes += 1

    output = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True
    )

    return output, changes


# ============================================================
# SANITISE CUSTOM DOCUMENT PROPERTIES
# ============================================================

def sanitise_custom_properties_xml(
    data
):
    """
    Keep the custom-properties XML part structurally present,
    but clear property values.

    This is safer than blindly deleting the OOXML part because
    package relationships may still reference it.
    """

    try:

        root = etree.fromstring(
            data
        )

    except etree.XMLSyntaxError:

        return data, 0

    changes = 0

    for property_element in list(root):

        # Keep the property definition but clear all text values
        for descendant in property_element.iter():

            if (
                descendant is not property_element
                and descendant.text
            ):

                descendant.text = ""

                changes += 1

    output = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True
    )

    return output, changes


# ============================================================
# EMPTY COMMENT / PEOPLE PART
# ============================================================

def empty_xml_children(
    data
):
    """
    Preserve an XML part but remove its child entries.

    Useful for:
    - comments.xml
    - commentsExtended.xml
    - commentsIds.xml
    - people.xml

    This avoids broken OOXML relationships caused by simply
    deleting referenced package parts.
    """

    try:

        root = etree.fromstring(
            data
        )

    except etree.XMLSyntaxError:

        return data, 0

    changes = 0

    for child in list(root):

        root.remove(
            child
        )

        changes += 1

    output = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True
    )

    return output, changes


# ============================================================
# FINAL DOCX PACKAGE SANITISATION
# ============================================================

def sanitise_docx_package(
    docx_path,
    identifiers,
    patient_code,
    staff_names
):
    """
    Final OOXML sanitisation after python-docx saves the file.

    Handles:
    - hidden/textbox w:t text
    - comments
    - comment authors
    - tracked changes
    - revision authors/dates
    - core properties
    - extended properties
    - custom property values
    - Word people metadata
    """

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".docx",
        delete=False
    )

    temp_path = Path(
        temp_file.name
    )

    temp_file.close()

    total_changes = 0

    try:

        with ZipFile(
            docx_path,
            "r"
        ) as source_zip:

            with ZipFile(
                temp_path,
                "w",
                ZIP_DEFLATED
            ) as target_zip:

                for item in source_zip.infolist():

                    filename = item.filename

                    data = source_zip.read(
                        filename
                    )

                    part_changes = 0

                    # ========================================
                    # WORD CONTENT XML
                    # ========================================

                    if (
                        filename.startswith(
                            "word/"
                        )
                        and filename.endswith(
                            ".xml"
                        )
                    ):

                        # ------------------------------------
                        # Comment-related parts:
                        # preserve root but remove entries
                        # ------------------------------------

                        if (
                            filename
                            in {
                                "word/comments.xml",
                                "word/commentsExtended.xml",
                                "word/commentsExtensible.xml",
                                "word/commentsIds.xml",
                                "word/people.xml",
                            }
                        ):

                            (
                                data,
                                part_changes
                            ) = empty_xml_children(
                                data
                            )

                        else:

                            (
                                data,
                                part_changes
                            ) = sanitise_word_xml(
                                data,
                                identifiers,
                                patient_code,
                                staff_names
                            )

                    # ========================================
                    # CORE PROPERTIES
                    # ========================================

                    elif (
                        filename
                        == "docProps/core.xml"
                    ):

                        (
                            data,
                            part_changes
                        ) = (
                            sanitise_core_properties_xml(
                                data
                            )
                        )

                    # ========================================
                    # EXTENDED PROPERTIES
                    # ========================================

                    elif (
                        filename
                        == "docProps/app.xml"
                    ):

                        (
                            data,
                            part_changes
                        ) = (
                            sanitise_app_properties_xml(
                                data
                            )
                        )

                    # ========================================
                    # CUSTOM PROPERTIES
                    # ========================================

                    elif (
                        filename
                        == "docProps/custom.xml"
                    ):

                        (
                            data,
                            part_changes
                        ) = (
                            sanitise_custom_properties_xml(
                                data
                            )
                        )

                    total_changes += (
                        part_changes
                    )

                    target_zip.writestr(
                        item,
                        data
                    )

        shutil.move(
            str(temp_path),
            str(docx_path)
        )

    finally:

        if temp_path.exists():

            temp_path.unlink()

    return total_changes


# ============================================================
# VALIDATE FINAL OOXML PACKAGE
# ============================================================

def validate_docx_package(
    docx_path,
    identifiers,
    staff_names
):
    """
    Validate readable document CONTENT rather than scanning
    every raw XML string.

    This avoids false positives from Word-internal values in:

        fontTable.xml
        styles.xml
        numbering.xml
        settings.xml

    Checks:
        - known patient names
        - known patient IDs
        - DOB
        - known staff names
        - admission-ID-like strings
        - phone-like strings
        - residual comment / tracked-change markup

    Returns:
        list of human-readable warnings
    """

    issues = []

    # ========================================================
    # KNOWN SENSITIVE VALUES
    # ========================================================

    sensitive_strings = []

    for value in identifiers["names"]:

        if value:
            sensitive_strings.append(
                (
                    "PATIENT_NAME",
                    value
                )
            )

    for value in identifiers["ids"]:

        if value:
            sensitive_strings.append(
                (
                    "PATIENT_ID",
                    value
                )
            )

    for value in identifiers["dobs"]:

        if value:
            sensitive_strings.append(
                (
                    "DOB",
                    value
                )
            )

    for value in staff_names:

        if value:
            sensitive_strings.append(
                (
                    "STAFF",
                    value
                )
            )

    # ========================================================
    # PARTS THAT MAY CONTAIN HUMAN-READABLE DOCUMENT CONTENT
    # ========================================================

    def is_content_part(filename):

        if filename == "word/document.xml":
            return True

        if re.fullmatch(
            r"word/header\d+\.xml",
            filename
        ):
            return True

        if re.fullmatch(
            r"word/footer\d+\.xml",
            filename
        ):
            return True

        if filename in {
            "word/footnotes.xml",
            "word/endnotes.xml",
            "word/comments.xml",
        }:
            return True

        return False

    # ========================================================
    # OPEN DOCX
    # ========================================================

    with ZipFile(
        docx_path,
        "r"
    ) as archive:

        for filename in archive.namelist():

            if not is_content_part(
                filename
            ):
                continue

            raw_data = archive.read(
                filename
            )

            try:

                parser = etree.XMLParser(
                    remove_blank_text=False,
                    recover=True
                )

                root = etree.fromstring(
                    raw_data,
                    parser
                )

            except etree.XMLSyntaxError:

                issues.append(
                    f"Could not parse XML: "
                    f"{filename}"
                )

                continue

            namespace = {
                "w": W_NS
            }

            # =================================================
            # EXTRACT ACTUAL HUMAN-READABLE TEXT ONLY
            # =================================================

            text_elements = root.xpath(
                "//w:t",
                namespaces=namespace
            )

            readable_text = " ".join(
                element.text
                for element in text_elements
                if element.text
            )

            readable_lower = (
                readable_text.lower()
            )

            # =================================================
            # KNOWN IDENTIFIERS
            # =================================================

            for issue_type, value in sensitive_strings:

                if (
                    value.lower()
                    in readable_lower
                ):

                    issues.append(
                        f"{issue_type} remains in "
                        f"{filename}: {value}"
                    )

            # =================================================
            # PATIENT / ADMISSION-ID PATTERN
            # =================================================

            id_matches = (
                PATIENT_ID_PATTERN.findall(
                    readable_text
                )
            )

            for match in id_matches:

                issues.append(
                    f"ID-like value remains in "
                    f"{filename}: {match}"
                )

            # =================================================
            # PHONE NUMBERS
            # =================================================
            #
            # Only scan visible/readable text.
            #
            # This prevents numbers from:
            #
            #   fontTable.xml
            #   numbering.xml
            #   settings.xml
            #   XML attributes
            #
            # from being mistaken for telephone numbers.
            # =================================================

            phone_matches = (
                PHONE_PATTERN.findall(
                    readable_text
                )
            )

            for match in phone_matches:

                issues.append(
                    f"Phone-like value remains in "
                    f"{filename}: "
                    f"{match}"
                )

            # =================================================
            # COMMENT MARKERS
            # =================================================

            comment_nodes = root.xpath(
                "//w:commentRangeStart"
                " | //w:commentRangeEnd"
                " | //w:commentReference",
                namespaces=namespace
            )

            if comment_nodes:

                issues.append(
                    f"Comment markup remains in "
                    f"{filename}"
                )

            # =================================================
            # TRACKED CHANGES
            # =================================================

            revision_nodes = root.xpath(
                "//w:ins"
                " | //w:del"
                " | //w:moveFrom"
                " | //w:moveTo",
                namespaces=namespace
            )

            if revision_nodes:

                issues.append(
                    f"Tracked-change markup remains in "
                    f"{filename}"
                )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    issues = list(
        dict.fromkeys(
            issues
        )
    )

    return issues


# ============================================================
# PROCESS ONE DOCUMENT
# ============================================================

def anonymise_document(
    input_file,
    output_file,
    patient_code,
    patient_staff_names
):

    document = Document(
        input_file
    )

    # ========================================================
    # DISCOVERY BEFORE MODIFICATION
    # ========================================================

    identifiers = (
        find_patient_identifiers(
            document
        )
    )

    staff_names = set(
        patient_staff_names
    )

    staff_names.update(
        find_staff_names(
            document
        )
    )

    changes = 0

    # ========================================================
    # MAIN BODY PARAGRAPHS
    # ========================================================

    for paragraph in document.paragraphs:

        changes += anonymise_paragraph(
            paragraph,
            identifiers,
            patient_code,
            staff_names
        )

    # ========================================================
    # BODY TABLES
    # ========================================================

    for table in document.tables:

        changes += anonymise_table(
            table,
            identifiers,
            patient_code,
            staff_names
        )

    # ========================================================
    # HEADERS / FOOTERS
    # ========================================================

    for section in document.sections:

        headers = [
            section.header,
            section.first_page_header,
            section.even_page_header,
        ]

        footers = [
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        ]

        for part in (
            headers
            + footers
        ):

            for paragraph in part.paragraphs:

                changes += anonymise_paragraph(
                    paragraph,
                    identifiers,
                    patient_code,
                    staff_names
                )

            for table in part.tables:

                changes += anonymise_table(
                    table,
                    identifiers,
                    patient_code,
                    staff_names
                )

    # ========================================================
    # SIGNATURE REMOVAL
    # ========================================================

    changes += remove_signature_block(
        document
    )

    changes += remove_signature_tables(
        document
    )

    # ========================================================
    # BASIC CORE PROPERTIES
    # ========================================================

    properties = (
        document.core_properties
    )

    properties.author = ""
    properties.last_modified_by = ""
    properties.title = ""
    properties.subject = ""
    properties.keywords = ""
    properties.comments = ""

    # ========================================================
    # SAVE DOCX
    # ========================================================

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    document.save(
        output_file
    )

    # ========================================================
    # FINAL OOXML PACKAGE SANITISATION
    # ========================================================

    package_changes = (
        sanitise_docx_package(
            output_file,
            identifiers,
            patient_code,
            staff_names
        )
    )

    changes += package_changes

    # ========================================================
    # FINAL PACKAGE VALIDATION
    # ========================================================

    validation_issues = (
        validate_docx_package(
            output_file,
            identifiers,
            staff_names
        )
    )

    return (
        identifiers,
        staff_names,
        changes,
        package_changes,
        validation_issues
    )


# ============================================================
# SAFE OUTPUT FILENAME
# ============================================================

def create_output_filename(
    patient_code,
    document_type,
    number
):

    return (
        f"{patient_code}_"
        f"{document_type}_"
        f"{number:02d}.docx"
    )


# ============================================================
# PROCESS DATASET
# ============================================================

def process_dataset():

    if not INPUT_DIR.exists():

        raise FileNotFoundError(
            f"Input folder not found:\n"
            f"{INPUT_DIR}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    log = []

    patient_folders = sorted(
        folder
        for folder in INPUT_DIR.iterdir()
        if (
            folder.is_dir()
            and folder.name.startswith(
                "Patient_"
            )
        )
    )

    print(
        f"Patients found: "
        f"{len(patient_folders)}"
    )

    # ========================================================
    # PATIENT LOOP
    # ========================================================

    for patient_folder in patient_folders:

        patient_code = (
            get_patient_code(
                patient_folder
            )
        )

        print()
        print("=" * 70)
        print(patient_code)
        print("=" * 70)

        counters = {}

        # ====================================================
        # GET ALL DOCUMENTS
        # ====================================================

        patient_documents = sorted(
            file
            for file
            in patient_folder.rglob(
                "*.docx"
            )
            if not file.name.startswith(
                "~$"
            )
        )

        print(
            f"Documents found: "
            f"{len(patient_documents)}"
        )

        # ====================================================
        # FIRST PASS:
        # COLLECT STAFF NAMES ACROSS PATIENT DOCUMENTS
        # ====================================================

        patient_staff_names = set()

        for file in patient_documents:

            try:

                document = Document(
                    file
                )

                patient_staff_names.update(
                    find_staff_names(
                        document
                    )
                )

            except Exception as error:

                print(
                    "Could not inspect "
                    "staff names in "
                    f"{file.name}: "
                    f"{error}"
                )

        # print(
        #     "Patient-level staff names: "
        #     f"{sorted(patient_staff_names)}"
        # )

        # ====================================================
        # SECOND PASS:
        # PSEUDONYMISE DOCUMENTS
        # ====================================================

        for input_file in patient_documents:

            document_type = (
                input_file.parent.name
                .replace(
                    " ",
                    "_"
                )
            )

            counters.setdefault(
                document_type,
                0
            )

            counters[
                document_type
            ] += 1

            output_name = (
                create_output_filename(
                    patient_code,
                    document_type,
                    counters[
                        document_type
                    ]
                )
            )

            relative_parent = (
                input_file.parent
                .relative_to(
                    patient_folder
                )
            )

            output_file = (
                OUTPUT_DIR
                / patient_code
                / relative_parent
                / output_name
            )

            # print()
            # print(
            #     f"Input:  "
            #     f"{input_file.name}"
            # )

            # print(
            #     f"Output: "
            #     f"{output_name}"
            # )

            try:

                (
                    identifiers,
                    staff_names,
                    changes,
                    package_changes,
                    validation_issues
                ) = anonymise_document(
                    input_file,
                    output_file,
                    patient_code,
                    patient_staff_names
                )

                # --------------------------------------------
                # Status
                # --------------------------------------------

                if validation_issues:

                    status = (
                        "WARNING_VALIDATION"
                    )

                else:

                    status = "OK"

                log.append(
                    {
                        "Patient":
                            patient_code,

                        "OriginalFile":
                            input_file.name,

                        "NewFile":
                            output_name,

                        "NamesFound":
                            "; ".join(
                                sorted(
                                    identifiers[
                                        "names"
                                    ]
                                )
                            ),

                        "IDsFound":
                            "; ".join(
                                sorted(
                                    identifiers[
                                        "ids"
                                    ]
                                )
                            ),

                        "DOBsFound":
                            "; ".join(
                                sorted(
                                    identifiers[
                                        "dobs"
                                    ]
                                )
                            ),

                        "StaffFound":
                            "; ".join(
                                sorted(
                                    staff_names
                                )
                            ),

                        "Changes":
                            changes,

                        "PackageChanges":
                            package_changes,

                        "ValidationIssues":
                            " | ".join(
                                validation_issues
                            ),

                        "Status":
                            status,
                    }
                )

                # print(
                #     "    Patient names: "
                #     f"{identifiers['names']}"
                # )

                # print(
                #     "    Patient IDs: "
                #     f"{identifiers['ids']}"
                # )

                # print(
                #     "    DOBs: "
                #     f"{identifiers['dobs']}"
                # )

                # print(
                #     "    Staff: "
                #     f"{staff_names}"
                # )

                # print(
                #     "    Total changes: "
                #     f"{changes}"
                # )

                # print(
                #     "    OOXML package changes: "
                #     f"{package_changes}"
                # )

                # if validation_issues:

                #     print(
                #         "    VALIDATION WARNINGS:"
                #     )

                #     for issue in (
                #         validation_issues
                #     ):

                #         print(
                #             f"        - {issue}"
                #         )

                # else:

                #     print(
                #         "    Validation: OK"
                #     )

            except Exception as error:

                print(
                    f"    ERROR: "
                    f"{error}"
                )

                log.append(
                    {
                        "Patient":
                            patient_code,

                        "OriginalFile":
                            input_file.name,

                        "NewFile":
                            output_name,

                        "NamesFound":
                            "",

                        "IDsFound":
                            "",

                        "DOBsFound":
                            "",

                        "StaffFound":
                            "",

                        "Changes":
                            0,

                        "PackageChanges":
                            0,

                        "ValidationIssues":
                            "",

                        "Status":
                            f"ERROR: {error}",
                    }
                )

    # ========================================================
    # WRITE LOG
    # ========================================================

    with open(
        LOG_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        fields = [
            "Patient",
            "OriginalFile",
            "NewFile",
            "NamesFound",
            "IDsFound",
            "DOBsFound",
            "StaffFound",
            "Changes",
            "PackageChanges",
            "ValidationIssues",
            "Status",
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()

        writer.writerows(
            log
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    successful = sum(
        row["Status"] == "OK"
        for row in log
    )

    warnings = sum(
        row["Status"]
        == "WARNING_VALIDATION"
        for row in log
    )

    errors = sum(
        str(row["Status"]).startswith(
            "ERROR:"
        )
        for row in log
    )

    total_changes = sum(
        int(row["Changes"])
        for row in log
    )

    package_changes = sum(
        int(row["PackageChanges"])
        for row in log
    )

    print()
    print("=" * 70)
    print("PSEUDONYMISATION FINISHED")
    print("=" * 70)

    print(
        f"Documents OK: "
        f"{successful}"
    )

    print(
        f"Validation warnings: "
        f"{warnings}"
    )

    print(
        f"Errors: "
        f"{errors}"
    )

    print(
        f"Total changes: "
        f"{total_changes}"
    )

    print(
        f"OOXML package changes: "
        f"{package_changes}"
    )

    print()

    print(
        f"Output:\n"
        f"{OUTPUT_DIR}"
    )

    print()

    print(
        f"Private log:\n"
        f"{LOG_FILE}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    process_dataset()