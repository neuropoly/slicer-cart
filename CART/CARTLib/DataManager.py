from __future__ import annotations
from pathlib import Path
import csv
from collections import deque
from typing import Optional, List, Dict

from .VolumeOnlyDataIO import VolumeOnlyDataUnit
from .DataUnitBase import DataUnitBase

class TaskConfig:
    """
    Placeholder for future configuration settings.
    """
    pass

class DataManager:
    """
    Manages a CSV-based cohort and provides a fixed-size window of DataIO
    objects for efficient forward/backward traversal.

    # TODO: Implement support for non-1 length queues in the future.
    # TODO: Implement way to indicate if a whole list was traversed.

    Attributes:
        config: Optional TaskConfig for behavior customization.
        _data_cohort_csv: Path to the cohort CSV file.
        raw_data: List of row dictionaries loaded from CSV.
        queue_length: Number of DataIO objects in the traversal window (must be odd).
        queue: Deque holding the current window of DataIO objects.
        current_queue_index: Position within the queue for traversal (always center for odd lengths).
        current_raw_index: Current position in the raw_data list.
    """

    def __init__(
        self,
        config: TaskConfig | None = None,
        queue_length: int = 1,
    ) -> None:
        """
        Initialize DataManager with optional configuration and window size.

        Args:
            config: Configuration object for customizing behavior.
            queue_length: Max number of DataIO objects in the window (must be odd, currently only 1 supported).

        Raises:
            ValueError: If queue_length is not odd or not supported.
        """
        if queue_length % 2 == 0:
            raise ValueError("Queue length must be odd")
        if queue_length != 1:
            raise ValueError("Currently only queue_length=1 is supported")

        self.config = config
        self._data_cohort_csv: Path | None = None
        self.raw_data: List[Dict[str, str]] = []
        self.queue_length = queue_length
        self.queue: deque[DataUnitBase] = deque(maxlen=self.queue_length)
        self.current_queue_index: int = 0  # For queue_length=1, this is always 0
        self.current_raw_index: int = 0  # Current position in raw_data

    def set_data_cohort_csv(self, csv_path: Path) -> None:
        """
        Configure the cohort CSV file to use for data loading.

        Args:
            csv_path: Path to the cohort CSV file.
        """
        self._data_cohort_csv = csv_path

    def get_data_cohort_csv(self) -> Optional[Path]:
        """
        Retrieve the configured cohort CSV file path.

        Returns:
            Path to the cohort CSV, or None if not set.
        """
        return self._data_cohort_csv

    def load_data(self, csv_path: Path | None = None) -> None:
        """
        Load CSV into raw_data, validate it, and initialize the traversal window.
        Uses either the provided csv_path or the one previously configured.

        Args:
            csv_path: Optional Path to CSV file. If omitted, uses the configured data_cohort_csv.

        Raises:
            ValueError: If no path is provided/configured, or if CSV is invalid.
        """
        path = csv_path or self._data_cohort_csv
        if not self._data_cohort_csv:
            self._data_cohort_csv = path
        if path is None:
            raise ValueError("No CSV path provided or configured for loading data")
        rows = self._read_csv(path)
        self._validate_columns(rows)
        self._validate_unique_uids(rows)
        self.raw_data = rows
        self.current_raw_index = 0  # Start at beginning
        self._init_queue()
        print(f"Loaded {len(rows)} rows from {path}")

    def _init_queue(self) -> None:
        """
        Populate the queue with DataIO objects based on current_raw_index
        and reset the queue traversal index.
        """
        if not self.raw_data:
            self.queue.clear()
            return

        self.queue.clear()

        # For queue_length=1, just load the current item
        if self.queue_length == 1:
            # TODO: make the type of DataUnit selectable/configurable somehow
            row = self.raw_data[self.current_raw_index]
            self.queue.append(
                VolumeOnlyDataUnit(
                    data=row
                )
            )
            self.current_queue_index = 0
        else:
            # Future implementation for larger odd queue lengths
            # Would center the queue around current_raw_index
            raise NotImplementedError("Queue lengths > 1 not yet implemented")

    def get_queue(self) -> List[DataUnitBase]:
        """
        Return the current window of DataIO objects.

        Returns:
            List of DataIO in current window order.
        """
        return list(self.queue)

    def current_item(self) -> DataUnitBase:
        """
        Return the current DataIO in the queue without changing the index.

        Raises:
            IndexError: If the queue is empty or raw_data is empty.
        """
        if not self.queue or not self.raw_data:
            raise IndexError("Traversal queue is empty")
        return self.queue[self.current_queue_index]

    def next_item(self) -> DataUnitBase:
        """
        Advance to the next item in raw_data with wraparound, update queue, and return current item.

        Returns:
            The DataIO at the new position.

        Raises:
            IndexError: If the queue is empty or raw_data is empty.
        """
        if not self.raw_data:
            raise IndexError("No data loaded")

        # Move to next position in raw_data with wraparound
        self.current_raw_index = (self.current_raw_index + 1) % len(self.raw_data)

        # Update queue to reflect new position
        self._init_queue()

        return self.current_item()

    def previous_item(self) -> DataUnitBase:
        """
        Move to the previous item in raw_data with wraparound, update queue, and return current item.

        Returns:
            The DataIO at the new position.

        Raises:
            IndexError: If the queue is empty or raw_data is empty.
        """
        if not self.raw_data:
            raise IndexError("No data loaded")

        # Move to previous position in raw_data with wraparound
        self.current_raw_index = (self.current_raw_index - 1) % len(self.raw_data)

        # Update queue to reflect new position
        self._init_queue()

        return self.current_item()

    def get_current_position(self) -> tuple[int, int]:
        """
        Get current positions in both queue and raw data.

        Returns:
            Tuple of (current_queue_index, current_raw_index)
        """
        return (self.current_queue_index, self.current_raw_index)

    def get_position_info(self) -> Dict[str, int]:
        """
        Get detailed position information.

        Returns:
            Dictionary with position details including total count.
        """
        return {
            'queue_index': self.current_queue_index,
            'raw_index': self.current_raw_index,
            'total_items': len(self.raw_data),
            'queue_length': self.queue_length
        }

    def _read_csv(self, csv_path: Path) -> List[Dict[str, str]]:
        with csv_path.open(newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row")
            return list(reader)

    def _validate_columns(self, rows: List[Dict[str, str]]) -> None:
        if not rows:
            raise ValueError("CSV file contains no data rows")
        cols = rows[0].keys()
        if 'uid' not in cols:
            raise ValueError("CSV must contain 'uid' column")
        if len(cols) < 2:
            raise ValueError(
                "CSV must contain at least one resource column besides 'uid'"
            )

    def _validate_unique_uids(self, rows: List[Dict[str, str]]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for row in rows:
            uid = row['uid']
            if uid in seen:
                duplicates.add(uid)
            seen.add(uid)
        if duplicates:
            raise ValueError(f"Duplicate uid values found in file: {duplicates}")


if __name__ == "__main__":
    # Example usage with queue_length=1
    manager = DataManager(queue_length=1)
    csv_path = Path("/Users/iejohnson/NAMIC/CART/sample_data/example_cohort.csv")
    manager.set_data_cohort_csv(csv_path)
    manager.load_data()  # uses configured CSV

    print("Initial state:")
    print(f"Queue: {[item.uid for item in manager.get_queue()]}")
    print(f"Current item: {manager.current_item().uid}")
    print(f"Position: {manager.get_position_info()}")

    print("\nAfter next:")
    next_item = manager.next_item()
    print(f"Next item: {next_item.uid}")
    print(f"Position: {manager.get_position_info()}")

    print("\nAfter previous:")
    prev_item = manager.previous_item()
    print(f"Previous item: {prev_item.uid}")
    print(f"Position: {manager.get_position_info()}")