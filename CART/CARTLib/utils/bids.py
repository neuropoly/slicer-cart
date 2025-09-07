"""
Various utilities for managing BIDS-like datasets.

This is a barebones implementation, making only two assumptions about
the structure of the data within the dataset:
    * Each subject has a unique folder, named "sub-{name}"
    * Derivative files for each subject are stored in a "derivatives" folder
"""

import csv
from pathlib import Path
from typing import Optional, List, Dict

from CARTLib.utils.data_checker import find_new_cohort_path


def check_pseudo_bids(data_path: Path) -> bool:
    """
    Check if the dataset follows a (pseudo-)BIDS structure
    """
    # First check if the derivatives folder exists
    derivatives_folder = data_path / "derivatives"

    if not derivatives_folder.is_dir():
        return False

    # Second check if structure under raw exists under derivatives
    raw_folders = [p.name for p in data_path.iterdir() if p.is_dir() and p.name.startswith("sub")]

    for name in raw_folders:
        matches = [p for p in derivatives_folder.rglob(name) if p.is_dir()]
        if matches:
            return True

    return False


def generate_blank_cohort(root_path: Path) -> Path:
    # Validation
    if not root_path.exists():
        raise ValueError(f"Provided BIDS directory {root_path} does not exist!")

    if not root_path.is_dir():
        raise ValueError(f"Provided BIDS directory {root_path} was not a directory!")

    # Find a path for the new cohort file in the desired directory
    cohort_path = find_unused_cohort_path(root_path)
    cohort_path.parent.mkdir(parents=True, exist_ok=True)

    # Get a list of subjects in this path, and extract unique UIDs from them
    uids = [v.name for v in fetch_subject_ids(root_path)]

    # Sort and format them for the CSV writer
    uids = [[x] for x in sorted(uids)]

    # If the cohort file doesn't exist, create it
    with open(cohort_path, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["uid"])
        csv_writer.writerows(uids)

    # Return the path to the newly created file
    print(f"Successfully created blank BIDS cohort at {cohort_path}")
    return cohort_path


def find_unused_cohort_path(root_path: Path):
    # Ensure t
    code_root = root_path / "code"
    return find_new_cohort_path(code_root)


def fetch_subject_ids(root_path: Path) -> list[Path]:
    """
    Scan a BIDS folder and identify the subjects within it
    """
    return [p for p in root_path.glob("sub-*") if p.is_dir()]


def find_associated_files(root_path: Path, search_path: Path, excluded_ext: list[str]):
    #
    files = []
    for file_path in search_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() not in excluded_ext:
            rel_path = file_path.relative_to(root_path)
            files.append(rel_path.as_posix())
    return files


def fetch_bids_subject_map(
    root_path: Path,
    excluded_extensions: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """
    Scan a BIDS dataset folder structure and return a dict mapping subject IDs
    (e.g., 'sub-01') to all their relevant file paths (raw + all derivatives subfolders).

    Parameters:
    - root_path: Path to the root BIDS dataset folder.
    - excluded_extensions: list of file extensions to exclude (e.g., ['.json']).

    Returns:
    - Dictionary: { subject_id: [list of relative file paths as POSIX strings] }
    """
    excluded_ext = [e.lower().strip() for e in excluded_extensions or []]
    temp_cases = {}

    # 1. Raw BIDS subjects at root
    for subj_dir in root_path.glob('sub-*'):
        if subj_dir.is_dir():
            subj_id = subj_dir.name
            temp_cases[subj_id] = find_associated_files(
                root_path, subj_dir, excluded_ext
            )

    # 2. Derivatives subjects under any subfolder of derivatives/
    derivatives_path = root_path / 'derivatives'
    if derivatives_path.is_dir():
        for subfolder in derivatives_path.iterdir():
            if not subfolder.is_dir():
                continue
            for deriv_subj_dir in subfolder.glob('sub-*'):
                if not subfolder.is_dir():
                    continue
                subj_id = deriv_subj_dir.name
                files = find_associated_files(
                    root_path, deriv_subj_dir, excluded_ext
                )
                if subj_id in temp_cases:
                    temp_cases[subj_id].extend(files)
                else:
                    temp_cases[subj_id] = files

    # Return sorted dictionary by subject ID
    return {case_id: files for case_id, files in sorted(temp_cases.items())}
