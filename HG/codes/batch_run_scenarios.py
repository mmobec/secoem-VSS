"""
Runs modular_ec_run's single-day pipeline (DA market) for the first day of
every scenario-count folder under a scenarios_AMPL_{same,dif}_ren directory
(generated in scentree-gen-remote), and appends one CSV row of metrics per run.

Each worker process is pinned to a disjoint set of CPU cores (lanes) so that
"cores used" is precisely known even when several instances solve in parallel.

Usage:
  python batch_run_scenarios.py \
      --root /path/to/scenarios_AMPL/scenarios_AMPL_same_ren \
      --ren-type same_ren \
      --branch-label 15min_ren_same \
      --csv /path/to/results.csv \
      --lanes 16 --threads 4 --time-limit 7200

Resumable: rows already present in --csv with status "ok" for a given
(ren_type, num_scenarios_folder) are skipped on rerun.
"""

import argparse
import contextlib
import csv
import io
import os
import re
import socket
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

CODES_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODES_DIR)

GUROBI_NODE_RE = re.compile(r"Explored (\d+) nodes? \((\d+) simplex iterations")
GUROBI_GAP_RE = re.compile(
    r"Best objective ([\-\d.e+]+), best bound ([\-\d.e+]+), gap ([\-\d.]+)%"
)

FIELDNAMES = [
    "ren_type", "branch", "num_scenarios_folder", "scenario_dir",
    "lane", "pinned_cores", "concurrency_lanes", "threads_per_solve",
    "pid", "hostname",
    "loadavg_1min_start", "loadavg_1min_end",
    "num_scenarios_original", "num_scenarios_reduced", "num_scenarios_in_model",
    "preprocess_time_s", "build_instance_time_s", "solve_time_s", "wall_time_total_s",
    "solver_status", "termination_condition", "solver_message", "solver_wallclock_time_s",
    "num_variables", "num_constraints", "num_binary_vars", "num_integer_vars",
    "lower_bound", "upper_bound",
    "gurobi_nodes_explored", "gurobi_simplex_iterations",
    "gurobi_best_objective", "gurobi_best_bound", "gurobi_gap_pct",
    "obj_fun", "obj_DA_income", "obj_RM_income", "obj_IM_income",
    "obj_IB_income", "obj_IB_costs", "obj_IB_net", "obj_FD_costs",
    "results_dir", "solver_log_path",
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


def _worker_init(lane_queue, threads_per_solve):
    global _LANE, _CORES
    _LANE = lane_queue.get()
    _CORES = list(range(_LANE * threads_per_solve, _LANE * threads_per_solve + threads_per_solve))
    if hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, _CORES)
        except OSError:
            pass


def _run_one(num_scen, family_dir, ren_type, branch_label, threads_per_solve,
             time_limit, n_lanes):
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
    try:
        row["loadavg_1min_start"] = os.getloadavg()[0]
    except OSError:
        pass

    t_wall_start = time.time()

    try:
        import config_definition as cfg
        cfg.PROJECT_ROOT = __import__("pathlib").Path(CODES_DIR).resolve().parent
        cfg.famscen_all = os.path.basename(family_dir)
        cfg.pathscen_all = family_dir
        cfg.SIMS = ["001"]
        cfg.SOLVER_OPTIONS["TimeLimit"] = time_limit
        cfg.SOLVER_OPTIONS["Threads"] = threads_per_solve

        from simulation_context import SimulationContext
        from preprocessing import PreProcessor
        from instancemanager import InstanceManager
        from solver import Solver
        from postprocess import PostProcess

        sim_ctx = SimulationContext(sim="001", market="DA", include_hydro=False)
        preprocessing = PreProcessor(sim_ctx)

        t0 = time.time()
        scenario_data, model = preprocessing.run_preprocessing()
        row["preprocess_time_s"] = time.time() - t0
        row["num_scenarios_original"] = int(scenario_data["nS"])
        row["num_scenarios_reduced"] = len(preprocessing.S_preserved)

        instance_wrapper = InstanceManager(scenario_data, sim_ctx, model)
        t0 = time.time()
        instance_wrapper.compute_instance()
        row["build_instance_time_s"] = time.time() - t0

        log_buf = io.StringIO()
        t_solve_start = time.time()
        results = None
        solve_exc = None
        try:
            with contextlib.redirect_stdout(log_buf):
                results = Solver(instance_wrapper, sim_ctx).solve()
        except Exception as e:
            solve_exc = e
        solver_log = log_buf.getvalue()

        try:
            log_path = os.path.join(str(sim_ctx.pathres), "solver_log.txt")
            with open(log_path, "w") as lf:
                lf.write(solver_log)
            row["solver_log_path"] = log_path
        except OSError:
            pass

        # sim_ctx.solve_time is only set by solver.py if solve() returned
        # normally; on abort (e.g. TimeLimit hit with no loadable solution)
        # fall back to our own wall-clock measurement around the call.
        row["solve_time_s"] = sim_ctx.solve_time if sim_ctx.solve_time is not None else (time.time() - t_solve_start)
        row["num_scenarios_in_model"] = sim_ctx.n_scenarios

        m_nodes = GUROBI_NODE_RE.search(solver_log)
        if m_nodes:
            row["gurobi_nodes_explored"] = int(m_nodes.group(1))
            row["gurobi_simplex_iterations"] = int(m_nodes.group(2))
        m_gap = GUROBI_GAP_RE.search(solver_log)
        if m_gap:
            row["gurobi_best_objective"] = float(m_gap.group(1))
            row["gurobi_best_bound"] = float(m_gap.group(2))
            row["gurobi_gap_pct"] = float(m_gap.group(3))

        if solve_exc is not None:
            # No loadable solution (e.g. Gurobi status "aborted" after
            # hitting TimeLimit with no incumbent). Record what we know
            # from the log/preprocessing and move on without postprocessing.
            row["status"] = "timeout_no_solution"
            row["solver_status"] = "aborted"
            row["termination_condition"] = "maxTimeLimit_noSolution"
            row["error"] = f"{type(solve_exc).__name__}: {solve_exc}"
            row["results_dir"] = str(sim_ctx.pathres)
        else:
            try:
                solver_block = results.solver
                row["solver_status"] = str(getattr(solver_block, "status", ""))
                row["termination_condition"] = str(getattr(solver_block, "termination_condition", ""))
                row["solver_message"] = str(getattr(solver_block, "message", ""))
                wc = getattr(solver_block, "wallclock_time", None)
                if wc is None:
                    wc = getattr(solver_block, "time", None)
                row["solver_wallclock_time_s"] = wc
            except Exception:
                pass

            try:
                prob_block = results.problem[0]
                row["num_variables"] = getattr(prob_block, "number_of_variables", None)
                row["num_constraints"] = getattr(prob_block, "number_of_constraints", None)
                row["num_binary_vars"] = getattr(prob_block, "number_of_binary_variables", None)
                row["num_integer_vars"] = getattr(prob_block, "number_of_integer_variables", None)
                row["lower_bound"] = getattr(prob_block, "lower_bound", None)
                row["upper_bound"] = getattr(prob_block, "upper_bound", None)
            except Exception:
                pass

            postprocess = PostProcess(results, instance_wrapper.instance, sim_ctx)
            postprocess.perform_nac_checks()
            postprocess.store_results()

            for k, v in sim_ctx.obj_results.items():
                row[k] = v

            row["results_dir"] = str(sim_ctx.pathres)
            row["status"] = "ok"

    except Exception as e:
        row["status"] = "error"
        row["error"] = f"{type(e).__name__}: {e}"
        row["traceback"] = traceback.format_exc()

    try:
        row["loadavg_1min_end"] = os.getloadavg()[0]
    except OSError:
        pass
    row["wall_time_total_s"] = time.time() - t_wall_start

    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="scenarios_AMPL_{same,dif}_ren directory")
    ap.add_argument("--ren-type", required=True)
    ap.add_argument("--branch-label", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--lanes", type=int, default=16)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--time-limit", type=int, default=7200)
    ap.add_argument("--only", default=None, help="comma-separated scenario counts to run, e.g. 50,60")
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
        initargs=(lane_queue, args.threads),
    ) as executor:
        futures = {
            executor.submit(
                _run_one, num_scen, family_dir, args.ren_type, args.branch_label,
                args.threads, args.time_limit, n_lanes,
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
            print(f"  [{row['status']}] sc={num_scen} solve_time={row.get('solve_time_s')} "
                  f"reduced={row.get('num_scenarios_reduced')}/{row.get('num_scenarios_original')}")

    csv_file.close()
    print("Batch complete.")


if __name__ == "__main__":
    main()
