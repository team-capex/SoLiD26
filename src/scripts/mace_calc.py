"""Read a data file and apply a MACE calculator."""

import argparse
import json
import logging
from pathlib import Path

import ase.io  # type: ignore
import ase.db  # type: ignore
import numpy as np  # type: ignore
import mace.calculators  # type: ignore

from utils import add_job_args_to_parser, setup_job_dir_and_logging


def read_atoms_from_file(file_path):
    if Path(file_path).suffix == ".xyz":
        atoms_list = ase.io.read(file_path, index=":")
    elif Path(file_path).suffix in [".db", ".aselmdb"]:
        with ase.db.connect(file_path) as db:
            atoms_list = [row.toatoms() for row in db.select()]
    else:
        raise ValueError(f"Unsupported file format: {Path(file_path).suffix}")
    return atoms_list


def get_energy_and_forces_from_atoms(atoms, i):
    # Note: Use apply_constraint=False to get the true forces and energy, not the constrained ones.
    if not atoms.calc is None:
        energy = atoms.get_potential_energy(apply_constraint=False)
    elif "energy" in atoms.info:
        energy = atoms.info["energy"]
    elif "MACE_energy" in atoms.info:
        energy = atoms.info["MACE_energy"]
    else:
        raise ValueError(f"Energy not found in atoms object at index {i}.")
    if not atoms.calc is None:
        forces = atoms.get_forces(apply_constraint=False)
    elif "forces" in atoms.arrays:
        forces = atoms.arrays["forces"]
    elif "MACE_forces" in atoms.arrays:
        forces = atoms.arrays["MACE_forces"]
    else:
        raise ValueError(f"Forces not found in atoms object at index {i}.")
    assert forces.shape == (len(atoms), 3), (
        f"Forces shape {forces.shape} is not correct for atoms object at index {i}."
    )
    return energy, forces


def main(args):
    # Check arguments
    assert Path(args.data).is_file(), f"{args.data} is not a file."
    assert Path(args.model).is_file(), f"{args.model} is not a file."
    assert args.device in ["cpu", "cuda", "mps", "xpu"], f"{args.device} is not a valid device."
    # Setup job
    job_dir = setup_job_dir_and_logging(args)
    logging.info("Ready to work!")
    logging.info(f"Job directory: {job_dir.resolve()}")
    # Prepare output directory
    output_dir = Path("/tmp/output") if args.tmp else job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configure calculator
    logging.info(
        f"Configure calculator with model: {args.model}, device: {args.device}, "
        f"d3: {args.d3}, cueq: {args.enable_cueq}"
    )
    calc = mace.calculators.mace_mp(
        model=args.model,
        device=args.device,
        dispersion=args.d3,
        damping="zero",
        enable_cueq=args.enable_cueq,
    )

    # Read input data file
    logging.info(f"Reading data file: {args.data}")
    atoms_list = read_atoms_from_file(args.data)

    N = len(atoms_list)
    logging.info(f"Number of configurations: {N}")

    # Running sums for error metrics
    total_atoms = 0
    energy_sae = 0.0  # Sum of absolute errors
    energy_sse = 0.0  # Sum of squared errors
    energy_saepa = 0.0  # Sum of absolute errors per atom
    energy_ssepa = 0.0  # Sum of squared errors per atom
    forces_sae = 0.0  # Sum of absolute errors
    forces_sse = 0.0  # Sum of squared errors

    # Apply calculator to atoms
    logging.info("Apply calculator and computing errors for each configuration...")
    for i, atoms in enumerate(atoms_list):
        # Get original energy and forces
        energy1, forces1 = get_energy_and_forces_from_atoms(atoms, i)

        atoms.calc = calc  # Attach the calculator to the atoms object
        atoms.get_potential_energy()  # Calculate energy and forces

        # Get calculated energy and forces
        energy2, forces2 = get_energy_and_forces_from_atoms(atoms, i)

        # Prepare atoms object for output
        atoms.calc = None
        atoms.info["energy"] = energy2
        atoms.arrays["forces"] = forces2

        # Calculate running errors
        num_atoms = len(atoms)
        total_atoms += num_atoms
        delta_e = energy1 - energy2
        delta_e_pa = delta_e / num_atoms
        delta_f = forces1 - forces2

        assert delta_f.shape == (num_atoms, 3), (
            f"Error forces shape {delta_f.shape} is not correct for configuration at index {i}."
        )

        energy_sae += np.abs(delta_e)
        energy_sse += np.square(delta_e)
        energy_saepa += np.abs(delta_e_pa)
        energy_ssepa += np.square(delta_e_pa)
        forces_sae += np.sum(np.abs(delta_f))
        forces_sse += np.sum(np.square(delta_f))

        if (i + 1) % 10_000 == 0:
            logging.info(f"Processed {i + 1}/{N} configurations.")

    # Calculate final errors
    results = {}
    results["energy_mae"] = energy_sae / N
    results["energy_rmse"] = np.sqrt(energy_sse / N)
    results["energy_maepa"] = energy_saepa / N
    results["energy_rmsepa"] = np.sqrt(energy_ssepa / N)
    results["forces_mae"] = forces_sae / (total_atoms * 3)
    results["forces_rmse"] = np.sqrt(forces_sse / (total_atoms * 3))

    # Print results
    logging.info("Error metrics:")
    for key in results:
        logging.info(f"{key:<15}: {results[key]:.8f} {results[key]:.4f}")

    logging.info("Save results...")

    # Save error metrics json file
    output_path = output_dir / "error_metrics.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=4)

    # Save atoms xyz file
    if args.save_xyz:
        output_name = Path(args.data).name
        output_path = output_dir / output_name
        ase.io.write(output_path, images=atoms_list, format="extxyz")

    logging.info("All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read a data file and apply a MACE calculator.")
    parser.add_argument("--data", help="Path to input data file.", required=True)
    parser.add_argument("--model", help="Path to model file.", required=True)
    parser.add_argument("--device", help="Device to use (cpu,cuda,mps,xpu).", default="cuda")
    parser.add_argument(
        "--enable_cueq",
        action="store_true",
        help="Enable cuequivariance acceleration.",
    )
    parser.add_argument(
        "--d3",
        action="store_true",
        help="Create calculator with D3 dispersion corrections.",
    )
    parser.add_argument(
        "--save_xyz",
        action="store_true",
        help="Save the results to a .xyz file.",
    )
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
