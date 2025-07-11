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

        # Segmentation editor widget
        self.segmentEditorWidget = None

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
        # Set the widget to only accept directories
        self.outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs

        # When the widget's contents change, update our output dir to match
        self.outputFileEdit.currentPathChanged.connect(self.outputPathChanged)

        # Make it the first widget in our "form"
        formLayout.addRow(_("Output Path:"), self.outputFileEdit)

    def addSegmentationEditor(self, formLayout):
        # Build the editor widget
        # TODO: Fix this "stealing" from the original Segment Editor widget
        self.segmentEditorWidget = \
            slicer.modules.segmenteditor.widgetRepresentation().self().editor

        formLayout.addRow(self.segmentEditorWidget)

    def update(self, data_unit: SegmentationEvaluationDataUnit):
        """
        Update the GUI to match the contents of the new data unit.

        Currently only selects the volume + segmentation node associated with
         the provided data node, allowing the user to immediately start editing.
        """
        # As the volume node is tied to the segmentation node, this will also
        #  set the selected volume node automagically for us!
        self.segmentEditorWidget.setSegmentationNode(data_unit.segmentation_node)

    ## GUI actions ##
    def outputPathChanged(self):
        # Get the current path from the GUI
        current_path_specified = self.outputFileEdit.currentPath

        # Strip it of leading/trailing whitespace
        current_path_specified = current_path_specified.strip()

        # If the data path is now empty, reset to the previous path and end early
        if not current_path_specified:
            print("Error: Base path was empty, retaining previous base path.")
            self.outputFileEdit.currentPath = str(self.bound_task.output_dir)
            return

        # Otherwise, update the task's path; re
        err_msg = self.bound_task.set_output_dir(Path(current_path_specified))

        # If we failed, prompt the user as to why
        if err_msg:
            # Display an error message notifying the user
            failurePrompt = qt.QErrorMessage()

            # Add some details on what's happening for the user
            failurePrompt.setWindowTitle("PATH ERROR!")

            # Show the message
            failurePrompt.showMessage(err_msg)
            failurePrompt.exec_()


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

        # If we have GUI, update the GUI with our current data unit
        self.gui.update(self.data_unit)

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

        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(self.data_unit)

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

    ## Utils ##
    def set_output_dir(self, new_path: Path) -> Optional[str]:
        """
        Update the output directory; returns an error message if it failed!
        """
        # Confirm the directory exists
        if not new_path.exists():
            err = f"Error: Data path does not exist: {new_path}"
            return err

        # Confirm that it is a directory
        if not new_path.is_dir():
            err = f"Error: Data path was not a directory: {new_path}"
            return err

        # If that all ran, update our data path to the new data path
        self.output_dir = new_path
        print(f"Output path set to: {self.output_dir}")

        return None
