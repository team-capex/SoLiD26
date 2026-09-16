"""Find data file paths in a list of directories."""

import argparse
import logging
import os
from multiprocessing import Pool
from pathlib import Path

import yaml  # type: ignore

from utils import add_job_args_to_parser, setup_job_dir_and_logging


def worker_function(
    directory: str, pattern: str, filters: list[str], output_dir: str, lines_per_file: int
) -> None:
    """Find paths in 'directory' matching 'pattern' excluding 'filters' and write to .txt files."""
    search_path = Path(directory)
    lines_written = 0
    for file_path in search_path.rglob(pattern):
        # Skip if any filter matches the path
        if any(filter in str(file_path) for filter in filters):
            continue
        # Create new output file every lines_per_file lines
        if lines_written % lines_per_file == 0:
            part = lines_written // lines_per_file
            output_name = (
                f"paths_{search_path}_{pattern}_part{part:04}".replace("/", "-")
                .replace("*", "star")
                .replace(".", "dot")
                + ".txt"
            )
            output_path = Path(output_dir) / output_name
            assert not output_path.exists(), f"Output file {output_path} already exists."
            output_file = open(output_path, "w")
        # Write path to output file
        output_file.write(f"{file_path.resolve()}\n")
        lines_written += 1
        # Close output file if reached lines_per_file
        if lines_written % lines_per_file == 0:
            output_file.close()
    # Close output file if still open
    if lines_written > 0 and not output_file.closed:
        output_file.close()


def main(args):
    # Check arguments
    assert Path(args.search_params).is_file(), f"{args.search_params} is not a file."
    assert args.lines_per_file > 0, "lines_per_file must be a positive integer."
    # Setup job
    job_dir = setup_job_dir_and_logging(args)
    logging.info("Ready to work!")
    logging.info(f"Job directory: {job_dir.resolve()}")
    # Prepare output directory
    output_dir = Path("/tmp/output") if args.tmp else job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    # Read search params and write copy in job directory
    with open(args.search_params) as f:
        search_params = yaml.safe_load(f)
    with open(job_dir / "search_params.yaml", "w") as f:
        yaml.dump(search_params, f, sort_keys=False)
    # Prepare directories
    assert "directories" in search_params, "No 'directories' in search params."
    directories = [d.strip() for d in search_params.get("directories") if d.strip()]
    assert len(directories) > 0, "No directories."
    assert len(directories) == len(set(directories)), "Duplicate directories."
    for d in directories:
        assert Path(d).is_dir(), f"Search directory {d} is not a directory."
    # Prepare patterns
    assert "patterns" in search_params, "No 'patterns' in search params."
    patterns = [p.strip() for p in search_params.get("patterns") if p.strip()]
    assert len(patterns) > 0, "No patterns."
    assert len(patterns) == len(set(patterns)), "Duplicate patterns."
    # Prepare filters
    filters = [f.strip() for f in search_params.get("filters", []) if f.strip()]
    # Start searching
    logging.info(
        f"Search: {len(directories)} directories, "
        f"{len(patterns)} patterns, "
        f"{len(filters)} filters, "
        f"{args.lines_per_file} lines per output file."
    )
    args_list = [
        (d, p, filters, str(output_dir), args.lines_per_file) for d in directories for p in patterns
    ]
    logging.info(f"Start multiprocessing {len(args_list)} tasks with {os.cpu_count()} CPUs...")
    with Pool(processes=None) as pool:
        _ = pool.starmap(worker_function, args_list)
    logging.info("All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find data file paths in a list of directories.")
    parser.add_argument("--search_params", help="YAML file with search parameters.", required=True)
    parser.add_argument(
        "--lines_per_file", type=int, default=10000, help="Number of lines per output file."
    )
    parser.add_argument(
        "--tmp",
        action="store_true",
        help="Write output files to /tmp/output/ instead of job directory.",
    )
    add_job_args_to_parser(parser, default_name=Path(__file__).stem)
    args = parser.parse_args()
    main(args)
