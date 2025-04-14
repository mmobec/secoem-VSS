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

## Repository Structure

### 1. Data Files

Data is spread through several files. It is divided in two directories. The directory `data/` contains all deterministic parameters and the directory `scenarios/` contains all uncertain parameters:

a. `data/ec_BESS.dat` AMPL data file containing the values of the battery's parameters.

b. `data/demand.dat` AMPL data file containing the values of the flexible demand's parameters. 

c. `data/ec_wind.dat` AMPL data file containing the values of the wind farm and solar PV parameters.

d. `data/market.dat` AMPL data file containing the market parameters.

e. `scenarios/famscen("nom de la familia")/famscen-SIM.dat` AMPL data file containing the values of all scenarios (all electricity market prices and wind and PV generation). It also contains the cluster structure to represent the scenario tree.

See Section *Convert AMPL Data to Pyomo Format* on converting the AMPL data files into Pyomo data files.

### 2. Code Files

The code files are in the directory `codes/`:

a. `codes/ec_model.py` contains the optimization model in a Pyomo Abstract Model format. It follows the mathematical formulation found in `model_formulation/ec_model_formulation.pdf`.

b. `codes/ec_run.py` controls the execution of the model. It loads the optimization model in `codes/ec_model.py`, loads the required data in `data/` and `scenarios/`, executes the model in the specified days and stores the results in `results/`.

### 3. Results Files

The directory `results/` contains the results files of the days for which the model has been executed. 

They are indexed by scenario family. This means that if the code has been executed for the scenario family `famscen`, the results will be stored in `results/famscen/`.

### 4. Mathematical Formulation Files

An updated mathematical formulation in `LaTeX` of the optimization model in `codes/ec_model.py` is maintained in the file `model_formulation/ec_model_formulation.pdf`.

## Notes

- If you re-run the simulation, results will be overwritten.
- The `results/` folder is ignored in Git to keep the repository clean.

---

### License
This project is licensed under the GNU License - see the [LICENSE](LICENSE) file for details.

### Contact
For questions or contributions, please open an issue or contact the repository maintainers.
