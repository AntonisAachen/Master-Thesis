#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Aug  2 16:10:43 2026

@author: administrator
"""

from pathlib import Path
import shutil
import re

# Main folder
main_folder = Path("/Users/administrator/Documents/Μεταπτυχιακό/Thesis/Fallaktendokumentation")

# Destination folder
destination = main_folder / "Thesis"
destination.mkdir(exist_ok=True)

# Two letters followed by digits
pattern = re.compile(r"^[A-Za-z]{2}\d+$")

# Find all matching directories recursively
for folder in main_folder.rglob("*"):
    if (
        folder.is_dir()
        and folder != destination
        and destination not in folder.parents
        and pattern.match(folder.name)
    ):
        target = destination / folder.name

        print(f"Moving {folder} -> {target}")
        shutil.move(str(folder), str(target))

print("Done!")