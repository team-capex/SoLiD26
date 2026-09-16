"""Read ase.db files from a directory and write to a single database."""

import argparse
import logging
from pathlib import Path

import ase.db  # type: ignore

from utils import add_job_args_to_parser, setup_job_dir_and_logging


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
    input_files = [
        str(p)
        for p in Path(args.input_dir).iterdir()
        if p.is_file() and p.suffix in [".db", ".aselmdb"]
    ]
    assert len(input_files) > 0, f"No input files found in {args.input_dir}."
    logging.info(f"Found {len(input_files)} input files in {args.input_dir}.")
    # Merge databases
    output_db_path = output_dir / "merged.aselmdb" if args.lmdb else output_dir / "merged.db"
    assert not output_db_path.exists(), f"Output database {output_db_path} already exists."
    logging.info(f"Merging databases into {output_db_path}...")
    with ase.db.connect(output_db_path) as output_db:
        for input_file in input_files:
            logging.info(f"Processing {input_file}...")
            with ase.db.connect(input_file) as input_db:
                for i in range(len(input_db)):
                    row = input_db.get(i + 1)
                    output_db.write(row, key_value_pairs=row.key_value_pairs, data=row.data)
    logging.info("All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Read ase.db files from a directory and write to a single database."
    )
    parser.add_argument(
        "--input_dir", help="Directory with database files to merge.", required=True
    )
    parser.add_argument("--lmdb", action="store_true", help="Use LMDB format for output database.")
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
