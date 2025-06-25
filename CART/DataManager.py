from __future__ import annotations
from pathlib import Path
import csv
from collections import deque

# TODO: Replace Dummy Implementation with actual imports
class DataIO:
    def __init__(self, uid: str, resources: dict[str, str]) -> None:
        self.uid = uid
        self.resources = resources

class TaskConfig:
    pass

class DataManager:
    """
    Manages CSV data and provides a fixed-size window (queue) of DataIO objects
    with efficient forward/backward traversal.

    Attributes:
        config: Optional TaskConfig for behavior customization.
        raw_data: List of row dicts loaded from CSV.
        queue_length: Number of DataIO objects in the traversal window.
        queue: Deque holding current window of DataIO objects.
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
        self.raw_data: list[dict[str, str]] = []
        self.queue_length = queue_length
        self.queue: deque[DataIO] = deque(maxlen=self.queue_length)
        self.current_queue_index: int = 0

    def load_data(self, csv_path: Path) -> None:
        """
        Load CSV into raw_data, validate, and initialize the traversal queue.

        Args:
            csv_path: Path to CSV file.

        Raises:
            ValueError: If CSV is invalid.
        """
        rows = self._read_csv(csv_path)
        self._validate_columns(rows)
        self._validate_unique_uids(rows)
        self.raw_data = rows
        self._init_queue()
        print(f"Loaded {len(rows)} rows from {csv_path}")

    def _init_queue(self) -> None:
        """
        Populate the queue with the first `queue_length` DataIO objects
        and reset the traversal index.
        """
        self.queue.clear()
        initial = self.raw_data[: self.queue_length]
        for row in initial:
            self.queue.append(
                DataIO(uid=row['uid'], resources={k: v for k, v in row.items() if k != 'uid'})
            )
        self.current_queue_index = 0

    def get_queue(self) -> list[DataIO]:
        """
        Return the current window of DataIO objects.
        """
        return list(self.queue)

    def current_item(self) -> DataIO:
        """
        Return the current DataIO in the queue without changing the index.

        Raises:
            IndexError: If the queue is empty.
        """
        length = len(self.queue)
        if length == 0:
            raise IndexError("Traversal queue is empty")
        return self.queue[self.current_queue_index]

    def next_item(self) -> DataIO:
        """
        Advance the traversal pointer forward by one within the queue.

        Returns:
            The next DataIO in the window.

        Raises:
            IndexError: If no items are in the queue.
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
            IndexError: If no items are in the queue.
        """
        length = len(self.queue)
        if length == 0:
            raise IndexError("Traversal queue is empty")
        self.current_queue_index = (self.current_queue_index - 1) % length
        return self.queue[self.current_queue_index]

    def _read_csv(self, csv_path: Path) -> list[dict[str, str]]:
        with csv_path.open(newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            if reader.fieldnames is None:
                raise ValueError("CSV file has no header row")
            return list(reader)

    def _validate_columns(self, rows: list[dict[str, str]]) -> None:
        if not rows:
            raise ValueError("CSV file contains no data rows")
        cols = rows[0].keys()
        if 'uid' not in cols:
            raise ValueError("CSV must contain 'uid' column")
        if len(cols) < 2:
            raise ValueError("CSV must contain at least one resource column besides 'uid'")

    def _validate_unique_uids(self, rows: list[dict[str, str]]) -> None:
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
    manager.load_data(Path("/Users/iejohnson/NAMIC/CART/sample_data/example_cohort.csv"))
    print([item.uid for item in manager.get_queue()])
    print(manager.current_item().uid)
    print(manager.next_item().uid)
    print(manager.next_item().uid)
    print(manager.previous_item().uid)
