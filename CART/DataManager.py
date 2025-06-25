from __future__ import annotations
from collections import deque
from pathlib import Path
import csv

# TODO: Replace Dummy Implementation with actual imports
class DataIO:
    def __init__(self, uid: str, resources: dict[str, str]) -> None:
        self.uid = uid
        self.resources = resources

class TaskConfig:
    pass

class DataManager:
    """
    Base class for managing CSV data input and converting rows into DataIO objects.

    Attributes:
        config: Optional TaskConfig for customizing behavior.
        raw_data: List of row dicts loaded from the last CSV.
        queue: Rolling queue of DataIO objects built on demand.
    """

    def __init__(
        self,
        config: TaskConfig | None = None,
        queue_length: int = 1,
    ) -> None:
        """
        Initialize DataManager with optional configuration and queue capacity.

        Args:
            config: Configuration object for customizing behavior.
            queue_length: Maximum number of DataIO objects to retain in the rolling queue.
        """
        self.config = config
        self.raw_data: list[dict[str, str]] = []
        self.queue_length = queue_length
        self.queue: deque[DataIO] = deque(maxlen=self.queue_length)
        self.current_index: int = 0

    def load_data(self, csv_path: Path) -> None:
        """
        Read a CSV file, validate its structure, update raw_data,
        and reset the rolling queue and index.

        Args:
            csv_path: Path to the CSV file.

        Raises:
            ValueError: If the CSV structure or content is invalid.
        """
        rows = self._read_csv(csv_path)
        self._validate_columns(rows)
        self._validate_unique_uids(rows)
        self.raw_data = rows
        self.queue.clear()
        self.current_index = 0
        print(f"Loaded {len(rows)} rows from {csv_path}")

    def get_queue(self) -> list[DataIO]:
        """
        Retrieve the current rolling queue of DataIO objects.
        If the queue is empty, populate it based on raw_data,
        current_index, and queue_length.

        Returns:
            A list of DataIO instances in FIFO order.
        """
        if not self.queue:
            self._populate_queue()
        return list(self.queue)

    def _populate_queue(self) -> None:
        """
        Populate the rolling queue with DataIO objects from raw_data
        starting at current_index, wrapping around as needed.
        Advances current_index by queue_length.
        """
        total = len(self.raw_data)
        if total == 0:
            return
        for _ in range(self.queue_length):
            idx = self.current_index % total
            row = self.raw_data[idx]
            data_io = DataIO(uid=row['uid'], resources={k: v for k, v in row.items() if k != 'uid'})
            self.queue.append(data_io)
            self.current_index += 1

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
    # Example usage
    manager = DataManager()
    try:
        manager.load_data(Path("/Users/iejohnson/NAMIC/CART/sample_data/example_cohort.csv"))
        manager.raw_data
    except ValueError as e:
        print(f"Error loading data: {e}")