from pathlib import Path

import json
import random
import re
import time
from datetime import datetime

import importlib.metadata

import ollama
from ollama import chat


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

PROMPT_FILE = (
    BASE_DIR
    / "config"
    / "extraction_prompt.txt"
)

OUTPUT_DIR = (
    BASE_DIR
    / "data"
    / "model_outputs"
    / "pilot"
    / "mistral"
)

MANIFEST_FILE = (
    OUTPUT_DIR
    / "pilot_manifest.json"
)

MODEL_NAME = "mistral"

# Context window passed explicitly to Ollama. Without this Ollama
# uses a small default, and a longer prompt can be cut silently,
# so the model would never see parts of the schema or document.
# Adjust to the document lengths and to the memory of the machine.
NUM_CTX = 16384

# Maximum number of tokens the model may generate. This stops a
# model that gets stuck repeating array items from running until
# the context is full. A run that hits the limit ends with
# done_reason == "length" and is flagged in the manifest.
NUM_PREDICT = 4096

# Tokens kept free for the model's answer. A run is flagged when
# prompt_tokens + OUTPUT_RESERVE_TOKENS would not fit in NUM_CTX.
# Equal to NUM_PREDICT, so a prompt that passes this check can
# always be answered in full.
OUTPUT_RESERVE_TOKENS = NUM_PREDICT

# Start small while testing structured output.
PILOT_SIZE = 10

# Fixed seed for reproducible document selection.
RANDOM_SEED = 42


# ============================================================
# LOAD CONFIGURATION
# ============================================================

def load_schema():
    """
    Load the formal JSON Schema used both:
    - in the prompt
    - as Ollama's structured-output format
    """

    with open(
        SCHEMA_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def load_prompt_template():

    return PROMPT_FILE.read_text(
        encoding="utf-8"
    )


# ============================================================
# DOCUMENT METADATA
# ============================================================

def get_document_type(file_path):

    filename = (
        file_path.name
        .lower()
    )

    if "visitendokumentation" in filename:
        return "Visitendokumentation"

    if "empfehlungen" in filename:
        return "Empfehlungen"

    if "medikationsplan" in filename:
        return "Medikationsplan"

    return "Unknown"


def get_patient_id(file_path):

    match = re.search(
        r"Patient_\d{4}",
        str(file_path)
    )

    if match:
        return match.group()

    return "UNKNOWN"


# ============================================================
# PILOT DOCUMENT SELECTION
# ============================================================

def select_pilot_documents():
    """
    Select a reproducible set of pilot documents.

    Only:
        - Visitendokumentation
        - Empfehlungen

    are used in this first pilot.
    """

    files = sorted(
        file
        for file in TEXT_DIR.rglob("*.txt")
        if get_document_type(file)
        in {
            "Visitendokumentation",
            "Empfehlungen",
        }
    )

    if len(files) < PILOT_SIZE:

        raise ValueError(
            f"Only {len(files)} eligible files found, "
            f"but PILOT_SIZE is {PILOT_SIZE}."
        )

    # A local generator gives exactly the same selection as
    # random.seed() + random.sample() did, without changing the
    # global random state.
    rng = random.Random(
        RANDOM_SEED
    )

    selected = rng.sample(
        files,
        PILOT_SIZE
    )

    return sorted(
        selected
    )


# ============================================================
# BUILD FINAL PROMPT
# ============================================================

def build_prompt(
    document_text,
    schema,
    prompt_template,
    document_id,
    document_type
):
    """
    Insert document text and JSON schema into the fixed prompt.
    """

    schema_text = json.dumps(
        schema,
        ensure_ascii=False,
        indent=2
    )

    metadata_text = (
        f"\n\nDOCUMENT METADATA:\n"
        f"document_id: {document_id}\n"
        f"document_type: {document_type}\n"
    )

    prompt = (
        prompt_template
        .replace(
            "{{DOCUMENT_TEXT}}",
            document_text
        )
        .replace(
            "{{OUTPUT_SCHEMA}}",
            schema_text
        )
    )

    prompt = (
        prompt
        + metadata_text
    )

    return prompt


# ============================================================
# MODEL SETTINGS AND PROVENANCE
# ============================================================

def get_model_options():
    """
    Generation options sent to Ollama. Also written to the manifest,
    so that the exact settings of a run can be reconstructed.
    """

    return {
        "temperature": 0,
        "num_ctx": NUM_CTX,
        "num_predict": NUM_PREDICT,
        "seed": RANDOM_SEED,
    }


def get_model_info():
    """
    Identify the exact model that produced the outputs.

    The tag "mistral" is a moving target: if the model is updated,
    the same tag points to different weights. The digest identifies
    the weights. Failures are recorded instead of stopping the run.
    """

    info = {
        "model_name": MODEL_NAME,
        "digest": None,
        "modified_at": None,
        "size_bytes": None,
        "ollama_python_version": None,
        "error": None,
    }

    try:

        info["ollama_python_version"] = (
            importlib.metadata.version(
                "ollama"
            )
        )

    except Exception:

        pass

    try:

        for entry in ollama.list().models:

            name = (
                getattr(entry, "model", None)
                or getattr(entry, "name", None)
            )

            if name in (
                MODEL_NAME,
                f"{MODEL_NAME}:latest"
            ):

                info["digest"] = getattr(
                    entry,
                    "digest",
                    None
                )

                info["modified_at"] = str(
                    getattr(
                        entry,
                        "modified_at",
                        None
                    )
                )

                info["size_bytes"] = getattr(
                    entry,
                    "size",
                    None
                )

                break

        if info["digest"] is None:

            info["error"] = (
                f"model '{MODEL_NAME}' not found in ollama list"
            )

    except Exception as error:

        info["error"] = str(
            error
        )

    return info


# ============================================================
# MODEL CALL
# ============================================================

def run_model(
    prompt,
    schema
):
    """
    Run local Mistral using Ollama structured outputs.

    temperature=0 is used here because this pilot is testing:
        - prompt behaviour
        - JSON structure
        - extraction logic

    Reproducibility testing will come later.
    """

    response = chat(
        model=MODEL_NAME,

        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],

        # Enforce the formal JSON schema.
        format=schema,

        options=get_model_options()
    )

    return (
        response.message.content,
        response
    )


# ============================================================
# PARSE JSON RESPONSE
# ============================================================

def extract_json_from_response(
    response_text
):
    """
    Parse the model response.

    Structured output should normally already be pure JSON,
    but Markdown fences are removed defensively.
    """

    cleaned = (
        response_text
        .strip()
    )

    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    cleaned = (
        cleaned.strip()
    )

    return json.loads(
        cleaned
    )


# ============================================================
# VALIDATE BASIC OUTPUT STRUCTURE
# ============================================================

def validate_output_structure(
    result
):
    """
    Additional lightweight validation after JSON parsing.

    Ollama already receives the formal JSON Schema, but this
    gives us a simple independent check for the pilot report.
    """

    required_fields = [
        "document_id",
        "document_type",
        "diagnoses",
        "comorbidities",
        "recommendations",
        "icd10_gm",
        "ops",
    ]

    list_fields = [
        "diagnoses",
        "comorbidities",
        "recommendations",
        "icd10_gm",
        "ops",
    ]

    issues = []

    # ========================================================
    # REQUIRED TOP-LEVEL FIELDS
    # ========================================================

    for field in required_fields:

        if field not in result:

            issues.append(
                f"Missing field: {field}"
            )

    # ========================================================
    # ARRAY FIELDS
    # ========================================================

    for field in list_fields:

        if (
            field in result
            and not isinstance(
                result[field],
                list
            )
        ):

            issues.append(
                f"{field} is not a list"
            )

    return issues


# ============================================================
# PROCESS ONE DOCUMENT
# ============================================================

def process_document(
    text_file,
    schema,
    prompt_template
):

    document_id = (
        text_file.stem
    )

    patient_id = (
        get_patient_id(
            text_file
        )
    )

    document_type = (
        get_document_type(
            text_file
        )
    )

    document_text = (
        text_file.read_text(
            encoding="utf-8"
        )
    )

    prompt = build_prompt(
        document_text,
        schema,
        prompt_template,
        document_id,
        document_type
    )

    # ========================================================
    # TIMER START
    # ========================================================

    start_time = (
        time.perf_counter()
    )

    # ========================================================
    # RUN MODEL
    # ========================================================

    (
        response_text,
        response
    ) = run_model(
        prompt,
        schema
    )

    # ========================================================
    # TIMER STOP
    # ========================================================

    elapsed_seconds = (
        time.perf_counter()
        - start_time
    )

    # ========================================================
    # OUTPUT FOLDER
    # ========================================================

    patient_output_dir = (
        OUTPUT_DIR
        / patient_id
    )

    patient_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # SAVE RAW MODEL RESPONSE
    # ========================================================

    raw_file = (
        patient_output_dir
        / f"{document_id}_raw.txt"
    )

    raw_file.write_text(
        response_text,
        encoding="utf-8"
    )

    # ========================================================
    # PARSE JSON
    # ========================================================

    try:

        parsed_result = (
            extract_json_from_response(
                response_text
            )
        )

        json_valid = True

        parse_error = ""

    except Exception as error:

        parsed_result = None

        json_valid = False

        parse_error = str(
            error
        )

    # ========================================================
    # STRUCTURE VALIDATION
    # ========================================================

    if parsed_result is not None:

        structure_issues = (
            validate_output_structure(
                parsed_result
            )
        )

    else:

        structure_issues = []

    # ========================================================
    # SAVE PARSED JSON
    # ========================================================

    if parsed_result is not None:

        parsed_file = (
            patient_output_dir
            / f"{document_id}.json"
        )

        with open(
            parsed_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                parsed_result,
                f,
                ensure_ascii=False,
                indent=2
            )

    # ========================================================
    # OLLAMA METRICS
    # ========================================================

    ollama_total_seconds = None

    if getattr(
        response,
        "total_duration",
        None
    ):

        ollama_total_seconds = round(
            response.total_duration
            / 1_000_000_000,
            2
        )

    prompt_tokens = getattr(
        response,
        "prompt_eval_count",
        None
    )

    output_tokens = getattr(
        response,
        "eval_count",
        None
    )

    # ========================================================
    # CONTEXT WINDOW CHECK
    #
    # If the prompt does not fit in NUM_CTX the model may have
    # received a truncated prompt, or its answer may have been
    # cut off. Such documents must not be scored as if they had
    # been processed normally.
    # ========================================================

    done_reason = getattr(
        response,
        "done_reason",
        None
    )

    context_issues = []

    if prompt_tokens is None:

        context_issues.append(
            "prompt_eval_count not reported; "
            "context usage could not be verified"
        )

    elif prompt_tokens + OUTPUT_RESERVE_TOKENS > NUM_CTX:

        context_issues.append(
            f"prompt uses {prompt_tokens} of {NUM_CTX} "
            f"context tokens (reserve for output: "
            f"{OUTPUT_RESERVE_TOKENS}); the prompt may "
            f"have been truncated"
        )

    if done_reason == "length":

        context_issues.append(
            "generation stopped at the token limit "
            "(done_reason=length); output may be incomplete"
        )

    # ========================================================
    # RETURN PILOT METADATA
    # ========================================================

    return {
        "patient_id":
            patient_id,

        "document_id":
            document_id,

        "document_type":
            document_type,

        "source_file":
            str(text_file),

        "model":
            MODEL_NAME,

        "json_valid":
            json_valid,

        "parse_error":
            parse_error,

        "structure_valid":
            (
                json_valid
                and len(
                    structure_issues
                ) == 0
            ),

        "structure_issues":
            structure_issues,

        "input_characters":
            len(
                document_text
            ),

        "output_characters":
            len(
                response_text
            ),

        "elapsed_seconds":
            round(
                elapsed_seconds,
                2
            ),

        "ollama_total_seconds":
            ollama_total_seconds,

        "prompt_tokens":
            prompt_tokens,

        "output_tokens":
            output_tokens,

        "num_ctx":
            NUM_CTX,

        "done_reason":
            done_reason,

        "context_ok":
            len(context_issues) == 0,

        "context_issues":
            context_issues,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # TOTAL TIMER START
    # ========================================================

    pilot_start_time = (
        time.perf_counter()
    )

    # ========================================================
    # CHECK INPUTS
    # ========================================================

    if not TEXT_DIR.exists():

        raise FileNotFoundError(
            f"Text directory not found:\n"
            f"{TEXT_DIR}"
        )

    if not SCHEMA_FILE.exists():

        raise FileNotFoundError(
            f"Schema file not found:\n"
            f"{SCHEMA_FILE}"
        )

    if not PROMPT_FILE.exists():

        raise FileNotFoundError(
            f"Prompt file not found:\n"
            f"{PROMPT_FILE}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # LOAD CONFIG
    # ========================================================

    schema = load_schema()

    prompt_template = (
        load_prompt_template()
    )

    model_info = get_model_info()

    if model_info["digest"] is None:

        print(
            "WARNING: model digest could not be determined: "
            f"{model_info['error']}"
        )

    # ========================================================
    # SELECT DOCUMENTS
    # ========================================================

    selected_documents = (
        select_pilot_documents()
    )

    print("=" * 70)
    print("LLM EXTRACTION PILOT")
    print("=" * 70)

    print(
        f"Model: "
        f"{MODEL_NAME}"
    )

    print(
        f"Digest: "
        f"{model_info['digest']}"
    )

    print(
        f"Options: "
        f"{get_model_options()}"
    )

    print(
        f"Documents: "
        f"{len(selected_documents)}"
    )

    print()

    results = []

    # ========================================================
    # DOCUMENT LOOP
    # ========================================================

    for index, text_file in enumerate(
        selected_documents,
        start=1
    ):

        print(
            f"[{index}/"
            f"{len(selected_documents)}] "
            f"{text_file.name}"
        )

        try:

            result = process_document(
                text_file,
                schema,
                prompt_template
            )

            results.append(
                result
            )

            if not result["context_ok"]:

                print(
                    "    WARNING: context window problem"
                )

                for issue in result[
                    "context_issues"
                ]:

                    print(
                        f"        - {issue}"
                    )

            # =================================================
            # CONSOLE RESULT
            # =================================================

            if result[
                "structure_valid"
            ]:

                print(
                    f"    JSON: OK | "
                    f"{result['elapsed_seconds']} s"
                )

            elif result[
                "json_valid"
            ]:

                print(
                    f"    JSON parsed, "
                    f"but schema issue | "
                    f"{result['elapsed_seconds']} s"
                )

                for issue in result[
                    "structure_issues"
                ]:

                    print(
                        f"        - {issue}"
                    )

            else:

                print(
                    f"    Invalid JSON | "
                    f"{result['elapsed_seconds']} s"
                )

                print(
                    f"        "
                    f"{result['parse_error']}"
                )

        except Exception as error:

            print(
                f"    ERROR: "
                f"{error}"
            )

            # Keep the identifiers so that documents which failed
            # are still recognised as pilot documents when the
            # held-out evaluation sample is built.
            results.append(
                {
                    "patient_id":
                        get_patient_id(
                            text_file
                        ),

                    "document_id":
                        text_file.stem,

                    "document_type":
                        get_document_type(
                            text_file
                        ),

                    "source_file":
                        str(text_file),

                    "model":
                        MODEL_NAME,

                    "error":
                        str(error),
                }
            )

    # ========================================================
    # TOTAL TIMER STOP
    # ========================================================

    pilot_elapsed = (
        time.perf_counter()
        - pilot_start_time
    )

    # ========================================================
    # SAVE PILOT MANIFEST
    # ========================================================

    pilot_manifest = {
        "model":
            MODEL_NAME,

        "pilot_size":
            PILOT_SIZE,

        "random_seed":
            RANDOM_SEED,

        "model_info":
            model_info,

        "model_options":
            get_model_options(),

        "created":
            datetime.now().isoformat(),

        "schema_file":
            str(SCHEMA_FILE),

        "prompt_file":
            str(PROMPT_FILE),

        "total_elapsed_seconds":
            round(
                pilot_elapsed,
                2
            ),

        "results":
            results,
    }

    with open(
        MANIFEST_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            pilot_manifest,
            f,
            ensure_ascii=False,
            indent=2
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    successful_json = sum(
        result.get(
            "json_valid",
            False
        )
        for result in results
    )

    valid_structure = sum(
        result.get(
            "structure_valid",
            False
        )
        for result in results
    )

    errors = sum(
        "error" in result
        for result in results
    )

    minutes = int(
        pilot_elapsed // 60
    )

    seconds = (
        pilot_elapsed % 60
    )

    print()
    print("=" * 70)
    print("PILOT FINISHED")
    print("=" * 70)

    print(
        f"Documents: "
        f"{len(results)}"
    )

    print(
        f"Valid JSON: "
        f"{successful_json}"
    )

    print(
        f"Valid structure: "
        f"{valid_structure}"
    )

    print(
        f"Errors: "
        f"{errors}"
    )

    context_problems = sum(
        result.get("context_ok", True) is False
        for result in results
    )

    print(
        f"Context window problems: "
        f"{context_problems}"
    )

    print(
        f"Total runtime: "
        f"{minutes} min "
        f"{seconds:.1f} s"
    )

    # ========================================================
    # OPTIONAL SPEED SUMMARY
    # ========================================================

    completed_times = [
        result["elapsed_seconds"]
        for result in results
        if "elapsed_seconds" in result
    ]

    if completed_times:

        average_time = (
            sum(completed_times)
            / len(completed_times)
        )

        print(
            f"Average per document: "
            f"{average_time:.1f} s"
        )

    print()

    print(
        f"Output:\n"
        f"{OUTPUT_DIR}"
    )

    print()

    print(
        f"Pilot manifest:\n"
        f"{MANIFEST_FILE}"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()