#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 23 11:46:23 2026

@author: administrator
"""

import csv
from pathlib import Path
import re

#%%
root_dir = Path(r"/Users/administrator/Documents/GitHub/Master-Thesis/data/raw")
mapping_dir = Path(r"/Users/administrator/Documents/Μεταπτυχιακό/Thesis")

pattern = re.compile(r"^([A-Za-z]{2}\d+)_.*$")

#%%
# # Process deepest directories first
# directories = sorted(
#     [p for p in root_dir.rglob("*") if p.is_dir()],
#     key=lambda p: len(p.parts),
#     reverse=True
# )

# for directory in directories:
#     match = pattern.match(directory.name)

#     if match:
#         new_name = match.group(1)
#         new_path = directory.parent / new_name

#         if not new_path.exists():
#             print(f"Renaming: {directory} -> {new_path}")
#             directory.rename(new_path)
#         else:
#             print(f"Skipping {directory}: target exists")
            

