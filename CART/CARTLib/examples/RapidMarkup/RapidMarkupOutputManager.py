import csv
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path

from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.data import save_markups_to_json, save_markups_to_nifti

from RapidMarkupUnit import RapidMarkupUnit

VERSION = "0.0.1"

# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from RapidMarkupConfig import RapidMarkupConfig

class RapidMarkupOutputManager:

    class OutputFormat(Enum):
        json = 0
        nifti = 1

    UID_KEY = "uid"
    PROFILE_KEY = "profile"
    TIMESTAMP_KEY = "timestamp"
    OUTPUT_KEY = "output_path"
    VERSION_KEY = "version"

    LOG_HEADERS = [
        UID_KEY,
        PROFILE_KEY,
        TIMESTAMP_KEY,
        OUTPUT_KEY,
        VERSION_KEY
    ]

    def __init__(
        self,
        config: "RapidMarkupConfig",
        output_dir: Path
    ):
        """
        Initialize the output manager.

        :param config: The current configuration instance for the task
        :param output_dir: Root path where all output should be placed
        """
        # We cannot make an output manager w/o an output directory!
        if not output_dir:
            raise ValueError("Cannot create a OutputManager without an output directory!")

        # Core attributes
        self.config = config
        self.output_dir = output_dir

    ## PROPERTIES ##
    @property
    def profile_config(self) -> ProfileConfig:
        """
        Wrapper for accessing the parent (profile) config; allows us to
        suppress the "incorrect type" warning once, rather than everywhere
        this is needed.
        """
        # noinspection PyTypeChecker
        return self.config.parent_config

    @property
    def profile_label(self) -> str:
        # Simple alias to sidestep a common argument chain
        return self.profile_config.label

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @output_dir.setter
    def output_dir(self, new_path: Path):
        # Update our output directory
        self._output_dir = new_path

        # Invalidate associated caches, if they exist
        if hasattr(self, "csv_log"):
            del self.csv_log
        if hasattr(self, "markup_output_dir"):
            del self.markup_output_dir

    @property
    def csv_log_file(self) -> Path:
        """
        Where the CSV log should be saved too.

        Read-only, as it's tightly associated with the output directory.
        """
        return self.output_dir / f"cart_markup.csv"

    @cached_property
    def csv_log(self) -> dict[tuple[str, str], dict[str, str]]:
        """
        Cached contents of the CSV log file currently monitored by this
        output manager.

        Cached and loaded lazily to prevent each and every change
        in the output directory from creating files all over the place
        (or, worse, loading large CSV logs immediately every single time)
        """
        # If not, initialize a blank CSV file
        csv_log = dict()

        # If a CSV log already exists in our output directory, load its contents
        if self.csv_log_file.exists():
            with open(self.csv_log_file) as fp:
                reader = csv.DictReader(fp)
                for i, row in enumerate(reader):
                    # Skip rows w/o a CSV
                    uid = row.get(self.UID_KEY, None)
                    if not uid:
                        print(f"Skipped entry #{i} in {self.csv_log_file}, as it lacks a UID")
                        continue
                    # Generate a UID + profile pair to act as our key
                    profile = row.get(self.PROFILE_KEY, None)
                    csv_log[(uid, profile)] = row

        return csv_log

    @cached_property
    def markup_output_dir(self) -> Path:
        """
        Cached property which, when requested, both finds AND creates
        the path where the markup output(s) should be placed.
        """
        # Determine the path and create the requisite folders
        markup_output_dir = self._output_dir / self.profile_label
        markup_output_dir.mkdir(parents=True, exist_ok=True)

        # Return the result for caching
        return markup_output_dir

    @property
    def output_format(self) -> OutputFormat:
        # Alias for ease of access
        return self.config.output_format

    ## I/O ##
    def save_markups(self, data_unit: RapidMarkupUnit) -> str:
        # Get the markup node from the data unit
        markup_node = data_unit.markup_node

        # If the output format is JSON, save it using Slicer's JSON formatting
        if self.output_format == self.OutputFormat.json:
            # Save it to the Slicer JSON format
            markup_output_file = self.markup_output_dir / f"{data_unit.uid}.mrk.json"
            save_markups_to_json(
                markups_node=markup_node,
                path=markup_output_file
            )
        # Otherwise, save in our "custom" NiFTI format w/ sidecar
        elif self.output_format == self.OutputFormat.nifti:
            markup_output_file = self.markup_output_dir / f"{data_unit.uid}.nii.gz"
            # noinspection PyTypeChecker
            save_markups_to_nifti(
                markup_node=markup_node,
                reference_volume=data_unit.primary_volume_node,
                path=markup_output_file,
                profile=self.profile_config
            )
        # If the user asked to save to an invalid output format,
        # yell at them for it and end.
        else:
            raise ValueError(
                f"Could not save to format '{self.output_format}', was not a valid format."
            )

        # Add/replace the entry in our CSV log with one representing this file
        new_entry_key = (data_unit.uid, self.profile_label)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.csv_log[new_entry_key] = {
            self.UID_KEY: data_unit.uid,
            self.PROFILE_KEY: self.profile_label,
            self.TIMESTAMP_KEY: timestamp,
            self.OUTPUT_KEY: str(self._output_dir.resolve()),
            self.VERSION_KEY: VERSION
        }

        # Save the new contents to file
        with open(self.csv_log_file, "w") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
            writer.writeheader()
            writer.writerows(self.csv_log.values())

        # Return a success message
        result_msg = (
            f"Markups saved to {str(markup_output_file.resolve())}."
            f"\n\n"
            f"Status logged to {str(self.csv_log_file.resolve())}."
        )
        return result_msg
