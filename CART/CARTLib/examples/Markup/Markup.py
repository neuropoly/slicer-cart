import csv
import json
import logging
from datetime import datetime
from enum import Enum
from functools import cached_property
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.core.DataUnitBase import DataUnitFactory
from CARTLib.utils.config import JobProfileConfig, DictBackedConfig, MasterProfileConfig
from CARTLib.utils.data import (
    CARTStandardUnit,
    save_markups_to_nifti,
    save_markups_to_json,
    find_json_sidecar_path,
    stack_sidecars,
    save_json_sidecar,
    add_generated_by_entry,
    create_emtpy_markup_fiducial_node,
    load_markups,
    MarkupResource,
    save_markups_to_csv,
)
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import CARTMarkupEditorWidget


if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


VERSION = "0.0.2"


class MarkupUnit(CARTStandardUnit):
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


@cart_task("Markup")
class MarkupTask(TaskBaseClass[MarkupUnit]):

    README_PATH = Path(__file__).parent / "README.md"

    @classmethod
    def description(cls):
        with open(cls.README_PATH, "r") as fp:
            txt = fp.read()

        # Remove the image, which cannot render in QT
        cleaned = []
        for l in txt.split('\n'):
            if "![" in l:
                continue
            cleaned.append(l)
        return "\n".join(cleaned)

    def __init__(
        self,
        master_profile: MasterProfileConfig,
        job_profile: JobProfileConfig,
        cohort_features: list[str]
    ):
        super().__init__(master_profile, job_profile, cohort_features)

        # GUI and data unit
        self.gui: Optional[MarkupGUI] = None
        self.data_unit: Optional[MarkupUnit] = None

        # Markup tracking
        self.markups: list[tuple[str, Optional[str]]] = []
        self.untracked_markups: dict[str, list[str]] = {}

        # Config management
        self.config: MarkupConfig = MarkupConfig(parent_config=self.job_profile)

        # Output logging
        self._output_manager: MarkupOutput = MarkupOutput(
            config=self.config, output_dir=self.job_profile.output_path
        )

    def setup(self, container: qt.QWidget):
        # Initialize the GUI
        self.gui = MarkupGUI(self)
        container.setLayout(self.gui.setup())

        # If we have a data unit, notify the GUI to synchronize
        if self.data_unit:
            self.gui.sync()

    def receive(self, data_unit: MarkupUnit):
        # Update the data unit
        self.data_unit = data_unit

        # If we have a GUI, sync it
        if self.gui:
            self.gui.sync()

    def save(self) -> Optional[str]:
        msg = self._output_manager.save_unit(self.data_unit, self.master_profile)
        if self.gui and msg is not None:
            self.gui.saveSuccessPrompt(msg)

    def isTaskComplete(self, case_data: dict[str, str]) -> bool:
        author = self.master_profile.author
        uid = case_data['uid']
        return self._output_manager.is_unit_complete(author, uid)

    @classmethod
    def getDataUnitFactory(cls) -> DataUnitFactory:
        return MarkupUnit

    @classmethod
    def init_config(cls, job_config: JobProfileConfig) -> DictBackedConfig:
        return MarkupConfig(job_config)


class MarkupGUI:
    def __init__(self, bound_task: MarkupTask):
        self.bound_task = bound_task

        # Widget displaying the data unit
        self.markupEditor: CARTMarkupEditorWidget = CARTMarkupEditorWidget()

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout
        layout = qt.QFormLayout()

        # Insert the markup editor widget
        layout.addWidget(self.markupEditor)

        # Return the result
        return layout

    def sync(self):
        self.markupEditor.refresh()

    @property
    def data_unit(self) -> MarkupUnit:
        return self.bound_task.data_unit

    def saveSuccessPrompt(self, msg_text: str):
        msg = qt.QMessageBox()
        msg.setWindowTitle("Saved Markups!")
        msg.setText(msg_text)
        msg.setTextFormat(3)  # 3 -> Markdown enum value
        msg.setStandardButtons(qt.QMessageBox.Ok)
        return msg.exec()


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

    def save_unit(self, data_unit: MarkupUnit, profile: MasterProfileConfig) -> str:
        # Define (and, if need be, create) an output folder for this unit's case ID
        case_output = self.output_dir / data_unit.uid
        case_output.mkdir(parents=True, exist_ok=True)

        # Save each markup node (with any modifications) into it
        unknown_idx = 0
        # TODO: Add user naming support for "custom" markups
        saved_files = []
        failed_files = []
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

            output_file = self.determine_output_file(
                case_output, data_unit, input_path, key, unknown_idx
            )

            # Create hte corresponding parent directory, if needed
            output_file.parent.mkdir(exist_ok=True)

            # Delete any previous sidecar file associated with our output to avoid unintentional carry-over
            prior_sidecar = find_json_sidecar_path(output_file)
            prior_sidecar.unlink(missing_ok=True)

            # Save the node's contents to this file
            try:
                if self._config_reference.output_format == MarkupOutputFormat.NIFTI:
                    # Save the node to a NIfTI file, w/ a sidecar containing label data!
                    save_markups_to_nifti(
                        markup_node=node,
                        reference_volume=data_unit.reference_volume_node,
                        path=output_file
                    )
                    saved_files.append(output_file)
                elif self._config_reference.output_format == MarkupOutputFormat.CSV:
                    # Save the node to Slicer's native .csv format
                    save_markups_to_csv(markups_node=node, path=output_file)
                    saved_files.append(output_file)
                else:
                    # Save the node to Slicer's native .mrk.json format
                    save_markups_to_json(markups_node=node, path=output_file)
                    saved_files.append(output_file)
            except Exception as e:
                logging.error(f"Failed to save markup file {output_file.name}.", exc_info=e)
                failed_files.append(output_file)

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
            self.OUTPUT_KEY: str(case_output.resolve()),
            self.VERSION_KEY: VERSION,
        }

        # Save the new contents to file
        with open(self.log_file, "w") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.LOG_HEADERS)
            writer.writeheader()
            writer.writerows(self.log.values())

        # Build the result message
        result_msg = ""
        if len(saved_files) > 0:
            result_msg += _("Saved the following files:\n")
            for f in saved_files:
                result_msg += f"  * {str(f)}\n"
            result_msg += "\n"
        if len(failed_files):
            result_msg += _("Failed to save the following files:\n")
            for f in failed_files:
                result_msg += f"  * {str(f)}\n"
            result_msg += "\n"

        return result_msg

    def determine_output_file(
        self,
        case_output: Path,
        data_unit: MarkupUnit,
        input_path: Optional[Path],
        key: str,
        unknown_idx: int,
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
            file_name = f"{data_unit.uid}_{key}_{unknown_idx}.{extension}"
            unknown_idx += 1
        else:
            original_name = input_path.name.split(".")[0]
            file_name = f"{original_name}.{extension}"

        # Determine the output directory
        if self._config_reference.output_structure == MarkupOutputStructure.BIDS:
            uid = data_unit.uid
            # Split the "subject" and "session" parts of the UID, if they're present
            if "sub" in uid and "ses" in uid:
                sub, ses = uid.split(
                    "__"
                )  # TODO: Define this "magic" string somewhere explicitly
                stem_path = self.job_config.output_path / sub / ses
            # Otherwise, use the case output dir we already have
            else:
                stem_path = case_output
            # Add an "anat" dir to the end to meet BIDS requirements
            stem_path /= "anat"
        # Otherwise, just put it into the case output directory
        else:
            stem_path = case_output

        # Combine the two to get our file name
        output_file = stem_path / file_name
        return output_file

    def is_unit_complete(self, author: str, uid: MarkupUnit):
        return (author, uid) in self.log.keys()


class MarkupOutputStructure(Enum):
    BIDS = "BIDS"
    FolderPerCase = "Folder-per-Case"


class MarkupOutputFormat(Enum):
    NIFTI = "NIfTI"
    CSV = "CSV"
    JSON = "JSON"


class MarkupConfig(DictBackedConfig):
    CONFIG_KEY = "markup"

    def __init__(self, parent_config: JobProfileConfig = None):
        super().__init__(parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    OUTPUT_STRUCTURE_KEY = "output_structure"

    @property
    def output_structure(self) -> MarkupOutputStructure:
        str_val = self.get_or_default(
            self.OUTPUT_STRUCTURE_KEY, MarkupOutputStructure.BIDS.value
        )
        return MarkupOutputStructure(str_val)

    @output_structure.setter
    def output_structure(self, new_val: MarkupOutputStructure):
        self.backing_dict[self.OUTPUT_STRUCTURE_KEY] = new_val.value
        self.has_changed = True

    OUTPUT_FORMAT_KEY = "output_format"

    @property
    def output_format(self):
        str_val = self.get_or_default(
            self.OUTPUT_FORMAT_KEY, MarkupOutputFormat.CSV.value
        )
        return MarkupOutputFormat(str_val)

    @output_format.setter
    def output_format(self, new_val: MarkupOutputFormat):
        self.backing_dict[self.OUTPUT_FORMAT_KEY] = new_val.value
        self.has_changed = True

    ALLOW_DUPLICATES_KEY = "allow_duplicates"

    @property
    def allow_duplicates(self) -> bool:
        return self.get_or_default(self.ALLOW_DUPLICATES_KEY, False)

    @allow_duplicates.setter
    def allow_duplicates(self, new_val: bool):
        self.backing_dict[self.ALLOW_DUPLICATES_KEY] = new_val
        self.has_changed = True

    HIDE_TO_EDIT = "hide_to_edit"

    @property
    def hide_to_edit(self) -> bool:
        return self.get_or_default(self.HIDE_TO_EDIT, False)

    @hide_to_edit.setter
    def hide_to_edit(self, new_val: bool):
        self.backing_dict[self.HIDE_TO_EDIT] = new_val
        self.has_changed = True

    def generateGUILayout(self) -> Optional[tuple[str, qt.QLayout]]:
        return _("Markup Configuration"), MarkupConfigGUILayout(self)


class MarkupConfigGUILayout(qt.QFormLayout):
    def __init__(self, config: MarkupConfig, parent = None):
        super().__init__(parent)

        # Output folder structure selection
        fileStructureComboBox = qt.QComboBox(None)
        fileStructureToolTip = _(
            "How the folders within the output directory should be organized."
        )
        fileStructureComboBox.setToolTip(fileStructureToolTip)
        fileStructureComboBox.addItems([x.value for x in MarkupOutputStructure])
        fileStructureComboBox.setCurrentText(config.output_structure.value)
        fileStructureLabel = qt.QLabel(_("Output File Structure:"))
        fileStructureLabel.setToolTip(fileStructureToolTip)
        self.addRow(fileStructureLabel, fileStructureComboBox)

        # Output file structure selection
        fileFormatComboBox = qt.QComboBox(None)
        fileFormatToolTip = _(
            "What file format (of Slicer's supported options) the markups should be saved in."
        )
        fileFormatComboBox.setToolTip(fileFormatToolTip)
        fileFormatComboBox.addItems([x.value for x in MarkupOutputFormat])
        fileFormatComboBox.setCurrentText(config.output_structure.value)
        fileFormatLabel = qt.QLabel(_("Output File Format:"))
        fileFormatLabel.setToolTip(fileFormatToolTip)
        self.addRow(fileFormatLabel, fileFormatComboBox)

        # Toggle-able options
        toggleLayout = qt.QFormLayout(None)
        self.addRow(toggleLayout)

        ## TODO
        # ## Duplicate Markups
        # duplicateMarkupsCheckBox = qt.QCheckBox()
        # duplicateMarkupsCheckBox.setChecked(config.allow_duplicates)
        # duplicateMarkupsLabel = qt.QLabel(_("Allow Duplicate Markups"))
        # toggleLayout.addRow(duplicateMarkupsCheckBox, duplicateMarkupsLabel)
        #
        # ## Hide To-Edit Segments on Load
        # hideEditSegmentsCheckBox = qt.QCheckBox()
        # hideEditSegmentsCheckBox.setChecked(config.hide_to_edit)
        # hideEditSegmentsLabel = qt.QLabel(
        #     _("Initially Hide To-Edit Markups")
        # )
        # toggleLayout.addRow(
        #     hideEditSegmentsCheckBox, hideEditSegmentsLabel
        # )

        # Connections
        @qt.Slot(str)
        def onStructureChanged(new_val: str):
            config.output_structure = MarkupOutputStructure(new_val)
        fileStructureComboBox.currentTextChanged.connect(onStructureChanged)
        fileStructureComboBox.setCurrentText(config.output_structure.value)

        @qt.Slot(str)
        def onFormatChanged(new_val: str):
            config.output_format = MarkupOutputFormat(new_val)
        fileFormatComboBox.currentTextChanged.connect(onFormatChanged)
        fileFormatComboBox.setCurrentText(config.output_format.value)

        ## TODO
        # @qt.Slot(None)
        # def onDuplicatesToggled():
        #     config.allow_duplicates = duplicateMarkupsCheckBox.isChecked()
        # duplicateMarkupsCheckBox.toggled.connect(onDuplicatesToggled)
        # duplicateMarkupsCheckBox.setChecked(config.allow_duplicates)
        #
        # @qt.Slot(None)
        # def onHideEditsToggled():
        #     config.hide_to_edit = hideEditSegmentsCheckBox.isChecked()
        # hideEditSegmentsCheckBox.toggled.connect(onHideEditsToggled)
        # hideEditSegmentsCheckBox.setChecked(config.hide_to_edit)
