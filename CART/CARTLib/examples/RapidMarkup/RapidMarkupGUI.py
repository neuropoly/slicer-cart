from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _

from RapidMarkupUnit import RapidMarkupUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from RapidMarkupTask import RapidMarkupTask


## WIDGETS ##
class MarkupListWidget(qt.QWidget):

    COMPLETED_BRUSH = qt.QBrush(
        qt.QColor(0, 255, 0, 100)
    )
    HIGHLIGHTED_BRUSH = qt.QBrush(
        qt.QColor(0, 0, 255, 100)
    )
    SKIPPED_BRUSH = qt.QBrush(
        qt.QColor(255, 0, 0, 100)
    )
    BLANK_BRUSH = qt.QBrush(
        qt.QColor(0, 0, 0, 0)
    )

    def __init__(self, task: "RapidMarkupTask"):
        super().__init__()

        # Create the layout to hold everything in
        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        self._addMarkupList(layout)

        self._addButtonPanel(layout)

        # Track it for later
        self.bound_task = task

        # Synchronize ourselves with the loaded task
        self.syncStateWithTask()

    ## GUI Construction ##
    def _addMarkupList(self, layout):
        # Create a list widget
        markupList = qt.QListWidget()
        markupListLabel = qt.QLabel("Markup Labels")

        # When the selected item changes, update our state to match
        markupList.itemSelectionChanged.connect(
            self._onSelectionChanged
        )

        # Track it for later and add it to the layout
        layout.addWidget(markupListLabel)
        layout.addWidget(markupList)
        self.markupList = markupList

    def _addButtonPanel(self, layout):
        # Add a button to add items to the list
        addButton = qt.QPushButton("Add")
        addButton.clicked.connect(self._addNewMarkup)

        # Add a button to remove items from the list
        removeButton = qt.QPushButton("Remove")
        removeButton.clicked.connect(self.remove_selected_markups)

        # Make them side-by-side and add them to the layout
        buttonLayout = qt.QHBoxLayout()
        buttonLayout.addWidget(addButton)
        buttonLayout.addWidget(removeButton)
        layout.addLayout(buttonLayout)

        # Track them for later
        self.addButton = addButton
        self.removeButton = removeButton

    ## Properties ##
    @property
    def count(self) -> int:
        # Alias for the underlying list widget's count
        return self.markupList.count

    @property
    def rowsInserted(self):
        # Alias to easily expose the function for connections
        return self.markupList.model().rowsInserted

    @property
    def rowsRemoved(self):
        # Alias to easily expose the function for connections
        return self.markupList.model().rowsRemoved

    @property
    def selectedIdx(self) -> int:
        return self.markupList.currentRow

    @property
    def selectionChanged(self):
        # Expose this signal for easy access
        return self.markupList.itemSelectionChanged

    ## Signal Functions ##
    def _onSelectionChanged(self):
        # Make it so we can only remove items when there are items
        #  selected to be removed
        self.removeButton.setEnabled(
            len(self.markupList.selectedItems()) > 0
        )

    def _addNewMarkup(self):
        # Start the Add Markup dialog
        dialog = AddMarkupDialog()

        # Exec it to show it to the user
        dialog_return = dialog.exec()

        # If the user closed the dialog, just end as-is
        if not dialog_return:
            return

        # Otherwise, get the text from the markup
        new_markup_str = dialog.getMarkup().strip()
        # If the markup string exists, add it to the list
        if new_markup_str:
            newItem = qt.QListWidgetItem(new_markup_str)
            self.markupList.addItem(newItem)
        # Otherwise, notify the user it was blank and not added
        else:
            slicer.util.warningDisplay(_(
                "Label was blank, no markup was added."
            ))

    ## Utils ##
    def remove_selected_markups(self):
        for item in self.markupList.selectedItems():
            # Why "removeItemWidget" doesn't do this, only god knows
            self.markupList.takeItem(self.markupList.row(item))

    def itemAt(self, idx: int) -> qt.QListWidgetItem:
        return self.markupList.item(idx)

    def selectAt(self, idx: int) -> None:
        self.markupList.setCurrentRow(idx)

    @contextmanager
    def noUpdateSignals(self):
        self.markupList.blockSignals(True)
        self.markupList.model().blockSignals(True)

        yield

        self.markupList.blockSignals(False)
        self.markupList.model().blockSignals(False)

    def syncStateWithTask(self):
        # Re-assess the markup list state based on the logic
        with self.noUpdateSignals():
            self.markupList.clear()

            for i, (label, markup_id) in enumerate(self.bound_task.markups):
                listItem = qt.QListWidgetItem(label)
                if markup_id:
                    listItem.setBackground(self.COMPLETED_BRUSH)
                else:
                    listItem.setBackground(self.BLANK_BRUSH)
                self.markupList.addItem(listItem)

        # Disable the remove button, as there is no longer any selection
        self.removeButton.setEnabled(False)


## PROMPTS ##
class RapidMarkupSetupPrompt(qt.QDialog):
    def __init__(self, bound_logic: "RapidMarkupTask"):
        super().__init__()

        self.setWindowTitle("Set Up Rapid Markup")

        self.bound_logic = bound_logic

        self._build_ui()

    def _build_ui(self):
        """
        Build the GUI elements into this prompt
        """
        # Create the layout to actually place everything in
        layout = qt.QFormLayout(self)

        self._buildOutputGUI(layout)

        self._buildButtons(layout)

    def _buildOutputGUI(self, layout: qt.QFormLayout):
        # Add a label clarifying the next widget's purpose
        description = qt.QLabel("Output Directory:")
        layout.addRow(description)

        # Ensure only directories are chosen
        outputFileEdit = ctk.ctkPathLineEdit()
        outputFileEdit.setToolTip(
            _("The directory where the saved markups will be placed.")
        )
        outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs

        # Set its state to match the task's if it has one
        outputFileEdit.currentPath = str(self.bound_logic.output_dir)

        # Update the layout and track it for later
        layout.addRow(outputFileEdit)
        self.outputFileEdit = outputFileEdit

    def _buildButtons(self, layout: qt.QFormLayout):
        # Button box for confirming/rejecting the current use
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addRow(buttonBox)

        # Connect signals
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    # Output management
    def get_output(self):
        new_path = self.outputFileEdit.currentPath
        if new_path is "":
            return None
        new_path = Path(new_path)
        if not new_path.exists():
            return None
        if not new_path.is_dir():
            return None
        return new_path


class AddMarkupDialog(qt.QDialog):
    def __init__(self):
        # Initialize the prompt itself
        super().__init__()

        # Update our basic attributes
        self.setWindowTitle(_("New Markup Label"))

        # Initialize our layout
        layout = qt.QFormLayout(self)

        # Set up our own GUI
        self._buildUI(layout)

    def _buildUI(self, layout: qt.QFormLayout):
        # Line edit + its label
        lineEditLabel = qt.QLabel(_("Markup Label"))
        lineEdit = qt.QLineEdit()

        # Add it to our layout
        layout.addRow(lineEditLabel, lineEdit)

        # Track the line edit for later
        self.lineEdit = lineEdit

        # Add a button box to confirm and cancel
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )

        # Function to map button presses to corresponding actions
        def onButtonPressed(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonPressed)

        # Add it to the layout
        layout.addRow(buttonBox)

    def getMarkup(self) -> str:
        return self.lineEdit.text


## GUIs ##
class RapidMarkupGUI:
    def __init__(self, bound_task: "RapidMarkupTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[RapidMarkupUnit] = None

        # Widget displaying the data unit
        self.markupList: MarkupListWidget = None

        # Observer IDs; need to be tracked here to avoid cyclic referencing
        self.markup_observer_id: Optional[str] = None
        self.backout_observer_id: Optional[str] = None

        # Whether the user is actively placing markups currently
        self.is_user_placing_markups: bool = False

        # Quick reference variables
        self._prior_placement_mode = None
        self._interaction_node = slicer.app.applicationLogic().GetInteractionNode()

    def setup(self) -> qt.QFormLayout:
        # Initialize a layout we'll insert everything into
        formLayout = qt.QFormLayout()

        self._initMarkupList(formLayout)

        self._addStartButton(formLayout)

        self._addConfigButton(formLayout)

        return formLayout

    def _initMarkupList(self, formLayout: qt.QFormLayout):
        # Create a markup list
        markupList = MarkupListWidget(self.bound_task)

        # Connect the row addition/removal signals to sync functions
        markupList.rowsInserted.connect(self.onMarkupAdded)
        markupList.rowsRemoved.connect(self.onMarkupRemoved)

        # Add it to the layout and track it for later
        formLayout.addWidget(markupList)
        self.markupList = markupList

    def _addStartButton(self, formLayout: qt.QFormLayout):
        # Create the button itself
        startButton = qt.QPushButton(_("Begin Placement"))

        # When the start button is clicked, start user placement
        startButton.clicked.connect(
            # Lambda required to prevent passing the buttons "state" post-click
            lambda: self.initiateMarkupPlacement()
        )

        # Only enable the start button when something has been selected
        self.markupList.selectionChanged.connect(
            lambda: startButton.setEnabled(self.markupList.selectedIdx != -1)
        )

        # Initially disable the button, as nothing has been selected yet
        startButton.setEnabled(False)

        # Add it to the layout
        formLayout.addWidget(startButton)

    def _addConfigButton(self, formLayout: qt.QFormLayout):
        # Create the button itself
        configButton = qt.QPushButton(_("Configure"))

        # When the button is pressed, make the config GUI appear
        configButton.clicked.connect(self.bound_task.config.show_gui)

        # Add it to the layout
        formLayout.addWidget(configButton)

    def update(self, data_unit: RapidMarkupUnit):
        # Track the new data unit
        self.data_unit = data_unit

        # Synchronize with our logic's state
        self.markupList.syncStateWithTask()

        # Start node placement automatically if configured
        if self.bound_task.config.start_automatically:
            # See if there is an unplaced label to still place
            first_incomplete = self.findNextUnplaced()
            # If so, initiate its placement
            if first_incomplete is not None:
                self.markupList.selectAt(first_incomplete)
                self.initiateMarkupPlacement()

    def onMarkupAdded(self, _, start_idx, end_idx):
        # Add the new elements to our logic as well
        for i in range(start_idx, end_idx+1):
            item = self.markupList.itemAt(i)
            label = item.text()
            markup_id = self.bound_task.add_markup_label(i, label)
            # If there was an associated markup ID, color the new item
            # as having already been placed
            if markup_id:
                item.setBackground(self.markupList.COMPLETED_BRUSH)

    def onMarkupRemoved(self, _, start_idx, end_idx):
        # Remove the dropped elements from our logic as well
        for i in range(start_idx, end_idx+1):
            self.bound_task.remove_markup_label(i)

    ## User Interaction Management ##
    def _enterMarkupMode(self):
        # If we are already in markup mode, end here
        if self.is_user_placing_markups:
            return

        # Mark ourselves as being in markup mode
        self.is_user_placing_markups = True

        # Ensure the data unit's markup node is selected
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetActivePlaceNodeID(self.data_unit.markup_node.GetID())

        # Disable the markup list to prevent markups from being added/removed
        self.markupList.setEnabled(False)

        # Enable persistent placement mode
        self._prior_placement_mode = self._interaction_node.GetPlaceModePersistence()
        self._interaction_node.SetPlaceModePersistence(True)

    def _exitMarkupMode(self):
        # If we are not in markup mode, end here
        if not self.is_user_placing_markups:
            return

        # Mark ourselves as no longer being in markup mode
        self.is_user_placing_markups = False

        # If observer callbacks are in place, remove them
        self.unregisterObservers()

        # Exit placement mode, if we were in it
        # TODO: Figure out why this throws a "control point does not exist" error
        #  when the user moves an existing markup AND all control points managed
        #  by the logic have been placed.
        # KO: Seems to be an upstream bug caused by a de-sync when a control point
        #  (markup) has been deleted very recently, but I cannot tell for sure.
        #  In any case, the code still works just fine without it; just spams the
        #  console with errors, which can be quite annoying.
        self._interaction_node.SetCurrentInteractionMode(
            self._interaction_node.ViewTransform
        )

        # Restore place mode persistence to what it was prior to our change
        self._interaction_node.SetPlaceModePersistence(
            self._prior_placement_mode
        )
        self._prior_placement_mode = None

        # Unselect everything
        self.markupList.selectAt(-1)

        # Re-enable the ability to select, add, and remove markup nodes
        self.markupList.setEnabled(True)

    def initiateMarkupPlacement(self, idx: int = None):
        """
        Initiate the user placing a given markup position.
        """
        # If we're not already in markup mode, enter it
        if not self.is_user_placing_markups:
            self._enterMarkupMode()

        # If no index was specified, use the selected index instead
        if idx is None:
            idx = self.markupList.selectedIdx
        else:
            # Otherwise, select the specified index automatically
            self.markupList.selectAt(idx)

        # Tell slicer to enter placement mode
        self._interaction_node.SetCurrentInteractionMode(
            self._interaction_node.Place
        )

        # Register observers for post-placement functions
        self.registerObservers(idx)

    def registerObservers(self, target_idx: int):
        """
        Register observers for cleaning up after markup placement is done.

        Specifically:
            * Marks the list item with the correct color
            * Change the text of the placed markup to match the label
            * Ensures placement mode is exited correctly when needed
            * (If configured) Initiate the next label's placement
        """
        # Pull information for the target index
        markup_item = self.markupList.itemAt(target_idx)

        # Find the next unplaced markup index
        next_idx = self.findNextUnplaced(target_idx + 1)

        # Register a callback for when a new point has been placed
        def _onPlace(_, __):
            # Change the name of the newly added node to the label
            self.bound_task.update_on_new_markup(target_idx)

            # Mark this markup as being placed visually
            markup_item.setBackground(self.markupList.COMPLETED_BRUSH)

            # Try to prompt the user for the next unplaced markup
            if next_idx is not None and self.bound_task.config.chain_placement:
                self.initiateMarkupPlacement(next_idx)
            # Otherwise, end markup mode here
            else:
                self._exitMarkupMode()

        def _onCancel(_, __):
            # Highlight the entry in "skipped" colors
            markup_item.setBackground(self.markupList.SKIPPED_BRUSH)

            # Try to prompt the user for the next unplaced markup
            if next_idx is not None and self.bound_task.config.chain_placement:
                self.initiateMarkupPlacement(next_idx)
            # Otherwise, end markup mode here
            else:
                self._exitMarkupMode()

        # Unregister previous observers
        self.unregisterObservers()

        # Register the new observers
        markup_node = self.bound_task.data_unit.markup_node
        self.markup_observer_id = markup_node.AddObserver(
            markup_node.PointPositionDefinedEvent, _onPlace
        )
        self.backout_observer_id = self._interaction_node.AddObserver(
            self._interaction_node.InteractionModeChangedEvent, _onCancel
        )

    def unregisterObservers(self) -> None:
        # Remove the previous observer callbacks
        markup_node = self.bound_task.data_unit.markup_node
        if self.markup_observer_id:
            markup_node.RemoveObserver(self.markup_observer_id)

        if self.backout_observer_id:
            self._interaction_node.RemoveObserver(self.backout_observer_id)

    def findNextUnplaced(self, start_idx: int = 0) -> Optional[int]:
        """
        Find the next unplaced markup in our logic.
        If none exist, returns None.
        """
        for i in range(start_idx, len(self.bound_task.markups)):
            __, cp_id = self.bound_task.markups[i]
            if not cp_id:
                return i
        return None

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        pass

    def exit(self) -> None:
        # If we are in markup mode (the user was placing markups), exit it
        if self.is_user_placing_markups:
            self._exitMarkupMode()
        pass
