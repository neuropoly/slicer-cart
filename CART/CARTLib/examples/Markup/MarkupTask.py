from pathlib import Path
from typing import Optional, TYPE_CHECKING

import qt
import slicer
from slicer.i18n import tr as _

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

        # If we have a data unit, have the GUI sync up with it
        if self.data_unit:
            self.gui.setModel(self.data_unit.dataModel)

    def receive(self, data_unit: MarkupUnit):
        # Update the data unit
        self.data_unit = data_unit

        # Rebuild the tree model for the data unit based on our config
        data_unit.apply_config(self.config)

        # If we have a GUI, sync it with the new unit
        if self.gui:
            self.gui.setModel(self.data_unit.dataModel)

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

    def cleanup(self):
        if self.gui:
            self.gui.clean()


class MarkupGUI:
    ## Setup ##
    def __init__(self, bound_task: MarkupTask):
        self.bound_task = bound_task

        # Warning panels for user messaging
        self.missingWarningPanel = None
        self.uniqueWarningPanel = None

        # TreeView for interacting with the markup list
        self.markupTreeView: qt.QTreeView = self._initMarkupView()

        # Observer ID which will need to be purged when the GUI is destroyed
        self.stateChangedObserverID = None

    @property
    def data_unit(self) -> MarkupUnit:
        return self.bound_task.data_unit

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout
        layout = qt.QFormLayout(None)

        ## Warning Panels ##
        # Warning panel for displaying warnings about missing "required" markups
        missingRequiredWarningPanel = qt.QTextBrowser(None)
        missingRequiredWarningPanel.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        missingRequiredWarningPanel.setReadOnly(True)

        # Initialize it hidden w/ no text initially
        missingRequiredWarningPanel.setVisible(False)

        # Add it to the layout and track it
        layout.addRow(missingRequiredWarningPanel)
        self.missingWarningPanel = missingRequiredWarningPanel

        # Warning panel for displaying warnings about multiple "unique" markups
        nonUniqueWarningPanel = qt.QTextBrowser(None)
        nonUniqueWarningPanel.setAlignment(qt.Qt.AlignLeft | qt.Qt.AlignTop)
        nonUniqueWarningPanel.setReadOnly(True)

        # Initialize it hidden w/ no text initially
        nonUniqueWarningPanel.setVisible(False)

        # Add it to the layout and track it
        layout.addRow(nonUniqueWarningPanel)
        self.uniqueWarningPanel = nonUniqueWarningPanel

        ## Contents Viewer ##
        # Insert the markup review/placement widget
        layout.addRow(self.markupTreeView)

        ## Buttons ##
        # Button to place all "missing" markup labels
        placeMissingButton = qt.QPushButton(_("Place Missing"))
        placeMissingToolTip = _(
            "Place any labels which have not been placed in their "
            "respective markups yet, one after the other. Left click to "
            "place, right click to skip over."
        )
        placeMissingButton.setToolTip(placeMissingToolTip)
        placeMissingButton.clicked.connect(
            # Lambda to avoid passing the boolean
            lambda __: self.data_unit.placeNextMissing()
        )
        layout.addRow(placeMissingButton)

        ## Checkboxes ##
        # Checkbox to enable "Place Multiple" mode
        placeMultipleCheckBox = qt.QCheckBox(None)
        placeMultipleLabel = qt.QLabel(_("Place labels repeatedly"))
        placeMultipleToolTip = _(
            "When enabled, placing a markup label queues another with the same"
            "name to be placed immediately. Repeats until you right-click to finish."
        )
        placeMultipleCheckBox.setToolTip(placeMultipleToolTip)
        placeMultipleLabel.setToolTip(placeMultipleToolTip)
        layout.addRow(placeMultipleCheckBox, placeMultipleLabel)

        # Sync with Slicer's current state
        interactionNode = slicer.app.applicationLogic().GetInteractionNode()
        placeMultipleCheckBox.setChecked(interactionNode.GetPlaceModePersistence())

        # When the checkbox changes, update Slicer to match
        placeMultipleCheckBox.stateChanged.connect(
            lambda new_state: interactionNode.SetPlaceModePersistence(new_state)
        )

        # Update the checkbox to match when Slicer's state changes
        self.stateChangedObserverID = interactionNode.AddObserver(
            interactionNode.InteractionModePersistenceChangedEvent,
            lambda n, __: placeMultipleCheckBox.setChecked(n.GetPlaceModePersistence())
        )

        # Return the result
        return layout

    def setModel(self, newModel: qt.QStandardItemModel):
        # Track the model within our view
        self.markupTreeView.setModel(newModel)

        # Update our header settings (now that there is contents to work with)
        header: qt.QHeaderView = self.markupTreeView.header()
        header.setSectionResizeMode(0, qt.QHeaderView.Stretch)
        header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
        self.markupTreeView.resizeColumnToContents(1)

        # Make the rows alternating
        self.markupTreeView.setAlternatingRowColors(True)

        # Disable user selection to avoid unintuitive behaviour
        self.markupTreeView.setSelectionMode(qt.QTreeView.NoSelection)

        # Expand everything by default
        self.markupTreeView.expandAll()

        # Update ourselves when the missing markups change
        self.data_unit.markupModelManager.when_label_counts_change(self.onLabelCountsChanged)
        self.onLabelCountsChanged()

    # When the no. missing labels changes, update our warning message to match
    def onLabelCountsChanged(self):
        # If there are no missing labels, hide the missing warning panel
        missing_required_labels = self.data_unit.markupModelManager.missing_required_labels
        if len(missing_required_labels) < 1:
            self.missingWarningPanel.setVisible(False)
        # Otherwise, build a warning message and reveal it
        else:
            msg = _("Missing the following 'required' markups: ")
            entries = sorted([
                f"  * {label} [{node_id}]" for node_id, label in missing_required_labels
            ])
            msg = "\n".join([msg, *entries])
            self.missingWarningPanel.setMarkdown(msg)
            self.missingWarningPanel.setVisible(True)

        # If there are no missing labels, hide the warning panel
        non_unique_labels = self.data_unit.markupModelManager.should_be_unique_labels
        if len(non_unique_labels) < 1:
            self.uniqueWarningPanel.setVisible(False)
        # Otherwise, build a warning message and reveal it
        else:
            msg = _("The following labels should be unique, but are not: ")
            entries = sorted(
                [f"  * {label} [{node_id}]" for node_id, label in non_unique_labels]
            )
            msg = "\n".join([msg, *entries])
            self.uniqueWarningPanel.setMarkdown(msg)
            self.uniqueWarningPanel.setVisible(True)

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

            # If this was not on the label column, skip
            if idx.column() != 0:
                return

            # If the index does not have a parent, do nothing
            if not idx.parent().isValid():
                return

            # Initiate placement for this label within this node
            model = self.data_unit.dataModel
            node_id = model.data(idx.parent(), qt.Qt.DisplayRole)
            label = model.data(idx, qt.Qt.DisplayRole)

            # Tell the unit to begin placing a new node
            self.data_unit.beginLabelPlacement(node_id, label)

        view.doubleClicked.connect(onDoubleClicked)

        return view

    def clean(self):
        if self.stateChangedObserverID is not None:
            interactionNode = slicer.app.applicationLogic().GetInteractionNode()
            interactionNode.RemoveObserver(self.stateChangedObserverID)
