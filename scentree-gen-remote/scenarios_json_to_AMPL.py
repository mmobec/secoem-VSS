"""
Converts the scenario data from JSON to AMPL following the structure given in the JSON. 
Current version considers:
- The data can be hourly or quarterly 
- For the IB we are given the IB+ (IB_UP) and IB- (IB_DOWN).


Structure of the JSON:

[
DAY1 {"num_scenarios": 15,
     "num_stages": 30,
     "in_sample_prediction": true,
     "scenario_tree_data": [
        [SCEN1],
        [SCEN2],
        ...
        ],
     "mean_value_scenario_tree": [(SZE 816)],
     "predicted_value": [(SZE 816)],
     "observed_value": [(SZE 816)],
     "scenario_probabilities": ["float, ..."],
     "mapping_datasets_columns": [
        {
        "dataset": DA,      
        "columns": ["int, ..."],  
        "stage_ids": ["int, ..."] 
        },
        ...
     ],

     "tree": [
        {
        "key": ["int", "int"],       
        "scenario_ids": ["int, ..."],   
        "parent_key": ["int", "int"] ,  
        "description": "string"         
        }
     ]
    },
DAY2 {...},
]


"""

"""
JSON Scenario Tree -> AMPL formatter
=====================================
Input:  JSON array with one scenario tree object per day [{}, {}, ...]
        All files are read from and written to the same folder.
Output: One AMPL .dat file per day, named:
        <last_folder_name>-001.dat, <last_folder_name>-002.dat, ...
        containing:
    - nS, nSG
    - nRVSG
    - ScenF (predicted_value)
    - ScenO (observed_value)
    - Scen0 (scenario_tree_data)
    - Prob0 (scenario_probabilities)
    - set c[stage, cluster] (tree structure)
"""

import json
import os
import glob


def compute_nRVSG(mapping_datasets_columns, num_stages):
    """
    Computes nRVSG: number of random variables per stage.
    For each stage, counts how many columns are assigned to it
    according to mapping_datasets_columns.
    Only stages with count > 0 are included.
    """
    stage_counts = {}
    for dataset in mapping_datasets_columns:
        for stage in dataset["stage_ids"]:
            stage_counts[stage] = stage_counts.get(stage, 0) + int(len(dataset["columns"])/len(dataset["stage_ids"]))
    return stage_counts


def format_nRVSG(stage_counts, num_stages):
    """
    Formats nRVSG in the compact AMPL style:
    groups of 10 pairs per line, aligned.
    """
    pairs = [(s, stage_counts[s]) for s in sorted(stage_counts.keys())]

    lines = ["param nRVSG :="]
    group_size = 10
    for i in range(0, len(pairs), group_size):
        chunk = pairs[i:i + group_size]
        row = "  " + "   ".join(f"{s:2d} {c:3d}" for s, c in chunk)
        lines.append(row)
    lines.append(";")
    return "\n".join(lines)


def format_scen_flat(name, values):
    """
    Formats ScenF or ScenO as a flat AMPL param block.
    5 index-value pairs per line.
    """
    lines = [f"param {name} :="]
    group_size = 5
    items = list(enumerate(values, start=1))
    for i in range(0, len(items), group_size):
        chunk = items[i:i + group_size]
        row = "  " + "   ".join(f"{idx:3d} {v:10.4f}" for idx, v in chunk)
        lines.append(row)
    lines.append(";")
    return "\n".join(lines)


def format_scen0(scenario_tree_data):
    """
    Formats Scen0 as a transposed (tr) matrix: scenarios x columns.
    param Scen0 (tr)
     :   1   2  ...  N :=
        s1 v1 v2 ... vN
        ...
    ;
    """
    num_scenarios = len(scenario_tree_data)
    if num_scenarios == 0:
        return "param Scen0 (tr)\n;\n"

    num_cols = len(scenario_tree_data[0])

    # Column index header
    col_header = "  " + " ".join(f"{c:7d}" for c in range(1, num_cols + 1))

    lines = ["param Scen0 (tr)"]
    lines.append(col_header + " :=")

    for s_idx, scenario in enumerate(scenario_tree_data, start=1):
        vals = " ".join(f"{v:8.4f}" for v in scenario)
        lines.append(f"  {s_idx:3d} {vals}")

    lines.append(";")
    return "\n".join(lines)


def format_prob0(scenario_probabilities):
    """
    Formats Prob0: probability of each scenario.
    """
    lines = ["param Prob0 :="]
    for i, p in enumerate(scenario_probabilities, start=1):
        lines.append(f"  {i:4d} {p:.17f}")
    lines.append(";")
    return "\n".join(lines)


def format_tree_sets(tree):
    """
    Formats set c[stage, cluster] from the JSON tree.
    Each tree node has key=[stage, cluster] and a list of scenario_ids.
    Nodes are sorted by stage, then cluster.
    """
    lines = []
    sorted_nodes = sorted(tree, key=lambda n: (n["key"][0], n["key"][1]))
    for node in sorted_nodes:
        stage   = node["key"][0]
        cluster = node["key"][1]
        ids     = " ".join(str(s) for s in node["scenario_ids"])
        lines.append(f"set c[{stage},{cluster}] := {ids};")
    return "\n".join(lines)


def day_to_ampl(data):
    """
    Converts a single scenario tree object (one day) to AMPL .dat content string.
    """
    num_scenarios      = data["num_scenarios"]
    num_stages         = data["num_stages"]
    scenario_tree_data = data["scenario_tree_data"]
    predicted_value    = data["predicted_value"]
    observed_value     = data["observed_value"]
    scenario_probs     = data["scenario_probabilities"]
    mapping            = data["mapping_datasets_columns"]
    tree               = data["tree"]

    stage_counts = compute_nRVSG(mapping, num_stages)

    blocks = []

    # --- nS, nSG ---
    blocks.append(f"param nS :=  {num_scenarios:4d};")
    blocks.append(f"param nSG :=  {num_stages:4d};")
    blocks.append("")

    # --- nRVSG ---
    blocks.append(format_nRVSG(stage_counts, num_stages))
    blocks.append("")

    # --- ScenF: predicted (forecasted) values ---
    blocks.append(format_scen_flat("ScenF", predicted_value))
    blocks.append("")

    # --- ScenO: observed values ---
    blocks.append(format_scen_flat("ScenO", observed_value))
    blocks.append("")

    # --- Scen0: full scenario tree data matrix ---
    blocks.append(format_scen0(scenario_tree_data))
    blocks.append("")

    # --- Prob0: scenario probabilities ---
    blocks.append(format_prob0(scenario_probs))
    blocks.append("")

    # --- set c[stage, cluster]: tree node membership ---
    blocks.append(format_tree_sets(tree))
    blocks.append("")

    return "\n".join(blocks)


def process_file(input_path):
    """
    Reads a JSON file containing an array of scenario tree objects (one per day).
    Writes one .dat file per object in the same folder as the input file.
    Output filenames: <last_folder_name>-001.dat, <last_folder_name>-002.dat, ...
    """
    folder     = os.path.dirname(os.path.abspath(input_path))
    folder_name = os.path.basename(folder)

    with open(input_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    # Accept both a single object and an array
    if isinstance(records, dict):
        records = [records]

    written = []
    for idx, data in enumerate(records, start=1):
        content   = day_to_ampl(data)
        filename  = f"{folder_name}-{idx:03d}_DA.dat"
        out_path  = os.path.join(folder, filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(out_path)
        print(f"  OK  {filename}  (day {idx}/{len(records)})")

    return written


def run(input_dir="scenarios/FTC_20251031_20251130_c30_sc10_15min_ren_same"):
    """
    Processes all JSON scenario tree files found in input_dir.
    Output .dat files are written to the same folder as each input file.
    """
    pattern    = os.path.join(input_dir, "*.json")
    json_files = glob.glob(pattern)

    if not json_files:
        print(f"No JSON files found in '{input_dir}'")
        return

    print(f"\nInput dir: {input_dir}\n")

    for jf in sorted(json_files):
        print(f"Processing: {jf}")
        process_file(jf)

    print("\nDone.")

# --- CLI ---
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JSON scenario tree -> AMPL .dat (one file per day)")
    parser.add_argument("--input-dir", default="scenarios/FTC_20251031_20251130_c30_sc300_15min_ren_same", help="Folder with input JSON files")
    args = parser.parse_args()

    run(input_dir=args.input_dir)

    #USAGE: python scenarios_json_to_AMPL.py --input-dir "scenarios/FTC_20251031_20251130_c30_sc10_15min_different_ren"