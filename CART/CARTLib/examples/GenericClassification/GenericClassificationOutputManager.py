import csv
import json
from datetime import datetime
from functools import cached_property
from pathlib import Path

from CARTLib.utils.config import JobProfileConfig

from GenericClassificationUnit import GenericClassificationUnit


VERSION = 0.01


class GenericClassificationOutputManager:

    UID_KEY = "uid"
    JOB_NAME_KEY = "job_name"
    TIMESTAMP_KEY = "timestamp"
    VERSION_KEY = "version"
    CLASSES_KEY = "classifications"
    REMARKS_KEY = "other_remarks"

    LOG_HEADERS = [
        UID_KEY,
        JOB_NAME_KEY,
        TIMESTAMP_KEY,
        VERSION_KEY,
        CLASSES_KEY,
        REMARKS_KEY
    ]

    def __init__(
        self,
        config: JobProfileConfig
    ):
        # Core attributes
        self.config = config

    @property
    def output_dir(self) -> Path:
        return self.config.output_path

    @property
    def job_name(self) -> str:
        # Simple alias to sidestep a common argument chain
        return self.config.name

    @property
    def csv_data_file(self) -> Path:
        """
        Where the CSV log should be saved too.

        Read-only, as it's tightly associated with the output directory.
        """
        return self.output_dir / f"cart_classifications.csv"

    @cached_property
    def csv_data(self) -> dict[tuple[str, str], dict]:
        """
        Cached contents of the CSV data file currently monitored by this
        output manager.

        Cached and loaded lazily to prevent each and every change
        in the output directory from creating files all over the place
        (or, worse, loading large CSV logs immediately every single time)
        """
        # Initialize a blank CSV dict
        csv_data = dict()

        # If a CSV data file already exists, try to load its contents
        if self.csv_data_file.exists():
            with open(self.csv_data_file) as fp:
                reader = csv.DictReader(fp)
                for i, row in enumerate(reader):
                    # Skip rows w/o a valid UID entry
                    uid = row.get(self.UID_KEY, None)
                    if not uid:
                        print(f"Skipped entry #{i} in {self.csv_data_file}, as it lacks a UID.")
                        continue
                    # Skip rows w/o a valid profile label
                    uid = row.get(self.JOB_NAME_KEY, None)
                    if not uid:
                        print(f"Skipped entry #{i} in {self.csv_data_file}, as it lacks a Profile ID.")
                        continue
                    # Generate a UID + profile pair to act as our key
                    profile = row.get(self.JOB_NAME_KEY, None)
                    # Insert it into the data dict
                    csv_data[(uid, profile)] = row

        # Return the resulting data
        return csv_data

    @property
    def json_metadata_file(self) -> Path:
        """
        Where the JSON metadata should be saved too.

        Read-only, as it's tightly associated with the output directory.
        """
        return self.output_dir / f"cart_classifications.json"

    def save_unit(self, data_unit: GenericClassificationUnit):
        # Generate the entry key
        entry_key = (data_unit.uid, self.job_name)

        # Edge-case; if no classes are provided, using "" instead of "set()"
        unit_classes = data_unit.classes
        if len(unit_classes) < 1:
            unit_classes = ""

        # Add/replace the corresponding entry in our data dict
        self.csv_data[entry_key] = {
            self.UID_KEY: data_unit.uid,
            self.JOB_NAME_KEY: self.job_name,
            self.TIMESTAMP_KEY: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.VERSION_KEY: VERSION,
            self.CLASSES_KEY: unit_classes,
            self.REMARKS_KEY: data_unit.remarks
        }

        # Save the results to file
        with open(self.csv_data_file, "w") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
            writer.writeheader()
            writer.writerows(self.csv_data.values())

        # Return a success message
        result_msg = (
            f"Classifications saved to {str(self.csv_data_file.resolve())}."
        )
        return result_msg

    def read_metadata(self) -> dict[str, str]:
        # If the JSON file doesn't exist, return an empty dict
        if not self.json_metadata_file.exists():
            return dict()
        # Otherwise, read the JSON file's contents and return it
        with open(self.json_metadata_file, "r") as fp:
            class_map = json.load(fp)
            return class_map

    def save_metadata(self, class_map: dict[str, str]):
        # Just dumps the provided class map to file
        with open(self.json_metadata_file, "w") as fp:
            json.dump(class_map, fp, indent=2)
