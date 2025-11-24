from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
from CARTLib.utils.widgets import CARTSegmentationEditorWidget, showSuccessPrompt, showErrorPrompt
from slicer.i18n import tr as _

from SegmentationReviewUnit import SegmentationReviewUnit
from SegmentationReviewOutputManager import OutputMode


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from SegmentationReviewTask import SegmentationReviewTask


class OutputConfigurationPrompt(qt.QDialog):

    COPY_BUTTON_ID = 0
    OVERWRITE_BUTTON_ID = 1

    def __init__(self, reference_task: "SegmentationReviewTask", cancellable: bool = True):
        super().__init__()

        # Attributes
        self.cancellable = cancellable
        self.has_changed = False

        # Basic settings and layout
        self.setWindowTitle("Configure Task Output")
        layout = qt.QVBoxLayout()
        self.setLayout(layout)

        # Radio buttons for output mode
        self._buildOutputSection(layout, reference_task)

        # Add separator for clarity
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        layout.addWidget(separator)

        # CSV logging section with group box for better organization
        self._buildLoggingSection(layout, reference_task)

        # Config/Cancel buttons
        self._buildButtonBox(layout, cancellable)

        # Resize for better appearance
        self.resize(500, self.minimumHeight)

    def _buildOutputSection(self, layout, task):
        self.outputModeGroup = qt.QButtonGroup()

        # Label describing the section
        sectionLabel = qt.QLabel(_(
            "Choose how segmentations should be saved:"
        ))
        layout.addWidget(sectionLabel)

        # "Replace Original" button
        overwriteRadio = qt.QRadioButton(_("Replace Original Segmentations"))
        overwriteRadio.setToolTip(_(
            "When saved, the segmentation will overwrite the input segmentation used to modify it.\n\n"
            "The sidecar for the file will be updated to denote a change was made as well "
            "(if no sidecar exists, a new one will be made)."
        ))
        self.outputModeGroup.addButton(overwriteRadio, self.OVERWRITE_BUTTON_ID)
        layout.addWidget(overwriteRadio)

        # "Save Copy" button
        parallelRadio = qt.QRadioButton(_("Save Copies to Directory"))
        parallelRadio.setToolTip(_(
            "Saves a copy of the segmentation(s) with your edits to the following directory.\n\n"
            "If a sidecar file is present, it will also be copied with an additional note tracking "
            "the changes made (if no sidecar exists, a new one will will be made instead)."
        ))
        self.outputModeGroup.addButton(parallelRadio, self.COPY_BUTTON_ID)
        layout.addWidget(parallelRadio)

        # Set the selected button to match the reference task
        if task.output_mode == OutputMode.PARALLEL_DIRECTORY:
            parallelRadio.setChecked(True)
        else:
            overwriteRadio.setChecked(True)

        # Directory selection widget (only inter-actable in COPY mode)
        outputFileLabel = qt.QLabel(_("Output Directory:"))
        self.outputFileEdit = ctk.ctkPathLineEdit()
        self.outputFileEdit.setToolTip(_(
            "Saved segmentations will be placed here, in a BIDS-like file structure."
        ))
        self.outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs

        # Set current directory to match the task's, if it has one
        if task.output_dir:
            self.outputFileEdit.currentPath = str(task.output_dir)
        else:
            self.outputFileEdit.currentPath = ""

        # When any state changes, mark ourselves as being changed
        self.outputModeGroup.buttonToggled.connect(self.mark_changed)
        self.outputFileEdit.currentPathChanged.connect(self.mark_changed)

        # When the CSV logging state is changed, enable/disable the editor to match
        def _onOutputModeChanged():
            isCopyMode = self.output_mode == OutputMode.PARALLEL_DIRECTORY
            outputFileLabel.setEnabled(isCopyMode)
            self.outputFileEdit.setEnabled(isCopyMode)
        _onOutputModeChanged()
        self.outputModeGroup.buttonToggled.connect(_onOutputModeChanged)

        # Insert everything into the provided layout
        layout.addWidget(outputFileLabel)
        layout.addWidget(self.outputFileEdit)

    def _buildLoggingSection(self, layout, task):
        # Initial setup
        csvGroupBox = qt.QGroupBox(_("Processing Log"))
        csvGroupLayout = qt.QVBoxLayout()
        csvGroupBox.setLayout(csvGroupLayout)

        # CSV log option checkbox
        self.enableCsvLogging = qt.QCheckBox(_("Enable Logging"))
        self.enableCsvLogging.setChecked(task.with_logging)
        self.enableCsvLogging.setToolTip(_(
            "Log all processing activities to a CSV file for tracking."
        ))
        csvGroupLayout.addWidget(self.enableCsvLogging)

        # CSV file path selection
        csvLogLabel = qt.QLabel(_("Path to Logging File (CSV):"))
        self.csvLogEdit = ctk.ctkPathLineEdit()
        self.csvLogEdit.setToolTip(_(
            "Where the CSV file will be placed."
        ))
        self.csvLogEdit.filters = ctk.ctkPathLineEdit.Files
        self.csvLogEdit.nameFilters = ["CSV files (*.csv)"]

        # Add browse button for CSV file selection
        csvBrowseButton = qt.QToolButton()
        csvBrowseButton.setText("+")
        csvBrowseButton.setToolTip("Create a new CSV log file from scratch")
        csvBrowseButton.clicked.connect(
            lambda: self._selectLogPath(task)
        )

        # Place all the buttons in a line
        csvPathLayout = qt.QHBoxLayout()
        csvPathLayout.addWidget(self.csvLogEdit)
        csvPathLayout.addWidget(csvBrowseButton)

        # Set current CSV log path to match the logic
        if task.csv_log_path:
            self.csvLogEdit.currentPath = str(task.csv_log_path)
        else:
            self.csvLogEdit.currentPath = ""

        # When any state changes, mark ourselves as being changed
        self.enableCsvLogging.stateChanged.connect(self.mark_changed)
        self.csvLogEdit.currentPathChanged.connect(self.mark_changed)

        # When the CSV logging state is changed, enable/disable the editor to match
        def _onLoggingChanged():
            isChecked = self.enableCsvLogging.isChecked()
            csvLogLabel.setEnabled(isChecked)
            self.csvLogEdit.setEnabled(isChecked)
        _onLoggingChanged()
        self.enableCsvLogging.stateChanged.connect(_onLoggingChanged)

        # Place everything into the group box
        csvGroupLayout.addWidget(csvLogLabel)
        csvGroupLayout.addLayout(csvPathLayout)

        # Add it to the main layout
        layout.addWidget(csvGroupBox)

    def _buildButtonBox(self, layout, cancellable: bool):
        # The button box to hold everything
        buttonBox = qt.QDialogButtonBox()

        # Hide the cancel button from the user requested
        # (Usually during initialization, where some input needs to be specified)
        if cancellable:
            buttonRoles = qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        else:
            buttonRoles = qt.QDialogButtonBox.Ok
        buttonBox.setStandardButtons(buttonRoles)

        # Delegate to our respective functions for each button
        def onButtonPressed(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.AcceptRole:
                self.onAccept()
            elif button_role == qt.QDialogButtonBox.RejectRole:
                self.onReject()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonPressed)

        # Add to our layout
        layout.addWidget(buttonBox)

    def _selectLogPath(self, task):
        """
        Open a file dialog to designate a path to a new or pre-existing
        CSV log file.
        """
        dialog = qt.QFileDialog()
        dialog.setWindowTitle("Select CSV Log File Location")
        dialog.setAcceptMode(qt.QFileDialog.AcceptSave)
        dialog.setFileMode(qt.QFileDialog.AnyFile)
        dialog.setNameFilter("CSV files (*.csv)")
        dialog.setDefaultSuffix("csv")

        # Set a default filename if one doesn't already exist
        currentPath = self.csvLogEdit.currentPath.strip()
        if not currentPath:
            # Generate default filename based on profile name and current date
            name = task.profile_label
            current_time = datetime.now().strftime('%Y%m%d')
            default_name = f"segmentation_review_log_{name}_{current_time}.csv"
            dialog.selectFile(default_name)
        else:
            # Use existing path as starting point
            existing_path = Path(currentPath)
            if existing_path.parent.exists():
                dialog.setDirectory(str(existing_path.parent))
            dialog.selectFile(existing_path.name)

        # If the user confirms their selection, update ourselves to match
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            # Only change the selected path if another one was selected
            if selected_files:
                selected_path = selected_files[0]
                self.csvLogEdit.currentPath = selected_path

    ## PROPERTIES ##
    @property
    def output_mode(self) -> OutputMode:
        # Parses the checked output ID into our OutputManager's enum equivalent
        selected_id = self.outputModeGroup.checkedId()
        if selected_id == self.COPY_BUTTON_ID:
            return OutputMode.PARALLEL_DIRECTORY
        elif selected_id == self.OVERWRITE_BUTTON_ID:
            return OutputMode.OVERWRITE_ORIGINAL
        else:
            raise ValueError("No output mode selected!")

    @property
    def output_dir(self) -> Optional[Path]:
        if self.outputFileEdit.currentPath:
            currentPath = self.outputFileEdit.currentPath.strip()
            return Path(currentPath)
        else:
            return None

    @property
    def should_log(self) -> bool:
        return self.enableCsvLogging.isChecked()

    @property
    def logging_path(self) -> Optional[Path]:
        if self.csvLogEdit.currentPath:
            currentPath = self.csvLogEdit.currentPath.strip()
            return Path(currentPath)
        else:
            return None

    def mark_changed(self, *__):
        """
        Shortcut function which allows us to make any QT signal
        also mark ourselves as having changed
        """
        self.has_changed = True

    ## CLOSING SIGNALS ##
    def onAccept(self):
        """
        Validate the contents of this prompt before allowing the user to exit
        """
        # If we are saving copies...
        if self.output_mode == OutputMode.PARALLEL_DIRECTORY:
            # Confirm a path was provided
            output_path_str = self.outputFileEdit.currentPath.strip()
            if not output_path_str:
                msg = _("No destination for the copies was provided!")
                showErrorPrompt(msg, self)
                return
            output_path = Path(output_path_str)
            if output_path.is_file():
                msg = _("Cannot save the segmentation files on top of another file!")
                showErrorPrompt(msg, self)
                return

        # If we are logging entries...
        if self.enableCsvLogging.isChecked():
            # Confirm a path was provided
            csv_path_str = self.csvLogEdit.currentPath.strip()
            if not csv_path_str:
                msg = _("No logging CSV path was provided!")
                showErrorPrompt(msg, self)
                return

            # Confirm it is not a directory
            csv_log_path = Path(csv_path_str)
            if csv_log_path.is_dir():
                msg = _("Cannot use a directory as a log file!")
                showErrorPrompt(msg, self)
                return

        # If everything above passed, close the prompt with an accept signal
        self.accept()

    def onReject(self):
        # If we are not cancellable, be VERY clear that closing here will cause problems
        if not self.cancellable:
            msg = qt.QMessageBox()
            msg.setWindowTitle(_("ARE YOU SURE?"))
            msg.setText(_(
                "WARNING: About to exit the setup prompt. Doing so will likely put CART into "
                "locked-up state!\n"
                "Are you sure you want to proceed?"
            ))
            msg.setStandardButtons(
                qt.QMessageBox.Yes | qt.QMessageBox.No
            )
            return msg.exec()

        # If we have made changes, confirm the user wants to back out!
        if self.has_changed:
            # Otherwise, confirm the user wants to discard said changes
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            msg.setText("You have unsaved changes. Are you sure you want to exit?")
            msg.setStandardButtons(
                qt.QMessageBox.Yes | qt.QMessageBox.No
            )
            result = msg.exec()
            # If the user does anything except confirm, return them to the original prompt
            if result != qt.QMessageBox.Yes:
                return result

        # Leave
        return self.reject()

    ## QT Events ##
    def closeEvent(self, event):
        """
        Intercepts when the user closes the window by clicking the 'x' in the
        dialog; ensures any modifications don't get discarded by mistake.
        """
        # Delegate to our "rejection" logic
        result = self.onReject()
        # If the result was not explicit confirmation "yes", ignore the close signal
        if result != qt.QMessageBox.Yes:
            event.ignore()
        # Otherwise, close as usual (and let anything that breaks do so)
        else:
            event.accept()


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
        # Prompt the user for output settings, preventing them from cancelling until done!
        self.promptSelectOutputMode(cancellable=False)

        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # Segmentation selection widget
        self._addSegmentSelectionWidget(formLayout)

        # Segmentation editor
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # Output controls
        self._addOutputSelectionButton(formLayout)

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

    def _addOutputSelectionButton(self, layout: qt.QFormLayout) -> None:
        btn = qt.QPushButton("Change Output Settings")
        btn.clicked.connect(
            lambda: self.promptSelectOutputMode(cancellable=True)
        )
        layout.addRow(btn)

    ## USER PROMPTS ##
    def promptSelectOutputMode(self, cancellable):
        """
        Prompt the user to select output mode and location.
        """
        # Initialize the prompt and show it to the users
        prompt = OutputConfigurationPrompt(self.bound_task, cancellable)

        # Until everything is validated, keep showing the user the prompt!
        # TODO: move validation checks into logic to centralize it
        while True:
            # Show the prompt (again)
            result = prompt.exec()

            # If the user backed out (and was allowed to), break the loop here
            if result == qt.QDialog.Rejected and cancellable:
                if cancellable:
                    break
                else:
                    showErrorPrompt(
                        "You managed to cancel an un-cancellable prompt.\n"
                        "Please report this to the developers!",
                        self
                    )

            msg = None
            # Check that the output is valid
            if prompt.output_mode == OutputMode.PARALLEL_DIRECTORY:
                if prompt.output_dir.is_file():
                    msg = _("Cannot use a file as an output directory!")
            elif prompt.should_log:
                if prompt.logging_path.is_dir():
                    msg = _("Cannot use a directory as a logging file!")

            # If we had a problem (a message was made), report it and loop again
            if msg is not None:
                msg = qt.QMessageBox()
                msg.setWindowTitle(_("Invalid Setting!"))
                msg.setText(msg)
                msg.setStandardButtons(qt.QMessageBox.Ok)
                msg.exec()
                continue
            # If all checks passed, break the loop
            break

        # If we got a reject signal, end here
        if result == qt.QDialog.Rejected:
            return

        # Update our logic with the new contents
        self.bound_task.output_mode = prompt.output_mode
        if prompt.output_dir:
            self.bound_task.output_dir = prompt.output_dir
        self.bound_task.with_logging = prompt.should_log
        if prompt.logging_path:
            self.bound_task.csv_log_path = prompt.logging_path

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
