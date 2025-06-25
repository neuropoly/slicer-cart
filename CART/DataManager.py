from __future__ import annotations
from pathlib import Path
import csv
from collections import deque
from typing import Optional, List, Dict

# TODO: Replace Dummy Implementation with actual imports
class DataIO:
    """
    Represents a single data record with a unique identifier and associated resources.
    """

    def __init__(self, uid: str, resources: Dict[str, str]) -> None:
        self.uid = uid
        self.resources = resources

class TaskConfig:
    """
    Placeholder for future configuration settings.
    """
    pass

class DataManager:
    """
    Manages a CSV-based cohort and provides a fixed-size window of DataIO
    objects for efficient forward/backward traversal.

    Attributes:
        config: Optional TaskConfig for behavior customization.
        _data_cohort_csv: Path to the cohort CSV file.
        raw_data: List of row dictionaries loaded from CSV.
        queue_length: Number of DataIO objects in the traversal window.
        queue: Deque holding the current window of DataIO objects.
        current_queue_index: Position within the queue for traversal.
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
            queue_length: Max number of DataIO objects in the window.
        """
        self.config = config
        self._data_cohort_csv: Path | None = None
        self.raw_data: List[Dict[str, str]] = []
        self.queue_length = queue_length
        self.queue: deque[DataIO] = deque(maxlen=self.queue_length)
        self.current_queue_index: int = 0

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
        self._init_queue()
        print(f"Loaded {len(rows)} rows from {path}")

    def _init_queue(self) -> None:
        """
        Populate the queue with the first `queue_length` DataIO objects
        and reset the traversal index.
        """
        self.queue.clear()
        initial = self.raw_data[: self.queue_length]
        for row in initial:
            self.queue.append(
                DataIO(
                    uid=row['uid'],
                    resources={k: v for k, v in row.items() if k != 'uid'}
                )
            )
        self.current_queue_index = 0

    def get_queue(self) -> List[DataIO]:
        """
        Return the current window of DataIO objects.

        Returns:
            List of DataIO in current window order.
        """
        return list(self.queue)

    def current_item(self) -> DataIO:
        """
        Return the current DataIO in the queue without changing the index.

        Raises:
            IndexError: If the queue is empty.
        """
        if not self.queue:
            raise IndexError("Traversal queue is empty")
        return self.queue[self.current_queue_index]

    def next_item(self) -> DataIO:
        """
        Advance the traversal pointer forward by one within the queue.

        Returns:
            The next DataIO in the window.

        Raises:
            IndexError: If the queue is empty.
        """
        length = len(self.queue)
        if length == 0:
            raise IndexError("Traversal queue is empty")
        self.current_queue_index = (self.current_queue_index + 1) % length
        return self.queue[self.current_queue_index]

    def previous_item(self) -> DataIO:
        """
        Move the traversal pointer backward by one within the queue.

        Returns:
            The previous DataIO in the window.

        Raises:
            IndexError: If the queue is empty.
        """
        length = len(self.queue)
        if length == 0:
            raise IndexError("Traversal queue is empty")
        self.current_queue_index = (self.current_queue_index - 1) % length
        return self.queue[self.current_queue_index]

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
    manager = DataManager(queue_length=3)
    csv_path = Path("/Users/iejohnson/NAMIC/CART/sample_data/example_cohort.csv")
    manager.set_data_cohort_csv(csv_path)
    manager.load_data()  # uses configured CSV
    print([item.uid for item in manager.get_queue()])
    print(manager.current_item().uid)
    print(manager.next_item().uid)
    print(manager.previous_item().uid)
