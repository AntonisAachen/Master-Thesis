#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov  2 09:22:51 2026

@author: administrator
"""

"""
Measure prompt and output sizes to choose NUM_CTX for pilot_extraction.py.

Run from the project folder (next to pilot_extraction.py):

    python context_stats.py

Prints numbers only, no document content, so the output can be shared.

Data sources
------------
1. All extracted text files in TEXT_DIR (character counts).
2. The pilot manifest, if it exists: prompt_tokens, output_tokens and
   input_characters per document, as reported by Ollama.

If the pilot ran with Ollama's small default context, prompt_tokens
was capped at that size and is NOT usable (the script warns about
this). In that case set NUM_CTX = 32768 once, re-run the pilot, and
run this script again: the token counts are then exact.
"""

import json
import math
from collections import Counter

import pilot_extraction as pe

# Fallback if no usable pilot data exists. German text with a
# Llama/Mistral-style tokenizer typically gives roughly 2.5-3.5
# characters per token; the low end is used to stay on the safe side.
FALLBACK_CHARS_PER_TOKEN = 2.8

CONTEXT_LADDER = [
    4096, 6144, 8192, 12288, 16384, 24576, 32768, 49152, 65536
]

SAFETY_FACTOR = 1.10

# KV cache per token for Mistral-7B-like models (fp16):
# 32 layers x 8 KV heads x 128 dims x 2 (K and V) x 2 bytes.
# Only valid for that architecture.
KV_BYTES_PER_TOKEN = 32 * 8 * 128 * 2 * 2


def percentile(values, q):

    if not values:
        return None

    ordered = sorted(values)

    index = max(
        0,
        math.ceil(q / 100 * len(ordered)) - 1
    )

    return ordered[index]


def describe(name, values):

    if not values:
        print(f"{name}: no data")
        return

    print(
        f"{name}: n={len(values)}  "
        f"median={percentile(values, 50)}  "
        f"p95={percentile(values, 95)}  "
        f"max={max(values)}"
    )


def next_context_size(required):

    for size in CONTEXT_LADDER:

        if size >= required:
            return size

    return CONTEXT_LADDER[-1]


def main():

    schema = pe.load_schema()

    template = pe.load_prompt_template()

    fixed_prompt = pe.build_prompt(
        "",
        schema,
        template,
        "Patient_0000_Visitendokumentation_00",
        "Visitendokumentation"
    )

    fixed_chars = len(fixed_prompt)

    print("=" * 60)
    print("CONTEXT SIZE ANALYSIS")
    print("=" * 60)
    print(f"Model: {pe.MODEL_NAME}")
    print(f"Current NUM_CTX: {pe.NUM_CTX}")
    print(
        f"Fixed prompt (template + schema + metadata): "
        f"{fixed_chars} characters"
    )
    print()

    # --------------------------------------------------------
    # DOCUMENT SIZES (all extracted text files)
    # --------------------------------------------------------

    document_chars = [
        len(
            path.read_text(
                encoding="utf-8",
                errors="replace"
            )
        )
        for path in sorted(
            pe.TEXT_DIR.rglob("*.txt")
        )
    ]

    describe(
        "Document text (characters)",
        document_chars
    )

    max_document_chars = max(
        document_chars,
        default=0
    )

    # --------------------------------------------------------
    # PILOT MEASUREMENTS
    # --------------------------------------------------------

    results = []

    if pe.MANIFEST_FILE.exists():

        with open(
            pe.MANIFEST_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            results = json.load(f).get(
                "results",
                []
            )

    measured = [
        r for r in results
        if r.get("prompt_tokens")
        and r.get("input_characters") is not None
    ]

    prompt_values = [
        r["prompt_tokens"]
        for r in measured
    ]

    suspicious_cap = None

    if prompt_values:

        top_value = max(prompt_values)

        if Counter(prompt_values)[top_value] >= 2:

            suspicious_cap = top_value

    reliable = [
        r for r in measured
        if r["prompt_tokens"] != suspicious_cap
        and r.get("context_ok", True)
    ]

    print()

    describe(
        "Pilot prompt_tokens",
        prompt_values
    )

    describe(
        "Pilot output_tokens",
        [
            r["output_tokens"]
            for r in results
            if r.get("output_tokens")
        ]
    )

    if suspicious_cap:

        print()
        print(
            f"WARNING: the largest prompt_tokens value "
            f"({suspicious_cap}) occurs several times. That is the "
            f"signature of a prompt cut at the context limit. "
            f"These counts are not reliable; they were excluded."
        )

    # --------------------------------------------------------
    # TOKENS PER CHARACTER
    # --------------------------------------------------------

    if reliable:

        worst_tokens_per_char = max(
            r["prompt_tokens"]
            / (fixed_chars + r["input_characters"])
            for r in reliable
        )

        basis = (
            f"measured on {len(reliable)} pilot documents "
            f"(worst case)"
        )

    else:

        worst_tokens_per_char = 1 / FALLBACK_CHARS_PER_TOKEN

        basis = (
            f"ASSUMED {FALLBACK_CHARS_PER_TOKEN} characters/token "
            f"(no usable pilot data)"
        )

    print()
    print(
        f"Tokens per character: {worst_tokens_per_char:.3f} "
        f"({1 / worst_tokens_per_char:.2f} chars/token), {basis}"
    )

    fixed_tokens = round(
        fixed_chars * worst_tokens_per_char
    )

    max_prompt_tokens = round(
        (fixed_chars + max_document_chars)
        * worst_tokens_per_char
    )

    # --------------------------------------------------------
    # OUTPUT RESERVE
    # --------------------------------------------------------

    output_max = max(
        (
            r["output_tokens"]
            for r in results
            if r.get("output_tokens")
        ),
        default=0
    )

    output_reserve = max(
        pe.OUTPUT_RESERVE_TOKENS,
        math.ceil(output_max * 1.25)
    )

    required = max_prompt_tokens + output_reserve

    recommended = next_context_size(
        required * SAFETY_FACTOR
    )

    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Fixed part of the prompt:        ~{fixed_tokens} tokens")
    print(f"Longest document + fixed part:   ~{max_prompt_tokens} tokens")
    print(f"Output reserve:                  ~{output_reserve} tokens")
    print(f"Required (without safety):       ~{required} tokens")
    print(
        f"Recommended NUM_CTX:             {recommended} "
        f"(includes {int((SAFETY_FACTOR - 1) * 100)}% margin)"
    )
    print(
        f"OUTPUT_RESERVE_TOKENS to set:    {output_reserve}"
    )

    gib = recommended * KV_BYTES_PER_TOKEN / 1024 ** 3

    print()
    print(
        f"KV cache at this size (Mistral-7B-like, fp16): "
        f"~{gib:.1f} GiB, on top of the model weights."
    )

    too_long = [
        c for c in document_chars
        if (fixed_chars + c) * worst_tokens_per_char
        + output_reserve > recommended
    ]

    if too_long:

        print()
        print(
            f"{len(too_long)} documents would still not fit; "
            f"consider a larger NUM_CTX or splitting them."
        )


if __name__ == "__main__":
    main()