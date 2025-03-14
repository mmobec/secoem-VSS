# MMOBEC-Pyomo: Energy Community Optimization with Pyomo

## Table of Contents
1. [Introduction](#introduction)
2. [Setting Up the Environment](#setting-up-the-environment)
3. [Workflow](#workflow)
4. [Running the Simulation](#running-the-simulation)
5. [Output and Results](#output-and-results)
6. [Notes](#notes)

---

## Introduction

**MMOBEC-Pyomo** is an optimization model for an energy community interacting with the electricity market to maximize profits. The model is implemented using the **Pyomo** library, replacing an AMPL-based formulation. 

The energy community consists of:
- **Flexible Demand** (implicit modeling)
- **Wind Farm**
- **Solar Farm**
- **Battery Energy Storage System (BESS)**

The problem is formulated as a **multi-stage stochastic optimization** for scheduling energy production, consumption, and trading.

---

## Setting Up the Environment

This project requires **Python 3.11+** and dependencies listed in `optirec_env.yml`.

### 1. Install Conda (if not installed)
If you haven't installed Conda, download and install [Miniconda](https://docs.conda.io/en/latest/miniconda.html).

### 2. Clone the Repository
```sh
git clone https://github.com/mmobec/mmobec-pyomo.git
cd mmobec-pyomo
conda env create -f python_environment/optirec_env.yml
conda activate optirec_env
```

---

## Workflow

1. Copy your AMPL-formatted `.dat` scenario files into the `scenarios/` folder.
2. Ensure the directory follows the naming convention, e.g., `FTC_10_2023_12/` for a 10-scenario simulation.

### Convert AMPL Data to Pyomo Format
Navigate to the `pre_process_AMPL_to_Pyomo_scenario_data/` directory:

```sh
cd pre_process_AMPL_to_Pyomo_scenario_data
```

Run the conversion script:

```sh
python ampl_to_pyomo_scenario_files.py
```

This script:
- Reads `.dat` scenario files from `scenarios/`
- Converts them into a format compatible with Pyomo
- Overwrites the files in `scenarios/`

---

## Running the Simulation

Navigate to the `codes/` directory:

```sh
cd ../codes
```

Run the optimization model:

```sh
python ec_run.py
```

This will:
- Load the scenario data from `scenarios/`
- Optimize the energy scheduling
- Store results in the `results/` directory

---

## Output and Results

- The results of the optimization will be stored in the `results/` directory.
- The output includes scheduled energy production, consumption, and trading strategies.

---

## Notes

- If you re-run the simulation, results will be overwritten.
- The `results/` folder is ignored in Git to keep the repository clean.

---

### License
This project is licensed under the GNU License - see the [LICENSE](LICENSE) file for details.

### Contact
For questions or contributions, please open an issue or contact the repository maintainers.
