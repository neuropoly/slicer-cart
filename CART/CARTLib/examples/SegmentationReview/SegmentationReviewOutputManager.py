import csv
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import qt
import slicer

from CARTLib.utils.data import save_segmentation_to_nifti
from CARTLib.utils.config import ProfileConfig

from SegmentationReviewUnit import (
    SegmentationReviewUnit,
)

VERSION = 0.02


class OutputMode(Enum):
    PARALLEL_DIRECTORY = "parallel"
    OVERWRITE_ORIGINAL = "overwrite"


class SegmentationReviewOutputManager:
    """
    Unified output manager that handles both parallel directory and overwrite original modes.
    Now includes CSV tracking for centralized logging of all completed data.
    """

    UID_KEY = "uid"
    AUTHOR_KEY = "author"
    TIMESTAMP_KEY = "timestamp"
    OUTPUT_MODE_KEY = "output_mode"
    INPUT_SEGMENTATION_KEY = "original_segmentation_path"
    SEGMENTATION_PATH_KEY = "segmentation_path"
    SIDECAR_PATH_KEY = "sidecar_path"
    VERSION_KEY = "version"
    NOTES_KEY = "notes"

    HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        TIMESTAMP_KEY,
        OUTPUT_MODE_KEY,
        SEGMENTATION_PATH_KEY,
        SIDECAR_PATH_KEY,
        INPUT_SEGMENTATION_KEY,
        VERSION_KEY,
        NOTES_KEY,
    ]

    def __init__(
        self,
        profile: ProfileConfig,
        output_mode: OutputMode,
        output_dir: Optional[Path] = None,
        csv_log_path: Optional[Path] = None,
    ):
        """
        Initialize the output manager.

        Args:
            profile: Profile configuration
            output_mode: OutputMode enum value (PARALLEL_DIRECTORY or OVERWRITE_ORIGINAL)
            output_dir: Required for PARALLEL_DIRECTORY mode, ignored for OVERWRITE_ORIGINAL
            csv_log_path: Optional path to CSV log file. If None, will be auto-generated.
        """
        self.profile = profile
        self.output_mode = output_mode
        self.output_dir = output_dir

        # Set up CSV logging
        self.csv_log_path: Path = self._setup_csv_log_path(csv_log_path)
        self.csv_log: dict[tuple[str, str], dict[str, str]] = self._init_csv_log()

        # Validate configuration
        if output_mode == OutputMode.PARALLEL_DIRECTORY and not output_dir:
            raise ValueError("output_dir is required for PARALLEL_DIRECTORY mode")

    ## ALIASES ##
    @property
    def profile_label(self) -> str:
        return self.profile.label

    ## CSV LOGGING ##
    def _setup_csv_log_path(self, csv_log_path: Optional[Path]) -> Path:
        """Set up the CSV log file path."""
        if csv_log_path:
            return csv_log_path

        # Auto-generate CSV log path
        return self.output_dir / "segmentation_review_log.csv"

    def _init_csv_log(self) -> dict[tuple[str, str], dict[str, str]]:
        """
        Load the CSV file designated by the user into memory; if one doesn't exist
        create it instead.
        """
        # If the CSV file already exists, load it
        if self.csv_log_path.exists():
            # Read existing entries
            csv_log = dict()
            if self.csv_log_path.exists():
                with open(self.csv_log_path, newline="") as csvfile:
                    reader = csv.DictReader(csvfile)
                    for i, row in enumerate(reader):
                        # Confirm the row has a UID; if not, skip it
                        uid = row.get('uid', None)
                        if not uid:
                            print(f"WARNING: Skipping entry #{i} in {self.csv_log_path}, lacked a valid UID")
                        # Generate a unique uid + author combo to use as our key
                        author = row.get('author', None)
                        # KO: In Python, as long as the contents of a tuple are hashable,
                        # the tuple is hashable as well!
                        csv_log[(uid, author)] = row

            return csv_log

        # Otherwise, make a new file and return an empty to-be-filled dictionary
        else:
            # Create parent directory if it doesn't exist
            self.csv_log_path.parent.mkdir(parents=True, exist_ok=True)

            # Create an empty CSV file with appropriate headers
            with open(self.csv_log_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.HEADERS)
                writer.writeheader()

            # Return an empty dictionary, as we don't have anything yet
            return dict()

    ## I/O ##
    def save_unit(
        self, unit: SegmentationReviewUnit, segments_to_save: list[str]
    ) -> str:
        """
        Save the contents of a data unit, as dictated by the current
        logic settings and user configurations.

        :param unit: The data unit to reference for node data
        :param segments_to_save: List of segmentation IDs that should be saved
        :return str: A message to report to the user when saving is complete
        """
        # Begin building the return message
        should_overwrite = self.output_mode == OutputMode.OVERWRITE_ORIGINAL
        if should_overwrite:
            result_msg = f"Overwrote the following entries for case '{unit.uid}':\n"
        else:
            result_msg = f"Saved the following entries for case '{unit.uid}':\n"

        for s in segments_to_save:
            # Determine the original source path for the segmentation and its sidecar
            segment_source_path = unit.segmentation_paths.get(s)
            sidecar_source_path = Path(str(segment_source_path).split('.')[0] + ".json")

            # Determine the output paths
            if self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
                segment_dest_path = segment_source_path
                sidecar_dest_path = sidecar_source_path
            else:
                segment_dest_path, sidecar_dest_path = self._get_parallel_outputs(s, unit)
            # Get the segmentation and volume node for the segmentation from the data unit
            segment_node = unit.segmentation_nodes[s]

            # Save the node to the destination path
            save_segmentation_to_nifti(segment_node, unit.primary_volume_node, segment_dest_path)

            # Save/update a copy of the sidecar
            self._save_sidecar(sidecar_source_path, sidecar_dest_path)

            # Add a log entry
            self._log_to_csv(
                unit,
                segment_dest_path,
                sidecar_dest_path,
                segment_source_path
            )

            # Extend the return message with the segment name
            result_msg += f"  * {s}\n"

        # Complete the message by denoting where the (now updated) log file is
        result_msg += f"\nSee log at '{str(self.csv_log_path.resolve())}' for details."
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
            self.AUTHOR_KEY: self.profile_label,
            self.TIMESTAMP_KEY: timestamp,
            self.OUTPUT_MODE_KEY: self.output_mode.value,
            self.SEGMENTATION_PATH_KEY: str(segmentation_path.resolve()),
            self.SIDECAR_PATH_KEY: str(sidecar_path.resolve()),
            self.INPUT_SEGMENTATION_KEY: str(initial_path.resolve()),
            self.VERSION_KEY: VERSION,
            # TODO Populate this with data from a note section or similar
            self.NOTES_KEY: f"Segmentation review completed using {self.output_mode.value} mode",
        }

        # Set/Replace the corresponding entry in our CSV log
        self.csv_log[(data_unit.uid, self.profile_label)] = log_entry

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
            "Author": self.profile_label,
            "Version": VERSION,
            "Date": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
            "OutputMode": self.output_mode.value,
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

        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            return (
                self.output_dir
                and self.output_dir.exists()
                and self.output_dir.is_dir()
            )
        elif self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
            return (
                True  # Can always attempt to overwrite (file will be created if needed)
            )

        return False

    def is_case_completed(self, case_data: dict[str, str]):
        # Check against the log; other solutions are too complicated
        uid = case_data["uid"]
        author = self.profile_label
        if self.csv_log.get((uid, author), None) is not None:
            return True
        return False

