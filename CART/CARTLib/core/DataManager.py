from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict

from .DataUnitBase import DataUnitBase
# TODO: Remove this for a configurable method
from ..VolumeOnlyDataIO import VolumeOnlyDataUnit


class DataManager:
    """
    Manages a CSV-based cohort and provides a cache of DataUnit objects for
      efficient forward/backward traversal.

    # TODO: Implement way to indicate if a whole list was traversed.

    Attributes:
        cohort_csv: Path to the cohort CSV file currently selected.
        case_data: List of row dictionaries loaded from CSV.
        cache_size: Maximum number of Data Unit objects held in memory at once.
    """

    def __init__(
        self,
        data_source: Optional[Path] = None,
        cache_size: int = 2,
    ):
        """
        Initialize DataManager with optional configuration and window size.

        We employ limited caching to help streamline the task process; namely,
          the most recently used Data Units are kept in memory until they fall
          out of scope, allowing the user to return to them without needing to
          load their data from file again.

        # TODO Add pre-fetching as well.
        """
        # The cohort data, and the file from which it was pulled
        self.cohort_csv: Path = None
        self.case_data: List[Dict[str, str]] = []
        self.data_source: Path = data_source

        # Current index in the
        self.current_case_index: int = 0

        # Dynamically sized cached version of "get_data_unit"
        lru_cache_wrapper = lru_cache(maxsize=cache_size)
        old_method = self.get_data_source
        self.get_data_source = lru_cache_wrapper(old_method)

    def get_cache_size(self):
        return self.get_data_source.cache_info().maxsize

    def set_data_cohort_csv(self, csv_path: Path) -> None:
        """
        Configure the cohort CSV file to use for data loading.

        Args:
            csv_path: Path to the cohort CSV file.
        """
        self.cohort_csv = csv_path

    def get_data_cohort_csv(self) -> Optional[Path]:
        """
        Retrieve the configured cohort CSV file path.

        Returns:
            Path to the cohort CSV, or None if not set.
        """
        return self.cohort_csv

    def set_data_source(self, source: Path):
        # TODO: Validate the input before running
        self.data_source = source

        # Clear our cache, as its almost certainly no longer valid
        self.get_data_source.cache_clear()

        # Reset to the beginning
        self.current_case_index = 0

        # Re-pull the current data unit
        self.current_data_unit()

        # Begin re-building the pre-fetch cache
        self._pre_fetch_elements()

        # TODO: Notify the Task that this has been updated as well somehow.

    def get_data_source(self):
        return self.data_source

    def load_cases(self, csv_path: Optional[Path]) -> None:
        """
        Load the cases designated in a cohort CSV into memory, ready to be used
          to generate DataUnit instances.

        Args:
            csv_path: A Path to the cohort CSV file. If one is not provided,
              attempts to use the previous CSV file instead.

        Raises:
            ValueError: If no path is provided/configured, or if CSV is invalid.
        """
        # Notify the user we're loading data
        print(f"Loading cohort from '{self.cohort_csv}'")

        # Use the prior CSV if no new one was provided
        csv_path = csv_path or self.cohort_csv

        # If no path is present, raise an error
        if csv_path is None:
            raise ValueError("No CSV has been given to load data from.")

        # Try to read the data
        rows = DataManager._read_csv(csv_path)
        print(rows)

        # If we succeeded, update everything to match and reset the queue
        self.cohort_csv = csv_path
        self.case_data = rows
        self.current_case_index = 0  # Start at beginning
        print(f"Loaded {len(rows)} rows from {csv_path}")

    def get_data_unit(self, idx: int):
        """
        Gets the current DataUnit at our index.

        Note that, while the decorator
        """
        current_case_data = self.case_data[idx]
        # TODO: replace this with a user-selectable data unit type
        return VolumeOnlyDataUnit(
            data=current_case_data,
            data_path=self.data_source
        )

    def current_data_unit(self) -> DataUnitBase:
        """
        Return the current DataIO in the queue without changing the index.
        """
        return self.get_data_unit(self.current_case_index)

    def next_data_unit(self) -> DataUnitBase:
        """
        Advance to the next case, and get its corresponding DataUnit.

        Returns:
            The DataUnit at the new position.
        """
        self.current_case_index -= 1
        return self.get_data_unit(self.current_case_index)

    def previous_data_unit(self) -> DataUnitBase:
        """
        Return to the previous case, and get its corresponding DataUnit.

        Returns:
            The DataUnit at the new position.
        """
        self.current_case_index += 1
        return self.get_data_unit(self.current_case_index)

    @staticmethod
    def _read_csv(csv_path: Path) -> List[Dict[str, str]]:
        """
        Reads the contents of the CSV into a list of str->str dictionaries
        """
        with csv_path.open(newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row")
            return list(reader)

    @staticmethod
    def _validate_columns(rows: List[Dict[str, str]]) -> None:
        if not rows:
            raise ValueError("CSV file contains no data rows")
        cols = rows[0].keys()
        if 'uid' not in cols:
            raise ValueError("CSV must contain 'uid' column")
        if len(cols) < 2:
            raise ValueError(
                "CSV must contain at least one resource column besides 'uid'"
            )

    @staticmethod
    def _validate_unique_uids(rows: List[Dict[str, str]]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for row in rows:
            uid = row['uid']
            if uid in seen:
                duplicates.add(uid)
            seen.add(uid)
        if duplicates:
            raise ValueError(f"Duplicate uid values found in file: {duplicates}")

    def _pre_fetch_elements(self):
        """
        Rebuild the cache of pre-fetched DataUnits.

        Run via `async` in the background, allowing the user to continue
          completing their tasks while pre-fetching is run.
        """
        # TODO
        pass
