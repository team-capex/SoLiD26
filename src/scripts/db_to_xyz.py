"""Read a single ase.db file and write it in xyz format."""

import argparse
import logging
from pathlib import Path
import json

import ase.db

from utils import add_job_args_to_parser, setup_job_dir_and_logging


def main(args):
    # Check arguments
    assert Path(args.asedb).is_file(), f"{args.asedb} is not a file."
    # Setup job
    job_dir = setup_job_dir_and_logging(args)
    logging.info("Ready to work!")
    logging.info(f"Job directory: {job_dir.resolve()}")
    # Prepare output directory
    output_dir = Path("/tmp/output") if args.tmp else job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Read ase.db
    atoms_list = []
    with ase.db.connect(args.asedb) as input_db:
        N = len(input_db)
        logging.info(f"Read {N} rows from {args.asedb}...")
        for n in range(N):
            row = input_db.get(n + 1)
            atoms = row.toatoms()
            if args.exclude_constraints:
                del atoms.constraints  # Do not include constraints in the output .xyz file
            atoms_list.append(atoms)
            if (n+1) % 100_000 == 0:
                logging.info(f"Read {n+1}/{N} rows...")
    # Write .xyz file
    output_name = Path(args.asedb).stem + ".xyz"
    output_path = output_dir / output_name
    logging.info(f"Writing to {output_path}...")
    ase.io.write(output_path, images=atoms_list, format="extxyz")
    logging.info("All done!")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read a single ase.db file and write it in xyz format."
    )
    parser.add_argument("--asedb", help="Path to ASE database input file.", required=True)
    parser.add_argument(
            "--exclude_constraints",
            action="store_true",
            help="Exclude constraints from the output.",
        )
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
