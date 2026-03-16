import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import slicer.util

from CARTLib.examples.Segmentation.SegmentationUnit import SegmentationUnit
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.data import (
    save_segmentation_to_nifti,
    save_json_sidecar,
    find_json_sidecar_path,
)
from CARTLib.utils.formatting import FilePathFormatter

if TYPE_CHECKING:
    # Avoid a cyclic reference
    from SegmentationConfig import SegmentationConfig

VERSION = 0.04


class SegmentationIO:
    """
    Managed saving (and, if requested, loading) segmentation files for the
    Segmentation task
    """

    ## LOGGING CONSTANTS ##
    UID_KEY = "uid"
    AUTHOR_KEY = "author"
    TIMESTAMP_KEY = "timestamp"
    INPUT_SEGMENTATION_KEY = "original_segmentation_path"
    SEGMENTATION_PATH_KEY = "segmentation_path"
    SIDECAR_PATH_KEY = "sidecar_path"
    VERSION_KEY = "version"

    HEADERS = [
        UID_KEY,
        AUTHOR_KEY,
        TIMESTAMP_KEY,
        SEGMENTATION_PATH_KEY,
        SIDECAR_PATH_KEY,
        INPUT_SEGMENTATION_KEY,
        VERSION_KEY,
    ]

    ## OUTPUT PARSING CONSTANTS ##
    UID_PLACEHOLDER = "%u"
    NAME_PLACEHOLDER = "%n"
    FULLNAME_PLACEHOLDER = "%N"
    JOBNAME_PLACEHOLDER = "%j"
    FILENAME_PLACEHOLDER = "%f"

    REPLACEMENT_MAP_DESCRIPTIONS = {
        UID_PLACEHOLDER: "The UID of the case, as specified in the Cohort file.",
        NAME_PLACEHOLDER: "The name of the segmentation, stripped of any 'Segmentation_' prefix.",
        FULLNAME_PLACEHOLDER: "The name of the segmentation, with 'Segmentation_' prefixes retained.",
        JOBNAME_PLACEHOLDER: "The name of the job, as defined during the job's initial creation.",
        FILENAME_PLACEHOLDER: "The original filename (without its extensions). Only valid for segmentations loaded from a file.",
    }

    @classmethod
    def build_placeholder_map(
        cls,
        uid: str = "sub-abc123",
        segmentation_name: str = "Segmentation_Example",
        job_name: str = "Job_Name",
        file_name: str = None,
    ) -> dict[str, str]:
        short_name = segmentation_name
        if short_name.lower().startswith("segmentation_"):
            short_name = short_name[13:]

        placeholder_map = {
            cls.UID_PLACEHOLDER: uid,
            cls.NAME_PLACEHOLDER: short_name,
            cls.FULLNAME_PLACEHOLDER: segmentation_name,
            cls.JOBNAME_PLACEHOLDER: job_name,
        }
        if file_name is not None:
            placeholder_map[cls.FILENAME_PLACEHOLDER] = file_name.split('.')[0]
        return placeholder_map

    @classmethod
    def format_output_str(
        cls,
        output_str: str,
        placeholder_map: dict[str, str],
        output_path: Path = Path("..."),
    ) -> Optional[str]:
        # Empty strings, and strings with trailing slashes, are invalid
        if len(output_str) < 1 or (output_str[-1] in {"/", "\\"}):
            return None

        # Format the string
        formatted_str = output_str
        for k, v in placeholder_map.items():
            formatted_str = formatted_str.replace(k, v)

        # Prepend the "output_path" if this isn't an absolute path
        if Path(formatted_str).is_absolute():
            return formatted_str
        else:
            return str(output_path / formatted_str)

    def __init__(self, master_config: MasterProfileConfig, job_config: JobProfileConfig, task_config: "SegmentationConfig"):
        self.master_config: MasterProfileConfig = master_config
        self.job_config: JobProfileConfig = job_config
        self.task_config: "SegmentationConfig" = task_config

        # Map of previous CSV log entries
        self._log_data: Optional[dict[tuple[str, str], dict[str, str]]] = None

    @property
    def log_path(self) -> Path:
        return self.job_config.output_path / f"{self.job_config.name}_log.csv"

    @property
    def log_data(self) -> Optional[dict[tuple[str, str], dict[str, str]]]:
        """
        The data currently stored within the CSV-based log file

        Get-only, as the log file and its contents are tightly bound to
        the output directory.
        """

        # If the data has already been cached, use it instead
        if self._log_data is not None:
            return self._log_data

        # If there's no CSV log path to load, do nothing
        if self.log_path is None:
            return None

        # Otherwise, try to (re-)build the CSV log
        log_data = dict()

        # If the CSV file already exists, load its contents
        if self.log_path.exists():
            with open(self.csv_log_path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for i, row in enumerate(reader):
                    # Confirm the row has a UID; if not, skip it
                    uid = row.get(self.UID_KEY, None)
                    if uid is None:
                        logging.warning(
                            f"Skipping entry #{i} in {self.csv_log_path}, lacked a valid UID."
                        )
                        continue
                    # Likewise, skip entries without an author
                    author = row.get(self.AUTHOR_KEY, None)
                    if author is None:
                        logging.warning(
                            f"Skipping entry #{i} in {self.csv_log_path}, lacked a valid author."
                        )
                        continue
                    # Update CSV log dictionary
                    log_data[(uid, author)] = row

        # Track and return the result
        self._log_data = log_data
        return log_data

    def save_unit(self, unit: SegmentationUnit):
        # Save each edited segmentation if they were requested by the user
        saved_edited = dict()
        error_edited = dict()
        for seg_id, seg_node in unit.segmentation_nodes.items():
            # Don't save custom segmentations twice
            if seg_id in unit.custom_segmentations.keys():
                continue
            seg_path = unit.segmentation_paths.get(seg_id, None)
            try:
                result = self._save_edited_segmentation(seg_node, unit, seg_id, seg_path)
                if result is None:
                    continue
                saved_edited[seg_id] = str(result)
            except Exception as e:
                error_edited[seg_id] = str(e)

        # Save each custom segmentation
        saved_customs = dict()  # Name: Destination Path
        error_customs = dict()  # Name: Reason
        for seg_id, seg_node in unit.custom_segmentations.items():
            try:
                result = self._save_custom_segmentation(seg_node, unit, seg_id)
                saved_customs[seg_id] = str(result)
            except Exception as e:
                error_customs[seg_id] = str(e)
        return saved_edited, saved_customs, error_edited, error_customs

    def _save_edited_segmentation(
        self,
        seg_node: "slicer.vtkMRMLSegmentationNode",
        unit: SegmentationUnit,
        seg_id: str,
        source_path: Path = None,
    ):
        """
        Save edits made to the specified segmentation node, referencing the given data
        unit and segmentation ID to fill in the resulting files w/ additional
        details.

        :param seg_node: The segmentation node that should be saved
        :param unit: The data unit the segmentation node is part of
        :param seg_id: The identifier used by the segmentation within the data unit
        :param source_path: The path the original segmentation was loaded from
        :return: The output path of the MAIN (.nii.gz) saved file
        :raises ValueError: If the values provided would result in a corrupted save file.
        """
        # Find the corresponding segmentation name
        seg_name = None
        for k in self.task_config.segmentations_to_save:
            if k in seg_id:
                seg_name = k
                break

        # If none was found, skip over it
        if seg_name is None:
            return None

        # Skip blank segmentations
        for sid in seg_node.GetSegmentation().GetSegmentIDs():
            if not self.task_config.save_blank_segmentations and (
                not slicer.util.arrayFromSegmentBinaryLabelmap(seg_node, sid).max()
                > 0
            ):
                msg = f"Skipped '{seg_name}'; segmentation was blank!"
                logging.info(msg)
                raise ValueError(msg)

        # Determine the short name for this segmentation
        short_name = seg_name
        if short_name.lower().startswith("segmentation_"):
            short_name = short_name[len("segmentation_") :]

        # Change the file-name
        if source_path is None:
            file_name = f"{unit.uid}_{short_name}"
            output_str = self.task_config.default_custom_output_path
        else:
            file_name = source_path.name.split(".")[0]
            output_str = self.task_config.edit_output_path
        placeholder_map = FilePathFormatter.build_default_placeholder_map(
            uid=unit.uid,
            short_name=short_name,
            long_name=seg_name,
            job_name=self.job_config.name,
            file_name=file_name,
        )
        # TODO: Make the extension configurable
        formatter = FilePathFormatter(
            root_path=self.job_config.output_path,
            placeholder_map=placeholder_map,
            extension=".nii.gz",
        )

        # If this is a new (previously missing) segmentation, use the default custom path
        output_str = formatter.format_string(output_str)

        # If the output string is none (invalid), log an error and end this loop
        if output_str is None:
            msg = f"Could not save '{seg_name}', output path string was invalid"
            logging.error(msg)
            raise ValueError(msg)

        # Set up for file saving
        seg_path = Path(output_str)

        # See if there's sidecar data we can copy + update
        sidecar_data = None
        if source_path:
            sidecar_path = find_json_sidecar_path(source_path)
            if sidecar_path.exists():
                with open(sidecar_path, 'r') as fp:
                    sidecar_data = json.load(fp)
        # If not, start from scratch
        if sidecar_data is None:
            sidecar_data = {
                "SpatialReference": "orig",
                "GeneratedBy": [],
            }
        # Add our new generated by entry
        generated_by = sidecar_data["GeneratedBy"]
        generated_by.append(
            {
                "Name": f"CART Segmentation Task [{self.job_config.name}]",
                "Version": VERSION,
                "Author": self.master_config.author,
                "Position": self.master_config.position,
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
        json_path = seg_path.parent / (seg_path.name.split('.')[0] + ".json")

        # Save everything and return
        save_segmentation_to_nifti(seg_node, unit.primary_volume_node, seg_path)
        save_json_sidecar(json_path, sidecar_data)
        return seg_path.resolve()

    def _save_custom_segmentation(
        self,
        seg_node: "slicer.vtkMRMLSegmentationNode",
        unit: SegmentationUnit,
        seg_id: str,
    ) -> Path:
        """
        Save the specified (custom) segmentation node, referencing the given data
        unit and segmentation ID to fill in the resulting files w/ additional
        details.

        :param seg_node: The segmentation node that should be saved
        :param unit: The data unit the segmentation node is part of
        :param seg_id: The identifier used by the segmentation within the data unit
        :return: The output path of the MAIN (.nii.gz) saved file
        :raises ValueError: If the values provided would result in a corrupted save file.
        """
        # Find the relevant config entry for this seg
        output_str = None
        color_hex = None
        seg_name = None
        for k, v in self.task_config.custom_segmentations.items():
            if k in seg_id:
                output_str = v.get("path_string", None)
                color_hex = v.get("color", None)
                seg_name = k
                break

        # If that search failed, log and end
        if seg_name is None:
            msg = f"Could not save '{seg_name}', no valid configuration entry exists for it."
            logging.error(msg)
            raise ValueError(msg)

        # Skip blank segmentations
        for sid in seg_node.GetSegmentation().GetSegmentIDs():
            if (
                not self.task_config.save_blank_segmentations
                and not slicer.util.arrayFromSegmentBinaryLabelmap(seg_node, sid).max()
                > 0
            ):
                msg = f"Skipped '{seg_name}'; segmentation was blank!"
                logging.info(msg)
                raise ValueError(msg)

        # Generate the output path string
        output_str = self.format_output_str(
            output_str,
            self.build_placeholder_map(unit.uid, seg_name, self.job_config.name),
            self.job_config.output_path,
        )

        # If the output string is none (invalid), log an error and end this loop
        if output_str is None:
            msg = f"Could not save '{seg_name}', output path string was invalid"
            logging.error(msg)
            raise ValueError(msg)

        # Set up for file saving
        stem_path = Path(output_str)

        # TODO: Allow user-customizable file format
        output_path = stem_path.parent / (stem_path.name + ".nii.gz")

        # Build the corresponding sidecar
        # TODO: Only create this if outputting to BIDS-like format
        sidecar_data = {
            "SpatialReference": "orig",
            "GeneratedBy": [
                {
                    "Name": f"CART Segmentation Task [{self.job_config.name}]",
                    "Version": VERSION,
                    "Author": self.master_config.author,
                    "Position": self.master_config.position,
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            ],
        }
        json_path = stem_path.parent / (stem_path.name + ".json")

        # Save everything and report
        save_segmentation_to_nifti(seg_node, unit.primary_volume_node, output_path)
        save_json_sidecar(json_path, sidecar_data)
        return output_path.resolve()
