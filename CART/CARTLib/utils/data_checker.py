from pathlib import Path
from typing import Optional

### Accepted filetypes for conventions
bids_extensions = [
    # Core imaging
    ".nii", ".nii.gz",

    # Metadata / tabular / text
    ".json", ".tsv", ".txt", ".md",

    # Diffusion MRI
    ".bvec", ".bval",

    # Surfaces / Morphometry
    ".gii", ".surf.gii", ".label.gii", ".shape.gii",

    # Tractography / Streamlines (BEPs)
    ".trk", ".tck", ".vtk",

    # Microscopy
    ".ome.tif", ".ome.tiff",

    # EEG
    ".edf", ".bdf", ".set", ".fdt",
    ".vhdr", ".vmrk", ".eeg",
    ".mef3", ".nwb",

    # iEEG (same as EEG + clinical formats)
    # (not adding duplicates here, but same as above)

    # MEG
    ".fif",   # Elekta/Neuromag
    ".ds",    # CTF (directory)
    ".con",   # KIT/Yokogawa
    ".m4d", ".pdf", ".xyz",  # BTi/4D

    # Eye Tracking
    ".edf",  # (already included, but for eye tracking too)

    # Genetics (referenced, not always stored inside BIDS)
    ".vcf",
]

### Convention checking ###
# Add any custom convention checker here

def check_conventions(data_path: Path) -> Optional[str]:
    """
    Chain all the conventions until one matches, or all fail.
    """

    # TODO: Make this a dynamically loaded list instead
    from CARTLib.utils.bids import check_pseudo_bids
    checks = [check_pseudo_bids]

    # Set the first validated data convention as the current data convention
    for c in checks:
        if c(data_path):
            return c.__name__

    return None

### Paths fetching  ###
def fetch_resources(current_data_convention, root_path, excluded_extensions=None):
    if current_data_convention == "check_pseudo_bids":
        from CARTLib.utils.bids import fetch_bids_subject_map
        return fetch_bids_subject_map(
            root_path,
            excluded_extensions=excluded_extensions
        )
    else:
        return {}


def find_new_cohort_path(root_path: Path) -> Path:
    i = 0
    cohort_name = f"cohort_{i}.csv"
    cohort_path = root_path / cohort_name
    while cohort_path.exists():
        i += 1
        cohort_path = root_path / f"cohort_{i}.csv"
    return cohort_path
