"""Read data from files and write to database."""

import argparse
import logging
import os
from multiprocessing import Pool
from pathlib import Path

import ase.db  # type: ignore

from vasp import Vasp  # Use a modified Vasp calculator class
from utils import add_job_args_to_parser, setup_job_dir_and_logging


def get_calc_params_from_outcar_path(p) -> dict:
    """Read calculator parameters from OUTCAR path."""
    path = Path(p)
    if not path.is_dir():
        path = path.parent
    # calc.read() can fail and also reads atoms etc.
    # calc = Vasp(directory=path)
    # calc.read()
    # Try to read calc params manually instead
    calc = Vasp()
    calc.read_incar(path / "INCAR")
    calc.read_kpoints(path / "KPOINTS")
    calc.read_potcar(path / "POTCAR")
    # calc.parameters is empty so do this instead
    params = calc.asdict()["inputs"]
    params["xc"] = calc.get_xc_functional()  # use 'xc' or 'pp' if 'xc' is None
    return params


def has_vasppbed3_calc(atoms) -> bool:
    """Check if the atoms object has a VASP PBE D3 calculation."""
    if atoms.calc is None:
        return False
    is_vasp = atoms.calc.name.lower() == "vasp"
    is_pbe = atoms.calc.parameters.get("xc", "").lower() == "pbe"
    is_d3 = int(atoms.calc.parameters.get("ivdw", 0)) == 11  # TODO: Or 12 (not important)
    return is_vasp and is_pbe and is_d3


def worker_function(input_file: str, output_dir: str, lmdb: bool):
    """Read data file paths from input file and write filtered data to database."""
    # Write separate output files for each process
    # Writing to a single file requires locking and would mix trajectories.
    process_id = os.getpid()
    output_db_name = f"{process_id}.aselmdb" if lmdb else f"{process_id}.db"
    output_db_path = Path(output_dir) / output_db_name
    output_txt_path = Path(output_dir) / f"{process_id}.txt"  # Accepted paths file
    # Read data files and write to database
    with (
        open(input_file, "r") as f,
        ase.db.connect(output_db_path, append=True) as db,
        open(output_txt_path, "a") as accepted_paths,
    ):
        for line in f:
            try:
                p = line.strip()  # Data file path
                is_outcar = "OUTCAR" in Path(p).stem
                is_traj = p.endswith(".traj")
                has_pbe_d3_in_name = "PBE+D3" in Path(p).stem
                calc_params = None  # For caching calc params from OUTCAR paths
                for i, atoms in enumerate(ase.io.iread(p, index=":")):  # Read any file format
                    # ASE does not read calc params from OUTCAR, so we need to extract them manually
                    if is_outcar and atoms.calc and atoms.calc.name.lower() == "vasp":
                        assert len(atoms.calc.parameters) == 0, "Expected empty calc params."
                        if calc_params is None:
                            # Read calc params once and reuse for the rest of the trajectory
                            calc_params = get_calc_params_from_outcar_path(p)
                        atoms.calc.parameters.update(calc_params)
                    # Handle .traj without calc params but we know is VASP PBE D3
                    if is_traj and has_pbe_d3_in_name:
                        assert len(atoms.calc.parameters) == 0, "Expected empty calc params."
                        if calc_params is None:
                            # Read calc params once and reuse for the rest of the trajectory
                            calc_params = get_calc_params_from_outcar_path(p)
                            assert calc_params["xc"].lower() == "pbe", "Expected PBE functional."
                        # Now we know the calculation is VASP PBE and we assume D3 was added
                        atoms.calc.name = "vasp"
                        atoms.calc.parameters.update(calc_params)
                    # Only accept VASP PBE D3 calculations
                    if has_vasppbed3_calc(atoms) or (is_traj and has_pbe_d3_in_name):
                        db.write(atoms, file_path=p, file_index=i, data={"info": atoms.info})
                    else:
                        break  # Stop reading the file
                else:  # Only executed if the loop completed without break
                    accepted_paths.write(f"{p}\n")  # Write accepted path
            except Exception as e:
                # TODO: Use multiprocessing logging
                print(f"Failed to read '{p}': {e}")


def main(args):
    # Check arguments
    assert Path(args.input_dir).is_dir(), f"{args.input_dir} is not a directory."
    # Setup job
    job_dir = setup_job_dir_and_logging(args)
    logging.info("Ready to work!")
    logging.info(f"Job directory: {job_dir.resolve()}")
    # Prepare output directory
    output_dir = Path("/tmp/output") if args.tmp else job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Process input directory
    input_files = [str(p) for p in Path(args.input_dir).glob("*.txt") if p.is_file()]
    assert len(input_files) > 0, f"No input files found in: {args.input_dir}"
    logging.info(f"Found {len(input_files)} input files in: {args.input_dir}")
    # Start multiprocessing
    args_list = [(input_file, str(output_dir), args.lmdb) for input_file in input_files]
    logging.info(f"Start multiprocessing {len(args_list)} tasks with {os.cpu_count()} CPUs...")
    with Pool(processes=None) as pool:
        _ = pool.starmap(worker_function, args_list)
    logging.info("All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read data from files and write to database.")
    parser.add_argument(
        "--input_dir", help="Directory with .txt files containing data file paths.", required=True
    )
    parser.add_argument("--lmdb", action="store_true", help="Use LMDB format for output databases.")
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
