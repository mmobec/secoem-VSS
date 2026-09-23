"""
Runs the VSS study (static EEV_t/VSS_t via vssd/run_static_vss.py, dynamic
EDEV_t/VSSD_t via vssd/run_vssd.py) for sim "001" of every scenario-count
folder under a scenarios_AMPL_{QHS,HG} directory (generated in
scentree-gen-remote), and appends one CSV row of summary metrics per run.

Mirrors batch_run_scenarios.py's process-per-folder / lane-pinning /
resumable-CSV design, but calls the VSS chain functions instead of a plain
DA solve. Each folder does two independent full solves of RP (one inside
compute_static_chain, one inside compute_vssd_chain) since that is how the
two scripts are meant to be run standalone -- not optimized further here to
avoid touching the VSS/VSSD research code itself.

Usage:
  python batch_run_vss.py \
      --root /path/to/scenarios_AMPL/scenarios_AMPL_QHS \
      --ren-type dif_ren \
      --branch-label 15min_different_ren \
      --csv /path/to/vss_summary.csv \
      --lanes 16 --threads 4 --time-limit 14400

Resumable: rows already present in --csv with status "ok" for a given
(ren_type, num_scenarios_folder) are skipped on rerun.
"""

import argparse
import csv
import os
import re
import socket
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODES_DIR)

FIELDNAMES = [
    "ren_type", "branch", "num_scenarios_folder", "scenario_dir",
    "lane", "pinned_cores", "concurrency_lanes", "threads_per_solve",
    "pid", "hostname",
    "static_time_s", "vssd_time_s", "wall_time_total_s",
    "rp_value", "ev_value",
    "vss_2", "vss_6", "excluded_weight_static_6",
    "edev_6", "vssd", "vssd_6", "excluded_weight_dynamic_6",
    "vssd2_recourse", "excluded_weight_dynamic2_recourse",
    "propositions_valid",
    "status", "error", "traceback",
]

_LANE = None
_CORES = None


def discover_scenario_dirs(root):
    entries = []
    for d in sorted(os.listdir(root)):
        full = os.path.join(root, d)
        da_dir = os.path.join(full, "DA")
        if not os.path.isdir(da_dir):
            continue
        m = re.search(r"_sc(\d+)_", d)
        if not m:
            continue
        entries.append((int(m.group(1)), full))
    return sorted(entries)


def load_done_keys(csv_path):
    done = set()
    if not os.path.isfile(csv_path):
        return done
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "ok":
                done.add((row.get("ren_type"), row.get("num_scenarios_folder")))
    return done


def _worker_init(lane_queue, threads_per_solve, core_offset=0):
    global _LANE, _CORES
    _LANE = lane_queue.get()
    base = core_offset + _LANE * threads_per_solve
    _CORES = list(range(base, base + threads_per_solve))
    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, _CORES)
        except OSError:
            pass


def _run_one(num_scen, family_dir, ren_type, branch_label, threads_per_solve,
             time_limit, n_lanes, project_root=None):
    row = {fn: "" for fn in FIELDNAMES}
    row.update({
        "ren_type": ren_type,
        "branch": branch_label,
        "num_scenarios_folder": num_scen,
        "scenario_dir": family_dir,
        "lane": _LANE,
        "pinned_cores": ",".join(map(str, _CORES)) if _CORES else "",
        "concurrency_lanes": n_lanes,
        "threads_per_solve": threads_per_solve,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
    })

    t_wall_start = time.time()
    try:
        import config_definition as cfg
        cfg.PROJECT_ROOT = (
            __import__("pathlib").Path(project_root) if project_root
            else __import__("pathlib").Path(CODES_DIR).resolve().parent
        )
        cfg.famscen_all = os.path.basename(family_dir)
        cfg.pathscen_all = family_dir
        cfg.SIMS = ["001"]
        cfg.SOLVER_OPTIONS["TimeLimit"] = time_limit
        cfg.SOLVER_OPTIONS["Threads"] = threads_per_solve

        from vssd.run_static_vss import compute_static_chain
        from vssd.run_vssd import compute_vssd_chain

        t0 = time.time()
        static_result = compute_static_chain("001")
        row["static_time_s"] = time.time() - t0

        t0 = time.time()
        vssd_result = compute_vssd_chain("001")
        row["vssd_time_s"] = time.time() - t0

        row["rp_value"] = static_result["rp_value"]
        row["ev_value"] = static_result["ev_value"]
        row["vss_2"] = static_result["vss_by_stage"].get(2)
        row["vss_6"] = static_result["vss_by_stage"].get(6)
        row["excluded_weight_static_6"] = static_result["excluded_weight_by_stage"].get(6)

        row["edev_6"] = vssd_result["edev_by_stage"].get(6)
        row["vssd"] = vssd_result["vssd"]
        row["vssd_6"] = vssd_result["vssd_by_stage"].get(6)
        row["excluded_weight_dynamic_6"] = vssd_result["excluded_weight_by_stage"].get(6)
        row["vssd2_recourse"] = vssd_result["vssd2_recourse"]
        row["excluded_weight_dynamic2_recourse"] = vssd_result["edev2_recourse_excluded_weight"]
        row["propositions_valid"] = vssd_result["validation"]["ok"]

        row["status"] = "ok"

    except Exception as e:
        row["status"] = "error"
        row["error"] = f"{type(e).__name__}: {e}"
        row["traceback"] = traceback.format_exc()

    row["wall_time_total_s"] = time.time() - t_wall_start
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="scenarios_AMPL_{QHS,HG} directory")
    ap.add_argument("--ren-type", required=True)
    ap.add_argument("--branch-label", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--lanes", type=int, default=16)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--time-limit", type=int, default=14400)
    ap.add_argument("--only", default=None, help="comma-separated scenario counts to run, e.g. 50,60")
    ap.add_argument("--project-root", default=None,
                     help="override cfg.PROJECT_ROOT (results/<famscen>/... lands here); "
                          "defaults to the codes/ dir's parent")
    ap.add_argument("--core-offset", type=int, default=0,
                     help="shift pinned core ranges by this many cores, so a concurrent "
                          "batch (e.g. QHS's own run) doesn't collide on the same physical "
                          "cores -- lane L is pinned to [core_offset + L*threads, ...)")
    args = ap.parse_args()

    entries = discover_scenario_dirs(args.root)
    if args.only:
        wanted = {int(x) for x in args.only.split(",")}
        entries = [e for e in entries if e[0] in wanted]

    done = load_done_keys(args.csv)
    todo = [e for e in entries if (args.ren_type, str(e[0])) not in done]

    print(f"Found {len(entries)} folders, {len(entries) - len(todo)} already done, {len(todo)} to run.")
    if not todo:
        return

    write_header = not os.path.isfile(args.csv)
    csv_file = open(args.csv, "a", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
    if write_header:
        writer.writeheader()
        csv_file.flush()

    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    manager = ctx.Manager()
    lane_queue = manager.Queue()
    n_lanes = min(args.lanes, len(todo))
    for lane in range(n_lanes):
        lane_queue.put(lane)

    with ProcessPoolExecutor(
        max_workers=n_lanes,
        mp_context=ctx,
        initializer=_worker_init,
        initargs=(lane_queue, args.threads, args.core_offset),
    ) as executor:
        futures = {
            executor.submit(
                _run_one, num_scen, family_dir, args.ren_type, args.branch_label,
                args.threads, args.time_limit, n_lanes, args.project_root,
            ): num_scen
            for num_scen, family_dir in todo
        }
        for fut in as_completed(futures):
            num_scen = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                row = {fn: "" for fn in FIELDNAMES}
                row["ren_type"] = args.ren_type
                row["branch"] = args.branch_label
                row["num_scenarios_folder"] = num_scen
                row["status"] = "error"
                row["error"] = f"worker crashed: {type(e).__name__}: {e}"
            writer.writerow(row)
            csv_file.flush()
            os.fsync(csv_file.fileno())
            print(f"  [{row['status']}] sc={num_scen} static_time={row.get('static_time_s')} "
                  f"vssd_time={row.get('vssd_time_s')} vssd_6={row.get('vssd_6')}")

    csv_file.close()
    print("Batch complete.")


if __name__ == "__main__":
    main()
