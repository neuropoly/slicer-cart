from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.widgets import CARTSegmentationEditorWidget, showSuccessPrompt, showErrorPrompt
from CARTLib.utils.layout import Orientation
from CARTLib.utils.config import ProfileConfig
from CARTLib.utils.task import cart_task

from MultiContrastOutputManager import OutputMode, MultiContrastOutputManager
from MultiContrastSegmentationEvaluationDataUnit import (
    MultiContrastSegmentationEvaluationDataUnit,
)
from MultiContrastSegmentationConfig import MultiContrastSegmentationConfig


class MultiContrastSegmentationEvaluationGUI:
    def __init__(self, bound_task: "MultiContrastSegmentationEvaluationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

        # The currently selected orientation in the GUI; determine our viewer layout
        self.currentOrientation: Orientation = Orientation.AXIAL

        # Widgets we'll need to reference later:
        self.segmentEditorWidget: Optional[CARTSegmentationEditorWidget] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # 1). Configuration button
        self._addConfigButton(formLayout)

        # 2) Orientation buttons
        self._addOrientationButtons(formLayout)

        # 3) Segmentation editor
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # 4) Save controls
        self._addOutputSelectionButton(formLayout)

        # Prompt for initial output setup
        self.promptSelectOutputMode()

        return formLayout

    def _addConfigButton(self, layout: qt.QFormLayout):
        # A button to open the Configuration dialog, which changes how CART operates
        configButton = qt.QPushButton(_("Configure"))
        configButton.toolTip = _("Change how CART is configured to iterate through your data.")

        # Clicking the config button shows the Config prompt
        configButton.clicked.connect(self.bound_task.config.show_gui)

        # Add it to our layout
        layout.addRow(configButton)

    def _addOrientationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Buttons to set Axial/Sagittal/Coronal for all slice views.
        """
        hbox = qt.QHBoxLayout()
        for ori in Orientation.TRIO:
            label = ori.slicer_node_label()
            btn = qt.QPushButton(label)
            btn.clicked.connect(lambda _, o=ori: self.onOrientationChanged(o))
            hbox.addWidget(btn)

        btn = qt.QPushButton("All")
        btn.clicked.connect(lambda: self.onOrientationChanged(Orientation.TRIO))
        hbox.addWidget(btn)

        layout.addRow(qt.QLabel("View Orientation:"), hbox)

    def _addOutputSelectionButton(self, layout: qt.QFormLayout) -> None:
        btn = qt.QPushButton("Change Output Settings")
        btn.clicked.connect(self.promptSelectOutputMode)
        layout.addRow(btn)

    #
    # Handlers
    #

    def onOrientationChanged(self, orientation: Orientation) -> None:
        # Update our currently tracked orientation
        self.currentOrientation = orientation

        # If we don't have a data unit at this point, end here
        if not self.data_unit:
            return

        # Update the data unit's orientation to match
        self.data_unit.set_orientation(orientation)

        # Apply the (likely updated) layout
        self.data_unit.layout_handler.apply_layout()

    ## USER PROMPTS ##
    def promptSelectOutputMode(self):
        """
        Prompt the user to select output mode and location.
        """
        # Initialize the prompt
        prompt = self._buildOutputModePrompt()

        # Show the prompt with "exec", blocking the main window until resolved
        result = prompt.exec()

        # If the user cancelled out of the prompt, notify them
        if result == 0:
            notif = qt.QErrorMessage()
            if self.bound_task.can_save():
                notif.setWindowTitle(_("REVERTING!"))
                notif.showMessage(
                    _("Cancelled out of window; keeping previous output settings.")
                )
                notif.exec()
            else:
                notif.setWindowTitle(_("NO OUTPUT!"))
                notif.showMessage(
                    _(
                        "No output settings selected! You will need to "
                        "specify this before segmentations can be saved."
                    )
                )
                notif.exec()

    def _buildOutputModePrompt(self):
        """Build the output mode selection dialog with CSV logging option."""
        from datetime import datetime
        import csv

        prompt = qt.QDialog()
        prompt.setWindowTitle("Select Output Mode & Logging")
        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Add description
        description = qt.QLabel("Choose how to save your segmentations:")
        layout.addWidget(description)

        # Radio buttons for output mode
        self.outputModeGroup = qt.QButtonGroup()

        # Overwrite original option
        overwriteRadio = qt.QRadioButton("Overwrite original segmentation files")
        overwriteRadio.setToolTip("Saves directly over the input segmentation files")
        self.outputModeGroup.addButton(overwriteRadio, 1)
        layout.addWidget(overwriteRadio)

        # Alternative directory option
        parallelRadio = qt.QRadioButton("Save to separate directory structure")
        parallelRadio.setToolTip("Creates organized output in a separate directory")
        self.outputModeGroup.addButton(parallelRadio, 0)
        layout.addWidget(parallelRadio)

        # Set default selection based on current mode
        if hasattr(self.bound_task, "output_mode"):
            if self.bound_task.output_mode == OutputMode.PARALLEL_DIRECTORY:
                parallelRadio.setChecked(True)
            else:
                overwriteRadio.setChecked(True)
        else:
            parallelRadio.setChecked(True)  # Default to parallel

        # Directory selection widget (only shown for parallel mode)
        dirLabel = qt.QLabel("Output directory:")
        self.outputFileEdit = ctk.ctkPathLineEdit()
        self.outputFileEdit.setToolTip(
            _("The directory where modified segmentations will be placed.")
        )
        self.outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs

        # Set current directory if available
        if hasattr(self.bound_task, "output_dir") and self.bound_task.output_dir:
            self.outputFileEdit.currentPath = str(self.bound_task.output_dir)

        layout.addWidget(dirLabel)
        layout.addWidget(self.outputFileEdit)

        # Store references for enabling/disabling
        self.dirLabel = dirLabel

        # Add separator
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.HLine)
        separator.setFrameShadow(qt.QFrame.Sunken)
        layout.addWidget(separator)

        # CSV logging section with group box for better organization
        csvGroupBox = qt.QGroupBox("Processing Log (CSV)")
        csvGroupLayout = qt.QVBoxLayout()
        csvGroupBox.setLayout(csvGroupLayout)

        # CSV log option checkbox
        self.enableCsvLogging = qt.QCheckBox("Enable centralized logging")
        self.enableCsvLogging.setChecked(True)  # Default to enabled
        self.enableCsvLogging.setToolTip(
            "Log all processing activities to a CSV file for tracking"
        )
        csvGroupLayout.addWidget(self.enableCsvLogging)

        # CSV file path selection
        self.csvLogLabel = qt.QLabel(
            "CSV log file (optional - auto-generated if empty):"
        )

        # Create horizontal layout for CSV path input and buttons
        csvPathLayout = qt.QHBoxLayout()

        self.csvLogEdit = ctk.ctkPathLineEdit()
        self.csvLogEdit.setToolTip(
            _(
                "Optional: Specify custom CSV log file path. If empty, will be auto-generated."
            )
        )
        self.csvLogEdit.filters = ctk.ctkPathLineEdit.Files
        button = self.csvLogEdit.findChildren(qt.QToolButton)[0]
        button.setText("Select Existing")

        self.csvLogEdit.nameFilters = ["CSV files (*.csv)"]

        # Add browse button for CSV file selection
        self.csvBrowseButton = qt.QPushButton("Add...")
        self.csvBrowseButton.setToolTip("Add new CSV log file location")
        self.csvBrowseButton.clicked.connect(self._browseCsvLocation)
        self.csvBrowseButton.setMaximumWidth(80)

        # Set current CSV log path if available
        if hasattr(self.bound_task, "csv_log_path") and self.bound_task.csv_log_path:
            self.csvLogEdit.currentPath = str(self.bound_task.csv_log_path)

        csvPathLayout.addWidget(self.csvLogEdit)
        csvPathLayout.addWidget(self.csvBrowseButton)

        csvGroupLayout.addWidget(self.csvLogLabel)
        csvGroupLayout.addLayout(csvPathLayout)

        layout.addWidget(csvGroupBox)

        # Connect radio button changes to update UI
        parallelRadio.toggled.connect(self._onOutputModeChanged)
        self.enableCsvLogging.toggled.connect(self._onCsvLoggingChanged)

        # Initial UI state
        self._onOutputModeChanged(parallelRadio.isChecked())
        self._onCsvLoggingChanged(self.enableCsvLogging.isChecked())

        # Button box
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addWidget(buttonBox)

        # Connect acceptance
        buttonBox.accepted.connect(lambda: self._attemptOutputModeUpdate(prompt))
        buttonBox.rejected.connect(prompt.reject)

        # Resize for better appearance
        prompt.resize(500, prompt.minimumHeight)

        return prompt

    def _onCsvLoggingChanged(self, enabled: bool):
        """Enable/disable CSV logging options based on checkbox."""
        self.csvLogLabel.setEnabled(enabled)
        self.csvLogEdit.setEnabled(enabled)
        self.csvBrowseButton.setEnabled(enabled)

    def _browseCsvLocation(self):
        """Open file dialog to browse for CSV log file location."""
        dialog = qt.QFileDialog()
        dialog.setWindowTitle("Select CSV Log File Location")
        dialog.setAcceptMode(qt.QFileDialog.AcceptSave)
        dialog.setFileMode(qt.QFileDialog.AnyFile)
        dialog.setNameFilter("CSV files (*.csv)")
        dialog.setDefaultSuffix("csv")

        # Set default filename if none exists
        if not self.csvLogEdit.currentPath.strip():
            # Generate default filename based on username and current date
            username = self.bound_task.profile_label
            current_datetime = datetime.now().strftime('%Y%m%d')
            default_name = f"segmentation_review_log_{username}_{current_datetime}.csv"
            dialog.selectFile(default_name)
        else:
            # Use existing path as starting point
            existing_path = Path(self.csvLogEdit.currentPath.strip())
            if existing_path.parent.exists():
                dialog.setDirectory(str(existing_path.parent))
            dialog.selectFile(existing_path.name)

        # Show dialog and update path if user selects a file
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                selected_path = selected_files[0]
                self.csvLogEdit.currentPath = selected_path

    def _attemptOutputModeUpdate(self, prompt: qt.QDialog):
        """
        Validates and applies the selected output mode and path, including CSV logging.
        """
        # Get the selected mode
        selected_id = self.outputModeGroup.checkedId()
        if selected_id == 0:
            selected_mode = OutputMode.PARALLEL_DIRECTORY
        elif selected_id == 1:
            selected_mode = OutputMode.OVERWRITE_ORIGINAL
        else:
            self._linkedPathErrorPrompt("Please select an output mode", prompt)
            return

        # Get CSV log path if enabled
        csv_log_path = None
        if self.enableCsvLogging.isChecked():
            csv_path_str = self.csvLogEdit.currentPath.strip()
            if csv_path_str:
                csv_log_path = Path(csv_path_str)
                # Validate CSV path parent directory exists
                if not csv_log_path.parent.exists():
                    err_msg = f"CSV log directory does not exist: {csv_log_path.parent}"
                    self._linkedPathErrorPrompt(err_msg, prompt)
                    return

        # Handle parallel directory mode
        if selected_mode == OutputMode.PARALLEL_DIRECTORY:
            output_path_str = self.outputFileEdit.currentPath.strip()

            if not output_path_str:
                err_msg = "Output path was empty"
                self._linkedPathErrorPrompt(err_msg, prompt)
                return

            output_path = Path(output_path_str)
            err_msg = self.bound_task.set_output_mode(
                selected_mode, output_path, csv_log_path
            )
        else:
            # Overwrite original mode
            err_msg = self.bound_task.set_output_mode(
                selected_mode, csv_log_path=csv_log_path
            )

        # Check for errors
        if err_msg:
            self._linkedPathErrorPrompt(err_msg, prompt)
            return

        # Success - close the prompt
        prompt.accept()

    def _onOutputModeChanged(self, parallel_selected: bool):
        """Enable/disable directory selection based on mode."""
        self.dirLabel.setEnabled(parallel_selected)
        self.outputFileEdit.setEnabled(parallel_selected)

    def _linkedPathErrorPrompt(self, err_msg, prompt):
        """
        Prompt the user with an error message
        """
        failurePrompt = qt.QErrorMessage(prompt)
        failurePrompt.setWindowTitle("ERROR!")
        failurePrompt.showMessage(err_msg)
        failurePrompt.exec()

    def update(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        """
        Called whenever a new data-unit is in focus.
        Populate the volume combo, select primary, and fire off initial layers.
        """
        self.data_unit = data_unit

        # Apply the data unit's layout to our viewer
        self.data_unit.layout_handler.apply_layout()

        # Refresh the SegmentEditor Widget immediately
        self.segmentEditorWidget.refresh()

        # Force it to select the primary segmentation node
        self.segmentEditorWidget.setSegmentationNode(
            self.data_unit.primary_segmentation_node
        )

    def _save(self) -> None:
        err = self.bound_task.save()
        self.saveCompletePrompt(err)

    def saveCompletePrompt(self, err_msg: Optional[str]) -> None:
        if err_msg is None:
            success_message = self.bound_task.output_manager.get_success_message(
                self.bound_task.data_unit
            )
            showSuccessPrompt(success_message)
        else:
            showErrorPrompt(err_msg)

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        # Ensure the segmentation editor widget it set up correctly
        if self.segmentEditorWidget:
            self.segmentEditorWidget.enter()

    def exit(self) -> None:
        # Ensure the segmentation editor widget handles itself before hiding
        if self.segmentEditorWidget:
            self.segmentEditorWidget.exit()


@cart_task("Segmentation Review")
class MultiContrastSegmentationEvaluationTask(
    TaskBaseClass[MultiContrastSegmentationEvaluationDataUnit]
):

    def __init__(self, profile: ProfileConfig):
        super().__init__(profile)

        # Local Attributes
        self.gui: Optional[MultiContrastSegmentationEvaluationGUI] = None
        self.output_mode: OutputMode = OutputMode.PARALLEL_DIRECTORY
        self.output_dir: Optional[Path] = None
        self.output_manager: Optional[MultiContrastOutputManager] = None
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None
        self.csv_log_path: Optional[Path] = None  # Optional custom CSV log path

        # Configuration
        self.config: MultiContrastSegmentationConfig = (
            MultiContrastSegmentationConfig(
                parent_config=self.profile
            )
        )

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI: this prompts the user to configure some attributes we need
        self.gui = MultiContrastSegmentationEvaluationGUI(self)
        layout = self.gui.setup()

        # Integrate the task's GUI into CART
        container.setLayout(layout)

        # If the user provided output specifications, set up our manager here.
        if self.output_dir:
            self.output_manager = MultiContrastOutputManager(
                self.profile,
                self.output_mode,
                self.output_dir,
                self.csv_log_path
            )

        # If we have a data unit at this point, synchronize the GUI to it
        if self.data_unit:
            self.gui.update(self.data_unit)
        self.gui.enter()

    def receive(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        # Track the data unit for later
        self.data_unit = data_unit
        # Display primary volume + segmentation overlay
        slicer.util.setSliceViewerLayers(
            background=data_unit.primary_volume_node,
            foreground=data_unit.primary_segmentation_node,
            fit=True,
        )
        # Hide the segmentation node if requested by the user's config
        self.data_unit.set_primary_segments_visible(
            self.config.show_on_load
        )
        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def cleanup(self) -> None:
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def enter(self) -> None:
        if self.gui:
            self.gui.enter()

    def exit(self) -> None:
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {"Segmentation": MultiContrastSegmentationEvaluationDataUnit}

    def set_output_mode(
        self,
        mode: OutputMode,
        output_path: Optional[Path] = None,
        csv_log_path: Optional[Path] = None,
    ) -> Optional[str]:
        """
        Set the output mode and path if needed, with optional CSV logging path.
        Returns error message if failed, None if successful.
        """
        self.output_mode = mode
        self.csv_log_path = csv_log_path

        if mode == OutputMode.PARALLEL_DIRECTORY:
            if not output_path:
                return "Output path required for parallel directory mode"

            # Validate the directory
            if not output_path.exists():
                return f"Error: Output path does not exist: {output_path}"

            if not output_path.is_dir():
                return f"Error: Output path is not a directory: {output_path}"

            # Set up the consolidated output manager with CSV tracking
            self.output_dir = output_path
            self.output_manager = MultiContrastOutputManager(
                profile=self.profile,
                output_mode=mode,
                output_dir=output_path,
                csv_log_path=csv_log_path,
            )
            print(f"Output mode set to parallel directory: {self.output_dir}")
            print(f"CSV log will be saved to: {self.output_manager.csv_log_path}")

        elif mode == OutputMode.OVERWRITE_ORIGINAL:
            # Set up the consolidated output manager with CSV tracking
            self.output_dir = None
            self.output_manager = MultiContrastOutputManager(
                profile=self.profile, output_mode=mode, csv_log_path=csv_log_path
            )
            print("Output mode set to overwrite original")
            print(f"CSV log will be saved to: {self.output_manager.csv_log_path}")

        return None

    def can_save(self):
        # If we don't have a data unit or output manager, we can't even consider saving
        if not self.data_unit or not self.output_manager:
            return False
        # Otherwise, check with our output manager
        return self.output_manager.can_save(self.data_unit)

    def save(self) -> Optional[str]:
        """
        Save the current segmentation using the output manager.
        """
        # If we can't save, just return early
        # TODO improve how descriptive this error is
        if not self.can_save():
            return "Could not save!"
        # Have the output manager save the result
        # TODO handle the case where the original file doesn't exist And we are in "Overwrite Original" mode
        result = self.output_manager.save_segmentation(self.data_unit)
        # If we have a GUI, have it provide the appropriate response to the user
        if self.gui:
            self.gui.saveCompletePrompt(result)
        # Return the result for further use
        return result

    def isTaskComplete(self, case_data: dict[str: str]) -> bool:
        # The user might not have selected an output directory
        if not self.output_manager:
            # Without an output specified, we can't determine if we're done or not
            return False

        # Delegate to the output manager
        return self.output_manager.is_case_completed(case_data)
