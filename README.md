# SoLiD26 dataset pipeline

Data ingestion and preparation pipeline for the solid-liquid interface dataset, SoLiD26.

The dataset is collected by searching a list of directories for data files of interest and then loading and filtering the data into an ASE database.

The dataset consists primarily of solid-liquid interface data, and everything is calculated with VASP using the PBE functional and D3 dispersion corrections.

## Setup

Dependencies are defined in `pyproject.toml` and can be installed with:

    $ pip install .

## Pipeline

The pipeline consists of the following steps and uses scripts located in `src/scripts/`:
For more details about each script, use `$ python path/to/script.py --help`.

1. `find_files.py` is used to read search parameters from a YAML file (example in `config/find_files/`) and search the given list of directories for file paths matching a set of patterns and filters. The accepted file paths are written to `.txt` files in the output directory.

2. `files_to_db.py` is used to read file paths from `.txt` files in the input directory and check if the file data is calculated with VASP PBE D3. The accepted data are written to several ASE database files in the output directory.

3. `merge_db.py` is used to read all ASE database files in the input directory and write the combined data to a single ASE database file in the output directory.

4. `filter_db.py` is used to read an ASE database and build a lightweight dataframe of properties used for filtering and identifying duplicate rows. The dataframe and the filtered row indices are written to a CSV file and a JSON file, respectively, in the output directory.

5. Additional filtering is performed using the output from the previous steps.
Outliers and structures with high maximum force are excluded.
Cross-validation with machine learning models are used to identify additional outliers and unconverged structures with high prediction errors.
The updated list of indices is written to a JSON file.

6. `db_to_filtered_db.py` is used to read an ASE database and a JSON file with indices to include and write a new database with only the included data.

7. `filter_db.py` is applied again to validate the filtered ASE database.
