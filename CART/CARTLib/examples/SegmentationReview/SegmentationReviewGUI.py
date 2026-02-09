from contextlib import contextmanager
from typing import Optional

import ctk
import qt
from CARTLib.utils.widgets import CARTSegmentationEditorWidget
from slicer.i18n import tr as _

from SegmentationReviewUnit import SegmentationReviewUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from SegmentationReviewTask import SegmentationReviewTask


class SegmentationReviewGUI:
    def __init__(self, bound_task: "SegmentationReviewTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[SegmentationReviewUnit] = None

        # Widgets we'll need to reference later:
        self.segmentEditorWidget: Optional[CARTSegmentationEditorWidget] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # Segmentation selection widget
        self._addSegmentSelectionWidget(formLayout)

        # Segmentation editor
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # Configuration button
        self._addConfigButton(formLayout)

        return formLayout

    def _addSegmentSelectionWidget(self, layout: qt.QFormLayout):
        # Label for the widget
        segmentSelectionLabel = qt.QLabel(_(
            "Segmentations to Save:"
        ))

        # The widget itself
        segmentSelectionComboBox = ctk.ctkCheckableComboBox()

        # When a checked index changes, update the logic to match
        def onCheckedChanged():
            checkedSegments = [
                segmentSelectionComboBox.itemText(i.row()) for i in segmentSelectionComboBox.checkedIndexes()
            ]
            self.bound_task.segments_to_save = checkedSegments

        segmentSelectionComboBox.checkedIndexesChanged.connect(onCheckedChanged)

        # Add them to the layout
        layout.addRow(segmentSelectionLabel, segmentSelectionComboBox)

        # Track it for later
        self.segmentSelectionComboBox = segmentSelectionComboBox

    def _addConfigButton(self, layout: qt.QFormLayout):
        # A button to open the Configuration dialog, which changes how CART operates
        configButton = qt.QPushButton(_("Configure"))
        configButton.toolTip = _("Change how CART is configured to iterate through your data.")

        # Clicking the config button shows the Config prompt
        configButton.clicked.connect(self.bound_task.config.show_gui)

        # Add it to our layout
        layout.addRow(configButton)

    ## CORE ##
    @contextmanager
    def block_signals(self):
        widget_list = [self.segmentEditorWidget, self.segmentSelectionComboBox]
        for w in widget_list:
            w.blockSignals(True)

        yield

        for w in widget_list:
            w.blockSignals(False)

    def update(self, data_unit: SegmentationReviewUnit) -> None:
        """
        Called whenever a new data-unit is in focus.
        Populate the volume combo, select primary, and fire off initial layers.
        """
        self.data_unit = data_unit

        # Update the segmentation list to match the current logic's state
        with self.block_signals():
            # Reset the combobox
            self.segmentSelectionComboBox.clear()

            # Add each item from the data unit, and sync it with the logic
            for i, k in enumerate(data_unit.segmentation_keys):
                # Add the new item
                self.segmentSelectionComboBox.addItem(k)

                # Sync the check-state
                checkModel = self.segmentSelectionComboBox.checkableModel()
                idx = checkModel.index(i, 0)
                # KO: Slicer's impl of QT is not forthcoming about where the "real" enum is,
                #  so we hard code it here. If you find the enum, please fix this garbage.
                checked = k in self.bound_task.segments_to_save
                if checked:
                    checked = 2
                else:
                    checked = 0
                self.segmentSelectionComboBox.setCheckState(idx, checked)

            # Refresh the SegmentEditor Widget immediately
            self.segmentEditorWidget.refresh()

        # Force it to select the primary segmentation node; we rely on signals here!
        self.segmentEditorWidget.setSegmentationNode(
            self.data_unit.primary_segmentation_node
        )

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        # Ensure the segmentation editor widget it set up correctly
        if self.segmentEditorWidget:
            self.segmentEditorWidget.enter()

    def exit(self) -> None:
        # Ensure the segmentation editor widget handles itself before hiding
        if self.segmentEditorWidget:
            self.segmentEditorWidget.exit()
