import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
from slicer.i18n import tr as _

from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.layout import Orientation
from CARTLib.utils.task import cart_task

from RegistrationReviewDataUnit import RegistrationReviewDataUnit

VERSION = 0.01

# First step should be to check the current output CSV file for the current user and the current UID.
# If the current UID is already in the CSV file Add a button to skip the next unreviewed case.
# AND update the current data unit to have knowledge of the previous review status.


class RegistrationReviewGUI:
    def __init__(self, bound_task: "RegistrationReviewTask"):
        self.bound_task = bound_task
        self.data_unit: Optional["RegistrationReviewDataUnit"] = None

        # The currently selected orientation in the GUI
        self.currentOrientation: Orientation = Orientation.AXIAL

        # Registration classification selection
        self.registrationClassificationGroup: Optional[qt.QButtonGroup] = None
        self.selectedClassification: Optional[str] = None

        # Review status tracking
        self.reviewStatusLabel: Optional[qt.QLabel] = None

        # Opacity control
        self.opacitySlider: Optional[qt.QSlider] = None
        self.opacityLabel: Optional[qt.QLabel] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # 1) Review status display
        self._addReviewStatusDisplay(formLayout)

        # 2) Orientation buttons
        self._addOrientationButtons(formLayout)

        # 3) Opacity control slider
        self._addOpacityControl(formLayout)

        # 4) Registration classification options
        self._addClassificationButtons(formLayout)

        # 5) CSV output selection
        self._addCsvSelectionButton(formLayout)

        # Prompt for initial CSV setup
        self.promptSelectCsvOutput()

        return formLayout

    def _addReviewStatusDisplay(self, layout: qt.QFormLayout) -> None:
        """
        Display current review status for this case.
        """
        self.reviewStatusLabel = qt.QLabel("Review Status: Not checked")
        self.reviewStatusLabel.setStyleSheet("QLabel { font-weight: bold; }")
        layout.addRow(self.reviewStatusLabel)

    def _addOrientationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Buttons to set Axial/Sagittal/Coronal for all slice views.
        """
        hbox = qt.QHBoxLayout()
        for orientation in Orientation.TRIO:
            label = orientation.slicer_node_label()
            btn = qt.QPushButton(label)
            btn.clicked.connect(lambda _, o=orientation: self.onOrientationChanged(o))
            hbox.addWidget(btn)
        layout.addRow(qt.QLabel("View Orientation:"), hbox)

    def _addOpacityControl(self, layout: qt.QFormLayout) -> None:
        """
        Slider to control foreground/background opacity focus.
        """
        # Create a horizontal layout for the opacity controls
        opacityLayout = qt.QHBoxLayout()

        # Create the slider
        self.opacitySlider = qt.QSlider(qt.Qt.Horizontal)
        self.opacitySlider.setMinimum(0)
        self.opacitySlider.setMaximum(100)
        self.opacitySlider.setValue(50)  # Default to 50% opacity
        self.opacitySlider.setTickPosition(qt.QSlider.TicksBelow)
        self.opacitySlider.setTickInterval(25)
        self.opacitySlider.valueChanged.connect(self.onOpacityChanged)

        # Create the label to show current opacity value
        self.opacityLabel = qt.QLabel("50%")
        self.opacityLabel.setMinimumWidth(40)
        self.opacityLabel.setAlignment(qt.Qt.AlignCenter)

        # Add labels for background and foreground focus
        backgroundLabel = qt.QLabel("Background Focus")
        backgroundLabel.setStyleSheet("QLabel { font-size: 10px; color: gray; }")
        backgroundLabel.setAlignment(qt.Qt.AlignLeft)

        foregroundLabel = qt.QLabel("Foreground Focus")
        foregroundLabel.setStyleSheet("QLabel { font-size: 10px; color: gray; }")
        foregroundLabel.setAlignment(qt.Qt.AlignRight)

        # Create a vertical layout for the slider and labels
        sliderVLayout = qt.QVBoxLayout()

        # Add focus labels layout
        focusLayout = qt.QHBoxLayout()
        focusLayout.addWidget(backgroundLabel)
        focusLayout.addStretch()
        focusLayout.addWidget(foregroundLabel)
        sliderVLayout.addLayout(focusLayout)

        # Add slider
        sliderVLayout.addWidget(self.opacitySlider)

        # Add to main opacity layout
        opacityLayout.addLayout(sliderVLayout)
        opacityLayout.addWidget(self.opacityLabel)

        # Add to form layout with a descriptive label
        layout.addRow(qt.QLabel("Volume Focus:"), opacityLayout)

    def _addClassificationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Radio buttons for registration classification selection.
        """
        # Create a group box for the classification options
        classificationGroupBox = qt.QGroupBox("Registration Classification")
        classificationLayout = qt.QVBoxLayout()
        classificationGroupBox.setLayout(classificationLayout)

        # Create button group to ensure only one can be selected
        self.registrationClassificationGroup = qt.QButtonGroup()

        # Define the classification options
        classifications = [
            "Correctly Registered",
            "Non-Registered-Deformable",
            "Non-Registered-Rigid",
            "Other",
        ]

        # Create radio buttons for each classification
        for classification in classifications:
            radioButton = qt.QRadioButton(classification)
            radioButton.clicked.connect(
                lambda checked, c=classification: self.onClassificationChanged(c)
            )
            self.registrationClassificationGroup.addButton(radioButton)
            classificationLayout.addWidget(radioButton)

        # Add the group box to the main layout
        layout.addRow(classificationGroupBox)

    def _addCsvSelectionButton(self, layout: qt.QFormLayout) -> None:
        """
        Button to change CSV output location.
        """
        btn = qt.QPushButton("Change CSV Output Location")
        btn.clicked.connect(self.promptSelectCsvOutput)
        layout.addRow(btn)

    #
    # Handlers
    #

    def onOrientationChanged(self, orientation: Orientation) -> None:
        """Update the orientation for all views."""
        # Update our currently tracked orientation
        self.currentOrientation = orientation

        # If we don't have a data unit at this point, end here
        if not self.data_unit:
            return

        # Update the data unit's orientation
        self.data_unit.set_orientation(orientation)

        # Apply the layout
        self.data_unit.layout_handler.apply_layout()

    def onOpacityChanged(self, value: int) -> None:
        """Handle opacity slider changes."""
        # Convert slider value (0-100) to opacity (0.0-1.0)
        opacity = value / 100.0

        # Update the label
        self.opacityLabel.setText(f"{value}%")

        # Update the data unit's opacity if available
        if self.data_unit and hasattr(self.data_unit, "set_foreground_opacity"):
            self.data_unit.set_foreground_opacity(opacity)

    def onClassificationChanged(self, classification: str) -> None:
        """Handle registration classification selection."""
        self.selectedClassification = classification
        print(f"Selected classification: {classification}")

    ## USER PROMPTS ##
    def promptSelectCsvOutput(self):
        """
        Prompt the user to select CSV output location for registration review logging.
        """
        # Initialize the prompt
        prompt = self._buildCsvOutputPrompt()

        # Show the prompt with "exec", blocking the main window until resolved
        result = prompt.exec()

        # If the user cancelled out of the prompt, notify them
        if result != qt.QDialog.Accepted:
            notif = qt.QErrorMessage()
            if self.bound_task.can_save():
                notif.setWindowTitle(_("REVERTING!"))
                notif.showMessage(
                    _("Cancelled out of window; keeping previous CSV output settings.")
                )
                notif.exec()
            else:
                notif.setWindowTitle(_("NO OUTPUT!"))
                notif.showMessage(
                    _(
                        "No CSV output location selected! You will need to "
                        "specify this before registration reviews can be saved."
                    )
                )
                notif.exec()

    def _buildCsvOutputPrompt(self):
        """Build the CSV output selection dialog."""
        prompt = qt.QDialog()
        prompt.setWindowTitle("Select CSV Output Location")

        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Instruction label
        instructionLabel = qt.QLabel(
            "Select a CSV file location to log registration review results:"
        )
        instructionLabel.setWordWrap(True)
        layout.addWidget(instructionLabel)

        # CSV file path selection
        csvLabel = qt.QLabel("CSV log file:")
        layout.addWidget(csvLabel)

        # Create horizontal layout for CSV path input and buttons
        csvPathLayout = qt.QHBoxLayout()

        self.csvLogEdit = ctk.ctkPathLineEdit()
        self.csvLogEdit.setToolTip(
            _("Specify CSV log file path for registration review results.")
        )
        self.csvLogEdit.filters = ctk.ctkPathLineEdit.Files
        self.csvLogEdit.nameFilters = ["CSV files (*.csv)"]

        # Set current CSV log path if available
        if hasattr(self.bound_task, "csv_log_path") and self.bound_task.csv_log_path:
            self.csvLogEdit.currentPath = str(self.bound_task.csv_log_path)

        # Add browse button for CSV file selection
        csvBrowseButton = qt.QPushButton("Browse...")
        csvBrowseButton.setToolTip("Browse for CSV log file location")
        csvBrowseButton.clicked.connect(self._browseCsvLocation)
        csvBrowseButton.setMaximumWidth(100)

        csvPathLayout.addWidget(self.csvLogEdit)
        csvPathLayout.addWidget(csvBrowseButton)
        layout.addLayout(csvPathLayout)

        # Button box
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        buttonBox.addButton(_("Cancel"), qt.QDialogButtonBox.RejectRole)
        layout.addWidget(buttonBox)

        # Connect acceptance
        buttonBox.accepted.connect(lambda: self._attemptCsvUpdate(prompt))
        buttonBox.rejected.connect(prompt.reject)

        # Resize for better appearance - FIXED: minimumHeight is a property, not a method
        prompt.resize(450, prompt.minimumHeight)

        return prompt

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
            # Generate default filename based on user and current date
            user = getattr(self.bound_task, "user", "user")
            default_name = f"registration_review_log_{user}_{datetime.now().strftime('%Y%m%d')}.csv"
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

    def _attemptCsvUpdate(self, prompt: qt.QDialog):
        """
        Validates and applies the selected CSV output path.
        """
        csv_path_str = self.csvLogEdit.currentPath.strip()

        if not csv_path_str:
            err_msg = "CSV output path was empty"
            self._showErrorPrompt(err_msg, prompt)
            return

        csv_path = Path(csv_path_str)

        # Validate CSV path parent directory exists
        if not csv_path.parent.exists():
            err_msg = f"CSV output directory does not exist: {csv_path.parent}"
            self._showErrorPrompt(err_msg, prompt)
            return

        # Set the CSV path in the bound task
        err_msg = self.bound_task.set_csv_output(csv_path)

        # Check for errors
        if err_msg:
            self._showErrorPrompt(err_msg, prompt)
            return

        # Success - close the prompt
        prompt.accept()

    def _showErrorPrompt(self, err_msg, prompt):
        """
        Prompt the user with an error message
        """
        failurePrompt = qt.QErrorMessage(prompt)
        failurePrompt.setWindowTitle("ERROR!")
        failurePrompt.showMessage(err_msg)
        failurePrompt.exec()

    def update(self, data_unit: "RegistrationReviewDataUnit") -> None:
        """
        Called whenever a new data-unit is in focus.
        """
        self.data_unit = data_unit

        # Apply the data unit's layout to our viewer if it has one
        if hasattr(self.data_unit, "layout_handler"):
            self.data_unit.layout_handler.apply_layout()

        # Update review status and classification for this case
        self._updateReviewStatus()

    def _updateReviewStatus(self) -> None:
        """Update the review status display and classification selection for current case."""
        if not self.data_unit or not self.bound_task.csv_log_path:
            if self.reviewStatusLabel:
                self.reviewStatusLabel.setText("Review Status: Not checked")
            return

        # Get review status from CSV
        review_info = self.bound_task.get_review_status(self.data_unit.uid)

        if review_info:
            # Case has been reviewed
            status_text = f"Review Status: ✓ Reviewed ({review_info['registration_classification']})"
            self.reviewStatusLabel.setText(status_text)
            self.reviewStatusLabel.setStyleSheet(
                "QLabel { font-weight: bold; color: green; }"
            )

            # Set the classification selection to match existing review
            self._setClassificationSelection(review_info["registration_classification"])
        else:
            # Case not yet reviewed
            self.reviewStatusLabel.setText("Review Status: ✗ Not reviewed")
            self.reviewStatusLabel.setStyleSheet(
                "QLabel { font-weight: bold; color: red; }"
            )

            # Clear classification selection
            if self.registrationClassificationGroup:
                self.registrationClassificationGroup.setExclusive(False)
                for button in self.registrationClassificationGroup.buttons():
                    button.setChecked(False)
                self.registrationClassificationGroup.setExclusive(True)
                self.selectedClassification = None

    def _setClassificationSelection(self, classification: str) -> None:
        """Set the radio button selection to match the given classification."""
        if not self.registrationClassificationGroup:
            return

        for button in self.registrationClassificationGroup.buttons():
            if button.text == classification:
                button.setChecked(True)
                self.selectedClassification = classification
                break


@cart_task("Registration Review")
class RegistrationReviewTask(TaskBaseClass[RegistrationReviewDataUnit]):
    """
    Task for reviewing registration results.
    Saves review data to a CSV log file.
    """

    UID_KEY = "uid"
    USER_KEY = "user"
    STATUS_KEY = "review_status"

    REVIEW_COMPLETE = "reviewed"

    FIELD_NAMES = [
        UID_KEY,
        USER_KEY,
        "timestamp",
        STATUS_KEY,
        "registration_classification",
    ]

    def __init__(self, profile: str):
        super().__init__(profile)

        # Variable for tracking the active GUI instance
        self.gui: Optional["RegistrationReviewGUI"] = None

        # CSV log file path
        self.csv_log_path: Optional[Path] = None
        self.csv_log: Optional[dict[tuple[str, str], dict[str, str]]] = None

        # Current data unit
        self.data_unit: Optional[RegistrationReviewDataUnit] = None

        # Review status cache
        self._review_status_cache: Optional[dict] = None

    def setup(self, container: qt.QWidget):
        """Set up the GUI for this task."""
        print(f"Running {self.__class__.__name__} setup!")

        # Initialize the GUI instance for this task
        self.gui = RegistrationReviewGUI(self)

        # Build its GUI and install it into the container widget
        gui_layout = self.gui.setup()
        container.setLayout(gui_layout)

        # Try to initialize our CSV log from the settings provided by the GUI
        self.csv_log = self._load_csv_log()

        # Update this new GUI with our current data unit if it exists
        if self.data_unit:
            self.gui.update(self.data_unit)

    def receive(self, data_unit: RegistrationReviewDataUnit):
        """Receive a new data unit for review."""
        # Track the data unit for later
        self.data_unit = data_unit

        # Update GUI if it exists
        if self.gui:
            self.gui.update(data_unit)

    def cleanup(self):
        """Clean up resources when task is destroyed."""
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def save(self) -> Optional[str]:
        """Save the current registration review to CSV."""
        if not self.can_save():
            return "Cannot save: No CSV output location specified"

        if not self.data_unit:
            return "Cannot save: No data unit available"

        # Check if a classification has been selected
        if not self.gui or not self.gui.selectedClassification:
            return "Cannot save: No registration classification selected. Please select a classification option."

        try:
            # Prepare the data to save
            review_data = {
                self.UID_KEY: self.data_unit.uid,
                self.USER_KEY: self.profile_label,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.STATUS_KEY: self.REVIEW_COMPLETE,
                "registration_classification": self.gui.selectedClassification,
            }

            # Replace/add the entry to our CSV log
            self.csv_log[(self.data_unit.uid, self.profile_label)] = review_data

            # Write the updated data back to our CSV log file
            with open(self.csv_log_path, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=self.FIELD_NAMES)
                writer.writeheader()
                writer.writerows(self.csv_log.values())

            print(
                f"Registration review saved for UID: {self.data_unit.uid} with classification: {self.gui.selectedClassification}"
            )
            return None  # Success

        except Exception as e:
            error_msg = f"Error saving registration review: {str(e)}"
            print(error_msg)
            return error_msg

    def get_review_status(self, uid: str) -> Optional[dict]:
        """Get review status for a specific UID from the CSV file."""
        if not self.csv_log_path or not self.csv_log_path.exists():
            return None

        try:
            with open(self.csv_log_path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if row.get("uid") == uid and row.get(self.USER_KEY) == self.profile_label:
                        return row
            return None
        except Exception as e:
            print(f"Error reading review status: {str(e)}")
            return None

    def _load_csv_log(self) -> dict[tuple[str, str], dict[str, str]]:
        """Load all review statuses into cache for efficient lookup."""
        # If no log was specified, or a new path was specified, initiate a new log
        csv_log = {}
        if not self.csv_log_path or not self.csv_log_path.exists():
            return {}

        # Otherwise, read the contents of the log file ourselves
        with open(self.csv_log_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row in enumerate(reader):
                # Confirm the row has a UID; if not, skip it
                uid = row.get('uid', None)
                if not uid:
                    print(f"WARNING: Skipping entry #{i} in {self.csv_log_path}, lacked a valid UID")
                    continue
                # Generate a unique uid + author combo to use as our key
                author = row.get('author', None)
                # KO: In Python, as long as the contents of a tuple are hashable,
                # the tuple is hashable as well!
                csv_log[(uid, author)] = row

        return csv_log

    def can_save(self) -> bool:
        """Check if we can save the current registration review."""
        return self.csv_log_path is not None and self.data_unit is not None

    def set_csv_output(self, csv_path: Path) -> Optional[str]:
        """Set the CSV output path and validate it."""
        try:
            # Ensure parent directory exists
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Store the path
            self.csv_log_path = csv_path

            # Initialize CSV file with headers if it doesn't exist
            if not csv_path.exists():
                fieldnames = [
                    "uid",
                    "user",
                    "timestamp",
                    "review_status",
                    "registration_classification",
                ]
                with open(csv_path, "w", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

            # Clear the review status cache when CSV path changes
            self._review_status_cache = None

            return None  # Success

        except Exception as e:
            error_msg = f"Error setting CSV output path: {str(e)}"
            print(error_msg)
            return error_msg

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """Return the data unit factories for this task."""
        return {"Default": RegistrationReviewDataUnit}

    def isTaskComplete(self, case_data: dict[str: str]) -> bool:
        # If we don't have a CSV log, we can't check whether we're done
        if not self.csv_log_path or not self.csv_log:
            return False

        # Check if we have an entry for this user and UID
        case_entry = self.csv_log.get((self.data_unit.uid, self.profile_label), None)
        # If not, the task hasn't been completed
        if not case_entry:
            return False

        # Check if the case represents a complete review
        case_status = case_entry.get(self.STATUS_KEY)
        # If so, the review has been completed
        if case_status == self.REVIEW_COMPLETE:
            return True

        # If we've passed all the prior checks, assume the task has yet to be done
        return False
