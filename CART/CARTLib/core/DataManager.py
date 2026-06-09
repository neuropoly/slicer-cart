import csv
import logging
from functools import cached_property
from pathlib import Path
from threading import RLock
from typing import Optional, Callable

from .DataUnitBase import DataUnitBase, DataUnitFactory
from .TaskBaseClass import TaskBaseClass


def dynamic_lru_cache_wrapper(func: Callable, maxsize: int, n_hashing_vars: int = None) -> Callable:
    """
    Re-implementation of `functools:lru_cache` extended to allow for the following:
      * Dynamically resizing.
      * Considers only n variables when checking for a cached value.
      * Check whether the given value already exists in the cache or not.

    You really shouldn't use this; if you need specialized caches, you should
    consider the cachetools package instead. The only reason this exists is to
    keep CART dependency free.
    """
    # Make sure the n_hashing_vars variable is greater than 0
    if n_hashing_vars is not None and n_hashing_vars < 0:
        raise ValueError("Number of considered ")

    # Ensure the maximum size is valid
    def _validate_maxsize(new_size: int):
        # If the max size is invalid, raise an error
        if type(new_size) != int or new_size < 0:
            raise ValueError(
                "Dynamic LRUs must have a positive integer as its max size!"
            )

    def make_key(*args, **kwargs):
        nonlocal n_hashing_vars

        arglist = [*args, *kwargs.values()]
        if n_hashing_vars is not None:
            return hash(tuple(arglist[:n_hashing_vars]))
        else:
            return hash(tuple(arglist))

    _validate_maxsize(maxsize)

    # The cache itself, plus some statistics
    cache: dict[int, list[int]] = {}
    hits = misses = 0
    full = False

    # Explict binds to make it run a little faster
    cache_get = cache.get
    cache_len = cache.__len__

    # Lock to help with thread safety
    lock = RLock()

    # Linked list to track the elements
    PREV, NEXT, KEY, RESULT = 0, 1, 2, 3
    root = []
    # Initialize by pointing to ourselves in both directions
    root[:] = [root, root, None, None]

    # Build the wrapper function
    def wrapper(*args, **kwargs):
        nonlocal root, hits, misses, maxsize, full
        key = make_key(*args, **kwargs)
        with lock:
            new_link = cache_get(key)
            if new_link is not None:
                # Move the link to the front of our list
                prev_link, next_link, old_key, result = new_link
                prev_link[NEXT] = next_link
                next_link[PREV] = prev_link
                last = root[PREV]
                last[NEXT] = root[PREV] = new_link
                new_link[PREV] = last
                new_link[NEXT] = root
                # Return the result and report a hit
                hits += 1
                return result
            # Otherwise we had a miss, track it and run the function
            misses += 1
        result = func(*args, **kwargs)
        with lock:
            if key in cache:
                # Getting here means that this same key was added to the
                # cache while the lock was released.  Since the link
                # update is already done, we need only return the
                # computed result and update the count of misses.
                pass
            # If we're at capacity, trim off the last-used link
            elif full:
                # Insert our new values into the previous root
                old_root = root
                old_root[KEY] = key
                old_root[RESULT] = result
                # Empty the oldest link and make it the new root
                root = old_root[NEXT]
                old_key = root[KEY]
                # De-allocate the old root's contents so it can be garbage collected.
                # NOTE: We hold out the old result to prevent it from being garbage
                # collected early. Doing so could run arbitrary code (via a __del__
                # dunder, for example) which could break things.
                result_holdout = root[RESULT]
                root[KEY] = root[RESULT] = None
                # Drop the corresponding element in our cache
                del cache[old_key]
                # Re-insert last to ensure everything is consistent before risking
                # and override (re-entrant key)
                cache[key] = old_root
            # If not, insert our new result and check if we're at capacity now
            else:
                # Put the result in a new link at the front
                last_link = root[PREV]
                new_link = [last_link, root, key, result]
                last_link[NEXT] = root[PREV] = cache[key] = new_link
                # Check if we're full now
                full = (cache_len() >= maxsize)
        # Finally return the result
        return result

    # Utility functions
    def cache_hits() -> int:
        with lock:
            return hits

    def cache_misses() -> int:
        with lock:
            return misses

    def cache_size() -> int:
        with lock:
            return cache_len()

    def is_cached(*args, **kwargs) -> bool:
        key = make_key(*args, **kwargs)
        with lock:
            return key in cache.keys()

    def clear_cache():
        nonlocal hits, misses, full
        with lock:
            cache.clear()
            root[:] = [root, root, None, None]
            hits = misses = 0
            full = False

    def set_maxsize(new_size: int):
        nonlocal root, full, maxsize

        # Make sure our max size is valid
        _validate_maxsize(new_size)

        # If the new size is smaller than our current size, we need to trim
        with lock:
            if new_size < cache_len():
                # Hold onto the cached results until the end to avoid premature garbage collection
                results_holdout = []
                # Iterate through our cache until we've reached where we should cut
                current_tail = root[PREV]
                current_idx = cache_len() - 1
                while current_idx >= new_size:
                    results_holdout.append(current_tail[RESULT])
                    key = current_tail[KEY]
                    del cache[key]
                    current_tail[NEXT] = current_tail[RESULT] = current_tail[KEY] = None
                    current_tail = current_tail[PREV]
                    current_idx -= 1
                # Re-connect the tail to the root; this will isolate the trimmed section, allowing
                # it to be garbage collected.
                current_tail[NEXT] = root
                # Mark ourselves as full
                full = True
            # If its larger and we were full, we're no longer full!
            elif full and new_size > maxsize:
                full = False
            # Update our size to match
            maxsize = new_size

    wrapper.cache_hits = cache_hits
    wrapper.cache_misses = cache_misses
    wrapper.cache_size = cache_size
    wrapper.is_cached = is_cached
    wrapper.clear_cache = clear_cache
    wrapper.set_maxsize = set_maxsize

    return wrapper


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
        cohort_file: Optional[Path],
        data_source: Optional[Path],
        data_unit_factory: DataUnitFactory,
        reference_task: Optional[TaskBaseClass] = None,
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
        self.data_unit_factory: DataUnitFactory = data_unit_factory
        self.reference_task: Optional[TaskBaseClass] = reference_task

        # Data
        self.case_data = list()
        self.failed_indices = set()
        self.feature_labels = list()

        # Current index being tracked; -1 indicates one hasn't been selected yet
        self.current_case_index: int = -1

        # Convert the protected '_get_data_unit' into a public version,
        #  w/ the desired number of cached elements.
        self.get_data_unit: Callable[[int, dict], DataUnitBase] = dynamic_lru_cache_wrapper(
            self._get_data_unit, maxsize=cache_size, n_hashing_vars=1
        )

        # The data unit factory to parse case information with
        self.data_unit_factory: DataUnitFactory = data_unit_factory

        # Logger
        self.logger = logging.getLogger("CART Data Manager")

        # Load the data from file
        self._load_from_file()

    ## Properties ##
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

    ## Data Management ##
    def _load_from_file(self):
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
        self.current_case_index = -1

    def _get_data_unit(self, idx: int, prior_data: dict = None) -> DataUnitBase:
        """
        Gets the current DataUnit at our index. This method implicitly caches
        and does NOT update the state of the DataManager!

        Unless you know what you're doing, you should use `select_unit_at`
        instead!
        """
        current_case_data = self.case_data[idx]

        # TODO: replace this with a user-selectable data unit type
        new_unit = self.data_unit_factory(
            case_data=current_case_data,
            data_path=self.data_source,
            prior_data=prior_data,
        )

        # Validate the data unit (and thus before it enters the cache)
        new_unit.validate()

        # Return the new data unit
        return new_unit

    def _unit_at(self, idx: int) -> Optional[DataUnitBase]:
        # If we have no task to check for prior outputs, delegate to `get_data_unit` directly
        if self.reference_task is None:
            return self.get_data_unit(idx)

        # If the unit is already in cache, just return the cached entry outright
        if self.get_data_unit.is_cached(idx):
            return self.get_data_unit(idx)

        # If we somehow lack a UID, raise an error
        case_data = self.case_data[idx]
        uid = self.case_data[idx].get("uid")
        if uid is None:
            raise ValueError("Tried to get a data unit for a case without a UID!")

        # Using the reference task, generate our prior data and build the corresponding data unit
        prior_data = None
        if self.reference_task is not None:
            prior_data = self.reference_task.generate_prior_data_for(case_data)
        return self.get_data_unit(idx, prior_data)

    def current_data_unit(self) -> DataUnitBase:
        """
        Return the current DataUnit in the queue without changing the index or
        re-focusing it.
        """
        return self._unit_at(self.current_case_index)

    def select_current_unit(self):
        """
        Selects the current data unit again, bringing it into focus if it was
        not already
        """
        current_unit = self.current_data_unit()
        current_unit.focus_gained()
        return current_unit

    def has_next_case(self) -> bool:
        return self.current_case_index + 1 < len(self.case_data)

    def has_previous_case(self) -> bool:
        return self.current_case_index > 0

    def select_unit_at(
        self, idx: int, iter_on_failure: int = 0
    ) -> Optional[DataUnitBase]:
        """
        Update the current selection index + loaded data unit. This involves:

        * Revoking focus to the previously selected data unit
        * Granting focus to the new data unit
        * Updating our currently selected index

        In that order; how the first steps are managed depends on the DataUnit's
          specific implementation.

        :param idx: The index to try and select
        :param iter_on_failure: How much (and in which direction) to iterate when a unit
          fails to load.

        :return: The given data unit, or None if the index was invalid.
          If a non-zero `iter_on_failure` was provided, will re-attempt on that offset until
          either a valid unit is found, or the index becomes invalid.
        """
        # Attempt to grab the next data unit and focus it
        while True:
            try:
                # Check that the new index is valid before proceeding
                if idx < 0:
                    logging.warning("Index cannot be less than 0.")
                    return None
                elif idx >= len(self.case_data):
                    logging.warning(
                        "Index cannot be greater than the number of loaded cases."
                    )
                    return None

                # Select the unit at the specified index
                new_unit = self._unit_at(idx)

                # Try to transfer focus from the previous unit (if any) to our new one
                if self.current_case_index != -1:
                    prior_unit = self.current_data_unit()
                    prior_unit.focus_lost()
                new_unit.focus_gained()

                # Set the current index to that of the new unit
                self.current_case_index = idx

                # Return the new unit
                return new_unit
            except Exception as e:
                # If no iteration offset was given, end here
                if iter_on_failure == 0:
                    raise e
                # Otherwise, move onto the "next" case and try again
                else:
                    self.failed_indices.add(idx)
                    new_idx = idx + iter_on_failure
                    logging.error(
                        f"Failed to load unit at index {idx}; trying {new_idx}.",
                        exc_info=e,
                    )
                    idx = new_idx

    def next(self) -> Optional[DataUnitBase]:
        """
        Advance to the next case, and get its corresponding DataUnit.

        :return: The next data unit; None if it doesn't exist/is invalid
        """
        new_index = self.current_case_index + 1
        return self.select_unit_at(new_index, 1)

    def next_incomplete(self, task: TaskBaseClass, from_idx: int = None) -> Optional[DataUnitBase]:
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
                return self.select_unit_at(idx, 1)
            idx += 1
        # Fallback; if all subsequent cases are completed, print a warning and return the
        #  next case instead
        logging.warning("All cases were completed! Loaded next unit instead.")
        return self.next()

    def previous(self) -> DataUnitBase:
        """
        Advance to the next case, and get its corresponding DataUnit.

        :return: The previous data unit; None if it doesn't exist/is invalid
        """
        new_index = self.current_case_index - 1
        return self.select_unit_at(new_index, -1)

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
                return self.select_unit_at(idx, -1)
            idx -= 1

        # Fallback; if all prior cases are completed, print a warning and return the
        #  previous case instead
        logging.warning("All cases were completed! Loaded previous unit instead.")
        return self.previous()

    def first(self) -> DataUnitBase:
        # Wrapper to jump to the very first data unit
        return self.select_unit_at(0, 1)

    def first_incomplete(self, task: TaskBaseClass) -> DataUnitBase:
        # Wrapper function for the somewhat unintuitive "find the first" syntax
        return self.next_incomplete(task, -1)

    def last(self) -> DataUnitBase:
        # Wrapper to jump to the last first data unit
        last_idx = len(self.case_data) - 1
        return self.select_unit_at(last_idx, -1)

    def last_incomplete(self, task: TaskBaseClass) -> DataUnitBase:
        # Wrapper function for the somewhat unintuitive "find the last" syntax
        return self.previous_incomplete(task, -1)

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
