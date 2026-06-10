import csv
import json
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import slicer

from CARTLib.utils.config import MasterProfileConfig
from CARTLib.utils.data import (
    save_markups_to_nifti,
    save_markups_to_csv,
    save_markups_to_json,
    find_json_sidecar_path,
    stack_sidecars,
    add_generated_by_entry,
    save_json_sidecar, CARTStandardUnit, load_markups, create_emtpy_markup_fiducial_node, MarkupResource,
)

if TYPE_CHECKING:
    # Prevent cyclic imports
    from MarkupConfig import MarkupConfig

# Current Markup task version
VERSION = "0.0.3"


class MarkupUnit(CARTStandardUnit):

    def __init__(
        self,
        case_data: dict[str, str],
        data_path: Path,
        prior_data: dict = None,
        scene: slicer.vtkMRMLScene = slicer.mrmlScene,
    ) -> None:
        # Replace entries in our case data w/ our custom overrides
        if prior_data is not None:
            for k, v in prior_data.items():
                case_data[k] = v

        super().__init__(case_data, data_path, scene)

    def _load_markups_nodes(self, markup_paths: dict[str, Path]) -> None:
        # Ensure each "editable" markup has a corresponding node
        for key, path in markup_paths.items():
            # Try to read from file
            if path is not None:
                if path.exists():
                    # Try to load the markups naturally first
                    nodes = load_markups(path)
                # If there was a path specified, but it no longer exists, raise an error
                else:
                    raise ValueError(
                        f"Tried to load markup from path {path} which doesn't exist!"
                    )

            # If no file exists, create a blank markup node instead
            else:
                nodes = [create_emtpy_markup_fiducial_node(
                    f"{key} [{self.uid}]",
                    scene=self.scene,
                )]

            # Label the markups iteratively if there are multiple
            should_iter = len(nodes) > 1
            for i, node in enumerate(nodes):
                # Error out if the node is the wrong type (currently only fiducials are supported)
                if not isinstance(node, slicer.vtkMRMLMarkupsFiducialNode):
                    raise TypeError(
                        f"Expected a MarkupsFiducialNode, got {type(node)} for key {key}."
                    )
                # Determine how the node should be named
                if should_iter:
                    name = f"{MarkupResource.format_for_gui(key)} [{self.uid} - {i}]"
                else:
                    name = f"{key} [{self.uid}]"
                # Update the node's properties and track it
                node.SetName(name)
                self.markup_nodes[key] = node


class MarkupOutputStructure(Enum):
    BIDS = "BIDS"
    FolderPerCase = "Folder-per-Case"


class MarkupOutputFormat(Enum):
    NIFTI = "NIfTI"
    CSV = "CSV"
    JSON = "JSON"


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
        try:
            # Variable init, which should be filled in during the loop
            output_file = None

            # Save each markup node (with any modifications) into it
            for key, node in data_unit.markup_nodes.items():
                # Determine how the file should be named
                storage_node = node.GetStorageNode()
                if storage_node is None:
                    input_path = None
                else:
                    input_path = storage_node.GetFileName()
                    if input_path is None or input_path == "":
                        input_path = None
                    else:
                        input_path = Path(input_path)

                uid = data_unit.uid
                output_file = self.determine_output_file(uid, input_path, key)

                # Create the corresponding parent directory, if needed
                output_file.parent.mkdir(parents=True, exist_ok=True)

                # Save the node's contents to this file
                if self._config_reference.output_format == MarkupOutputFormat.NIFTI:
                    # Save the node to a NIfTI file, w/ a sidecar containing label data!
                    save_markups_to_nifti(
                        markup_node=node,
                        reference_volume=data_unit.reference_volume_node,
                        path=output_file
                    )
                elif self._config_reference.output_format == MarkupOutputFormat.CSV:
                    # Save the node to Slicer's native .csv format
                    save_markups_to_csv(markups_node=node, path=output_file)
                else:
                    # Save the node to Slicer's native .mrk.json format
                    save_markups_to_json(markups_node=node, path=output_file)

                # Update (or create) the sidecar files.
                current_sidecar = find_json_sidecar_path(output_file)
                if current_sidecar.exists():
                    # If we already had an output file, update it
                    with open(current_sidecar, 'r') as fp:
                        sidecar_data = json.load(fp)
                elif input_path is not None:
                    # If the input file had a sidecar, copy and extend it
                    prior_sidecar = find_json_sidecar_path(input_path)
                    current_sidecar = find_json_sidecar_path(output_file)
                    sidecar_data = stack_sidecars(prior_sidecar, current_sidecar)
                else:
                    # Otherwise, start from scratch
                    sidecar_data = {}
                # Add the "generated by" entry and proceed
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
        input_path: Optional[Path],
        label: str
    ) -> Path:
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

        # If this is a node w/o a previous file name, save it as such
        if input_path is None:
            file_name = f"{uid}_{label}.{extension}"
        else:
            original_name = input_path.name.split(".")[0]
            file_name = f"{original_name}.{extension}"

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
