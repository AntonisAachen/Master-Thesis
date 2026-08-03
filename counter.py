#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 30 09:01:39 2026

@author: administrator
"""

from pathlib import Path
from datetime import datetime

# Change this to your folder
folder = Path(r"/Users/administrator/Documents/Μεταπτυχιακό/Thesis/Fallaktendokumentation/Thesis")

docx_files = list(folder.rglob("*.docx"))

print(f"Found {len(docx_files)} .docx files.")

if docx_files:
    # Get creation times
    creation_times = [f.stat().st_ctime for f in docx_files]

    first = min(creation_times)
    last = max(creation_times)

    first_dt = datetime.fromtimestamp(first)
    last_dt = datetime.fromtimestamp(last)

    span = last_dt - first_dt

    print(f"First file created : {first_dt}")
    print(f"Last file created  : {last_dt}")
    print(f"Timespan           : {span}")
else:
    print("No .docx files found.")