import csv
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from CARTLib.utils.data import save_segmentation_to_nifti
from CARTLib.utils.config import JobProfileConfig

from SegmentationReviewUnit import (
    SegmentationReviewUnit,
)


VERSION = 0.03


class SegmentationReviewOutputManager:
    """
    Unified output manager that handles both parallel directory and overwrite original modes.
    Now includes CSV tracking for centralized logging of all completed data.
    """

    UID_KEY = "uid"
    AUTHOR_KEY = "author"
    TIMESTAMP_KEY = "timestamp"
    INPUT_SEGMENTATION_KEY = "original_segmentation_path"
    SEGMENTATION_PATH_KEY = "segmentation_path"
    SIDECAR_PATH_KEY = "sidecar_path"
    VERSION_KEY = "version"
    # NOTES_KEY = "notes"

    HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        TIMESTAMP_KEY,
        SEGMENTATION_PATH_KEY,
        SIDECAR_PATH_KEY,
        INPUT_SEGMENTATION_KEY,
        VERSION_KEY,
        # NOTES_KEY,
    ]

    def __init__(
        self,
        config: JobProfileConfig,
        with_logging: bool = True
    ):
        """
        Initialize an output manager for the Segmentation Review Task

        :param config: The job configuration to reference for settings

        :param output_dir: Where imaging files should be place, if not in Overwrite mode
        :param with_logging: Whether to track a log of edits in a CSV file.
        :param csv_log_path: A path to the CSV file to log edits too.
            Created if it does not exist.
        """
        self.config = config

        # CSV logging
        self._csv_log: Optional[dict[tuple[str, str], dict[str, str]]] = None

    ## PROPERTIES ##
    @property
    def input_dir(self) -> Path:
        return self.config.data_path

    @property
    def output_dir(self) -> Path:
        return self.config.output_path

    @property
    def csv_log_path(self):
        return self.output_dir / "cart_segmentation_log.csv"

    @property
    def job_name(self) -> str:
        return self.config.name

    @property
    def csv_log(self) -> Optional[dict[tuple[str, str], dict[str, str]]]:
        """
        Get only, as the CSV log is cached and tightly bound to the current
        CSV log path (being designed to be locked together in 1:1 form).
        """
        # If there's no CSV log path to load, do nothing
        if self.csv_log_path is None:
            return None

        # If we already have a cached CSV log, use it
        if self._csv_log is not None:
            return self._csv_log

        # Otherwise, try to (re-)build the CSV log
        csv_log = dict()

        # If the CSV file already exists, load its contents
        if self.csv_log_path.exists():
            with open(self.csv_log_path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for i, row in enumerate(reader):
                    # Confirm the row has a UID; if not, skip it
                    uid = row.get('uid', None)
                    if uid is None:
                        print(f"WARNING: Skipping entry #{i} in {self.csv_log_path}, lacked a valid UID")
                    # Generate a unique uid + author combo to use as our key
                    author = row.get('author', None)
                    csv_log[(uid, author)] = row

        # Track and return the result
        self._csv_log = csv_log
        return csv_log

    ## I/O ##
    def save_unit(
        self, unit: SegmentationReviewUnit, segments_to_save: list[str]
    ) -> str:
        """
        Save the contents of a data unit, as dictated by the current
        settings and user configurations.

        :param unit: The data unit to reference for node data
        :param segments_to_save: List of segmentation IDs that should be saved
        :return str: A message to report to the user when saving is complete
        """
        # Begin building the return message
        result_msg = f"Saved the following entries for case '{unit.uid}':\n"

        for s in segments_to_save:
            # Determine the original source path for the segmentation and its sidecar
            segment_source_path = unit.segmentation_paths.get(s)
            sidecar_source_path = Path(str(segment_source_path).split('.')[0] + ".json")

            # Determine the output paths
            if self.input_dir in segment_source_path.parents:
                # If the original files were within our data dir, preserve their folder structure
                segment_dest_path = self.output_dir / segment_source_path.relative_to(self.input_dir)
                sidecar_dest_path = self.output_dir / sidecar_source_path.relative_to(self.input_dir)
            else:
                # Otherwise, generate new locations for them from scratch
                segment_dest_path, sidecar_dest_path = self._get_parallel_outputs(s, unit)
            # Get the corresponding segmentation node from the data unit
            segment_node = unit.segmentation_nodes[s]

            # Save the node to the destination path
            save_segmentation_to_nifti(segment_node, unit.primary_volume_node, segment_dest_path)

            # Save/update the sidecar
            self._save_sidecar(sidecar_source_path, sidecar_dest_path)

            # Save a log entry as well
            self._log_to_csv(
                unit,
                segment_dest_path,
                sidecar_dest_path,
                segment_source_path
            )

            # Extend the return message with the segment name
            result_msg += f"  * {s}\n"

        # Complete the message by denoting where the (now updated) log file is
        result_msg += f"\nLogged into file '{str(self.csv_log_path.resolve())}'."
        return result_msg

    def _log_to_csv(
        self,
        data_unit: SegmentationReviewUnit,
        segmentation_path: Path,
        sidecar_path: Path,
        initial_path: Path,
    ):
        """Log the completed processing to CSV file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create a new log entry for this UID Author pair
        log_entry = {
            self.UID_KEY: data_unit.uid,
            self.AUTHOR_KEY: self.job_name,
            self.TIMESTAMP_KEY: timestamp,
            self.SEGMENTATION_PATH_KEY: str(segmentation_path.resolve()),
            self.SIDECAR_PATH_KEY: str(sidecar_path.resolve()),
            self.INPUT_SEGMENTATION_KEY: str(initial_path.resolve()),
            self.VERSION_KEY: VERSION,
            # TODO Populate this with data from a note section or similar
            # self.NOTES_KEY: "FOOBAR!",
        }

        # Set/Replace the corresponding entry in our CSV log
        self.csv_log[(data_unit.uid, self.job_name)] = log_entry

        # If the CSV file doesn't already exist, create it and its parent directory
        if not self.csv_log_path.exists():
            self.csv_log_path.parent.mkdir(parents=True, exist_ok=True)
            self.csv_log_path.touch()

        # Write the (now updated) log to the corresponding file
        with open(self.csv_log_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.HEADERS)
            writer.writeheader()
            writer.writerows(self.csv_log.values())

    def _save_sidecar(
        self,
        source_file: Path,
        target_file: Path
    ):
        """
        Save or update the sidecar JSON file with processing metadata.
        """
        # Try to start with the previous sidecars data
        if source_file.exists():
            with open(source_file) as fp:
                sidecar_data = json.load(fp)
        else:
            # If there isn't any, start from scratch
            sidecar_data = {}

        # Create new entry for this processing step
        entry_time = datetime.now()
        new_entry = {
            "Name": "Segmentation Review [CART]",
            "Author": self.job_name,
            "Version": VERSION,
            "Date": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "CSVLogPath": (
                str(self.csv_log_path.resolve()) if self.csv_log_path else None
            ),
        }

        # Add the new entry to the GeneratedBy list
        generated_by = sidecar_data.get("GeneratedBy", [])
        generated_by.append(new_entry)
        sidecar_data["GeneratedBy"] = generated_by

        # Write the updated sidecar file
        with open(target_file, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    ## UTILS ##
    def _get_parallel_outputs(self, s: str, unit: SegmentationReviewUnit) -> tuple[Path, Path]:
        output_root = self.output_dir / unit.uid / "anat"
        segment_file_name = f"{s}.nii.gz"
        sidecar_file_name = f"{s}.json"
        segment_dest_path = output_root / segment_file_name
        sidecar_dest_path = output_root / sidecar_file_name
        return segment_dest_path, sidecar_dest_path

    def can_save(
        self, data_unit: Optional[SegmentationReviewUnit]
    ) -> bool:
        """
        Check whether we can save with the current configuration.

        Args:
            data_unit: The data unit to potentially save (can be None)

        Returns:
            True if saving is possible, False otherwise
        """
        if not data_unit:
            return False

        return (
            self.output_dir
            and self.output_dir.exists()
            and self.output_dir.is_dir()
        )

    def is_case_completed(self, case_data: dict[str, str]):
        # Check against the log; other solutions are too complicated
        uid = case_data["uid"]
        author = self.job_name
        if self.csv_log.get((uid, author), None) is not None:
            return True
        return False
