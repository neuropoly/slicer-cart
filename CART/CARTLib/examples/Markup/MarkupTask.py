from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt
import slicer

from CARTLib.core.TaskBaseClass import CARTTask
from CARTLib.core.DataUnitBase import DataUnitFactory
from CARTLib.utils.config import JobProfileConfig, DictBackedConfig, MasterProfileConfig
from CARTLib.utils.data import (
    MarkupResource,
    ReferenceVolumeResource,
    VolumeResource,
)
from CARTLib.utils.task import cart_task

from MarkupConfig import MarkupConfig
from MarkupIO import MarkupOutput
from MarkupUnit import MarkupUnit

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


@cart_task("Markup")
class MarkupTask(CARTTask):

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
            self.gui.setModel(self.data_unit.markupModel)

    def receive(self, data_unit: MarkupUnit):
        # Update the data unit
        self.data_unit = data_unit

        # Apply the user's configuration options to the result
        data_unit.apply_markup_configs(self.config)

        # If we have a GUI, sync it
        if self.gui:
            self.gui.setModel(self.data_unit.markupModel)

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

        # If this case hasn't been completed already, end immediately
        if not self._output_manager.is_unit_complete(self.master_profile.author, uid):
            return case_overrides

        # Find the reference volume (if any) for this case
        ref_volume = None
        for k, v in case_data.items():
            if ReferenceVolumeResource.is_type(k):
                ref_volume = Path(v)
                break
            elif VolumeResource.is_type(k) and ref_volume is None:
                ref_volume = Path(v)

        # Replace markup entries w/ their previous entries, if available
        for k, v in case_data.items():
            # Skip non-markup resources
            if not MarkupResource.is_type(k):
                continue
            # Determine where the previous output file would be, if it still exists
            output_file = self._output_manager.determine_output_file(uid, k, ref_volume)
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
    ## Setup ##
    def __init__(self, bound_task: MarkupTask):
        self.bound_task = bound_task

        # TreeView for interacting with the markup list
        self.markupTreeView: qt.QTreeView = self._initMarkupView()

        # Markup currently being moved/placed; if none, the user is not currently placing any markups
        self.markupToPlace = tuple[str, str, Optional[int]]

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout
        layout = qt.QFormLayout(None)

        # Insert the markup editor widget
        layout.addWidget(self.markupTreeView)

        # Return the result
        return layout

    def setModel(self, newModel: qt.QStandardItemModel):
        # Track the model within our view
        self.markupTreeView.setModel(newModel)
        self.markupTreeView.expandAll()
        self.markupTreeView.setItemsExpandable(False)

    def _initMarkupView(self) -> qt.QTreeView:
        """
        Hooks up all the signals and slots to the model to run our behavior
        """
        view = qt.QTreeView(None)

        # Add double-clicking action for each markup
        @qt.Slot(qt.QModelIndex)
        def onDoubleClicked(idx: qt.QModelIndex):
            # If the index is invalid, end here
            if not idx.isValid():
                return
            # "Unroll" the index to get the data for the selected entry
            selected_data = list()
            while idx.parent().isValid():
                selected_data.insert(0, self.data_unit.markupModel.data(idx, qt.Qt.DisplayRole))
                idx = idx.parent()
            # Final index is always a markup node; track its index instead
            selected_data.insert(0, self.data_unit.markupModel.data(idx, qt.Qt.DisplayRole))
            # If the data had fewer than 2 entries (indicating a header or invalid entry), end here
            n_elements = len(selected_data)
            if n_elements < 2:
                return
            # If we had 2, this was a markup type; try and place a new node
            elif n_elements == 2:
                print(f"PLACING NODE {selected_data[1]}")
            # If we had 3, this is an existing markup; move it
            elif n_elements == 3:
                print(f"MOVING NODE {selected_data[1]} {selected_data[2]}")

        view.doubleClicked.connect(onDoubleClicked)

        return view

    @property
    def data_unit(self) -> MarkupUnit:
        return self.bound_task.data_unit

    ## Markup Placement ##
    def _initPlacementMode(self, node_id: str):
        # Select the requested node
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        targetNode = self.markup_nodes[node_id]
        selectionNode.SetActivePlaceNodeID(targetNode.GetID())

        # Put slicer into placement mode
        interactionNode.SetCurrentInteractionMode(interactionNode.Place)

    def _registerNewMarkupObservers(self):
        """
        Registers observers to continue after the user places a markup.

        Specifically:
          * Adds the new markup to the data unit
          * Exit placement mode
          * TODO: Continue to next unplaced markup when configured
        """
        # Pull the information for this

    def placeNewMarkup(self, node_id: str, markup_label: str):
        # Track the metadata for later
        self.markupToPlace = (node_id, markup_label, None)

        # Enter placement mode
        self._initPlacementMode(node_id)

        # Register observers for when the markup is placed
        self._registerNewMarkupObservers()

