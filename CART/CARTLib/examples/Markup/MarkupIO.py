import csv
import json
import shutil
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from CARTLib.utils.config import MasterProfileConfig
from CARTLib.utils.data import (
    save_markups_to_nifti,
    save_markups_to_csv,
    save_markups_to_json,
    find_json_sidecar_path,
    stack_sidecars,
    add_generated_by_entry,
    save_json_sidecar
)

if TYPE_CHECKING:
    # Prevent cyclic imports
    from MarkupUnit import MarkupUnit
    from MarkupConfig import MarkupConfig

# Current Markup task version
VERSION = "0.0.4"


class MarkupOutputStructure(Enum):
    BIDS = "BIDS"
    FolderPerCase = "Folder-per-Case"


class MarkupOutputFormat(Enum):
    NIFTI = "NIfTI"
    CSV = "CSV"
    JSON = "MRK.JSON"


class MarkupOutput:
    def __init__(self, config: "MarkupConfig", output_dir: Path = None):
        # Reference config
        self._config_reference = config

        # The directory to save everything into
        self._output_dir: Path = output_dir

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    @output_dir.setter
    def output_dir(self, new_dir: Path):
        # Change the output dir
        self._output_dir = new_dir
        # Clear the log cache, so it can implicitly sync when needed
        if self.log:
            del self.log

    @property
    def log_file(self) -> Path:
        """
        Where the TSV log should be saved too.

        Read-only, as it's tightly associated with the output directory.
        """
        return self._output_dir / f"cart_markup.csv"

    # Elements of the log file
    AUTHOR_KEY = "author"
    UID_KEY = "uid"
    TIMESTAMP_KEY = "timestamp"
    OUTPUT_KEY = "output_path"
    VERSION_KEY = "version"

    LOG_HEADERS = [
        AUTHOR_KEY,
        UID_KEY,
        TIMESTAMP_KEY,
        OUTPUT_KEY,
        VERSION_KEY
    ]

    @cached_property
    def log(self) -> dict[tuple[str, str], dict[str, str]]:
        """
        Cached contents of the log file currently monitored by this output manager.

        The log is a dictionary which uses the pair of the current username
        and case UID as its key, with each value being a dictionary in
        column: value format for the log file (see the LOG_HEADER constant prior
        for the names and order of these columns).

        Cached and loaded lazily to avoid needing to immediately read/write a log
        file whenever the output directory is changed to ensure sync.
        """
        # If the log file is a directory, something has gone very wrong
        if self.log_file.is_dir():
            raise ValueError(f"Cannot load log file '{str(self.log_file)}', as it is a directory!")

        log_data = dict()

        if self.log_file.exists():
            with open(self.log_file, 'r') as fp:
                reader = csv.DictReader(fp)
                for i, row in enumerate(reader):
                    uid = row.get(self.UID_KEY, None)
                    username = row.get(self.AUTHOR_KEY, None)
                    if any([x is None for x in [uid, username]]):
                        print(
                            f"Skipped entry #{i} in '{self.log_file}', as it lacked a UID or username."
                        )
                        continue
                    log_data[(username, uid)] = row

        return log_data

    def save_unit(self, data_unit: "MarkupUnit", profile: MasterProfileConfig):
        # Back out if an error occurs to avoid cascading issues later
        try:
            # Variable init, which should be filled in during the loop
            output_file = None

            # Fetch the reference volume's path name to use for file naming
            ref_volume = data_unit.reference_volume_node
            ref_path = self._find_source_path_for(ref_volume)

            # Save each markup node (with any modifications) into it
            for key, node in data_unit.markup_nodes.items():
                # Identify where the file should be saved
                uid = data_unit.uid
                output_file = self.determine_output_file(uid, key, ref_path)

                # Create the corresponding parent directory, if needed
                output_file.parent.mkdir(parents=True, exist_ok=True)

                # Before saving, check if we need to copy over the original markup's sidecar
                current_sidecar = find_json_sidecar_path(output_file)
                markup_filepath = self._find_source_path_for(node)
                if not current_sidecar.exists() and markup_filepath is not None:
                    original_sidecar = find_json_sidecar_path(markup_filepath)
                    # If there was an original sidecar, copy it over before proceeding
                    if original_sidecar.exists():
                        shutil.copy(original_sidecar, current_sidecar)

                # Save the node's contents to the desired file
                if self._config_reference.output_format == MarkupOutputFormat.NIFTI:
                    # Use CART's automated mapping if no metadata was available
                    metadata = data_unit.metadata_for(key)
                    if metadata is None:
                        value_map = None
                    else:
                        value_map = metadata.nifti_values
                    # Save the markup data using the value map, if available.
                    save_markups_to_nifti(
                        markup_node=node,
                        reference_volume=data_unit.reference_volume_node,
                        path=output_file,
                        value_map=value_map,
                    )
                elif self._config_reference.output_format == MarkupOutputFormat.CSV:
                    # Save the node to Slicer's native .csv format
                    save_markups_to_csv(markups_node=node, path=output_file)
                else:
                    # Save the node to Slicer's native .mrk.json format
                    save_markups_to_json(markups_node=node, path=output_file)

                # Update (or create) relevant sidecar data
                current_sidecar = find_json_sidecar_path(output_file)
                # If there's already a sidecar file, use it.
                if current_sidecar.exists():
                    with open(current_sidecar, "r") as fp:
                        sidecar_data = json.load(fp)
                # Otherwise, start from scratch
                else:
                    sidecar_data = {}

                # Add a "generated by" entry to the sidecar and save
                add_generated_by_entry(sidecar_data, profile)
                save_json_sidecar(current_sidecar, sidecar_data)

            # Update our log file to match
            log_entry_key = (profile.author, data_unit.uid)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.log[log_entry_key] = {
                self.AUTHOR_KEY: profile.author,
                self.UID_KEY: data_unit.uid,
                self.TIMESTAMP_KEY: timestamp,
                self.OUTPUT_KEY: str(output_file.resolve()),
                self.VERSION_KEY: VERSION,
            }
            # Save the new contents to file
            with open(self.log_file, "w") as fp:
                writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
                writer.writeheader()
                writer.writerows(self.log.values())
        except Exception as e:
            # If an error occurred, log it and proceed as-is
            log_entry_key = (profile.author, data_unit.uid)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.log[log_entry_key] = {
                self.AUTHOR_KEY: profile.author,
                self.UID_KEY: data_unit.uid,
                self.TIMESTAMP_KEY: timestamp,
                self.OUTPUT_KEY: "ERROR",
                self.VERSION_KEY: VERSION,
            }
            # Save the new contents to file
            with open(self.log_file, "w") as fp:
                writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
                writer.writeheader()
                writer.writerows(self.log.values())
            # Raise the error as normal
            raise e

    def determine_output_file(
        self,
        uid: str,
        label: str,
        volume_path: Optional[Path],
    ) -> Path:
        """
        Determine where the markup file would be saved, given its UID,
        the reference volume's path (if any), and its label.
        """
        # Determine the appropriate extension for the file
        if self._config_reference.output_format == MarkupOutputFormat.JSON:
            # Markdown JSON is unique in that it gets two extensions
            extension = "mrk.json"
        elif self._config_reference.output_format == MarkupOutputFormat.NIFTI:
            # Likewise, NIfTI is almost always saved compressed
            extension = "nii.gz"
        else:
            # Remaining case is CSV, which has no double-convention
            extension = "csv"

        # Shorten the label's name, in case it still has the identifier mark
        from MarkupUnit import EditableMarkupResource  # Delayed to avoid an error
        short_label = EditableMarkupResource.get_short_name(label)

        if volume_path is None:
            # Default generator, for when there was no valid reference volume (should never happen)
            file_name = f"{uid}_{short_label}.{extension}"
        else:
            # Use the reference volume's name verbatim if available, extended w/ the label
            original_name = volume_path.name.split(".")[0]
            file_name = f"{original_name}_{short_label}.{extension}"

        # Determine the output directory
        if self._config_reference.output_structure == MarkupOutputStructure.BIDS:
            # Split the "subject" and "session" parts of the UID, if they're present
            if "sub" in uid and "ses" in uid:
                sub, ses = uid.split(
                    "__"
                )  # TODO: Define this "magic" string somewhere explicitly
                stem_path = self.output_dir / sub / ses
            # Otherwise, use the case output dir we already have
            else:
                stem_path = self.output_dir / uid
            # Add an "anat" dir to the end to meet BIDS requirements
            stem_path /= "anat"
        # Otherwise, just put it into the case output directory
        else:
            stem_path = self.output_dir / uid

        # Combine the two to get our file name
        output_file = stem_path / file_name
        return output_file

    def is_unit_complete(self, author: str, uid: str):
        k = (author, uid)
        entry = self.log.get(k)
        if entry is None:
            return None
        else:
            return entry[self.OUTPUT_KEY] != "ERROR"

    @staticmethod
    def _find_source_path_for(node):
        """
        Reference's Slicer's storage node attributes to try and find the
        original file the node was generated from. Returns None if it
        could not be determined (due to the node being generated dynamically
        or having its backing storage node reset).
        """
        storage_node = node.GetStorageNode()
        ref_path = None
        if storage_node is not None:
            ref_file = storage_node.GetFileName()
            if ref_file is not None and ref_file != "":
                ref_path = Path(ref_file)
        return ref_path
