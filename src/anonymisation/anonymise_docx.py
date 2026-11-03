#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 13 06:50:49 2026

@author: administrator
"""

from functools import lru_cache
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

PATIENT_ID_PATTERN = re.compile(
    r"\b[A-Z]{2,3}\d{6,}\b"
)

DOB_PATTERN = re.compile(
    r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"
)

# German phone numbers: +49 / 0049 / 0 prefix followed by digits that
# may be separated by single spaces, dashes or slashes. The old
# pattern started with \b, which can never match before a "+", and
# it also matched dosing schemes such as 0-0-1-0-0. Candidates are
# therefore checked again in looks_like_phone_number().
PHONE_PATTERN = re.compile(
    r"(?<![\w+/\-])"
    r"\(?"
    r"(?:\+49|0049|0)"
    r"(?:[ \t/\-]?\(?\d\)?){6,14}"
)

DATE_LIKE_PATTERN = re.compile(
    r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
)


# ------------------------------------------------------------
# PATIENT NAME VARIANTS
#
# The name found in the Name/DOB table (e.g. "Mustermann, Hans")
# is rarely written the same way in the free text. Besides the
# literal string, the following variants are matched:
#   - "First Last" / "Last First" / "Last, First"
#   - each name part on its own ("Herr Mustermann")
#   - German genitive ("Mustermanns")
# All matching is whole-word, so a short name such as "Ali" does
# not damage "Qualität".
# ------------------------------------------------------------

# Titles and forms of address: never treated as name parts.
NAME_TITLE_TOKENS = {
    "dr", "prof", "med", "dipl", "ing", "pd", "priv", "doz", "mag",
    "herr", "herrn", "frau", "fr", "hr", "frl",
}

# Name particles: part of the full name, but never matched alone.
NAME_PARTICLES = {
    "von", "van", "vom", "zu", "zur", "zum", "der", "den", "de",
    "di", "du", "la", "le", "da", "dos", "ten", "ter", "bin", "ibn",
}

# Words that can appear in a name cell without being a name. If the
# cell says "Patient unbekannt", "Patient" must not be removed from
# every document.
NAME_TOKEN_STOPWORDS = {
    "patient", "patientin", "patienten", "name", "vorname", "nachname",
    "unbekannt", "unknown", "geb", "geboren", "datum", "männlich",
    "weiblich", "divers", "männl", "weibl", "station", "klinik",
    "aufnahme", "entlassung", "fall", "nummer",
}

# German adjectives that are also common surnames. As a stand-alone
# name part they are matched only in capitalised form ("Herr Klein"),
# so that "klein" or "groß" in clinical text is left alone.
NAME_TOKENS_COMMON_WORDS = {
    "klein", "gross", "groß", "lang", "kurz", "jung", "alt", "neu",
    "schwarz", "weiss", "weiß", "braun", "hoch", "stark", "frei",
    "fest", "voll", "recht", "gut", "reich", "arm", "bauer", "wolf",
}

NAME_MIN_TOKEN_LENGTH = 3

# True: each part of the patient's name is also removed on its own
# ("Herr Mustermann", "Hans geht es besser"). This is the safer
# setting for privacy, but it also removes unrelated occurrences of
# a common first name. False: only complete name variants are
# matched (the surname alone is then NOT removed either).
MATCH_SINGLE_NAME_PARTS = True

NAME_TOKEN_PATTERN = re.compile(
    r"[^\W\d_]+(?:[-'’][^\W\d_]+)*"
)

# German genitive and similar endings: Mustermanns, Hans', Hanses
NAME_SUFFIX = r"(?:[’']?s|es|ens)?"


def _name_tokens(text):

    return [
        token.strip(".,;:()")
        for token in text.split()
        if token.strip(".,;:()")
    ]


def expand_name_variants(raw_name):
    """
    Return a list of (variant, case_sensitive) for one name string.
    The literal string is always included. Re-ordered and single-part
    variants are only derived when the string looks like a person's
    name (1-4 alphabetic parts), so that an odd cell content cannot
    cause common words to be removed everywhere.
    """

    raw_name = " ".join(raw_name.split())

    if not raw_name:
        return []

    variants = [
        (raw_name, False)
    ]

    # Name parts without titles ("Dr. med. Hans Mustermann")
    if "," in raw_name:

        pieces = [
            piece.strip()
            for piece in raw_name.split(",")
        ]

        last_part = pieces[0]

        first_part = " ".join(pieces[1:])

    else:

        last_part = None

        first_part = None

    def clean_tokens(text):

        return [
            token
            for token in _name_tokens(text)
            if token.lower().strip(".") not in NAME_TITLE_TOKENS
        ]

    if last_part is not None:

        last_tokens = clean_tokens(last_part)

        first_tokens = clean_tokens(first_part)

        all_tokens = last_tokens + first_tokens

    else:

        all_tokens = clean_tokens(raw_name)

        last_tokens = None

        first_tokens = None

    # Particles ("von", "van", ...) are lowercase and are not name
    # parts on their own, so they are ignored for this check.
    core_tokens = [
        token
        for token in all_tokens
        if token.lower() not in NAME_PARTICLES
    ]

    person_like = (
        1 <= len(core_tokens) <= 4
        and all(
            NAME_TOKEN_PATTERN.fullmatch(token)
            and token[0].isupper()
            for token in core_tokens
        )
    )

    if not person_like:

        return variants

    full = " ".join(all_tokens)

    # Order variants
    if last_tokens is not None and first_tokens:

        last = " ".join(last_tokens)

        first = " ".join(first_tokens)

        variants += [
            (f"{first} {last}", False),
            (f"{last} {first}", False),
            (f"{last}, {first}", False),
        ]

    elif len(all_tokens) >= 2:

        variants += [
            (full, False),
            (" ".join(reversed(all_tokens)), False),
            (
                f"{all_tokens[-1]}, "
                f"{' '.join(all_tokens[:-1])}",
                False
            ),
            (
                f"{all_tokens[0]}, "
                f"{' '.join(all_tokens[1:])}",
                False
            ),
        ]

    if not MATCH_SINGLE_NAME_PARTS:

        return variants

    # Single name parts (also the parts of hyphenated names)
    parts = []

    for token in core_tokens:

        parts.append(token)

        if "-" in token:

            parts.extend(token.split("-"))

    for part in parts:

        lowered = part.lower()

        if (
            len(part) < NAME_MIN_TOKEN_LENGTH
            or lowered in NAME_PARTICLES
            or lowered in NAME_TOKEN_STOPWORDS
        ):
            continue

        variants.append(
            (
                part,
                lowered in NAME_TOKENS_COMMON_WORDS
            )
        )

    return variants


@lru_cache(maxsize=256)
def build_name_patterns(names):
    """
    Compile whole-word patterns for a frozenset of raw patient
    names. Returns a tuple of compiled regular expressions.
    """

    seen = set()

    patterns = []

    for raw_name in sorted(names):

        for variant, case_sensitive in expand_name_variants(
            raw_name
        ):

            key = (variant.lower(), case_sensitive)

            if key in seen:
                continue

            seen.add(key)

            # Whitespace in the name matches any whitespace run
            # (double spaces, line breaks, non-breaking spaces).
            body = r"\s+".join(
                re.escape(piece)
                for piece in variant.split()
            )

            patterns.append(
                re.compile(
                    r"(?<!\w)"
                    + body
                    + NAME_SUFFIX
                    + r"(?!\w)",
                    0 if case_sensitive else re.IGNORECASE
                )
            )

    return tuple(patterns)


def looks_like_phone_number(candidate):

    digits = re.sub(
        r"\D",
        "",
        candidate
    )

    if not 7 <= len(digits) <= 15:
        return False

    # Real numbers contain at least one run of three digits.
    # Dosing schemes (1-0-1-0-1) and similar do not.
    if not re.search(r"\d{3}", candidate):
        return False

    if DATE_LIKE_PATTERN.fullmatch(
        candidate.strip("() ")
    ):
        return False

    return True


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

W_P = f"{{{W_NS}}}p"
W_PPR = f"{{{W_NS}}}pPr"
W_R = f"{{{W_NS}}}r"
W_T = f"{{{W_NS}}}t"
W_TAB = f"{{{W_NS}}}tab"
W_BR = f"{{{W_NS}}}br"
W_CR = f"{{{W_NS}}}cr"

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


# ============================================================
# BASIC HELPERS
# ============================================================

def get_patient_code(patient_folder):
    return patient_folder.name


def empty_identifiers():

    return {
        "names": set(),
        "ids": set(),
        "dobs": set(),
    }


def merge_identifiers(target, source):

    for key in target:

        target[key].update(
            source[key]
        )

    return target


# Only these folder names are carried over into the output tree.
# Any other subfolder of a patient folder may contain identifying
# text, so it is dropped (the original path is kept in the log).
ALLOWED_OUTPUT_SUBFOLDERS = {
    "empfehlungen": "Empfehlungen",
    "visitendokumentation": "Visitendokumentation",
    "medikationsplan": "Medikationsplan",
}


def safe_output_subfolder(relative_parent):
    """
    Return (path, dropped_count): the part of the original
    subfolder path that may be reused in the output.
    """

    kept = []

    dropped = 0

    for part in relative_parent.parts:

        if part in ("", "."):
            continue

        canonical = ALLOWED_OUTPUT_SUBFOLDERS.get(
            part.lower()
        )

        if canonical:

            kept.append(
                canonical
            )

        else:

            dropped += 1

    return Path(*kept), dropped


def get_document_type(input_file):
    """
    Determine document type from:
    1. parent folder
    2. filename
    3. document content
    """

    known_types = {
        "empfehlungen": "Empfehlungen",
        "visitendokumentation": "Visitendokumentation",
        "medikationsplan": "Medikationsplan",
    }

    # --------------------------------------------------------
    # Parent folder
    # --------------------------------------------------------

    parent_name = input_file.parent.name.lower()

    for keyword, document_type in known_types.items():

        if keyword in parent_name:
            return document_type

    # --------------------------------------------------------
    # Filename
    # --------------------------------------------------------

    filename = input_file.name.lower()

    for keyword, document_type in known_types.items():

        if keyword in filename:
            return document_type

    # --------------------------------------------------------
    # Document content
    # --------------------------------------------------------

    try:

        document = Document(
            input_file
        )

        paragraph_text = "\n".join(
            paragraph.text
            for paragraph in document.paragraphs
        )

        table_text = "\n".join(
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        )

        complete_text = (
            paragraph_text
            + "\n"
            + table_text
        ).lower()

        if (
            "sofa-score" in complete_text
            or "beatmung/bga" in complete_text
            or "verlaufsdokumentation" in complete_text
        ):
            return "Visitendokumentation"

        if (
            "telemedizinerin" in complete_text
            or (
                "empfehlungen" in complete_text
                and "klinische fragestellung"
                in complete_text
            )
        ):
            return "Empfehlungen"

        if (
            "patientenname:" in complete_text
            or "medikationsplan" in complete_text
        ):
            return "Medikationsplan"

    except Exception:

        pass

    return "Unknown"


# ============================================================
# FIND PATIENT IDENTIFIERS
# ============================================================

def find_patient_identifiers(document):

    identifiers = {
        "names": set(),
        "ids": set(),
        "dobs": set(),
    }

    def extract_ids(text):

        if not text:
            return

        for match in PATIENT_ID_PATTERN.findall(text):

            identifiers["ids"].add(
                match
            )

    # ========================================================
    # BODY TABLES
    # ========================================================

    for table in document.tables:

        rows = table.rows

        for row_index, row in enumerate(rows):

            cells = row.cells

            # ------------------------------------------------
            # Search IDs everywhere
            # ------------------------------------------------

            for cell in cells:

                extract_ids(
                    cell.text
                )

            # ------------------------------------------------
            # INLINE:
            #
            # Name, Geb.-Datum | Name | DOB
            # ------------------------------------------------

            for cell in cells:

                text = (
                    cell.text
                    .replace("\n", " | ")
                    .strip()
                )

                lower = text.lower()

                if (
                    "name" in lower
                    and (
                        "geb.-datum" in lower
                        or "geburtsdatum" in lower
                    )
                    and "|" in text
                ):

                    parts = [
                        part.strip()
                        for part in text.split("|")
                        if part.strip()
                    ]

                    # Label + name + DOB
                    if len(parts) >= 2:

                        for part in parts[1:]:

                            for dob in DOB_PATTERN.findall(
                                part
                            ):

                                identifiers[
                                    "dobs"
                                ].add(
                                    dob
                                )

                        # Usually second field is name
                        name_candidate = (
                            parts[1]
                            if len(parts) >= 2
                            else ""
                        )

                        if (
                            name_candidate
                            and not DOB_PATTERN.fullmatch(
                                name_candidate
                            )
                            and not PATIENT_ID_PATTERN.fullmatch(
                                name_candidate
                            )
                        ):

                            identifiers[
                                "names"
                            ].add(
                                name_candidate
                            )

            # ------------------------------------------------
            # SEPARATE ROW LAYOUT no 1
            #
            # Row X:
            # Name, Geb.-Datum
            #
            # Row X+1:
            # Name | DOB
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
                        and "vorname" not in label
                        and (
                            "geb.-datum" in label
                            or "geburtsdatum" in label
                            or "geb. datum" in label
                            or "geb datum" in label
                        )
                        and cell_index < len(cells)
                    ):

                        value = (
                            cells[cell_index]
                            .text
                            .strip()
                        )

                        for dob in DOB_PATTERN.findall(
                            value
                        ):

                            identifiers[
                                "dobs"
                            ].add(
                                dob
                            )

                        candidate = DOB_PATTERN.sub(
                            "",
                            value
                        )

                        candidate = (
                            candidate
                            .replace("*", "")
                            .strip(" |\n\t")
                        )

                        if (
                            candidate
                            and not candidate.startswith(
                                "Patient_"
                            )
                        ):

                            identifiers[
                                "names"
                            ].add(
                                candidate
                            )
                                
            # ------------------------------------------------
            # SEPARATE ROW LAYOUT no 2
            #
            # Row X:
            # Name, Vorname
            #
            # Row X+1:
            # Geburtsdatum
            #
            # Row X+2
            # Name, Vorname
            #
            # Row X+3
            # DOB
            # ------------------------------------------------
            
            if row_index >= 3:

                row_name_label = rows[
                    row_index - 3
                ]

                row_dob_label = rows[
                    row_index - 2
                ]

                row_name_value = rows[
                    row_index - 1
                ]

                row_dob_value = rows[
                    row_index
                ]

                # Check corresponding cells because the
                # structure may be part of a wider table.
                for cell_index in range(
                    min(
                        len(row_name_label.cells),
                        len(row_dob_label.cells),
                        len(row_name_value.cells),
                        len(row_dob_value.cells)
                    )
                ):

                    name_label = (
                        row_name_label.cells[
                            cell_index
                        ]
                        .text
                        .strip()
                        .lower()
                    )

                    dob_label = (
                        row_dob_label.cells[
                            cell_index
                        ]
                        .text
                        .strip()
                        .lower()
                    )

                    name_value = (
                        row_name_value.cells[
                            cell_index
                        ]
                        .text
                        .strip()
                    )

                    dob_value = (
                        row_dob_value.cells[
                            cell_index
                        ]
                        .text
                        .strip()
                    )

                    if (
                        "name" in name_label
                        and "vorname" in name_label
                        and "geburtsdatum" in dob_label
                    ):

                        # -----------------------------
                        # Actual patient name
                        # -----------------------------

                        if (
                            name_value
                            and not PATIENT_ID_PATTERN.fullmatch(
                                name_value
                            )
                        ):

                            identifiers[
                                "names"
                            ].add(
                                name_value
                            )

                        # -----------------------------
                        # Actual DOB
                        # -----------------------------

                        for dob in DOB_PATTERN.findall(
                            dob_value
                        ):

                            identifiers[
                                "dobs"
                            ].add(
                                dob
                            )

            # ------------------------------------------------
            # Medikationsplan
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

                        identifiers[
                            "names"
                        ].add(
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

                            identifiers[
                                "names"
                            ].add(
                                value
                            )

                    elif (
                        "geburtsdatum" in label
                        or "geb.-datum" in label
                    ):

                        for dob in DOB_PATTERN.findall(
                            value
                        ):

                            identifiers[
                                "dobs"
                            ].add(
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

def find_replacements(
    text,
    identifiers,
    patient_code,
    staff_names
):
    """
    Find everything in `text` that has to be replaced.

    Returns a sorted list of non-overlapping (start, end, replacement)
    tuples that refer to positions in `text`.

    All matches are collected on the ORIGINAL text in a single pass.
    If matches overlap, the category listed first wins (patient name,
    patient ID, date of birth, staff, phone number), then the longer
    match. This is the same priority the previous sequential
    replacement had.

    Returning positions (instead of a new string) allows the same
    result to be applied across Word runs without destroying the
    formatting, see apply_replacements_to_segments().
    """

    candidates = []

    def add_literals(
        values,
        replacement,
        priority,
        ignore_case=True,
        whole_word=False
    ):

        for value in values:

            if not value:
                continue

            body = re.escape(
                value
            )

            if whole_word:

                body = rf"\b{body}\b"

            pattern = re.compile(
                body,
                re.IGNORECASE if ignore_case else 0
            )

            for match in pattern.finditer(text):

                candidates.append(
                    (
                        priority,
                        match.start(),
                        match.end(),
                        replacement
                    )
                )

    # Names: all variants, whole-word (see expand_name_variants)
    for pattern in build_name_patterns(
        frozenset(
            name
            for name in identifiers["names"]
            if name
        )
    ):

        for match in pattern.finditer(text):

            candidates.append(
                (
                    0,
                    match.start(),
                    match.end(),
                    patient_code
                )
            )

    # IDs are long and distinctive, so they are matched anywhere
    # (not whole-word): an ID glued to other characters must not
    # survive.
    add_literals(
        identifiers["ids"],
        patient_code,
        1
    )

    add_literals(
        identifiers["dobs"],
        "[DOB_REMOVED]",
        2,
        ignore_case=False
    )

    add_literals(
        staff_names,
        "[STAFF_REMOVED]",
        3,
        whole_word=True
    )

    for match in PHONE_PATTERN.finditer(text):

        start, end = match.span()

        candidate = text[start:end]

        # Do not swallow a closing bracket that belongs to the
        # surrounding text: "(Tel 0241 123456)".
        while (
            candidate.endswith(")")
            and candidate.count(")") > candidate.count("(")
        ):

            end -= 1
            candidate = candidate[:-1]

        if looks_like_phone_number(candidate):

            candidates.append(
                (
                    4,
                    start,
                    end,
                    "[PHONE_REMOVED]"
                )
            )

    candidates.sort(
        key=lambda c: (
            c[0],
            -(c[2] - c[1]),
            c[1]
        )
    )

    accepted = []

    for _, start, end, replacement in candidates:

        overlaps = any(
            start < accepted_end
            and accepted_start < end
            for accepted_start, accepted_end, _ in accepted
        )

        if not overlaps:

            accepted.append(
                (
                    start,
                    end,
                    replacement
                )
            )

    accepted.sort()

    return [
        (start, end, replacement)
        for start, end, replacement in accepted
        if text[start:end] != replacement
    ]


def anonymise_text(
    text,
    identifiers,
    patient_code,
    staff_names
):

    if not text:
        return text, 0

    replacements = find_replacements(
        text,
        identifiers,
        patient_code,
        staff_names
    )

    if not replacements:
        return text, 0

    parts = []

    position = 0

    for start, end, replacement in replacements:

        parts.append(
            text[position:start]
        )

        parts.append(
            replacement
        )

        position = end

    parts.append(
        text[position:]
    )

    return "".join(parts), 1


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
# HANDLE INLINE NAME + DOB
# ============================================================

def remove_structured_patient_identity(
    table,
    patient_code
):
    """
    Remove patient identity from structured Name/DOB fields.

    Supports three layouts:

    A)
        Label row:
        Name, Geb.-Datum

        Value row:
        Original Patient Name | 17.04.1941

        Result:
        Patient_XXXX | [DOB_REMOVED]


    B)
        Same cell:
        Name, Geb.-Datum | Original Patient Name | 17.04.1941

        Result:
        Name, Geb.-Datum | Patient_XXXX | [DOB_REMOVED]


    C)
        Row X:
        Name, Vorname

        Row X+1:
        Geburtsdatum

        Row X+2:
        Original Patient Name

        Row X+3:
        17.04.1941

        Result:
        Name, Vorname
        Geburtsdatum
        Patient_XXXX
        [DOB_REMOVED]
    """

    changes = 0
    rows = table.rows

    for row_index, row in enumerate(rows):

        for cell_index, cell in enumerate(row.cells):

            original_text = cell.text.strip()

            text = (
                original_text
                .replace("\n", " | ")
                .strip()
            )

            lower = text.lower()

            # =================================================
            # CASE 3:
            # FOUR-ROW LAYOUT
            #
            # Name, Vorname
            # Geburtsdatum
            # Actual Patient Name
            # Actual DOB
            # =================================================

            is_name_vorname_label = (
                "name" in lower
                and "vorname" in lower
                and "geburtsdatum" not in lower
                and "geb.-datum" not in lower
            )

            if is_name_vorname_label:

                # Need three rows below the label row.
                if row_index + 3 < len(rows):

                    dob_label_row = rows[
                        row_index + 1
                    ]

                    name_value_row = rows[
                        row_index + 2
                    ]

                    dob_value_row = rows[
                        row_index + 3
                    ]

                    if (
                        cell_index < len(dob_label_row.cells)
                        and cell_index < len(name_value_row.cells)
                        and cell_index < len(dob_value_row.cells)
                    ):

                        dob_label_cell = (
                            dob_label_row.cells[
                                cell_index
                            ]
                        )

                        dob_label = (
                            dob_label_cell.text
                            .strip()
                            .lower()
                        )

                        if (
                            "geburtsdatum" in dob_label
                            or "geb.-datum" in dob_label
                            or "geb. datum" in dob_label
                            or "geb datum" in dob_label
                        ):

                            name_value_cell = (
                                name_value_row.cells[
                                    cell_index
                                ]
                            )

                            dob_value_cell = (
                                dob_value_row.cells[
                                    cell_index
                                ]
                            )

                            # Replace ONLY the patient name.
                            if (
                                name_value_cell.text.strip()
                                != patient_code
                            ):

                                name_value_cell.text = (
                                    patient_code
                                )

                                changes += 1

                            # Replace ONLY the DOB.
                            if (
                                dob_value_cell.text.strip()
                                != "[DOB_REMOVED]"
                            ):

                                dob_value_cell.text = (
                                    "[DOB_REMOVED]"
                                )

                                changes += 1

                            # IMPORTANT:
                            # Keep both labels untouched:
                            #
                            # Name, Vorname
                            # Geburtsdatum

                            continue

            # =================================================
            # OLD IDENTITY FIELD:
            #
            # Name, Geb.-Datum
            # or
            # Name, Geburtsdatum
            # =================================================

            is_identity_field = (
                "name" in lower
                and (
                    "geb.-datum" in lower
                    or "geburtsdatum" in lower
                    or "geb. datum" in lower
                    or "geb datum" in lower
                )
            )

            if not is_identity_field:
                continue

            # =================================================
            # CASE 1:
            # LABEL + PATIENT DATA IN SAME CELL
            # =================================================

            if "|" in text:

                parts = [
                    part.strip()
                    for part in text.split("|")
                    if part.strip()
                ]

                if len(parts) >= 2:

                    label = parts[0]

                    new_text = (
                        f"{label} | "
                        f"{patient_code} | "
                        f"[DOB_REMOVED]"
                    )

                    if original_text != new_text:

                        cell.text = new_text
                        changes += 1

                    continue

            # =================================================
            # CASE 2:
            # LABEL IN THIS ROW, VALUES IN NEXT ROW
            # =================================================

            if row_index + 1 >= len(rows):
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

            current_value = (
                value_cell.text
                .strip()
            )

            if not current_value:
                continue

            new_value = (
                f"{patient_code} | "
                f"[DOB_REMOVED]"
            )

            if current_value != new_value:

                value_cell.text = new_value
                changes += 1

    return changes

# ============================================================
# REMOVE NUMMER / KK / HEIGHT / WEIGHT FIELD
# ============================================================

def remove_sensitive_structured_cell(
    table
):
    """
    Supports two structures:

    A)
        Label row:
        Nummer, KK, Größe, Gewicht

        Next row:
        7240025719, TK, 180, 100

    B)
        Same cell:
        Nummer, KK, Größe, Gewicht |
        Patient_0009 | AOK | 174 cm, 73 kg

    The value content is removed completely.
    """

    changes = 0

    rows = table.rows

    for row_index, row in enumerate(
        rows
    ):

        for cell_index, cell in enumerate(
            row.cells
        ):

            text = (
                cell.text
                .replace("\n", " | ")
                .strip()
            )

            lower = text.lower()

            has_number = (
                "nummer" in lower
                or "aufnahme-nr" in lower
                or "aufnahme nr" in lower
            )

            has_insurance = (
                re.search(
                    r"\bkk\b",
                    lower
                )
                is not None
                or "krankenkasse" in lower
                or "versicherung" in lower
            )

            if not (
                has_number
                and has_insurance
            ):
                continue

            # =================================================
            # CASE 1:
            # LABEL + VALUE IN SAME CELL
            # =================================================

            if "|" in text:

                parts = [
                    part.strip()
                    for part in text.split("|")
                ]

                if len(parts) > 1:

                    label = parts[0]

                    new_text = (
                        f"{label} | [REMOVED]"
                    )

                    if (
                        cell.text.strip()
                        != new_text
                    ):

                        cell.text = new_text

                        changes += 1

                    continue

            # =================================================
            # CASE 2:
            # VALUE IN NEXT ROW
            # =================================================

            if (
                row_index + 1
                < len(rows)
            ):

                value_row = rows[
                    row_index + 1
                ]

                if (
                    cell_index
                    < len(value_row.cells)
                ):

                    value_cell = (
                        value_row.cells[
                            cell_index
                        ]
                    )

                    current_value = (
                        value_cell.text
                        .strip()
                    )

                    if (
                        current_value
                        and current_value
                        != "[REMOVED]"
                    ):

                        value_cell.text = (
                            "[REMOVED]"
                        )

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
    # STRUCTURED PATIENT IDENTITY
    #
    # Must run BEFORE generic text anonymisation.
    # Otherwise structural labels such as "Geburtsdatum"
    # may be modified before the layout can be recognised.
    # ========================================================

    changes += remove_structured_patient_identity(
        table,
        patient_code
    )

    # ========================================================
    # NORMAL CELL CONTENT
    # ========================================================

    for row in table.rows:

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

                if (
                    row.cells[1]
                    .text
                    .strip()
                ):

                    row.cells[1].text = (
                        "[STAFF_REMOVED]"
                    )

                    changes += 1

        for cell in row.cells:

            for paragraph in cell.paragraphs:

                changes += anonymise_paragraph(
                    paragraph,
                    identifiers,
                    patient_code,
                    staff_names
                )

    # ========================================================
    # STRUCTURED SPECIAL CASES
    # ========================================================

    changes += remove_sensitive_structured_cell(
        table
    )

    return changes


# ============================================================
# REMOVE SIGNATURE BLOCK
# ============================================================

def remove_signature_block(document):

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
# XML HELPER
# ============================================================

def unwrap_xml_element(element):

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
# PARAGRAPH-LEVEL TEXT (RUN-AWARE)
#
# Word splits text into runs (<w:r>/<w:t>) wherever the formatting,
# spell-check state or editing history changes, so a name such as
# "Mueller" can be stored as "Mue" + "ller". Matching has to be
# done on the text of the whole paragraph, and the result has to be
# written back into the individual runs.
# ============================================================

def collect_paragraph_segments(paragraph):
    """
    Return the visible text of a <w:p> in reading order as a list of
    (text_element, text) tuples.

    text_element is the <w:t> element, or None for characters that
    must never be modified (tabs and line breaks, which are included
    only so that words on either side of them are not glued
    together). Paragraphs nested in text boxes are skipped; they are
    visited as paragraphs of their own.
    """

    segments = []

    def walk(element):

        for child in element:

            if not isinstance(child.tag, str):
                continue

            if child.tag in (W_P, W_PPR):
                continue

            if child.tag == W_T:

                segments.append(
                    (
                        child,
                        child.text or ""
                    )
                )

            elif child.tag == W_TAB and element.tag == W_R:

                segments.append(
                    (
                        None,
                        "\t"
                    )
                )

            elif (
                child.tag in (W_BR, W_CR)
                and element.tag == W_R
            ):

                segments.append(
                    (
                        None,
                        "\n"
                    )
                )

            else:

                walk(child)

    walk(paragraph)

    return segments


def get_paragraph_text(paragraph):

    return "".join(
        text
        for _, text in collect_paragraph_segments(
            paragraph
        )
    )


def apply_replacements_to_segments(
    segments,
    replacements
):
    """
    Apply (start, end, replacement) positions, as returned by
    find_replacements(), to the runs of a paragraph.

    The replacement is written into the first run that the match
    touches; the matched characters are removed from every run they
    span. Text outside the matches keeps the formatting of its run.
    """

    offsets = []

    position = 0

    for _, text in segments:

        offsets.append(
            (
                position,
                position + len(text)
            )
        )

        position += len(text)

    new_texts = [
        text
        for _, text in segments
    ]

    # Last match first, so that the positions of earlier matches
    # are not shifted by changes in text length.
    for start, end, replacement in sorted(
        replacements,
        reverse=True
    ):

        replacement_placed = False

        for index, (element, _) in enumerate(segments):

            segment_start, segment_end = offsets[index]

            if (
                element is None
                or segment_end <= start
                or segment_start >= end
            ):
                continue

            local_start = max(start, segment_start) - segment_start
            local_end = min(end, segment_end) - segment_start

            current = new_texts[index]

            insert = "" if replacement_placed else replacement

            new_texts[index] = (
                current[:local_start]
                + insert
                + current[local_end:]
            )

            replacement_placed = True

    changed_elements = 0

    for (element, original), new_text in zip(
        segments,
        new_texts
    ):

        if element is None or new_text == original:
            continue

        element.text = new_text

        if new_text != new_text.strip():

            element.set(
                XML_SPACE,
                "preserve"
            )

        changed_elements += 1

    return changed_elements


def anonymise_paragraph_element(
    paragraph,
    identifiers,
    patient_code,
    staff_names
):
    """
    Anonymise one <w:p> element on the text of the whole
    paragraph. Returns 1 if the paragraph was changed, else 0.
    """

    segments = collect_paragraph_segments(
        paragraph
    )

    text = "".join(
        segment_text
        for _, segment_text in segments
    )

    if not text.strip():
        return 0

    replacements = find_replacements(
        text,
        identifiers,
        patient_code,
        staff_names
    )

    if not replacements:
        return 0

    apply_replacements_to_segments(
        segments,
        replacements
    )

    return 1


# ============================================================
# SANITISE WORD XML
# ============================================================

def sanitise_word_xml(
    data,
    identifiers,
    patient_code,
    staff_names
):

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
    # READABLE TEXT
    # ========================================================

    for paragraph in root.iter(W_P):

        changes += anonymise_paragraph_element(
            paragraph,
            identifiers,
            patient_code,
            staff_names
        )

    # ========================================================
    # COMMENT MARKERS
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
    # ACCEPT INSERTIONS
    # ========================================================

    insertion_nodes = root.xpath(
        "//w:ins | //w:moveTo",
        namespaces=namespace
    )

    for node in reversed(
        insertion_nodes
    ):

        unwrap_xml_element(
            node
        )

        changes += 1

    # ========================================================
    # REMOVE DELETIONS
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
    # REMOVE REVISION METADATA
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
# CORE PROPERTIES
# ============================================================

def sanitise_core_properties_xml(
    data
):

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
# EXTENDED PROPERTIES
# ============================================================

def sanitise_app_properties_xml(
    data
):

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
# CUSTOM PROPERTIES
# ============================================================

def sanitise_custom_properties_xml(
    data
):

    try:

        root = etree.fromstring(
            data
        )

    except etree.XMLSyntaxError:

        return data, 0

    changes = 0

    for property_element in list(root):

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
# EMPTY COMMENT / PEOPLE XML
# ============================================================

def empty_xml_children(
    data
):

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
# FINAL OOXML SANITISATION
# ============================================================

def sanitise_docx_package(
    docx_path,
    identifiers,
    patient_code,
    staff_names
):

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
                    # WORD XML
                    # ========================================

                    if (
                        filename.startswith(
                            "word/"
                        )
                        and filename.endswith(
                            ".xml"
                        )
                    ):

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

                    elif (
                        filename
                        == "docProps/core.xml"
                    ):

                        (
                            data,
                            part_changes
                        ) = sanitise_core_properties_xml(
                            data
                        )

                    elif (
                        filename
                        == "docProps/app.xml"
                    ):

                        (
                            data,
                            part_changes
                        ) = sanitise_app_properties_xml(
                            data
                        )

                    elif (
                        filename
                        == "docProps/custom.xml"
                    ):

                        (
                            data,
                            part_changes
                        ) = sanitise_custom_properties_xml(
                            data
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
# VALIDATION
# ============================================================

def validate_docx_package(
    docx_path,
    identifiers,
    staff_names
):

    issues = []

    sensitive_strings = []

    # Names are checked with the same whole-word variants that are
    # used for removal.
    name_patterns = build_name_patterns(
        frozenset(
            name
            for name in identifiers["names"]
            if name
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

            # Runs are joined without a separator (as Word shows
            # them), otherwise a name that is split across runs
            # would never be found. Paragraphs are separated by
            # a newline.
            readable_text = "\n".join(
                get_paragraph_text(paragraph)
                for paragraph in root.iter(W_P)
            )

            readable_lower = (
                readable_text.lower()
            )

            # ================================================
            # KNOWN IDENTIFIERS
            # ================================================

            for issue_type, value in sensitive_strings:

                if (
                    value.lower()
                    in readable_lower
                ):

                    issues.append(
                        f"{issue_type} remains in "
                        f"{filename}: {value}"
                    )

            # ================================================
            # PATIENT NAME VARIANTS
            # ================================================

            for pattern in name_patterns:

                name_match = pattern.search(
                    readable_text
                )

                if name_match:

                    issues.append(
                        f"PATIENT_NAME remains in "
                        f"{filename}: {name_match.group(0)}"
                    )

            # ================================================
            # RESIDUAL PATIENT-ID-LIKE VALUES
            # ================================================

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

            # ================================================
            # COMMENT MARKERS
            # ================================================

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

            # ================================================
            # TRACKED CHANGES
            # ================================================

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
    patient_staff_names,
    patient_identifiers=None
):

    document = Document(
        input_file
    )

    # ========================================================
    # DISCOVERY BEFORE MODIFICATION
    # ========================================================

    identifiers = find_patient_identifiers(
        document
    )

    # Identifiers found in ANY document of this patient apply to
    # every document of the patient. A document whose Name/DOB
    # table has an unexpected layout is then still cleaned with
    # what the other documents revealed.
    if patient_identifiers:

        merge_identifiers(
            identifiers,
            patient_identifiers
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
    # BODY PARAGRAPHS
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
    # SIGNATURES
    # ========================================================

    changes += remove_signature_block(
        document
    )

    changes += remove_signature_tables(
        document
    )

    # ========================================================
    # CORE PROPERTIES
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
    # SAVE
    # ========================================================

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    document.save(
        output_file
    )

    # ========================================================
    # OOXML SANITISATION
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
    # VALIDATION
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
# CREATE OUTPUT FILENAME
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

        patient_code = get_patient_code(
            patient_folder
        )

        print()
        print("=" * 70)
        print(patient_code)
        print("=" * 70)

        counters = {}

        patient_documents = sorted(
            file
            for file in patient_folder.rglob(
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
        # COLLECT STAFF NAMES AND PATIENT IDENTIFIERS
        # ACROSS ALL DOCUMENTS OF THE PATIENT
        # ====================================================

        patient_staff_names = set()

        patient_identifiers = empty_identifiers()

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

                merge_identifiers(
                    patient_identifiers,
                    find_patient_identifiers(
                        document
                    )
                )

            except Exception as error:

                print(
                    f"Could not inspect "
                    f"{file.name}: "
                    f"{error}"
                )

        # ====================================================
        # SECOND PASS:
        # ANONYMISE
        # ====================================================

        for input_file in patient_documents:

            document_type = get_document_type(
                input_file
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

            # Keep the category subfolder (Empfehlungen, ...) but
            # never any other folder name: it could contain
            # identifying text that the anonymiser never sees.
            relative_parent = (
                input_file.parent
                .relative_to(
                    patient_folder
                )
            )

            (
                output_subfolder,
                dropped_folder_names
            ) = safe_output_subfolder(
                relative_parent
            )

            if dropped_folder_names:

                print(
                    f"    NOTE: {dropped_folder_names} subfolder "
                    f"name(s) not carried over to the output"
                )

            output_file = (
                OUTPUT_DIR
                / patient_code
                / output_subfolder
                / output_name
            )

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
                    patient_staff_names,
                    patient_identifiers
                )

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

                        "OriginalSubfolder":
                            str(relative_parent),

                        "NewFile":
                            output_name,

                        "DocumentType":
                            document_type,

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

            except Exception as error:

                print(
                    f"    ERROR in "
                    f"{input_file.name}: "
                    f"{error}"
                )

                log.append(
                    {
                        "Patient":
                            patient_code,

                        "OriginalFile":
                            input_file.name,

                        "OriginalSubfolder":
                            str(relative_parent),

                        "NewFile":
                            output_name,

                        "DocumentType":
                            document_type,

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
            "OriginalSubfolder",
            "NewFile",
            "DocumentType",
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
    print("ANONYMISATION FINISHED")
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