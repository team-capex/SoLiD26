import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

import yaml  # type: ignore


def add_job_args_to_parser(parser, default_name="default") -> None:
    parser.add_argument(
        "--output_root_dir",
        default=os.getenv("JOB_OUTPUT_ROOT_DIR", "./output"),
        help="Output is saved in 'output_root_dir/name/version/'",
    )
    parser.add_argument(
        "--name", default=os.getenv("JOB_NAME", default_name), help="Job name."
    )
    parser.add_argument(
        "--version",
        default=os.getenv("JOB_VERSION", datetime.now().strftime("%Y%m%d_%H%M%S")),
        help="Job version (default is a timestamp).",
    )


def setup_job_dir_and_logging(args) -> Path:
    """Create job directory and configure logging."""
    # Create job directory (allow to exist so it can be created externally)
    job_dir = Path(args.output_root_dir) / args.name / args.version
    job_dir.mkdir(parents=True, exist_ok=True)
    # Setup logging
    log_file_handler = logging.FileHandler(job_dir / "script.log", mode="w")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[log_file_handler, logging.StreamHandler()],
    )
    # Write git details to file (overwrite if exists)
    with open(job_dir / "gitdetails.txt", "w") as f:
        subprocess.run("git show -s --format=%cI-%h HEAD", stdout=f, shell=True)
    # Write input arguments to file
    with open(job_dir / "args.yaml", "w") as f:
        yaml.dump(vars(args), f, sort_keys=False)
    return job_dir
