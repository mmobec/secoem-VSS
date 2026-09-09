"""
Batch driver: imports day_to_ampl() from scenarios_json_to_AMPL.py (the
low-level per-day converter) and adds discovery + output reorganization
on top of it. Builds scenarios_AMPL/ from every results_N.json (one per
day) of every scenariotree_XX folder under dif_ren_scentree and
same_ren_scentree -- this is the script to run for QHS/HG conversion,
not scenarios_json_to_AMPL.py's own standalone run()/CLI, which writes
.dat files back into the same input folder instead.

Output layout:
  scenarios_AMPL/
    scenarios_AMPL_QHS/
      FTC_20251031_20251130_c31_scXX_15min_different_ren/
        DA/
          FTC_20251031_20251130_c31_scXX_15min_different_ren-NNN_DA.dat
    scenarios_AMPL_HG/
      FTC_20251031_20251130_c31_scXX_15min_same_ren/
        DA/
          FTC_20251031_20251130_c31_scXX_15min_same_ren-NNN_DA.dat
"""

import os
import re
import json

from scenarios_json_to_AMPL import day_to_ampl

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCES = [
    {
        "src_root": os.path.join(SCRIPT_DIR, "dif_ren_scentree"),
        "out_subfolder": "scenarios_AMPL_QHS",
        "ren_suffix": "different_ren",
    },
    {
        "src_root": os.path.join(SCRIPT_DIR, "same_ren_scentree"),
        "out_subfolder": "scenarios_AMPL_HG",
        "ren_suffix": "same_ren",
    },
]

OUT_ROOT = os.path.join(SCRIPT_DIR, "scenarios_AMPL")


def extract_num_scenarios(folder_name):
    m = re.fullmatch(r"scenariotree_(\d+)", folder_name)
    if not m:
        return None
    return int(m.group(1))


def load_day(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    if isinstance(records, list):
        return records[0]
    return records


def find_result_files(tree_dir):
    """
    Returns [(day_index, json_path), ...] sorted by day_index, for every
    results_N.json in tree_dir.
    """
    results = []
    for fname in os.listdir(tree_dir):
        m = re.fullmatch(r"results_(\d+)\.json", fname)
        if m:
            results.append((int(m.group(1)), os.path.join(tree_dir, fname)))
    return sorted(results)


def main():
    total = 0
    for source in SOURCES:
        src_root = source["src_root"]
        ren_suffix = source["ren_suffix"]
        out_subfolder = source["out_subfolder"]

        tree_folders = sorted(
            d for d in os.listdir(src_root)
            if os.path.isdir(os.path.join(src_root, d))
        )

        for tree_folder in tree_folders:
            num_scen = extract_num_scenarios(tree_folder)
            if num_scen is None:
                print(f"  SKIP  {tree_folder} (unexpected folder name)")
                continue

            tree_dir = os.path.join(src_root, tree_folder)
            result_files = find_result_files(tree_dir)
            if not result_files:
                print(f"  SKIP  {tree_folder} (no results_N.json)")
                continue

            base_name = f"FTC_20251031_20251130_c31_sc{num_scen}_15min_{ren_suffix}"
            out_dir = os.path.join(OUT_ROOT, out_subfolder, base_name, "DA")
            os.makedirs(out_dir, exist_ok=True)

            for day_idx, json_path in result_files:
                out_path = os.path.join(out_dir, f"{base_name}-{day_idx:03d}_DA.dat")

                day_data = load_day(json_path)
                content = day_to_ampl(day_data)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(content)

                total += 1

            print(f"  OK  {tree_folder}  ({len(result_files)} days) -> {out_dir}")

    print(f"\nDone. Wrote {total} .dat files.")


if __name__ == "__main__":
    main()
