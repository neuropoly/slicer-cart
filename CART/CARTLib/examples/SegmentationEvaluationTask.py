from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _
from .SegmentationEvaluationDataUnit import SegmentationEvaluationDataUnit
from ..core.TaskBaseClass import TaskBaseClass, DataUnitFactory


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
        # TODO: Fix this "stealing" from the original Segment Editor widget
        segmentEditorWidget = \
            slicer.modules.segmenteditor.widgetRepresentation().self().editor

        formLayout.addRow(segmentEditorWidget)


class SegmentationEvaluationTask(TaskBaseClass[SegmentationEvaluationDataUnit]):
    def __init__(self):
        super().__init__()
        # Variable for tracking the active GUI instance
        self.gui: Optional[SegmentationEvaluationGUI] = None

        # Variable for tracking the output directory
        self.output_dir: Optional[Path] = None

        # Placeholder to track the currently-in-use Data Unit
        self.data_unit = None

    def setup(self, container: qt.QWidget):
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI instance for this task
        self.gui = SegmentationEvaluationGUI(self)

        # Build its GUI and install it into the container widget
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

    def receive(self, data_unit: SegmentationEvaluationDataUnit):
        # Track the data unit for later
        self.data_unit = data_unit

        # Bring the volume and associated segmentation into view again
        # TODO: Only do this if a GUI exists
        slicer.util.setSliceViewerLayers(
            background=self.data_unit.volume_node,
            foreground=self.data_unit.segmentation_node,
            label=self.data_unit.uid,
            fit=True
        )

    def cleanup(self):
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def save(self) -> bool:
        pass

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {
            "Single Segmentation": SegmentationEvaluationDataUnit
        }
