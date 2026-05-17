from typing import TYPE_CHECKING

import qt
from slicer.i18n import tr as _

from CARTLib.utils.formatting import FilePathFormatter
from CARTLib.utils.widgets import CARTSegmentationEditorWidget

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're perfect
    import PyQt5.Qt as qt
    # Avoid a cyclic reference
    from SegmentationTask import SegmentationTask


class SegmentationGUI:
    def __init__(self, bound_task: "SegmentationTask"):
        self.bound_task = bound_task

        # Segment editor; tracked so it can be refreshed
        self._segmentEditorWidget: CARTSegmentationEditorWidget = None

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout(None)

        # Segmentation editor
        segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(segmentEditorWidget)
        self._segmentEditorWidget = segmentEditorWidget

        return formLayout

    def enter(self):
        self._segmentEditorWidget.enter()

    def exit(self):
        self._segmentEditorWidget.exit()

    def refresh(self):
        self._segmentEditorWidget.refresh()
