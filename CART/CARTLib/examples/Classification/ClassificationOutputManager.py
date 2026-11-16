import csv
from ast import literal_eval
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Optional

from CARTLib.utils.config import JobProfileConfig

from ClassificationUnit import ClassificationUnit


VERSION = 0.02


class ClassificationOutputManager:

    UID_KEY = "uid"
    AUTHOR_KEY = "author"
    TIMESTAMP_KEY = "timestamp"
    VERSION_KEY = "version"
    CLASSES_KEY = "classifications"
    REMARKS_KEY = "other_remarks"

    LOG_HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        TIMESTAMP_KEY,
        VERSION_KEY,
        CLASSES_KEY,
        REMARKS_KEY
    ]

    def __init__(
        self,
        config: JobProfileConfig,
        author: str
    ):
        # Core attributes
        self.config = config
        self.author = author

    @property
    def output_dir(self) -> Path:
        return self.config.output_path

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
                    author = row.get(self.AUTHOR_KEY, None)
                    if not author:
                        print(f"Skipped entry #{i} in {self.csv_data_file}, as it lacks an author.")
                        continue
                    # Insert it into the data dict
                    csv_data[(uid, author)] = row

        # Return the resulting data
        return csv_data

    def get_data_for(self, uid: str) -> Optional[tuple[set, str]]:
        idx = (uid, self.author)
        entry = self.csv_data.get(idx)
        if entry is None:
            return None
        else:
            classes = entry[self.CLASSES_KEY]
            # If the class is a string, convert it to a set first
            if type(classes) == str:
                if classes == "":
                    classes = set()
                else:
                    classes = literal_eval(classes)
                    if type(classes) != set:
                        raise ValueError(f"Invalid entry for the classes in case '{uid}'.")
                    # classes = set(classes.strip("{").strip("}").split(", "))
                # Track the set form for later to save ourselves some work
                entry[self.CLASSES_KEY] = classes
            remarks = entry[self.REMARKS_KEY]
            return classes, remarks

    def save_unit(self, data_unit: ClassificationUnit):
        # Generate the entry key
        entry_key = (data_unit.uid, self.author)

        # Edge-case; if no classes are provided, using "" instead of "set()"
        unit_classes = data_unit.classes
        if len(unit_classes) < 1:
            unit_classes = ""

        # Add/replace the corresponding entry in our data dict
        self.csv_data[entry_key] = {
            self.UID_KEY: data_unit.uid,
            self.AUTHOR_KEY: self.author,
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
