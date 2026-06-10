from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt

from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.core.DataUnitBase import DataUnitFactory
from CARTLib.utils.config import JobProfileConfig, DictBackedConfig, MasterProfileConfig
from CARTLib.utils.data import (
    MarkupResource,
)
from CARTLib.utils.task import cart_task
from CARTLib.utils.widgets import CARTMarkupEditorWidget

from MarkupConfig import MarkupConfig
from MarkupIO import MarkupOutput, MarkupUnit

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


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
        # Delegate to the output manager
        self._output_manager.save_unit(self.data_unit, self.master_profile)

    def isTaskComplete(self, case_data: dict[str, str]) -> bool:
        author = self.master_profile.author
        uid = case_data['uid']
        return self._output_manager.is_unit_complete(author, uid)

    def generate_prior_data_for(self, case_data: dict) -> Optional[dict]:
        uid = case_data.get("uid")
        case_overrides = {}
        if self._output_manager.is_unit_complete(self.master_profile.author, uid):
            for k, v in case_data.items():
                # Skip non-markup resources
                if not MarkupResource.is_type(k):
                    continue
                # Reference the original input, if available
                init_input = Path(v) if v != '' else None
                # Determine where the previous output file would be, if it still exists
                output_file = self._output_manager.determine_output_file(
                    self.job_profile.output_path,
                    uid,
                    init_input,
                    k,
                )
                # If it does, replace the original to-be-loaded file reference with it.
                if output_file.exists():
                    case_overrides[k] = output_file

        return case_overrides

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
