from enum import Enum
from pathlib import Path
from typing import Optional

import ctk, qt
from slicer.i18n import tr as _
from .SegmentationEvaluationDataUnit import SegmentationEvaluationDataUnit
from ..core.TaskBaseClass import TaskBaseClass, D


class SegmentationEvaluationGUI:

    class EditTool(Enum):
        PAINT = 1
        ERASE = 2
        LASSO = 3
        SCISSOR = 4

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

        # Add the tool buttons
        self.addToolButtons(formLayout)

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

    def addToolButtons(self, formLayout):
        # Button panel layout
        buttonPanel = qt.QGridLayout()

        # Add the paint button
        paintButton = qt.QPushButton(_("Paint"))
        paintButton.setToolTip(_(
            "Add to the current segmentation via a paint brush."
        ))
        buttonPanel.addWidget(paintButton, 0, 0)

        # Add the erase button
        eraseButton = qt.QPushButton(_("Erase"))
        eraseButton.setToolTip(_(
            "Remove from the current segmentation via an erase brush."
        ))
        buttonPanel.addWidget(eraseButton, 0, 1)

        # Add the lasso fill button
        lassoButton = qt.QPushButton(_("Lasso"))
        lassoButton.setToolTip(_(
            "Add to the current segmentation via filling within a circled region"
        ))
        buttonPanel.addWidget(lassoButton, 1, 0)

        # Add the scissor delete button
        scissorButton = qt.QPushButton(_("Scissor"))
        scissorButton.setToolTip(_(
            "Removed from the current segmentation via deleting within a circled region"
        ))
        buttonPanel.addWidget(scissorButton, 1, 1)

        # Add the button panel to our layout
        formLayout.addRow(buttonPanel)

        # Add all the buttons to a (exclusive) button group
        self.buttonGroup = qt.QButtonGroup()
        for b in [paintButton, eraseButton, lassoButton, scissorButton]:
            self.buttonGroup.addButton(b)
            b.setCheckable(True)


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