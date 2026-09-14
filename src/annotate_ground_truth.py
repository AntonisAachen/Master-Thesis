from pathlib import Path
import json
import re


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

GROUND_TRUTH_DIR = (
    BASE_DIR
    / "data"
    / "ground_truth"
    / "pilot"
)

PILOT_MANIFEST = (
    BASE_DIR
    / "data"
    / "model_outputs"
    / "pilot"
    / "mistral"
    / "pilot_manifest.json"
)

SCHEMA_FILE = (
    BASE_DIR
    / "config"
    / "extraction_schema.json"
)


# ============================================================
# SCHEMA
# ============================================================

def load_schema():
    """Load the same JSON Schema used by the model."""

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
    """Read allowed diagnosis.status values from the schema."""

    try:
        return (
            schema["properties"]
            ["diagnoses"]
            ["items"]
            ["properties"]
            ["status"]
            ["enum"]
        )
    except KeyError as exc:
        raise ValueError(
            "Could not find diagnosis status enum "
            "in extraction_schema.json"
        ) from exc


def create_empty_annotation(schema, document_id, document_type):
    """Create an empty annotation using top-level schema fields."""

    annotation = {}
    properties = schema.get("properties", {})

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
# HELPERS
# ============================================================

def get_patient_id(file_path):
    match = re.search(r"Patient_\d{4}", str(file_path))
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


def load_pilot_files():
    """Load exactly the documents used in the current Mistral pilot."""

    if not PILOT_MANIFEST.exists():
        raise FileNotFoundError(
            f"Pilot manifest not found:\n{PILOT_MANIFEST}"
        )

    with open(
        PILOT_MANIFEST,
        "r",
        encoding="utf-8"
    ) as f:
        manifest = json.load(f)

    files = []

    for result in manifest["results"]:
        source_file = result.get("source_file")
        if not source_file:
            continue

        path = Path(source_file)
        if path.exists():
            files.append(path)

    return files


def ask_text(prompt, allow_blank=True):
    """Read a text value from the terminal."""

    while True:
        value = input(prompt).strip()
        if value or allow_blank:
            return value
        print("This field cannot be empty.")


def ask_yes_no(prompt, default=True):
    """Ask a yes/no question and return True/False."""

    suffix = " [Y/n]: " if default else " [y/N]: "

    while True:
        value = input(prompt + suffix).strip().lower()

        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False

        print("Please enter y or n.")


def ask_number(prompt, minimum, maximum):
    """Ask for an integer within an inclusive range."""

    while True:
        value = input(prompt).strip()

        try:
            number = int(value)
        except ValueError:
            print("Please enter a number.")
            continue

        if minimum <= number <= maximum:
            return number

        print(f"Enter a number from {minimum} to {maximum}.")


# ============================================================
# DIAGNOSIS STATUS
# ============================================================

def ask_status(status_options, current=None):
    """Select diagnosis status from schema-defined values."""

    while True:
        print()
        print("Diagnosis status:")

        for index, status in enumerate(status_options, start=1):
            current_marker = "  <-- current" if status == current else ""
            print(f"{index} = {status}{current_marker}")

        prompt = "Select status"
        if current is not None:
            prompt += " (ENTER = keep current)"
        prompt += ": "

        choice = input(prompt).strip()

        if current is not None and not choice:
            return current

        try:
            choice_index = int(choice) - 1
        except ValueError:
            print("Invalid choice.")
            continue

        if 0 <= choice_index < len(status_options):
            return status_options[choice_index]

        print("Invalid choice.")


# ============================================================
# ENTRY CREATION / EDITING
# ============================================================

def create_diagnosis(status_options):
    text = ask_text("Diagnosis: ", allow_blank=False)
    status = ask_status(status_options)
    evidence = ask_text("Evidence from source: ", allow_blank=False)

    return {
        "text": text,
        "status": status,
        "evidence": evidence,
    }


def edit_diagnosis(entry, status_options):
    print("Press ENTER to keep the current value.")

    text = input(f"Diagnosis [{entry['text']}]: ").strip()
    if text:
        entry["text"] = text

    entry["status"] = ask_status(
        status_options,
        current=entry["status"]
    )

    evidence = input(
        f"Evidence [{entry['evidence']}]: "
    ).strip()
    if evidence:
        entry["evidence"] = evidence


def create_comorbidity():
    return {
        "text": ask_text(
            "Comorbidity: ",
            allow_blank=False
        ),
        "evidence": ask_text(
            "Evidence from source: ",
            allow_blank=False
        ),
    }


def edit_comorbidity(entry):
    print("Press ENTER to keep the current value.")

    text = input(f"Comorbidity [{entry['text']}]: ").strip()
    if text:
        entry["text"] = text

    evidence = input(
        f"Evidence [{entry['evidence']}]: "
    ).strip()
    if evidence:
        entry["evidence"] = evidence


def create_recommendation():
    return {
        "recommendation": ask_text(
            "Recommendation: ",
            allow_blank=False
        ),
        "evidence": ask_text(
            "Evidence from source: ",
            allow_blank=False
        ),
    }


def edit_recommendation(entry):
    print("Press ENTER to keep the current value.")

    text = input(
        f"Recommendation [{entry['recommendation']}]: "
    ).strip()
    if text:
        entry["recommendation"] = text

    evidence = input(
        f"Evidence [{entry['evidence']}]: "
    ).strip()
    if evidence:
        entry["evidence"] = evidence


def create_code_entry(label):
    return {
        "code": ask_text(
            f"{label} code: ",
            allow_blank=False
        ),
        "description": ask_text(
            "Description: ",
            allow_blank=False
        ),
        "evidence": ask_text(
            "Evidence from source: ",
            allow_blank=False
        ),
    }


def edit_code_entry(entry, label):
    print("Press ENTER to keep the current value.")

    code = input(f"{label} code [{entry['code']}]: ").strip()
    if code:
        entry["code"] = code

    description = input(
        f"Description [{entry['description']}]: "
    ).strip()
    if description:
        entry["description"] = description

    evidence = input(
        f"Evidence [{entry['evidence']}]: "
    ).strip()
    if evidence:
        entry["evidence"] = evidence


# ============================================================
# GENERIC CATEGORY EDITOR
# ============================================================

def print_entries(entries, category):
    print()
    print("-" * 60)

    if not entries:
        print("No entries.")
        print("-" * 60)
        return

    for index, entry in enumerate(entries, start=1):
        print(f"{index}.")

        if category == "diagnoses":
            print(f"   Diagnosis: {entry['text']}")
            print(f"   Status: {entry['status']}")
        elif category == "comorbidities":
            print(f"   Comorbidity: {entry['text']}")
        elif category == "recommendations":
            print(f"   Recommendation: {entry['recommendation']}")
        elif category in {"icd10_gm", "ops"}:
            print(f"   Code: {entry['code']}")
            print(f"   Description: {entry['description']}")

        print(f"   Evidence: {entry['evidence']}")
        print()

    print("-" * 60)


def category_editor(
    entries,
    category,
    title,
    create_func,
    edit_func
):
    """Interactive add/edit/delete menu for one annotation category."""

    while True:
        print()
        print("=" * 60)
        print(title)
        print("=" * 60)

        print_entries(entries, category)

        print("a = add")
        print("e = edit")
        print("d = delete")
        print("b = back")

        choice = input("Choice: ").strip().lower()

        if choice == "a":
            entries.append(create_func())
            continue

        if choice == "e":
            if not entries:
                print("There is nothing to edit.")
                continue

            index = ask_number(
                "Entry number to edit: ",
                1,
                len(entries)
            ) - 1

            edit_func(entries[index])
            continue

        if choice == "d":
            if not entries:
                print("There is nothing to delete.")
                continue

            index = ask_number(
                "Entry number to delete: ",
                1,
                len(entries)
            ) - 1

            entry = entries[index]
            print()
            print("About to delete:")
            print(json.dumps(
                entry,
                ensure_ascii=False,
                indent=2
            ))

            if ask_yes_no("Delete this entry?", default=False):
                entries.pop(index)
                print("Deleted.")
            else:
                print("Deletion cancelled.")

            continue

        if choice == "b":
            return

        print("Invalid choice.")


# ============================================================
# INITIAL ANNOTATION SECTIONS
# ============================================================

def annotate_diagnoses(status_options):
    diagnoses = []

    print()
    print("=" * 60)
    print("DIAGNOSES")
    print("=" * 60)
    print("Enter normalized English diagnoses.")
    print("Keep the original German wording in evidence.")
    print("One independently evaluable diagnosis per entry.")
    print("Press ENTER without text when finished.")

    while True:
        text = ask_text("\nDiagnosis: ")
        if not text:
            break

        status = ask_status(status_options)
        evidence = ask_text(
            "Evidence from source: ",
            allow_blank=False
        )

        diagnoses.append({
            "text": text,
            "status": status,
            "evidence": evidence,
        })

    return diagnoses


def annotate_comorbidities():
    comorbidities = []

    print()
    print("=" * 60)
    print("COMORBIDITIES")
    print("=" * 60)
    print("Enter normalized English comorbidities.")
    print("One independently evaluable comorbidity per entry.")
    print("Press ENTER without text when finished.")

    while True:
        text = ask_text("\nComorbidity: ")
        if not text:
            break

        evidence = ask_text(
            "Evidence from source: ",
            allow_blank=False
        )

        comorbidities.append({
            "text": text,
            "evidence": evidence,
        })

    return comorbidities


def annotate_recommendations():
    recommendations = []

    print()
    print("=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    print("Enter normalized English recommendations.")
    print("Do NOT include the standard telemedicine disclaimer.")
    print("Only patient-specific clinical recommendations.")
    print("One independently evaluable recommendation per entry.")
    print("Press ENTER without text when finished.")

    while True:
        text = ask_text("\nRecommendation: ")
        if not text:
            break

        evidence = ask_text(
            "Evidence from source: ",
            allow_blank=False
        )

        recommendations.append({
            "recommendation": text,
            "evidence": evidence,
        })

    return recommendations


def annotate_icd():
    codes = []

    print()
    print("=" * 60)
    print("ICD-10-GM")
    print("=" * 60)
    print("Enter only codes you have independently verified.")
    print("Do not use wildcard codes such as K72.x.")
    print("Press ENTER without a code when finished.")

    while True:
        code = ask_text("\nICD-10-GM code: ")
        if not code:
            break

        description = ask_text(
            "Description: ",
            allow_blank=False
        )
        evidence = ask_text(
            "Evidence from source: ",
            allow_blank=False
        )

        codes.append({
            "code": code,
            "description": description,
            "evidence": evidence,
        })

    return codes


def annotate_ops():
    codes = []

    print()
    print("=" * 60)
    print("OPS")
    print("=" * 60)
    print("Enter only codes you have independently verified.")
    print("Press ENTER without a code when finished.")

    while True:
        code = ask_text("\nOPS code: ")
        if not code:
            break

        description = ask_text(
            "Description: ",
            allow_blank=False
        )
        evidence = ask_text(
            "Evidence from source: ",
            allow_blank=False
        )

        codes.append({
            "code": code,
            "description": description,
            "evidence": evidence,
        })

    return codes


# ============================================================
# VALIDATION
# ============================================================

def validate_annotation(annotation, schema):
    """Lightweight consistency check against the existing schema."""

    issues = []
    required_fields = schema.get("required", [])

    for field in required_fields:
        if field not in annotation:
            issues.append(f"Missing required field: {field}")

    properties = schema.get("properties", {})

    for field_name, field_definition in properties.items():
        if field_name not in annotation:
            continue

        expected_type = field_definition.get("type")
        value = annotation[field_name]

        if expected_type == "array" and not isinstance(value, list):
            issues.append(f"{field_name} must be an array")
        elif expected_type == "string" and not isinstance(value, str):
            issues.append(f"{field_name} must be a string")

    return issues


# ============================================================
# ANNOTATION EDIT MENU
# ============================================================

def edit_annotation_menu(ground_truth, status_options):
    """Allow editing of any category before saving."""

    while True:
        print()
        print("=" * 80)
        print("EDIT ANNOTATION")
        print("=" * 80)
        print("1 = Diagnoses")
        print("2 = Comorbidities")
        print("3 = Recommendations")
        print("4 = ICD-10-GM")
        print("5 = OPS")
        print("6 = Return to preview")

        choice = input("Choice: ").strip()

        if choice == "1":
            category_editor(
                ground_truth["diagnoses"],
                "diagnoses",
                "DIAGNOSES",
                lambda: create_diagnosis(status_options),
                lambda entry: edit_diagnosis(
                    entry,
                    status_options
                )
            )

        elif choice == "2":
            category_editor(
                ground_truth["comorbidities"],
                "comorbidities",
                "COMORBIDITIES",
                create_comorbidity,
                edit_comorbidity
            )

        elif choice == "3":
            category_editor(
                ground_truth["recommendations"],
                "recommendations",
                "RECOMMENDATIONS",
                create_recommendation,
                edit_recommendation
            )

        elif choice == "4":
            category_editor(
                ground_truth["icd10_gm"],
                "icd10_gm",
                "ICD-10-GM",
                lambda: create_code_entry("ICD-10-GM"),
                lambda entry: edit_code_entry(
                    entry,
                    "ICD-10-GM"
                )
            )

        elif choice == "5":
            category_editor(
                ground_truth["ops"],
                "ops",
                "OPS",
                lambda: create_code_entry("OPS"),
                lambda entry: edit_code_entry(
                    entry,
                    "OPS"
                )
            )

        elif choice == "6":
            return

        else:
            print("Invalid choice.")


def preview_annotation(ground_truth, schema):
    """Show annotation and any validation warnings."""

    validation_issues = validate_annotation(
        ground_truth,
        schema
    )

    print()
    print("=" * 80)
    print("ANNOTATION PREVIEW")
    print("=" * 80)
    print(json.dumps(
        ground_truth,
        ensure_ascii=False,
        indent=2
    ))

    if validation_issues:
        print()
        print("SCHEMA VALIDATION WARNINGS:")
        for issue in validation_issues:
            print(f"  - {issue}")


# ============================================================
# EXISTING ANNOTATION HANDLING
# ============================================================

def load_existing_annotation(output_file):
    with open(
        output_file,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def choose_existing_annotation_action(document_id):
    """Return one of: skip, edit, restart."""

    while True:
        print()
        print(f"Already annotated: {document_id}")
        print()
        print("1 = Keep existing annotation and skip")
        print("2 = Open and edit existing annotation")
        print("3 = Start annotation again from scratch")

        choice = input("Choice [1]: ").strip()

        if choice in {"", "1"}:
            return "skip"
        if choice == "2":
            return "edit"
        if choice == "3":
            return "restart"

        print("Invalid choice.")


# ============================================================
# SAVE / REVIEW LOOP
# ============================================================

def review_and_save(
    ground_truth,
    output_file,
    schema,
    status_options
):
    """Preview, edit, save, or discard one annotation."""

    while True:
        preview_annotation(
            ground_truth,
            schema
        )

        print()
        print("What would you like to do?")
        print("1 = Save annotation")
        print("2 = Edit annotation")
        print("3 = Discard changes")

        choice = input("Choice [1]: ").strip()

        if choice in {"", "1"}:
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

            print()
            print(f"Saved:\n{output_file}")
            return True

        if choice == "2":
            edit_annotation_menu(
                ground_truth,
                status_options
            )
            continue

        if choice == "3":
            if ask_yes_no(
                "Discard all unsaved changes?",
                default=False
            ):
                print("Changes discarded.")
                return False
            continue

        print("Invalid choice.")


# ============================================================
# ANNOTATE ONE DOCUMENT
# ============================================================

def annotate_document(
    text_file,
    schema,
    status_options
):
    document_id = text_file.stem
    document_type = get_document_type(text_file)
    patient_id = get_patient_id(text_file)

    output_dir = GROUND_TRUTH_DIR / patient_id
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"{document_id}.json"

    document_text = text_file.read_text(
        encoding="utf-8"
    )

    print()
    print("=" * 80)
    print(document_id)
    print("=" * 80)
    print()
    print(document_text)
    print()
    print("=" * 80)

    # Existing annotation
    if output_file.exists():
        action = choose_existing_annotation_action(
            document_id
        )

        if action == "skip":
            return False

        if action == "edit":
            try:
                ground_truth = load_existing_annotation(
                    output_file
                )
            except (json.JSONDecodeError, OSError) as exc:
                print()
                print(
                    "Could not load the existing annotation:"
                )
                print(exc)
                print(
                    "Starting a new annotation instead."
                )
                ground_truth = create_empty_annotation(
                    schema,
                    document_id,
                    document_type
                )
            else:
                return review_and_save(
                    ground_truth,
                    output_file,
                    schema,
                    status_options
                )

        # action == restart falls through to fresh annotation

    ground_truth = create_empty_annotation(
        schema,
        document_id,
        document_type
    )

    if "diagnoses" in ground_truth:
        ground_truth["diagnoses"] = (
            annotate_diagnoses(status_options)
        )

    if "comorbidities" in ground_truth:
        ground_truth["comorbidities"] = (
            annotate_comorbidities()
        )

    if "recommendations" in ground_truth:
        ground_truth["recommendations"] = (
            annotate_recommendations()
        )

    if "icd10_gm" in ground_truth:
        ground_truth["icd10_gm"] = annotate_icd()

    if "ops" in ground_truth:
        ground_truth["ops"] = annotate_ops()

    return review_and_save(
        ground_truth,
        output_file,
        schema,
        status_options
    )


# ============================================================
# MAIN
# ============================================================

def main():
    schema = load_schema()
    status_options = get_diagnosis_status_options(
        schema
    )

    pilot_files = load_pilot_files()

    GROUND_TRUTH_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 80)
    print("GROUND TRUTH ANNOTATION")
    print("=" * 80)
    print(f"Schema:\n{SCHEMA_FILE}")
    print()
    print(f"Pilot documents: {len(pilot_files)}")
    print()
    print("Editing features:")
    print("- Existing annotations can be reopened")
    print("- Entries can be added, edited, or deleted")
    print("- Final preview can be edited before saving")

    annotated = 0

    for index, text_file in enumerate(
        pilot_files,
        start=1
    ):
        print()
        print(f"[{index}/{len(pilot_files)}]")

        result = annotate_document(
            text_file,
            schema,
            status_options
        )

        if result:
            annotated += 1

        if index < len(pilot_files):
            print()
            continue_choice = input(
                "Continue to next document? [Y/n]: "
            ).strip().lower()

            if continue_choice == "n":
                break

    print()
    print("=" * 80)
    print("ANNOTATION SESSION FINISHED")
    print("=" * 80)
    print(
        "Annotations saved/updated this session: "
        f"{annotated}"
    )
    print()
    print(f"Ground truth folder:\n{GROUND_TRUTH_DIR}")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
