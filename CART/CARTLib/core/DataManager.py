import csv
import logging
from functools import lru_cache, cached_property
from pathlib import Path
from typing import Optional, Callable

from .DataUnitBase import DataUnitBase
from .TaskBaseClass import DataUnitFactory, TaskBaseClass


class DataManager:
    """
    Manages a CSV-based cohort and provides a cache of DataUnit objects for
      efficient forward/backward traversal.

    # TODO: Implement way to indicate if all cases were previously traversed

    Attributes:
        cohort_csv: Path to the cohort CSV file currently selected.
        case_data: List of row dictionaries loaded from CSV.
        data_unit_factory: The factory method for creating DataUnits from case entries
        cache_size: Maximum number of Data Unit objects held in memory at once.
    """

    def __init__(
        self,
        cohort_file: Optional[Path] = None,
        data_source: Optional[Path] = None,
        data_unit_factory: DataUnitFactory = None,
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
        self.cohort_csv: Path = cohort_file
        self.data_source: Path = data_source

        # Data
        self.case_data = list()
        self.feature_labels = list()

        # Current index being tracked
        self.current_case_index: int = 0

        # Convert the protected '_get_data_unit' into a public version,
        #  w/ the desired number of cached elements.
        lru_cache_wrapper = lru_cache(maxsize=cache_size)
        self.get_data_unit: Callable[[int], DataUnitBase] = lru_cache_wrapper(
            self._get_data_unit
        )

        # The data unit factory to parse case information with
        self.data_unit_factory: DataUnitFactory = data_unit_factory

        # Logger
        self.logger = logging.getLogger("CART Data Manager")

        # Load the data from file
        self.load_from_file()

    ## Data Management ##
    def load_from_file(self):
        # Log that we began loading the cohort data
        self.logger.info(f"Loading cohort from '{self.cohort_csv}'")

        # If no path is present, raise an error
        if self.cohort_csv is None:
            raise ValueError("No CSV has been given to load data from.")

        # Try to read the data from file
        with self.cohort_csv.open(newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row")
            self.feature_labels = list(reader.fieldnames)
            self.case_data = list(reader)

        # If we succeeded, reset our iteration step
        self.current_case_index = 0

    def get_cache_size(self):
        return self.get_data_unit.cache_info().maxsize

    def _get_data_unit(self, idx: int) -> DataUnitBase:
        """
        Gets the current DataUnit at our index. This method implicitly caches
        and does NOT update the state of the DataManager!

        Unless you know what you're doing, you should use `select_unit_at`
        instead!
        """
        current_case_data = self.case_data[idx]

        # TODO: replace this with a user-selectable data unit type
        new_unit = self.data_unit_factory(
            case_data=current_case_data, data_path=self.data_source
        )

        # Validate the data unit (and thus before it enters the cache)
        new_unit.validate()

        # Return the new data unit
        return new_unit

    def set_data_unit_factory(self, duf: DataUnitFactory):
        self.data_unit_factory = duf

    @cached_property
    def valid_uids(self):
        return_list = []
        for c in self.case_data:
            for k, v in c.items():
                if k.lower() == "uid" and v is not None:
                    return_list.append(v)
                    break
        return return_list

    @property
    def valid_features(self):
        return [f for f in self.feature_labels if f.lower() != "uid"]

    def current_uid(self):
        return self.case_data[self.current_case_index]["uid"]

    def current_case(self):
        """
        Return the case information for the current index
        """
        return self.case_data[self.current_case_index]

    def current_data_unit(self) -> DataUnitBase:
        """
        Return the current DataUnit in the queue without changing the index.
        """
        return self.get_data_unit(self.current_case_index)

    def select_current_unit(self):
        """
        Selects the current data unit again, bringing it into focus if it was
         not already
        """
        current_unit = self.get_data_unit(self.current_case_index)
        current_unit.focus_gained()

        return current_unit

    def has_next_case(self) -> bool:
        return self.current_case_index + 1 < len(self.case_data)

    def has_previous_case(self) -> bool:
        return self.current_case_index > 0

    def select_unit_at(self, idx: int) -> DataUnitBase:
        """
        Update the current selection index + loaded data unit. This involves:

        * Revoking focus to the previously selected data unit
        * Granting focus to the new data unit
        * Updating our currently selected index

        In that order; how the first steps are managed depends on the DataUnit's
         specific implementation.
        """
        # Check that the new index is valid before proceeding
        if idx < 0:
            raise ValueError("Index cannot be less than 0.")
        elif idx >= len(self.case_data):
            raise ValueError("Index cannot be greater than the number of loaded cases.")

        # Keep tabs on the prior data unit for later
        prior_unit = self.current_data_unit()

        # Attempt to grab the next data unit
        new_unit = self.get_data_unit(idx)

        # Try to transfer focus from one unit to the other
        if prior_unit:
            prior_unit.focus_lost()
        new_unit.focus_gained()

        # Set the current index to that of the new unit
        self.current_case_index = idx

        # Return the new unit
        return new_unit

    def next_incomplete(self, task: TaskBaseClass, from_idx: int = None) -> DataUnitBase:
        """
        Advance to the next case which hasn't been completed for the provided task and get its corresponding DataUnit.

        :param task: The task to query for whether the case has been completed yet or not
        :param from_idx: The index you want to search *past*.
            Setting this to -1 will search all cases.
            If not provided, will search all cases past the currently selected one.

        :return: The next incomplete data unit; None if it doesn't exist/is invalid.
            If all subsequent cases are valid, just returns the next data unit instead.
        """
        # If the user didn't provide a starting index, set it to our current index
        if not from_idx:
            from_idx = self.current_case_index

        # Step to the "next" case
        idx = from_idx + 1

        # Iterate until we run out of cases
        while idx < len(self.case_data):
            case = self.case_data[idx]
            if not task.isTaskComplete(case):
                return self.select_unit_at(idx)
            idx += 1
        # Fallback; if all subsequent cases are completed, print a warning and return the
        # next case instead
        print("WARNING: All cases were completed, falling back to next")
        return self.next()

    def previous_incomplete(self, task: TaskBaseClass, from_idx: int = None) -> DataUnitBase:
        """
        Step back to the most recent prior case which hasn't been completed for the
        provided task, and get its corresponding DataUnit.

        :param task: The task to query for whether the case has been completed yet or not
        :param from_idx: The index you want to search *from*.
            Setting this to -1 will search all cases, starting from the last
            If not provided, will search all cases prior to the currently selected one.

        :return: The previous incomplete data unit; None if it doesn't exist/is invalid.
            If all subsequent cases are valid, just returns the previous data unit instead.
        """
        # If the user didn't provide a starting index, set it to our current index
        if not from_idx:
            from_idx = self.current_case_index
        # If it was -1, set it explicitly to the last index to "act" like Python's indexing
        elif from_idx == -1:
            from_idx = len(self.case_data)

        # Step to the "previous" case
        idx = from_idx - 1

        # Iterate until we run out of cases
        while idx > -1:
            case = self.case_data[idx]
            if not task.isTaskComplete(case):
                return self.select_unit_at(idx)
            idx -= 1

        # Fallback; if all prior cases are completed, print a warning and return the
        # previous case instead
        print("WARNING: All cases were completed, falling back to previous!")
        return self.previous()

    def first(self) -> DataUnitBase:
        # Wrapper to jump to the very first data unit
        self.current_case_index = 0
        return self.select_current_unit()

    def first_incomplete(self, task: TaskBaseClass) -> DataUnitBase:
        # Wrapper function for the somewhat unintuitive "find the first" syntax
        return self.next_incomplete(task, -1)

    def last(self) -> DataUnitBase:
        # Wrapper to jump to the last first data unit
        self.current_case_index = len(self.case_data) - 1
        return self.select_current_unit()

    def last_incomplete(self, task: TaskBaseClass) -> DataUnitBase:
        # Wrapper function for the somewhat unintuitive "find the last" syntax
        return self.previous_incomplete(task, -1)

    def next(self) -> DataUnitBase:
        """
        Advance to the next case, and get its corresponding DataUnit.

        :return: The next data unit; None if it doesn't exist/is invalid
        """
        new_index = self.current_case_index + 1
        return self.select_unit_at(new_index)

    def previous(self) -> DataUnitBase:
        """
        Advance to the next case, and get its corresponding DataUnit.

        :return: The previous data unit; None if it doesn't exist/is invalid
        """
        new_index = self.current_case_index - 1
        return self.select_unit_at(new_index)

    # TODO Change rows to rows and define row typing at the definition of rows
    @staticmethod
    def _validate_columns(rows: list[dict[str, str]]) -> None:
        if not rows:
            raise ValueError("CSV file contains no data rows")
        cols = rows[0].keys()
        if "uid" not in cols:
            raise ValueError("CSV must contain 'uid' column")
        if len(cols) < 2:
            raise ValueError(
                "CSV must contain at least one resource column besides 'uid'"
            )

    @staticmethod
    def _validate_unique_uids(rows: list[dict[str, str]]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for row in rows:
            uid = row["uid"]
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

    ## Cleanup ##
    def clean(self):
        """
        Explicitly delete the cache right before deletion.

        This is in case the data inside references the DataManager (or one of its
         components), forming a cyclical reference that results in a memory leak
        """
        del self.get_data_unit

    def __del__(self):
        self.clean()

    def __delete__(self, instance):
        self.clean()
