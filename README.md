# Clinical Information Extraction from DOCX Medical Reports

## Overview
This project investigates the automatic extraction of clinically relevant information from unstructured DOCX documents generated during hospital visits.

The focus is on information extraction using large language models (LLMs), without performing semantic categorization or clinical interpretation. The LLM-based approach is compared with manual extraction and rule-based methods.

---

## Project Structure
clinical-ie-thesis/
│
├── data/
│   ├── raw/            # Original DOCX files (not uploaded)
│   ├── text/           # Extracted text
│   └── annotations/    # Ground truth data
│
├── src/
│   ├── docx_reader.py
│   ├── extractor.py
│   ├── evaluation.py
│   └── utils.py
│
├── main.py             # Entry point
├── requirements.txt
└── README.md

---

## Setup

### 1. Create environment

conda create -n thesis python=3.11
conda activate thesis

### 2. Install dependencies
pip install -r requirements.txt

### Usage
Run the pipeline:
python main.py
The script will:

Load a DOCX file
Extract raw text
Apply the extraction method
Output structured data (JSON)


### Methods
The project includes:

LLM-based extraction
Rule-based extraction (baseline)
Manual annotation (ground truth)


### Evaluation
Extraction performance is evaluated using:

Precision
Recall
F1-score


### Notes

Clinical data is not included in this repository for privacy reasons.
All experiments are reproducible via the provided scripts.


### Author
Master Thesis – RWTH Aachen University
