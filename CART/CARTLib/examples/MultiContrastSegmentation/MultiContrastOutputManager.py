import csv
import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import qt
import slicer
from .MultiContrastSegmentationEvaluationDataUnit import (
    MultiContrastSegmentationEvaluationDataUnit,
)
from CARTLib.utils.data import save_segmentation_to_nifti
from CARTLib.utils.config import ProfileConfig

VERSION = 0.01


class OutputMode(Enum):
    PARALLEL_DIRECTORY = "parallel"
    OVERWRITE_ORIGINAL = "overwrite"


class MultiContrastOutputManager:
    """
    Unified output manager that handles both parallel directory and overwrite original modes.
    Now includes CSV tracking for centralized logging of all completed data.
    """

    UID_KEY = "uid"
    AUTHOR_KEY = "author"

    HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        "timestamp",
        "output_mode",
        "segmentation_path",
        "sidecar_path",
        "original_segmentation_path",
        "version",
        "processing_notes",
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

        # Auto-generate CSV log path based on output mode
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY and self.output_dir:
            return self.output_dir / "segmentation_review_log.csv"
        else:
            # For overwrite mode or when no output dir, use current working directory
            return Path.cwd() / f"segmentation_review_log_{self.profile_label}.csv"

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

    def save_segmentation(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> Optional[str]:
        """
        Save segmentation according to the configured output mode and log to CSV.

        Returns:
            None if successful, error message string if failed
        """
        try:
            # Get output destinations based on mode
            segmentation_out, sidecar_out = self.get_output_destinations(data_unit)

            # Create directories if needed (only for parallel mode)
            if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
                segmentation_out.parent.mkdir(parents=True, exist_ok=True)

            # Save the segmentation file
            self._save_segmentation(data_unit, segmentation_out)

            # Save/update the sidecar file
            self._save_sidecar(data_unit, sidecar_out)

            # Log to CSV
            self._log_to_csv(data_unit, segmentation_out, sidecar_out)

            return None  # Success
        except Exception as e:
            return str(e)

    def _log_to_csv(
        self,
        data_unit: MultiContrastSegmentationEvaluationDataUnit,
        segmentation_path: Path,
        sidecar_path: Path,
    ):
        """Log the completed processing to CSV file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create a new log entry for this UID Author pair
        log_entry = {
            self.UID_KEY: data_unit.uid,
            self.AUTHOR_KEY: self.profile_label,
            "timestamp": timestamp,
            "output_mode": self.output_mode.value,
            "segmentation_path": str(segmentation_path.resolve()),
            "sidecar_path": str(sidecar_path.resolve()),
            "original_segmentation_path": str(
                data_unit.get_primary_segmentation_path().resolve()
            ),
            "version": VERSION,
            # TODO Populate this with data from a note section or similar
            "processing_notes": f"Segmentation review completed using {self.output_mode.value} mode",
        }

        # Set/Replace the corresponding entry in our CSV log
        self.csv_log[(data_unit.uid, self.profile_label)] = log_entry

        # Write the (now updated) log to the corresponding file
        with open(self.csv_log_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.HEADERS)
            writer.writeheader()
            writer.writerows(self.csv_log.values())

    def get_output_destinations(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> tuple[Path, Path]:
        """
        Get output paths for segmentation and sidecar files based on the current mode.

        Returns:
            Tuple of (segmentation_path, sidecar_path)
        """
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            return self._get_parallel_destinations(data_unit.uid)
        elif self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
            return self._get_overwrite_destinations(data_unit)
        else:
            raise ValueError(f"Unknown output mode: {self.output_mode}")

    def _get_parallel_destinations(
        self, uid: str
    ) -> tuple[Path, Path]:
        """Get destinations for parallel directory mode."""
        # Define the target output directory
        target_dir = self.output_dir / f"{uid}/anat/"

        # File name, before extensions
        fname = f"{uid}_{self.profile_label}_seg"

        # Define the target output file paths
        segmentation_out = target_dir / f"{fname}.nii.gz"
        sidecar_out = target_dir / f"{fname}.json"

        return segmentation_out, sidecar_out

    def _get_overwrite_destinations(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> tuple[Path, Path]:
        """Get destinations for overwrite original mode."""
        segmentation_path = data_unit.get_primary_segmentation_path()
        if segmentation_path is None:
            # If no segmentation path is found, prompt user for save location
            segmentation_path = self._promptForSaveLocation(data_unit)
        sidecar_path = (
            segmentation_path.parent / f"{segmentation_path.name.split('.')[0]}.json"
        )
        # Assumes there are not any "." in the filename, which is a reasonable assumption for segmentation files.
        # Now will be able to suppoort both .nii.gz, .nii files, and .nrrd files ect.
        return segmentation_path, sidecar_path

    @staticmethod
    def _save_segmentation(
        data_unit: MultiContrastSegmentationEvaluationDataUnit, target_file: Path
    ):
        """
        Save the data unit's segmentation to the designated output file.
        """
        # Extract the relevant node data from the data unit
        seg_node = data_unit.primary_segmentation_node
        vol_node = data_unit.primary_volume_node

        # Save the segmentation using the utility function
        save_segmentation_to_nifti(seg_node, vol_node, target_file)

    def _save_sidecar(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit, target_file: Path
    ):
        """
        Save or update the sidecar JSON file with processing metadata.
        """
        sidecar_data = {}

        # Try to read existing sidecar data
        if self.output_mode == OutputMode.OVERWRITE_ORIGINAL:
            # For overwrite mode, read from the target location if it exists
            if target_file.exists():
                with open(target_file) as fp:
                    sidecar_data = json.load(fp)
        else:
            # For parallel mode, read from the original location
            original_sidecar = self._get_original_sidecar_path(data_unit)
            if original_sidecar and original_sidecar.exists():
                with open(original_sidecar) as fp:
                    sidecar_data = json.load(fp)

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

    def _get_original_sidecar_path(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> Optional[Path]:
        """
        Get the path to the original sidecar file for reading existing metadata.
        """
        # Get the base filename without extension from the segmentation path
        fname = str(data_unit.get_primary_segmentation_path()).split(".")[0]
        return Path(f"{fname}.json")

    def _promptForSaveLocation(self, data_unit) -> Optional[str]:
        """
        Prompt user for save location when original file doesn't exist.
        """
        prompt = qt.QFileDialog()
        prompt.setWindowTitle("Select Save Location")
        prompt.setAcceptMode(qt.QFileDialog.AcceptSave)
        prompt.setFileMode(qt.QFileDialog.AnyFile)

        # Set default filename based on data unit
        default_name = f"{data_unit.uid}_seg.nii.gz"
        prompt.selectFile(default_name)

        if prompt.exec():
            selected_files = prompt.selectedFiles()
            if selected_files:
                save_path = Path(selected_files[0])
                return save_path.as_posix()
        # If user cancels or no file is selected, return None
        slicer.util.warningDisplay("No save location selected. Please try again.")

        return None

    def can_save(
        self, data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit]
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

    def get_success_message(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> str:
        """
        Get an appropriate success message based on the output mode.
        """
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            seg_out, _ = self.get_output_destinations(data_unit)
            return (
                f"Segmentation '{data_unit.uid}' saved to:\n{seg_out.resolve()}\n\n"
                f"Processing logged to: {self.csv_log_path.resolve()}"
            )
        else:
            return (
                f"Segmentation '{data_unit.uid}' saved over original file.\n\n"
                f"Processing logged to: {self.csv_log_path.resolve()}"
            )

    def is_case_completed(self, case_data: dict[str, str]):
        # If we have a logging CSV, just check against it
        if self.csv_log:
            uid = case_data["uid"]
            author = self.profile_label
            if self.csv_log.get((uid, author), None) is not None:
                return True
            return False

        # Fallback; check against the files on disk instead
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            # If we're saving to a parallel directory, simply check if the output file exist
            uid = case_data['uid']
            a, b = self._get_parallel_destinations(uid)
            return a.exists() and b.exists()

        # If we're in overwrite mode and don't have a log, assume they want to go through everything
        return False

