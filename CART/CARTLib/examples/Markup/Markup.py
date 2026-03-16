import csv
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory, D
from CARTLib.utils.config import JobProfileConfig, DictBackedConfig, MasterProfileConfig
from CARTLib.utils.data import (
    CARTStandardUnit,
    save_markups_to_nifti,
    save_markups_to_json,
    find_json_sidecar_path,
    stack_sidecars,
    save_json_sidecar,
    add_generated_by_entry,
)
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import CARTMarkupEditorWidget


if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


VERSION = "0.0.2"


@cart_task("Markup")
class MarkupTask(TaskBaseClass[CARTStandardUnit]):

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
        self.data_unit: Optional[CARTStandardUnit] = None

        # Markup tracking
        self.markups: list[tuple[str, Optional[str]]] = []
        self.untracked_markups: dict[str, list[str]] = {}

        # Output logging
        self._output_manager: MarkupOutput = MarkupOutput()
        self._output_manager.output_dir = self.job_profile.output_path

        # Config management
        self.config: MarkupConfig = MarkupConfig(parent_config=self.job_profile)

    def setup(self, container: qt.QWidget):
        # Initialize the GUI
        self.gui = MarkupGUI(self)
        container.setLayout(self.gui.setup())

        # If we have a data unit, notify the GUI to synchronize
        if self.data_unit:
            self.gui.sync()

    def receive(self, data_unit: D):
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
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": CARTStandardUnit
        }

    @classmethod
    def feature_types(cls, data_factory_label: str) -> dict[str, str]:
        # Defer to the data unit itself
        duf = cls.getDataUnitFactories().get(data_factory_label, None)
        if duf == CARTStandardUnit:
            return CARTStandardUnit.feature_types()
        return {}

    @classmethod
    def format_feature_label_for_type(
        cls, initial_label: str, data_unit_factory_type: str, feature_type: str
    ):
        # Apply default comma processing
        initial_label = super().format_feature_label_for_type(
            initial_label, data_unit_factory_type, feature_type
        )
        # Defer to the data unit itself for further processing
        duf = cls.getDataUnitFactories().get(data_unit_factory_type, None)
        if duf is CARTStandardUnit:
            return CARTStandardUnit.feature_label_for(
                initial_label, feature_type
            )
        return initial_label


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
    def data_unit(self) -> CARTStandardUnit:
        return self.bound_task.data_unit

    def saveSuccessPrompt(self, msg_text: str):
        msg = qt.QMessageBox()
        msg.setWindowTitle("Saved Markups!")
        msg.setText(msg_text)
        msg.setTextFormat(3)  # 3 -> Markdown enum value
        msg.setStandardButtons(qt.QMessageBox.Ok)
        return msg.exec()


class MarkupOutput:
    def __init__(self):
        # The directory to save everything into
        self._output_dir: Path = None

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

    def save_unit(self, data_unit: CARTStandardUnit, profile: MasterProfileConfig) -> str:
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
            input_path = data_unit.markup_paths.get(key, None)
            # If this is a node w/o a previous file name, save it as such
            if input_path is None:
                file_name = f"{key}_unknown_{unknown_idx}.mrk.json"
                unknown_idx += 1
            else:
                file_name = input_path.name
            output_file = case_output / file_name

            # Delete any previous sidecar file associated with our output to avoid unintentional carry-over
            prior_sidecar = find_json_sidecar_path(output_file)
            prior_sidecar.unlink(missing_ok=True)

            # Save the node's contents to this file
            if ".nii" in output_file.suffixes:
                # Save the node to a NiFTI file, w/ a sidecar containing label data!
                save_markups_to_nifti(
                    markup_node=node,
                    reference_volume=data_unit.primary_volume_node,
                    path=output_file
                )
                saved_files.append(output_file)
            elif ".mrk" in output_file.suffixes:
                # Save the node to Slicer's native mrk.json format.
                save_markups_to_json(
                    markups_node=node,
                    path=output_file
                )
                saved_files.append(output_file)
            else:
                failed_files.append(output_file)

            # Save the corresponding sidecar, extended w/ a new "GeneratedBy" entry
            current_sidecar = find_json_sidecar_path(output_file)
            sidecar_data = stack_sidecars(prior_sidecar, current_sidecar)
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

    def is_unit_complete(self, author: str, uid: CARTStandardUnit):
        return (author, uid) in self.log.keys()


class MarkupConfig(DictBackedConfig):
    CONFIG_KEY = "markup"

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    def show_gui(self) -> None:
        pass
