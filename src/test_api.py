#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Nov  2 13:29:40 2026

@author: administrator
"""



import os
import json
from openai import OpenAI

client = OpenAI(
    base_url="https://chat.kiconnect.nrw/api/v1",
    api_key=os.environ["KICONNECT_API_KEY"],
)

#model = "mistralai-mistral-small-4-119b"
model = "Qwen 3.8 27B"

response = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "system",
            "content": "Extrahiere klinische Informationen. Antworte ausschließlich als gültiges JSON."
        },
        {
            "role": "user",
            "content": (
                "Patient mit Pneumonie. "
                "Antibiotikatherapie mit Ceftriaxon empfohlen."
            )
        }
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "clinical_extraction_test",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "diagnose": {"type": "string"},
                    "empfehlung": {"type": "string"}
                },
                "required": ["diagnose", "empfehlung"],
                "additionalProperties": False
            }
        }
    },
    temperature=0,
    max_tokens=300,
)

content = response.choices[0].message.content
parsed = json.loads(content)

print(json.dumps(parsed, indent=2, ensure_ascii=False))
print("Finish reason:", response.choices[0].finish_reason)

