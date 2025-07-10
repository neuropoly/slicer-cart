from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _
from .SegmentationEvaluationDataUnit import SegmentationEvaluationDataUnit
from ..core.TaskBaseClass import TaskBaseClass, D


class SegmentationEvaluationGUI:
    def __init__(self, bound_task: 'SegmentationEvaluationTask'):
        # Track the task, so we can reference it later
        self.bound_task = bound_task

        # Button group; we don't use it, but need to track it so it doesn't get
        #  destroyed by garbage collection!
        self.buttonGroup: qt.QButtonGroup = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # Add the output path selector
        self.addOutputPathSelector(formLayout)

        # Add the segmentation editor widget
        self.addSegmentationEditor(formLayout)

        return formLayout

    def addOutputPathSelector(self, formLayout):
        # Output file designator
        self.outputFileEdit = ctk.ctkPathLineEdit()
        self.outputFileEdit.setToolTip(_(
            "The directory the modified segmentations (and corresponding "
            "metadata) should be placed."
        ))
        # Make it the first widget in our "form"
        formLayout.addRow(_("Output Path:"), self.outputFileEdit)

    def addSegmentationEditor(self, formLayout):
        # Build the editor widget
        segmentEditorWidget = \
            slicer.modules.segmenteditor.widgetRepresentation().self().editor

        formLayout.addRow(segmentEditorWidget)


class SegmentationEvaluationTask(TaskBaseClass[SegmentationEvaluationDataUnit]):
    def __init__(self, data_unit: SegmentationEvaluationDataUnit):
        # Run the base task's initialization
        super().__init__(data_unit)

        # Variable for tracking the active GUI instance
        self.gui: Optional[SegmentationEvaluationGUI] = None

        # Variable for tracking the output directory
        self.output_dir: Optional[Path] = None

    def setup(self, container: qt.QWidget):
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI instance for this task
        self.gui = SegmentationEvaluationGUI(self)

        # Build its GUI and install it into the container widget
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

    def receive(self, data_unit: D):
        pass

    def save(self) -> bool:
        pass