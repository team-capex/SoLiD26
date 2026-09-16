"""Read an ase.db file and a list of indices to include and write a new database."""

import argparse
import logging
from pathlib import Path
import json

import ase.db  # type: ignore

from utils import add_job_args_to_parser, setup_job_dir_and_logging


def main(args):
    # Check arguments
    assert Path(args.asedb).is_file(), f"{args.asedb} is not a file."
    assert Path(args.indices).is_file(), f"{args.indices} is not a file."
    # Setup job
    job_dir = setup_job_dir_and_logging(args)
    logging.info("Ready to work!")
    logging.info(f"Job directory: {job_dir.resolve()}")
    # Prepare output directory
    output_dir = Path("/tmp/output") if args.tmp else job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Read data indices
    with open(args.indices, "r") as f:
        indices = json.load(f)
    assert "include" in indices.keys(), "Indices file must contain 'include' key."
    assert isinstance(indices["include"], list), "Indices must be a list of integers."
    assert len(indices["include"]) == len(set(indices["include"])), "Indices must be unique."
    # Write filtered database
    N = len(indices["include"])  # Number of rows to write
    n = 0  # Number of rows written
    with ase.db.connect(args.asedb) as input_db:
        while n < N:  # While there are still rows to write
            # Determine output file name and format
            if args.rows_per_file < N:
                # Split into multiple files
                part = n // args.rows_per_file
                output_name = (
                    f"filtered_{part:02}.aselmdb" if args.lmdb else f"filtered_{part:02}.db"
                )
                output_path = output_dir / output_name
            else:
                # Single output file
                output_name = "filtered.aselmdb" if args.lmdb else "filtered.db"
                output_path = output_dir / output_name
            logging.info(f"Writing to {output_path}...")
            # Write rows to output database
            with ase.db.connect(output_path, use_lock_file=False) as output_db:
                for _ in range(args.rows_per_file):
                    if n >= N:
                        break  # No more rows to write
                    # Get row and write to output database
                    row = input_db.get(indices["include"][n] + 1)
                    if args.clean:
                        # Write only essential properties
                        row.user = ""
                        output_db.write(row, key_value_pairs={}, data={})
                    else:
                        # Write everything
                        output_db.write(row, key_value_pairs=row.key_value_pairs, data=row.data)
                    n += 1
                    if n % 100_000 == 0:
                        logging.info(f"Wrote {n}/{N} rows...")
                    if n % args.rows_per_file == 0:
                        break  # Start a new output file
    logging.info("All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read an ase.db file and a list of indices to include and write a new database."
    )
    parser.add_argument("--asedb", help="Path to ASE database input file.", required=True)
    parser.add_argument(
        "--indices", help="Path to JSON file with list of indices to include.", required=True
    )
    parser.add_argument("--lmdb", action="store_true", help="Use LMDB format for output database.")
    parser.add_argument(
        "--rows_per_file",
        type=int,
        default=100_000_000,
        help="Maximum number of rows to write per output file.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Whether to clean up the data by omitting unnecessary keys.",
    )
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
