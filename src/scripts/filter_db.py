"""Filter ASE database and write indices."""

import argparse
import json
import logging
from pathlib import Path

import ase.db  # type: ignore
import pandas as pd  # type: ignore

from utils import add_job_args_to_parser, setup_job_dir_and_logging


def build_dataframe_from_asedb(asedb_path: str, max_rows: int = -1):
    """Build lightweight dataframe of essential properties from ASE database."""
    records = []
    with ase.db.connect(asedb_path) as db:
        N = len(db)
        for i in range(N):
            try:
                row = db.get(i + 1)  # Fails on missing ids
                atoms = row.toatoms()
                record = {
                    "i": i,
                    "file_path": row.key_value_pairs.get("file_path"),  # For additional filtering
                    "file_index": row.key_value_pairs.get("file_index"),
                    "formula": atoms.get_chemical_formula(),
                    "num_atoms": len(atoms.numbers),  # For creating data splits
                    "energy": row.energy,
                    "fmax": row.fmax,
                    "center_of_mass_sum": atoms.get_center_of_mass().sum(),  # Proxy for positions
                    "encut": row.get("calculator_parameters", {}).get("encut", None),
                    "ivdw": row.get("calculator_parameters", {}).get("ivdw", None),
                }
                records.append(record)
            except Exception:
                pass  # Skip problematic rows
            if (i + 1) % 100_000 == 0:
                logging.info(f"Processed {i + 1}/{N} rows...")
            if i + 1 == max_rows:
                break
    # Create dataframe with explicit index in case of missing ids
    df = pd.DataFrame.from_records(records, index="i")
    # Round numbers to avoid floating point comparison issues
    df = df.round(decimals=8)
    return df


def main(args):
    # Check arguments
    assert Path(args.asedb).is_file(), f"{args.asedb} is not a file."
    assert args.fmax > 0.0, "fmax must be a positive float."
    assert args.rows == -1 or args.rows > 0, "rows must be -1 or a positive integer."
    # Setup job
    job_dir = setup_job_dir_and_logging(args)
    logging.info("Ready to work!")
    logging.info(f"Job directory: {job_dir.resolve()}")
    # Prepare output directory
    output_dir = Path("/tmp/output") if args.tmp else job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build lightweight dataframe of essential properties from the ASE database.
    logging.info(f"Building dataframe from: {Path(args.asedb).resolve()}")
    df = build_dataframe_from_asedb(args.asedb, args.rows)
    df.to_csv(output_dir / "properties.csv")

    # Apply filters

    # Exclude rows with encut not in {350, 400, 450}
    encut_values = {350, 400, 450}
    logging.info(f"Filtering rows with encut not in {encut_values}...")
    encut_idx = df[~df["encut"].isin(encut_values)].index.tolist()
    logging.info(f"Found {len(encut_idx)} rows with encut not in {encut_values}.")

    # Exclude rows with high forces
    logging.info(f"Filtering rows with fmax > {args.fmax}...")
    fmax_idx = df["fmax"].index[df["fmax"] > args.fmax].tolist()
    logging.info(f"Found {len(fmax_idx)} rows with fmax > {args.fmax}.")

    # Exclude duplicated rows
    logging.info("Finding duplicates...")
    # This seems to be quite efficient and does not use too much memory
    dup_mask = df.duplicated(
        subset=["formula", "energy", "fmax", "center_of_mass_sum"], keep="first"
    )
    dup_idx = dup_mask.index[dup_mask].tolist()
    logging.info(f"Found {len(dup_idx)} duplicates out of {len(df)} rows.")

    # Write include/exclude indices to output file
    exclude = set()  # Indices to exclude
    exclude.update(encut_idx)
    exclude.update(fmax_idx)
    exclude.update(dup_idx)
    include = {i for i in range(len(df)) if i not in exclude}  # Indices to include
    logging.info(f"Total rows to include: {len(include)}.")
    logging.info(f"Total rows to exclude: {len(exclude)}.")
    logging.info(f"Total rows processed: {len(include) + len(exclude)}/{len(df)}.")
    result = {"include": sorted(list(include)), "exclude": sorted(list(exclude))}
    with open(output_dir / "filter_indices.json", "w") as f:
        json.dump(result, f)
    logging.info("All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Filter ASE database and write indices.")
    parser.add_argument("--asedb", help="Path to ASE database input file.", required=True)
    parser.add_argument("--fmax", type=float, default=10.0, help="Maximum force (fmax) threshold.")
    parser.add_argument(
        "--rows", type=int, default=-1, help="Number of rows to process (default all)."
    )
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
