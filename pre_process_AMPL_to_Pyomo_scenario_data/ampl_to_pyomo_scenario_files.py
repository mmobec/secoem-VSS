# -*- coding: utf-8 -*-
"""
Created on Mon Jan 27 12:41:37 2025

@author: andre
"""

"""
A Python script to convert advanced pivot lines (Scen0 (tr), param X [*], etc.)
from an AMPL .dat file into a standard Pyomo-friendly format.
"""


import os
import shutil
import re

# Data
fam_scen = "FTC_1_2023_12"

# Define paths
root_dir = os.path.abspath(os.path.join(os.getcwd(), ".."))  # Root directory (mmobec-pyomo)
scenarios_dir = os.path.join(root_dir, "scenarios", fam_scen)
backup_dir = os.path.join(root_dir, "pre_process_AMPL_to_Pyomo_scenario_data", "AMPL format scenario data")
converted_dir = os.path.join(root_dir, "pre_process_AMPL_to_Pyomo_scenario_data", "Python format scenario data")

# Ensure backup and converted directories exist
os.makedirs(backup_dir, exist_ok=True)
os.makedirs(converted_dir, exist_ok=True)

def transform_datfile(infile, outfile):
    """
    Transforms `infile` (AMPL style with pivoted param) into `outfile` (Pyomo style).
    """
    with open(infile, 'r') as fin, open(outfile, 'w') as fout:
        lines = fin.readlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # 1) If we see "param Scen0 (tr)", we parse the pivot table
            if line.startswith("param Scen0 (tr)"):
                # We'll parse lines until we see a semicolon ';'
                # The next line might be something like ": 1 2 3 ... := or blank
                # We parse column headers, row lines, etc.

                # skip the param Scen0 (tr) line
                i += 1
                # read the next line, which might be something like:
                # ":    1   2   3   ... 231 :="
                
                # Example: line = ": 1 2 3 ... 231 :="
                header_line = lines[i].strip()
                i += 1
                # parse columns
                # typically: ": 1 2 3 4 5 ... 231 :="
                # remove leading ':' and trailing ':='
                header_line = header_line.lstrip(":").rstrip(":=").strip()
                col_headers = header_line.split()
                # col_headers = ['1','2','3',... '231']

                # now we accumulate rows until we see a line with ';'
                pivot_data = []
                while i < len(lines):
                    row_line = lines[i].strip()
                    if row_line.endswith(";"):
                        # last line of pivot
                        row_line = row_line[:-1].strip() # remove semicolon
                        done = True
                    else:
                        done = False
                    i += 1
                    if not row_line:
                        break
                    # row_line might look like:
                    # "1  93.5882 91.9265 ..."
                    parts = row_line.split()
                    if len(parts) == 0:
                        break
                    row_id = parts[0]   # e.g. "1"
                    row_vals = parts[1:]
                    pivot_data.append((row_id, row_vals))

                    if done:
                        break
                
                # Now we have col_headers = [...], pivot_data = list of (row, [vals]).
                # We'll rewrite as standard param lines: e.g.
                # param Scen0 :=
                # [row_id, col_header] val
                # ...
                
                fout.write("param Scen0 :=\n")
                for (row_id, row_vals) in pivot_data:
                    # row_vals aligned with col_headers
                    for c, val in zip(col_headers, row_vals):
                        # c is column scenario index, row_id is "rv" or whatever dimension
                        # produce line:  [row_id,c] val
                        fout.write(f"{c} {row_id} {val}\n")
                fout.write(";\n\n")
                continue
            
            # 2) If we see "param nRVSG [*] := ...", parse it as 1D param
            if re.match(r'^param\s+nRVSG\s*\[\*\]\s*:=', line):
                # read lines until semicolon
                i += 1
                data_lines = []
                while i < len(lines):
                    test_line = lines[i].strip()
                    i += 1
                    if test_line.endswith(";"):
                        test_line = test_line[:-1].strip()
                        data_lines.append(test_line)
                        break
                    data_lines.append(test_line)
                # combine them
                merged = " ".join(data_lines).split()
                # each pair [key value]
                fout.write("param nRVSG :=\n")
                for idx in range(0, len(merged), 2):
                    key = merged[idx]
                    val = merged[idx+1]
                    fout.write(f"{key} {val}\n")
                fout.write(";\n\n")
                continue
            
            # 3) Same for param ScenF [*], param ScenO [*], etc...
            if re.match(r'^param\s+ScenF\s*\[\*\]\s*:=', line):
                i += 1
                data_lines = []
                while i < len(lines):
                    test_line = lines[i].strip()
                    i += 1
                    if test_line.endswith(";"):
                        test_line = test_line[:-1].strip()
                        data_lines.append(test_line)
                        break
                    data_lines.append(test_line)
                merged = " ".join(data_lines).split()
                fout.write("param ScenF :=\n")
                for idx in range(0, len(merged), 2):
                    key = merged[idx]
                    val = merged[idx+1]
                    fout.write(f"{key} {val}\n")
                fout.write(";\n\n")
                continue

            if re.match(r'^param\s+ScenO\s*\[\*\]\s*:=', line):
                i += 1
                data_lines = []
                while i < len(lines):
                    test_line = lines[i].strip()
                    i += 1
                    if test_line.endswith(";"):
                        test_line = test_line[:-1].strip()
                        data_lines.append(test_line)
                        break
                    data_lines.append(test_line)
                merged = " ".join(data_lines).split()
                fout.write("param ScenO :=\n")
                for idx in range(0, len(merged), 2):
                    key = merged[idx]
                    val = merged[idx+1]
                    fout.write(f"{key} {val}\n")
                fout.write(";\n\n")
                continue

            # Otherwise, just copy the line
            fout.write(line+"\n")
            i += 1


def process_scenario_files():
    """
    Automates the transformation of all AMPL scenario files to Pyomo format.
    - Copies the original files to the backup folder.
    - Converts each file and saves it in both the processing folder and the original folder.
    """
    print("\n**Starting Scenario File Processing...**")

    # List all files in the scenarios folder
    scenario_files = [f for f in os.listdir(scenarios_dir) if f.endswith(".dat")]

    for file in scenario_files:
        ampl_file_path = os.path.join(scenarios_dir, file)
        backup_file_path = os.path.join(backup_dir, file)
        converted_file_path = os.path.join(converted_dir, file)
        final_file_path = os.path.join(scenarios_dir, file)  # Overwrite original

        print(f"Processing: {file}")

        # Step 1: Copy original file to backup folder
        shutil.copy(ampl_file_path, backup_file_path)
        print(f"Backup saved: {backup_file_path}")

        # Step 2: Convert the file
        transform_datfile(ampl_file_path, converted_file_path)
        print(f"Converted file created: {converted_file_path}")

        # Step 3: Overwrite the original file with the converted file
        shutil.copy(converted_file_path, final_file_path)
        print(f"Overwritten original in scenarios folder: {final_file_path}")

    print("\n**All scenario files have been processed successfully!**")


if __name__ == "__main__":
    process_scenario_files()


