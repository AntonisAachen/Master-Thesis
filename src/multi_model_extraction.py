#!/usr/bin/env python3
"""Multi-model development extraction for Master-Thesis.

Dry-run by default. Uses the existing extraction_prompt.txt and
extraction_schema.json unchanged. Never automatically samples evaluation data.

Dependencies: pip install openai ollama jsonschema
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, validators

MODELS = {
    "mistral-local": ("ollama", "mistral"),
    "mistral-small-4": ("kiconnect", "mistralai-mistral-small-4-119b"),
    "qwen-27b": ("kiconnect", "Qwen 3.8 27B"),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document_type(path):
    name = path.name.lower()
    if "visitendokumentation" in name:
        return "Visitendokumentation"
    if "empfehlungen" in name:
        return "Empfehlungen"
    return "Unknown"


def patient_id(path):
    match = re.search(r"Patient_\d{4}", str(path))
    return match.group() if match else "UNKNOWN"


def build_prompt(text, schema, template, document_id, kind):
    if "{{DOCUMENT_TEXT}}" not in template or "{{OUTPUT_SCHEMA}}" not in template:
        raise ValueError("Prompt template is missing a required placeholder")
    return (template.replace("{{DOCUMENT_TEXT}}", text)
            .replace("{{OUTPUT_SCHEMA}}", json.dumps(schema, ensure_ascii=False, indent=2))
            + f"\n\nDOCUMENT METADATA:\ndocument_id: {document_id}\ndocument_type: {kind}\n")


def read_list(path, text_dir):
    """Each line is a relative path under text_dir (or a unique basename)."""
    names = [s.strip() for s in path.read_text(encoding="utf-8").splitlines()
             if s.strip() and not s.lstrip().startswith("#")]
    if not names:
        raise ValueError(f"Document list is empty: {path}")
    all_txt = list(text_dir.rglob("*.txt"))
    by_name = {}
    for p in all_txt:
        by_name.setdefault(p.name, []).append(p)
    chosen = []
    for name in names:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Use paths relative to text directory: {name}")
        direct = text_dir / rel
        if direct.is_file():
            match = direct
        else:
            matches = by_name.get(name, []) if len(rel.parts) == 1 else []
            if len(matches) != 1:
                raise ValueError(f"Missing or ambiguous document '{name}' ({len(matches)} matches)")
            match = matches[0]
        if document_type(match) == "Unknown":
            raise ValueError(f"Unsupported document type: {match.name}")
        chosen.append(match.resolve())
    if len(set(chosen)) != len(chosen):
        raise ValueError("Duplicate documents in list")
    return chosen


def parse_json(content):
    clean = content.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.I)
    clean = re.sub(r"\s*```$", "", clean)
    return json.loads(clean)


def invoke(backend, model, prompt, schema, max_output, num_ctx):
    if backend == "ollama":
        import ollama
        result = ollama.chat(
            model=model, messages=[{"role": "user", "content": prompt}],
            format=schema,
            options={"temperature": 0, "seed": 42,
                     "num_ctx": num_ctx, "num_predict": max_output},
        )
        return {
            "text": result.message.content or "",
            "prompt_tokens": getattr(result, "prompt_eval_count", None),
            "output_tokens": getattr(result, "eval_count", None),
            "finish_reason": getattr(result, "done_reason", None),
            "provider_duration_ns": getattr(result, "total_duration", None),
        }
    from openai import OpenAI
    key = os.getenv("KICONNECT_API_KEY")
    if not key:
        raise RuntimeError("KICONNECT_API_KEY is missing from this Python process")
    client = OpenAI(base_url="https://chat.kiconnect.nrw/api/v1",
                    api_key=key, timeout=180.0, max_retries=0)
    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": {
            "name": "clinical_extraction", "strict": True, "schema": schema}},
        temperature=0, max_tokens=max_output,
    )
    choice = response.choices[0]
    usage = response.usage
    return {
        "text": choice.message.content or "",
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
        "finish_reason": choice.finish_reason,
        "provider_duration_ns": None,
        "response_model": response.model,
        "response_id": response.id,
    }


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", choices=MODELS, required=True)
    ap.add_argument("--development-list", type=Path, required=True)
    ap.add_argument("--evaluation-list", type=Path,
                    help="Required for execution: all held-out evaluation document filenames")
    ap.add_argument("--base-dir", type=Path,
                    default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--text-dir", type=Path)
    ap.add_argument("--output-dir", type=Path)
    ap.add_argument("--execute", action="store_true", help="Actually call the model")
    ap.add_argument("--allow-clinical-api", action="store_true",
                    help="Explicit acknowledgment of institutional authorization for KI:connect")
    ap.add_argument("--max-output-tokens", type=int, default=4096)
    ap.add_argument("--ollama-context", type=int, default=16384)
    ap.add_argument("--max-prompt-characters", type=int, default=24000,
                    help="Conservative screening threshold, NOT an exact tokenizer check")
    args = ap.parse_args()

    base = args.base_dir.expanduser().resolve()
    text_dir = (args.text_dir or base / "data/extracted/text").resolve()
    schema_file = base / "config/extraction_schema.json"
    prompt_file = base / "config/extraction_prompt.txt"
    backend, model_id = MODELS[args.model]
    output_dir = (args.output_dir or base / "data/model_outputs/development" / args.model).resolve()

    if not text_dir.is_dir():
        ap.error(f"Text directory does not exist: {text_dir}")
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    validator_class = validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema)
    template = prompt_file.read_text(encoding="utf-8")
    selected = read_list(args.development_list, text_dir)
    if args.evaluation_list:
        excluded = set(read_list(args.evaluation_list, text_dir))
        overlap = excluded.intersection(selected)
        if overlap:
            ap.error("Development list overlaps evaluation list: " + ", ".join(p.name for p in overlap))
    if args.execute and not args.evaluation_list:
        ap.error("--execute requires --evaluation-list to protect held-out documents")
    if args.execute and backend == "kiconnect" and not args.allow_clinical_api:
        ap.error("KI:connect execution requires --allow-clinical-api after UKA authorization")
    if args.max_output_tokens < 1 or args.ollama_context < 1:
        ap.error("Token limits must be positive")

    print(f"Model: {args.model} ({model_id})")
    print(f"Backend: {backend} | Documents: {len(selected)} | Execute: {args.execute}")
    for p in selected:
        print("  ", p.relative_to(text_dir))
    if not args.execute:
        print("DRY RUN ONLY: No model requests were sent.")
        return

    manifest_file = output_dir / "pilot_manifest.json"
    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "model_key": args.model, "model_id": model_id, "backend": backend,
        "prompt_sha256": sha256(prompt_file), "schema_sha256": sha256(schema_file),
        "development_list_sha256": sha256(args.development_list),
        "evaluation_list_sha256": sha256(args.evaluation_list),
        "parameters": {"temperature": 0, "max_output_tokens": args.max_output_tokens,
                       "ollama_context": args.ollama_context},
        "context_precheck": "Character threshold only; not exact tokenization",
        "results": [],
    }
    if backend == "ollama":
        try:
            import ollama
            entries = ollama.list().models
            manifest["model_digest"] = next(
                (getattr(e, "digest", None) for e in entries
                 if getattr(e, "model", None) in (model_id, model_id + ":latest")), None)
        except Exception as exc:
            manifest["model_digest_error"] = str(exc)

    for idx, p in enumerate(selected, 1):
        doc_id = p.stem
        print(f"[{idx}/{len(selected)}] {p.name}")
        record = {"document_id": doc_id, "patient_id": patient_id(p),
                  "document_type": document_type(p),
                  "source_file": str(p.relative_to(text_dir)), "status": "pending"}
        started = time.perf_counter()
        try:
            prompt = build_prompt(p.read_text(encoding="utf-8"), schema, template,
                                  doc_id, document_type(p))
            record["prompt_characters"] = len(prompt)
            if len(prompt) > args.max_prompt_characters:
                raise ValueError(
                    f"Prompt has {len(prompt)} characters; exceeds screening threshold "
                    f"{args.max_prompt_characters}. Exact token budget must be verified before inference.")
            result = invoke(backend, model_id, prompt, schema,
                            args.max_output_tokens, args.ollama_context)
            record.update({k: v for k, v in result.items() if k != "text"})
            dest = output_dir / patient_id(p)
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{doc_id}_raw.txt").write_text(result["text"], encoding="utf-8")
            try:
                parsed = parse_json(result["text"])
                record["json_valid"] = True
                issues = sorted(validator.iter_errors(parsed), key=lambda e: str(list(e.path)))
                record["schema_errors"] = [f"{list(e.path)}: {e.message}" for e in issues]
                record["schema_valid"] = not issues
                save_json(dest / f"{doc_id}.json", parsed)
            except (ValueError, TypeError) as exc:
                record.update(json_valid=False, schema_valid=False, parse_error=str(exc))
            if record.get("finish_reason") in ("length", "max_tokens"):
                record["status"] = "incomplete_generation"
            elif not record.get("schema_valid"):
                record["status"] = "invalid_output"
            else:
                record["status"] = "success"
            # Token counts are post-hoc; cannot establish absence of prompt truncation.
            record["context_verified"] = False
        except Exception as exc:
            record.update(status="technical_error", error=f"{type(exc).__name__}: {exc}")
        finally:
            record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
            manifest["results"].append(record)
            save_json(manifest_file, manifest)
            print(f"    {record['status']} | {record['elapsed_seconds']} s")
    print(f"Manifest: {manifest_file}")
    print("Note: context_verified=False until an exact model tokenizer precheck is implemented.")


if __name__ == "__main__":
    main()
