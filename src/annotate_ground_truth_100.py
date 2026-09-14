from pathlib import Path
import csv
import json
import random
import re
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(
    "/Users/administrator/Documents/GitHub/Master-Thesis"
)

TEXT_DIR = (
    BASE_DIR
    / "data"
    / "extracted"
    / "text"
)

SCHEMA_FILE = (
    BASE_DIR
    / "config"
    / "extraction_schema.json"
)

PILOT_MANIFEST = (
    BASE_DIR
    / "data"
    / "model_outputs"
    / "pilot"
    / "mistral"
    / "pilot_manifest.json"
)

GROUND_TRUTH_DIR = (
    BASE_DIR
    / "data"
    / "ground_truth"
    / "evaluation_100"
)

SAMPLE_MANIFEST = (
    GROUND_TRUTH_DIR
    / "evaluation_sample_manifest.json"
)

ANNOTATION_METADATA_FILE = (
    GROUND_TRUTH_DIR
    / "annotation_metadata.csv"
)

SAMPLE_SIZE = 100
RANDOM_SEED = 42

ELIGIBLE_DOCUMENT_TYPES = {
    "Empfehlungen",
    "Visitendokumentation",
}


# ============================================================
# SCHEMA
# ============================================================

def load_schema():

    if not SCHEMA_FILE.exists():

        raise FileNotFoundError(
            f"Schema file not found:\n{SCHEMA_FILE}"
        )

    with open(
        SCHEMA_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def get_diagnosis_status_options(schema):

    try:

        return (
            schema["properties"]
            ["diagnoses"]
            ["items"]
            ["properties"]
            ["status"]
            ["enum"]
        )

    except KeyError:

        raise ValueError(
            "Could not find diagnosis status enum "
            "in extraction_schema.json"
        )


def create_empty_annotation(
    schema,
    document_id,
    document_type
):

    annotation = {}

    properties = schema.get(
        "properties",
        {}
    )

    for field_name, field_definition in properties.items():

        if field_name == "document_id":

            annotation[field_name] = document_id

        elif field_name == "document_type":

            annotation[field_name] = document_type

        elif field_definition.get("type") == "array":

            annotation[field_name] = []

        elif field_definition.get("type") == "string":

            annotation[field_name] = ""

        else:

            annotation[field_name] = None

    return annotation


# ============================================================
# FILE HELPERS
# ============================================================

def get_patient_id(file_path):

    match = re.search(
        r"Patient_\d{4}",
        str(file_path)
    )

    if match:

        return match.group()

    return "UNKNOWN"


def get_document_type(file_path):

    filename = file_path.name.lower()

    if "visitendokumentation" in filename:

        return "Visitendokumentation"

    if "empfehlungen" in filename:

        return "Empfehlungen"

    if "medikationsplan" in filename:

        return "Medikationsplan"

    return "Unknown"


def get_document_id(file_path):

    return file_path.stem


# ============================================================
# PILOT EXCLUSION
# ============================================================

def load_pilot_document_ids():

    """
    The 10 pilot documents were used for prompt/schema
    development and must not be part of the final held-out
    evaluation sample.
    """

    pilot_ids = set()

    if not PILOT_MANIFEST.exists():

        print(
            "WARNING: Pilot manifest not found."
        )

        print(
            "No pilot documents will be excluded."
        )

        return pilot_ids

    with open(
        PILOT_MANIFEST,
        "r",
        encoding="utf-8"
    ) as f:

        manifest = json.load(f)

    for result in manifest.get(
        "results",
        []
    ):

        document_id = result.get(
            "document_id"
        )

        if document_id:

            pilot_ids.add(
                document_id
            )

    return pilot_ids


# ============================================================
# BUILD / LOAD 100-DOCUMENT SAMPLE
# ============================================================

def find_eligible_documents():

    pilot_ids = load_pilot_document_ids()

    eligible = []

    for file_path in sorted(
        TEXT_DIR.rglob("*.txt")
    ):

        document_type = get_document_type(
            file_path
        )

        if document_type not in ELIGIBLE_DOCUMENT_TYPES:

            continue

        document_id = get_document_id(
            file_path
        )

        if document_id in pilot_ids:

            continue

        eligible.append(
            file_path
        )

    return eligible


def save_sample_manifest(sample_files):

    counts = {}

    documents = []

    for file_path in sample_files:

        document_type = get_document_type(
            file_path
        )

        counts[document_type] = (
            counts.get(
                document_type,
                0
            )
            + 1
        )

        documents.append(
            {
                "patient_id":
                    get_patient_id(file_path),

                "document_id":
                    get_document_id(file_path),

                "document_type":
                    document_type,

                "source_file":
                    str(file_path),
            }
        )

    manifest = {
        "purpose":
            "Held-out manual ground-truth evaluation sample",

        "sample_size":
            len(sample_files),

        "random_seed":
            RANDOM_SEED,

        "pilot_documents_excluded":
            True,

        "medication_plans_excluded":
            True,

        "eligible_document_types":
            sorted(
                ELIGIBLE_DOCUMENT_TYPES
            ),

        "sampling_method":
            (
                "Simple random sample across all eligible "
                "documents; natural document-type proportions "
                "preserved."
            ),

        "created":
            datetime.now().isoformat(),

        "document_type_counts":
            counts,

        "documents":
            documents,
    }

    with open(
        SAMPLE_MANIFEST,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            manifest,
            f,
            ensure_ascii=False,
            indent=2
        )


def create_sample():

    eligible = find_eligible_documents()

    if len(eligible) < SAMPLE_SIZE:

        raise ValueError(
            f"Only {len(eligible)} eligible documents "
            f"were found, but SAMPLE_SIZE={SAMPLE_SIZE}."
        )

    rng = random.Random(
        RANDOM_SEED
    )

    sample_files = rng.sample(
        eligible,
        SAMPLE_SIZE
    )

    # Stable annotation order after random selection.
    sample_files = sorted(
        sample_files,
        key=lambda p: p.name
    )

    save_sample_manifest(
        sample_files
    )

    return sample_files


def load_existing_sample():

    with open(
        SAMPLE_MANIFEST,
        "r",
        encoding="utf-8"
    ) as f:

        manifest = json.load(f)

    sample_files = []

    missing_files = []

    for item in manifest.get(
        "documents",
        []
    ):

        source_file = Path(
            item["source_file"]
        )

        if source_file.exists():

            sample_files.append(
                source_file
            )

        else:

            missing_files.append(
                source_file
            )

    if missing_files:

        print()
        print(
            "WARNING: Some files from the saved sample "
            "manifest are missing:"
        )

        for path in missing_files:

            print(
                f"  {path}"
            )

    return sample_files


def load_or_create_sample():

    GROUND_TRUTH_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if SAMPLE_MANIFEST.exists():

        print()
        print(
            "Using existing evaluation sample."
        )

        print(
            f"Manifest:\n{SAMPLE_MANIFEST}"
        )

        return load_existing_sample()

    print()
    print(
        "Creating new reproducible "
        "100-document evaluation sample."
    )

    sample_files = create_sample()

    print(
        f"Sample manifest saved:\n"
        f"{SAMPLE_MANIFEST}"
    )

    return sample_files


# ============================================================
# INPUT HELPERS
# ============================================================

def ask_text(prompt):

    return input(
        prompt
    ).strip()


def ask_keepable_text(
    prompt,
    current_value
):

    value = input(
        f"{prompt} [{current_value}]: "
    ).strip()

    if value == "":

        return current_value

    return value


def ask_yes_no(
    prompt,
    default=True
):

    suffix = (
        "[Y/n]"
        if default
        else "[y/N]"
    )

    choice = input(
        f"{prompt} {suffix}: "
    ).strip().lower()

    if choice == "":

        return default

    return choice == "y"


# ============================================================
# DIAGNOSIS STATUS
# ============================================================

def ask_status(
    status_options,
    current_value=None
):

    while True:

        print()
        print(
            "Diagnosis status:"
        )

        for index, status in enumerate(
            status_options,
            start=1
        ):

            current_marker = ""

            if status == current_value:

                current_marker = "  <-- current"

            print(
                f"{index} = "
                f"{status}"
                f"{current_marker}"
            )

        if current_value is not None:

            print(
                "Press ENTER to keep current status."
            )

        choice = input(
            "Select status: "
        ).strip()

        if (
            choice == ""
            and current_value is not None
        ):

            return current_value

        try:

            choice_index = (
                int(choice)
                - 1
            )

        except ValueError:

            print(
                "Invalid choice."
            )

            continue

        if (
            0
            <= choice_index
            < len(status_options)
        ):

            return status_options[
                choice_index
            ]

        print(
            "Invalid choice."
        )


# ============================================================
# ANNOTATION GUIDELINES
# ============================================================

def print_annotation_guidelines():

    print()
    print("=" * 80)
    print(
        "GROUND-TRUTH ANNOTATION RULES"
    )
    print("=" * 80)

    print(
        """
1. Annotate only information supported by the source document.

2. One independently evaluable clinical concept per object.

3. Normalize diagnoses, comorbidities and recommendations into English.

4. Evidence must remain the original German wording.

5. Preserve uncertainty:
   - V.a. / suspected -> suspected
   - excluded findings -> excluded
   - historical diagnoses -> historical

6. Do NOT infer a diagnosis solely because it is medically plausible.

7. Do NOT expand an ambiguous abbreviation unless its meaning is
   established by the source document itself.

8. Obvious spelling errors may be normalized only when the intended
   meaning is unambiguous.

9. Do NOT include the standard telemedicine disclaimer as a clinical
   recommendation.

10. ICD-10-GM:
    - independently verify the code;
    - use an actual terminal/specific code supported by the text;
    - do not use wildcard codes such as K72.x;
    - do not invent missing specificity.

11. OPS:
    - independently verify the code;
    - assign a terminal OPS code only if the document contains enough
      information to support that level of coding;
    - do NOT guess procedure details;
    - if a procedure clearly occurred but the documentation is
      insufficient for a defensible OPS code, leave it out of the
      'ops' array and record that fact in the separate annotation
      metadata.

12. Empty OPS has TWO possible meanings:
    A) no relevant procedure was documented;
    B) procedures were documented, but the information was
       insufficient to assign a defensible terminal OPS code.
    The metadata question at the end distinguishes these situations.
"""
    )

    print("=" * 80)


# ============================================================
# GENERIC LIST DISPLAY
# ============================================================

def show_items(
    title,
    items,
    formatter
):

    print()
    print("-" * 60)
    print(title)
    print("-" * 60)

    if not items:

        print(
            "(none)"
        )

        return

    for index, item in enumerate(
        items,
        start=1
    ):

        print()
        print(
            f"{index}. "
            f"{formatter(item)}"
        )


# ============================================================
# DIAGNOSES
# ============================================================

def create_diagnosis(
    status_options
):

    text = ask_text(
        "Diagnosis: "
    )

    if not text:

        return None

    status = ask_status(
        status_options
    )

    evidence = ask_text(
        "Evidence from source: "
    )

    return {
        "text":
            text,

        "status":
            status,

        "evidence":
            evidence,
    }


def edit_diagnosis(
    item,
    status_options
):

    item["text"] = ask_keepable_text(
        "Diagnosis",
        item["text"]
    )

    item["status"] = ask_status(
        status_options,
        current_value=item["status"]
    )

    item["evidence"] = ask_keepable_text(
        "Evidence",
        item["evidence"]
    )


def diagnosis_formatter(item):

    return (
        f'{item["text"]} '
        f'[{item["status"]}]\n'
        f'   Evidence: '
        f'{item["evidence"]}'
    )


def manage_diagnoses(
    items,
    status_options
):

    while True:

        show_items(
            "DIAGNOSES",
            items,
            diagnosis_formatter
        )

        print()
        print(
            "[a] Add"
        )
        print(
            "[e] Edit"
        )
        print(
            "[d] Delete"
        )
        print(
            "[b] Back"
        )

        choice = ask_text(
            "Choice: "
        ).lower()

        if choice == "a":

            new_item = create_diagnosis(
                status_options
            )

            if new_item:

                items.append(
                    new_item
                )

        elif choice == "e":

            edit_list_item(
                items,
                lambda item:
                    edit_diagnosis(
                        item,
                        status_options
                    )
            )

        elif choice == "d":

            delete_list_item(
                items
            )

        elif choice == "b":

            return


def annotate_diagnoses(
    status_options
):

    items = []

    print()
    print("=" * 60)
    print("DIAGNOSES")
    print("=" * 60)

    print(
        "One diagnosis per object."
    )
    print(
        "Normalized English diagnosis; "
        "original German evidence."
    )
    print(
        "Press ENTER without text when finished."
    )

    while True:

        item = create_diagnosis(
            status_options
        )

        if item is None:

            break

        items.append(
            item
        )

    return items


# ============================================================
# SIMPLE TEXT + EVIDENCE CATEGORIES
# ============================================================

def create_text_evidence_item(
    label,
    key
):

    text = ask_text(
        f"{label}: "
    )

    if not text:

        return None

    evidence = ask_text(
        "Evidence from source: "
    )

    return {
        key:
            text,

        "evidence":
            evidence,
    }


def edit_text_evidence_item(
    item,
    label,
    key
):

    item[key] = ask_keepable_text(
        label,
        item[key]
    )

    item["evidence"] = ask_keepable_text(
        "Evidence",
        item["evidence"]
    )


def make_text_evidence_formatter(
    key
):

    def formatter(item):

        return (
            f'{item[key]}\n'
            f'   Evidence: '
            f'{item["evidence"]}'
        )

    return formatter


def manage_text_evidence_items(
    title,
    items,
    label,
    key
):

    formatter = (
        make_text_evidence_formatter(
            key
        )
    )

    while True:

        show_items(
            title,
            items,
            formatter
        )

        print()
        print(
            "[a] Add"
        )
        print(
            "[e] Edit"
        )
        print(
            "[d] Delete"
        )
        print(
            "[b] Back"
        )

        choice = ask_text(
            "Choice: "
        ).lower()

        if choice == "a":

            item = (
                create_text_evidence_item(
                    label,
                    key
                )
            )

            if item:

                items.append(
                    item
                )

        elif choice == "e":

            edit_list_item(
                items,
                lambda item:
                    edit_text_evidence_item(
                        item,
                        label,
                        key
                    )
            )

        elif choice == "d":

            delete_list_item(
                items
            )

        elif choice == "b":

            return


def annotate_comorbidities():

    items = []

    print()
    print("=" * 60)
    print(
        "COMORBIDITIES"
    )
    print("=" * 60)

    print(
        "One comorbidity per object."
    )
    print(
        "Do not expand ambiguous abbreviations "
        "based only on clinical plausibility."
    )
    print(
        "Press ENTER without text when finished."
    )

    while True:

        item = create_text_evidence_item(
            "Comorbidity",
            "text"
        )

        if item is None:

            break

        items.append(
            item
        )

    return items


def annotate_recommendations():

    items = []

    print()
    print("=" * 60)
    print(
        "RECOMMENDATIONS"
    )
    print("=" * 60)

    print(
        "One independently evaluable clinical "
        "recommendation per object."
    )
    print(
        "Do NOT include the standard "
        "telemedicine disclaimer."
    )
    print(
        "Press ENTER without text when finished."
    )

    while True:

        item = create_text_evidence_item(
            "Recommendation",
            "recommendation"
        )

        if item is None:

            break

        items.append(
            item
        )

    return items


# ============================================================
# ICD / OPS
# ============================================================

def create_code_item(
    coding_system
):

    code = ask_text(
        f"{coding_system} code: "
    )

    if not code:

        return None

    if (
        coding_system == "ICD-10-GM"
        and "x" in code.lower()
    ):

        print()
        print(
            "WARNING: Wildcard / partial ICD codes "
            "must not be used in ground truth."
        )

        print(
            "Verify a supported terminal code or "
            "leave this diagnosis uncoded."
        )

        keep = ask_yes_no(
            "Keep this code anyway?",
            default=False
        )

        if not keep:

            return None

    description = ask_text(
        "Description: "
    )

    evidence = ask_text(
        "Evidence from source: "
    )

    return {
        "code":
            code,

        "description":
            description,

        "evidence":
            evidence,
    }


def edit_code_item(
    item,
    coding_system
):

    item["code"] = ask_keepable_text(
        f"{coding_system} code",
        item["code"]
    )

    item["description"] = ask_keepable_text(
        "Description",
        item["description"]
    )

    item["evidence"] = ask_keepable_text(
        "Evidence",
        item["evidence"]
    )


def code_formatter(item):

    return (
        f'{item["code"]} — '
        f'{item["description"]}\n'
        f'   Evidence: '
        f'{item["evidence"]}'
    )


def manage_codes(
    title,
    items
):

    while True:

        show_items(
            title,
            items,
            code_formatter
        )

        print()
        print(
            "[a] Add"
        )
        print(
            "[e] Edit"
        )
        print(
            "[d] Delete"
        )
        print(
            "[b] Back"
        )

        choice = ask_text(
            "Choice: "
        ).lower()

        if choice == "a":

            item = create_code_item(
                title
            )

            if item:

                items.append(
                    item
                )

        elif choice == "e":

            edit_list_item(
                items,
                lambda item:
                    edit_code_item(
                        item,
                        title
                    )
            )

        elif choice == "d":

            delete_list_item(
                items
            )

        elif choice == "b":

            return


def annotate_icd():

    items = []

    print()
    print("=" * 60)
    print(
        "ICD-10-GM"
    )
    print("=" * 60)

    print(
        "Enter only independently verified codes."
    )

    print(
        "No wildcard codes and no unsupported specificity."
    )

    print(
        "Press ENTER without a code when finished."
    )

    while True:

        item = create_code_item(
            "ICD-10-GM"
        )

        if item is None:

            break

        items.append(
            item
        )

    return items


def annotate_ops():

    items = []

    print()
    print("=" * 60)
    print(
        "OPS"
    )
    print("=" * 60)

    print(
        "Enter only independently verified terminal OPS codes."
    )

    print(
        "Do NOT guess missing procedural details."
    )

    print(
        "If a procedure is documented but there is not enough "
        "information to assign a defensible terminal OPS code, "
        "do NOT add a placeholder code."
    )

    print(
        "This will be recorded separately in the "
        "annotation metadata."
    )

    print(
        "Press ENTER without a code when finished."
    )

    while True:

        item = create_code_item(
            "OPS"
        )

        if item is None:

            break

        items.append(
            item
        )

    return items


# ============================================================
# EDIT / DELETE HELPERS
# ============================================================

def select_item_index(
    items,
    action
):

    if not items:

        print(
            "No items available."
        )

        return None

    raw = ask_text(
        f"Item number to {action}: "
    )

    try:

        index = int(raw) - 1

    except ValueError:

        print(
            "Invalid number."
        )

        return None

    if not (
        0
        <= index
        < len(items)
    ):

        print(
            "Invalid item number."
        )

        return None

    return index


def edit_list_item(
    items,
    editor
):

    index = select_item_index(
        items,
        "edit"
    )

    if index is None:

        return

    editor(
        items[index]
    )


def delete_list_item(
    items
):

    index = select_item_index(
        items,
        "delete"
    )

    if index is None:

        return

    print()
    print(
        "Selected:"
    )
    print(
        json.dumps(
            items[index],
            ensure_ascii=False,
            indent=2
        )
    )

    if ask_yes_no(
        "Delete this item?",
        default=False
    ):

        del items[index]


# ============================================================
# VALIDATION
# ============================================================

def validate_annotation(
    annotation,
    schema
):

    issues = []

    required_fields = schema.get(
        "required",
        []
    )

    for field in required_fields:

        if field not in annotation:

            issues.append(
                f"Missing required field: {field}"
            )

    properties = schema.get(
        "properties",
        {}
    )

    for field_name, field_definition in properties.items():

        if field_name not in annotation:

            continue

        expected_type = (
            field_definition.get(
                "type"
            )
        )

        value = annotation[
            field_name
        ]

        if (
            expected_type == "array"
            and not isinstance(
                value,
                list
            )
        ):

            issues.append(
                f"{field_name} must be an array"
            )

        elif (
            expected_type == "string"
            and not isinstance(
                value,
                str
            )
        ):

            issues.append(
                f"{field_name} must be a string"
            )

    # Additional ground-truth checks.

    for item in annotation.get(
        "icd10_gm",
        []
    ):

        code = item.get(
            "code",
            ""
        )

        if "x" in code.lower():

            issues.append(
                f"Possible wildcard ICD code: {code}"
            )

    for item in annotation.get(
        "ops",
        []
    ):

        if not item.get(
            "code",
            ""
        ).strip():

            issues.append(
                "OPS entry contains an empty code."
            )

    return issues


# ============================================================
# OPS DOCUMENTATION SUFFICIENCY METADATA
# ============================================================

def ask_procedure_documentation_status():

    while True:

        print()
        print("=" * 60)
        print(
            "PROCEDURE / OPS DOCUMENTATION STATUS"
        )
        print("=" * 60)

        print(
            "This is stored separately from the "
            "ground-truth JSON."
        )

        print()
        print(
            "1 = No relevant procedure documented"
        )

        print(
            "2 = Procedure(s) documented, but information "
            "is insufficient for a defensible terminal OPS code"
        )

        print(
            "3 = Procedure(s) documented and terminal "
            "OPS code(s) could be assigned"
        )

        print(
            "4 = Mixed: some procedures could be coded, "
            "others lacked sufficient detail"
        )

        choice = ask_text(
            "Select status: "
        )

        mapping = {
            "1":
                "no_relevant_procedure_documented",

            "2":
                "procedure_present_insufficient_detail",

            "3":
                "terminal_ops_assignable",

            "4":
                "mixed_codable_and_insufficient",
        }

        if choice in mapping:

            status = mapping[
                choice
            ]

            break

        print(
            "Invalid choice."
        )

    notes = ask_text(
        "Optional OPS/documentation note: "
    )

    return status, notes


# ============================================================
# METADATA CSV
# ============================================================

def load_existing_metadata():

    metadata = {}

    if not ANNOTATION_METADATA_FILE.exists():

        return metadata

    with open(
        ANNOTATION_METADATA_FILE,
        "r",
        encoding="utf-8",
        newline=""
    ) as f:

        reader = csv.DictReader(
            f
        )

        for row in reader:

            document_id = row.get(
                "document_id"
            )

            if document_id:

                metadata[
                    document_id
                ] = row

    return metadata


def save_metadata_record(
    document_id,
    patient_id,
    document_type,
    procedure_status,
    procedure_notes
):

    metadata = load_existing_metadata()

    metadata[
        document_id
    ] = {
        "document_id":
            document_id,

        "patient_id":
            patient_id,

        "document_type":
            document_type,

        "procedure_documentation_status":
            procedure_status,

        "procedure_documentation_notes":
            procedure_notes,

        "updated":
            datetime.now().isoformat(),
    }

    fieldnames = [
        "document_id",
        "patient_id",
        "document_type",
        "procedure_documentation_status",
        "procedure_documentation_notes",
        "updated",
    ]

    with open(
        ANNOTATION_METADATA_FILE,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for key in sorted(
            metadata
        ):

            writer.writerow(
                metadata[key]
            )


# ============================================================
# EDIT COMPLETE ANNOTATION
# ============================================================

def edit_annotation_menu(
    annotation,
    status_options
):

    while True:

        print()
        print("=" * 60)
        print(
            "EDIT ANNOTATION"
        )
        print("=" * 60)

        print(
            "1 = Diagnoses"
        )
        print(
            "2 = Comorbidities"
        )
        print(
            "3 = Recommendations"
        )
        print(
            "4 = ICD-10-GM"
        )
        print(
            "5 = OPS"
        )
        print(
            "6 = Return to preview"
        )

        choice = ask_text(
            "Choice: "
        )

        if choice == "1":

            manage_diagnoses(
                annotation["diagnoses"],
                status_options
            )

        elif choice == "2":

            manage_text_evidence_items(
                "COMORBIDITIES",
                annotation["comorbidities"],
                "Comorbidity",
                "text"
            )

        elif choice == "3":

            manage_text_evidence_items(
                "RECOMMENDATIONS",
                annotation["recommendations"],
                "Recommendation",
                "recommendation"
            )

        elif choice == "4":

            manage_codes(
                "ICD-10-GM",
                annotation["icd10_gm"]
            )

        elif choice == "5":

            manage_codes(
                "OPS",
                annotation["ops"]
            )

        elif choice == "6":

            return


# ============================================================
# LOAD EXISTING ANNOTATION
# ============================================================

def load_annotation(
    output_file
):

    with open(
        output_file,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


# ============================================================
# ANNOTATE ONE DOCUMENT
# ============================================================

def annotate_document(
    text_file,
    schema,
    status_options
):

    document_id = (
        text_file.stem
    )

    document_type = (
        get_document_type(
            text_file
        )
    )

    patient_id = (
        get_patient_id(
            text_file
        )
    )

    output_dir = (
        GROUND_TRUTH_DIR
        / patient_id
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        output_dir
        / f"{document_id}.json"
    )

    # ========================================================
    # SOURCE DOCUMENT
    # ========================================================

    document_text = (
        text_file.read_text(
            encoding="utf-8"
        )
    )

    print()
    print("=" * 80)
    print(
        document_id
    )
    print(
        f"Document type: {document_type}"
    )
    print("=" * 80)
    print()
    print(
        document_text
    )
    print()
    print("=" * 80)

    # ========================================================
    # EXISTING ANNOTATION
    # ========================================================

    if output_file.exists():

        print()
        print(
            f"Already annotated:\n"
            f"{output_file}"
        )

        print()
        print(
            "1 = Keep existing annotation and skip"
        )
        print(
            "2 = Open and edit existing annotation"
        )
        print(
            "3 = Restart annotation from scratch"
        )

        choice = ask_text(
            "Choice [1]: "
        )

        if choice == "":

            choice = "1"

        if choice == "1":

            return False

        elif choice == "2":

            ground_truth = load_annotation(
                output_file
            )

        elif choice == "3":

            ground_truth = create_empty_annotation(
                schema,
                document_id,
                document_type
            )

        else:

            print(
                "Invalid choice; skipping."
            )

            return False

    else:

        ground_truth = create_empty_annotation(
            schema,
            document_id,
            document_type
        )

    # ========================================================
    # NEW ANNOTATION
    # ========================================================

    if not output_file.exists() or choice == "3":

        if "diagnoses" in ground_truth:

            ground_truth[
                "diagnoses"
            ] = annotate_diagnoses(
                status_options
            )

        if "comorbidities" in ground_truth:

            ground_truth[
                "comorbidities"
            ] = annotate_comorbidities()

        if "recommendations" in ground_truth:

            ground_truth[
                "recommendations"
            ] = annotate_recommendations()

        if "icd10_gm" in ground_truth:

            ground_truth[
                "icd10_gm"
            ] = annotate_icd()

        if "ops" in ground_truth:

            ground_truth[
                "ops"
            ] = annotate_ops()

    # ========================================================
    # PREVIEW / EDIT LOOP
    # ========================================================

    while True:

        validation_issues = validate_annotation(
            ground_truth,
            schema
        )

        print()
        print("=" * 80)
        print(
            "ANNOTATION PREVIEW"
        )
        print("=" * 80)

        print(
            json.dumps(
                ground_truth,
                ensure_ascii=False,
                indent=2
            )
        )

        if validation_issues:

            print()
            print(
                "VALIDATION WARNINGS:"
            )

            for issue in validation_issues:

                print(
                    f"  - {issue}"
                )

        print()
        print(
            "1 = Save"
        )
        print(
            "2 = Edit annotation"
        )
        print(
            "3 = Discard / do not save"
        )

        action = ask_text(
            "Choice [1]: "
        )

        if action == "":

            action = "1"

        if action == "2":

            edit_annotation_menu(
                ground_truth,
                status_options
            )

            continue

        if action == "3":

            print(
                "Annotation discarded."
            )

            return False

        if action != "1":

            print(
                "Invalid choice."
            )

            continue

        # Prevent accidental saving when clear
        # validation problems remain.

        if validation_issues:

            proceed = ask_yes_no(
                "Validation warnings remain. Save anyway?",
                default=False
            )

            if not proceed:

                continue

        break

    # ========================================================
    # PROCEDURE / OPS SUFFICIENCY METADATA
    # ========================================================

    procedure_status, procedure_notes = (
        ask_procedure_documentation_status()
    )

    # Basic consistency warning.

    if (
        ground_truth.get("ops")
        and procedure_status
        == "no_relevant_procedure_documented"
    ):

        print()
        print(
            "WARNING: OPS codes were entered, but metadata "
            "says no relevant procedure was documented."
        )

        confirm = ask_yes_no(
            "Keep this combination?",
            default=False
        )

        if not confirm:

            procedure_status, procedure_notes = (
                ask_procedure_documentation_status()
            )

    # ========================================================
    # SAVE GROUND TRUTH
    # ========================================================

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            ground_truth,
            f,
            ensure_ascii=False,
            indent=2
        )

    save_metadata_record(
        document_id=document_id,
        patient_id=patient_id,
        document_type=document_type,
        procedure_status=procedure_status,
        procedure_notes=procedure_notes
    )

    print()
    print(
        f"Saved annotation:\n"
        f"{output_file}"
    )

    print()
    print(
        f"Updated metadata:\n"
        f"{ANNOTATION_METADATA_FILE}"
    )

    return True


# ============================================================
# PROGRESS
# ============================================================

def count_saved_annotations(
    sample_files
):

    count = 0

    for file_path in sample_files:

        patient_id = get_patient_id(
            file_path
        )

        document_id = get_document_id(
            file_path
        )

        output_file = (
            GROUND_TRUTH_DIR
            / patient_id
            / f"{document_id}.json"
        )

        if output_file.exists():

            count += 1

    return count


def print_sample_summary(
    sample_files
):

    counts = {}

    for file_path in sample_files:

        document_type = (
            get_document_type(
                file_path
            )
        )

        counts[
            document_type
        ] = (
            counts.get(
                document_type,
                0
            )
            + 1
        )

    print()
    print("=" * 80)
    print(
        "EVALUATION SAMPLE"
    )
    print("=" * 80)

    print(
        f"Documents: {len(sample_files)}"
    )

    for document_type in sorted(
        counts
    ):

        print(
            f"{document_type}: "
            f"{counts[document_type]}"
        )

    saved = count_saved_annotations(
        sample_files
    )

    print()
    print(
        f"Already annotated: "
        f"{saved}/{len(sample_files)}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    schema = load_schema()

    status_options = (
        get_diagnosis_status_options(
            schema
        )
    )

    GROUND_TRUTH_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    sample_files = (
        load_or_create_sample()
    )

    print_annotation_guidelines()

    print_sample_summary(
        sample_files
    )

    annotated_this_session = 0

    for index, text_file in enumerate(
        sample_files,
        start=1
    ):

        print()
        print("#" * 80)
        print(
            f"[{index}/{len(sample_files)}]"
        )
        print("#" * 80)

        result = annotate_document(
            text_file,
            schema,
            status_options
        )

        if result:

            annotated_this_session += 1

        if index < len(
            sample_files
        ):

            print()

            continue_choice = input(
                "Continue to next document? "
                "[Y/n]: "
            ).strip().lower()

            if continue_choice == "n":

                break

    total_saved = (
        count_saved_annotations(
            sample_files
        )
    )

    print()
    print("=" * 80)
    print(
        "ANNOTATION SESSION FINISHED"
    )
    print("=" * 80)

    print(
        f"Annotations saved/updated "
        f"this session: "
        f"{annotated_this_session}"
    )

    print(
        f"Total evaluation annotations: "
        f"{total_saved}/"
        f"{len(sample_files)}"
    )

    print()
    print(
        f"Ground truth folder:\n"
        f"{GROUND_TRUTH_DIR}"
    )

    print()
    print(
        f"Sample manifest:\n"
        f"{SAMPLE_MANIFEST}"
    )

    print()
    print(
        f"Annotation metadata:\n"
        f"{ANNOTATION_METADATA_FILE}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
