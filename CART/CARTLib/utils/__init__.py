import logging
from functools import cache
from pathlib import Path

# Path instance for the CART installation path
CART_PATH = Path(__file__).parent.parent.parent

# Current version of CART; used to validate configuration files
CART_VERSION = "0.0.1"

# Function which fetches the git hash if available; otherwise uses the version above
@cache
def get_cart_version() -> str:
    """
    Function which fetches the Git hash for the current branch of
    CART being used, if it exists. Otherwise, uses the default
    version indicated prior (which is used for "full" releases).

    Cached to avoid repeatedly reading from the git files; we
    assume the user will not modify CART's files while its
    running.

    Method based on https://stackoverflow.com/a/56245722
    """
    git_dir = CART_PATH / "../.git"
    # If this isn't a git install, end here
    if not git_dir.exists():
        return CART_VERSION
    head_dir = git_dir / "HEAD"
    # If there's no head directory (somehow), end here.
    if not head_dir.exists():
        return CART_VERSION
    with (git_dir / "HEAD").open('r') as fp:
        ref = fp.readline().split(": ")[-1].strip()
    hash_dir = git_dir / ref
    # If the designated directory doesn't exist, warn the user and fallback to default.
    if not hash_dir.exists():
        logging.warning(
            "The git-based installation of CART may have been corrupted; "
            "you may want to re-download CART to avoid potential errors!")
        return CART_VERSION
    # Return the hash value used in the file.
    with hash_dir.open('r') as fp:
        return fp.readline().strip()
