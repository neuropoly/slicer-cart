import importlib
import logging
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Tuple

import ctk
import qt
import slicer.util
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

from CARTLib.core.DataManager import DataManager
from CARTLib.core.LayoutManagement import OrientationButtonArrayWidget
from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.core.SetupWizard import CARTSetupWizard, JobSetupWizard
from CARTLib.utils import CART_PATH, get_cart_version
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.task import CART_TASK_REGISTRY

# These become available when Slicer initializes
# noinspection PyUnresolvedReferences
import vtk
# noinspection PyUnresolvedReferences
from slicer import vtkMRMLScalarVolumeNode

if TYPE_CHECKING:
    import PyQt5.Qt as qt

#
# CART
#
class CART(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CART"  # It's an acronym title, not really translate-able
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []  # No dependencies
        # TODO: Move these metadata contents into a standalone file which can
        #  be updated automatically as new PRs are made
        self.parent.contributors = [
            "Kalum Ost (Montréal Polytechnique)",
            "Kuan Yi (Montréal Polytechnique)",
            "Ivan Johnson-Eversoll (University of Iowa)",
        ]
        self.parent.helpText = _("""
                CART (Case Annotation and Review Tool) provides a set
                of abstract base classes for creating streamlined annotation
                workflows in 3D Slicer. The framework enables efficient
                iteration through medical imaging cohorts with customizable
                tasks and flexible data loading strategies.

                See more information on the
                <a href="https://github.com/SomeoneInParticular/CART/tree/main">GitHub repository</a>.
            """)
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
                Originally created during Slicer Project Week #43.

                Special thanks the many members of the Slicer community who
                contributed to this work, including the many projects which
                were used as reference. Of note:
                <a href="https://github.com/neuropoly/slicercart">SlicerCART</a> (the name and general framework),
                <a href="https://github.com/JoostJM/SlicerCaseIterator">SlicerCaseIterator</a> (inspired much of our logic),
                <a href="https://github.com/SlicerUltrasound/SlicerUltrasound">SlicerUltrasound/AnnotateUltrasound</a> (basis for our UI design),
                and the many other projects discussed during the breakout session (notes
                <a href="https://docs.google.com/document/d/12XuYPVuRgy4RTuIabSIjy_sRrYSliewKhcbB1zJgXVI/">here.</a>)
            """)

        # Initialize our working environment
        self.init_env()

    @staticmethod
    def init_env():
        # Add CARTLib to the Python Path for ease of (re-)use
        import sys

        cartlib_path = (Path(__file__) / "CARTLib").resolve()
        sys.path.append(str(cartlib_path))


#
# CARTWidget
#
class CARTWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None) -> None:
        """
        Called when the module is initialized by Slicer
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)

        # Initialize our logic instance
        self.logic: CARTLogic = CARTLogic()

        # Core widgets, which can be swapped on the fly
        self.mainWidget: qt.QStackedWidget = None
        self.configWidgetIndex = -1
        self.jobWidgetIndex = -1

        # Widget which holds the current profile label
        self.userText: qt.QWidget = None

        # Widget which holds the task-specific GUI elements
        self.taskSubWidget: qt.QWidget = None

        # List of keyboard shortcuts to be installed/uninstalled within this widget
        self.keyboardShortcuts = []

        # When the logic changes our active job, update ourselves to match
        self.logic.jobChanged.connect(self._onJobChanged)

    ## Keyboard Shortcuts ##
    NEXT_CASE_HOTKEY = _("PgDown")
    NEXT_INCOMPLETE_HOTKEY = _("ALT+PgDown")
    PREVIOUS_CASE_HOTKEY = _("PgUp")
    PREVIOUS_INCOMPLETE_CASE_HOTKEY = _("ALT+PgUp")
    SAVE_HOTKEY = _("ALT+S")
    SAVE_AND_NEXT_HOTKEY = _("ALT+D")

    def _registerShortcut(self, key, action):
        shortcut = qt.QShortcut(slicer.util.mainWindow())
        shortcut.setKey(qt.QKeySequence(key))
        shortcut.activated.connect(action)
        self.keyboardShortcuts.append(shortcut)
        return shortcut

    def installKeyboardShortcuts(self):
        mainWindow = slicer.util.mainWindow()

        # Next Case
        self._registerShortcut(self.NEXT_CASE_HOTKEY, self.logic.next_case)

        # Next Incomplete Case
        self._registerShortcut(
            self.NEXT_INCOMPLETE_HOTKEY, self.logic.next_incomplete_case
        )

        # Previous Case
        self._registerShortcut(
            self.PREVIOUS_CASE_HOTKEY, self.logic.previous_case
        )

        # Previous Incomplete Case
        self._registerShortcut(
            self.PREVIOUS_INCOMPLETE_CASE_HOTKEY, self.logic.previous_incomplete_case
        )

        # Save case
        self._registerShortcut(self.SAVE_HOTKEY, self.logic.save_case)

        # Save case and move to next
        self._registerShortcut(self.SAVE_AND_NEXT_HOTKEY, self.logic.save_case_and_iterate)

    def uninstallKeyboardShortcuts(self):
        for kbs in self.keyboardShortcuts:
            kbs.activated.disconnect()
            kbs.setParent(None)
        self.keyboardShortcuts = []

    ## GUI ##
    def setup(self) -> None:
        """
        Called when the user opens the CART module within Slicer for the first time.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # The stacking widget, which will hold our sub-menus
        mainWidget = qt.QStackedWidget(self.parent)

        # Set up the configuration widget
        configWidget = self._setupConfigurationWidget()
        self.configWidgetIndex = mainWidget.addWidget(configWidget)

        # Set up the job widget
        jobWidget, taskWidget = self._setupJobWidget()
        self.taskSubWidget = taskWidget
        self.jobWidgetIndex = mainWidget.addWidget(jobWidget)

        # Insert the widget into our main layout
        self.layout.addWidget(mainWidget)
        self.mainWidget = mainWidget

        # Add a stretch to push everything to the top (seriously, why is this not default?)
        self.layout.addStretch()

    def _setupConfigurationWidget(self) -> qt.QWidget:
        # Setup
        mainWidget = qt.QWidget(self.parent)
        layout = qt.QVBoxLayout(mainWidget)

        # Profile configuration elements
        profileWidget = self._profileManagementPanel()
        layout.addWidget(profileWidget)

        # Button panel for creating, editing, or deleting jobs
        jobManagementPanel = self._jobManagementPanel()
        layout.addWidget(jobManagementPanel)

        # Add a stretch to push everything to the top
        layout.addStretch()

        return mainWidget

    def _profileManagementPanel(self) -> qt.QWidget:
        # Setup
        mainWidget = qt.QWidget(self.parent)
        layout = qt.QVBoxLayout(mainWidget)

        # Current user label + text box
        userLabel = qt.QLabel(_("Current User:"))
        userText = qt.QLineEdit()
        userText.setPlaceholderText(
            _(
                "The current username + role will appear here; you need to initialize a profile first!"
            )
        )
        userText.setReadOnly(True)
        layout.addWidget(userLabel)
        layout.addWidget(userText)

        # Edit profile button
        editProfileButton = qt.QPushButton()
        editProfileButton.setText(_("Edit Profile"))
        editProfileButton.setToolTip(_("Edit (or create) a user profile."))
        layout.addWidget(editProfileButton)

        # Connections
        editProfileButton.pressed.connect(self.runProfileEdit)

        # Setup and return
        self.userText = userText
        self.profileChanged()
        return mainWidget

    def _jobManagementPanel(self) -> qt.QWidget:
        # Setup
        mainWidget = qt.QWidget(None)
        layout = qt.QVBoxLayout(mainWidget)

        # Job selection dropdown
        jobSelectorComboBoxLabel = qt.QLabel(_("Please Select or Create a Job:"))
        jobSelectorComboBox = qt.QComboBox(None)

        # Ensure the job selection dropdown is properly updated upon request
        @qt.Slot()
        def updateJobSelector():
            jobSelectorComboBox.clear()
            jobSelectorComboBox.addItems(self.logic.registered_jobs_names)
            if len(self.logic.registered_jobs_names) > 0:
                jobSelectorComboBox.setEnabled(True)
                jobSelectorComboBox.setCurrentIndex(0)
            else:
                jobSelectorComboBox.setEnabled(False)

        # Ping to sync up immediately
        updateJobSelector()
        self.logic.jobListChanged.connect(updateJobSelector)

        layout.addWidget(jobSelectorComboBoxLabel)
        layout.addWidget(jobSelectorComboBox)

        # Button panel for Job editing operations
        buttonPanel = qt.QWidget(None)
        buttonPanelLayout = qt.QHBoxLayout(buttonPanel)
        layout.addWidget(buttonPanel)

        # "New" button
        newButton = qt.QPushButton(_("New"))
        newButton.setToolTip(_("Create a new Job"))

        @qt.Slot()
        def newButtonClicked():
            # Create a new job from scratch
            new_name = self.runNewJobSetup()
            # If the new name is not None (indicating success), start it automatically
            if new_name is not None:
                self.logic.set_active_job(new_name)

        newButton.clicked.connect(newButtonClicked)
        buttonPanelLayout.addWidget(newButton)

        # "Edit" button
        editButton = qt.QPushButton(_("Edit"))
        editButton.setToolTip(_("Edit the Job's configuration"))

        @qt.Slot()
        def editButtonClicked():
            # Edit the job currently selected by the dropdown
            job_name: str = jobSelectorComboBox.currentText.strip()
            # If the user didn't back out of the edit, start the job once they're done
            if self.editJob(job_name):
                self.logic.set_active_job(job_name)

        editButton.clicked.connect(editButtonClicked)
        buttonPanelLayout.addWidget(editButton)
        self.logic.jobListChanged.connect(
            lambda: editButton.setEnabled(jobSelectorComboBox.isEnabled())
        )
        editButton.setEnabled(jobSelectorComboBox.isEnabled())

        # "Delete" button
        deleteButton = qt.QPushButton(_("Delete"))
        deleteButton.setToolTip(_("Delete the Job configuration"))

        @qt.Slot()
        def onJobDelete():
            self.logic.delete_job_config(jobSelectorComboBox.currentText)

        deleteButton.clicked.connect(onJobDelete)
        buttonPanelLayout.addWidget(deleteButton)
        self.logic.jobListChanged.connect(
            lambda: deleteButton.setEnabled(jobSelectorComboBox.isEnabled())
        )
        deleteButton.setEnabled(jobSelectorComboBox.isEnabled())

        # Start button; initializes the job, or walks the user through job setup if there isn't one
        startButton = qt.QPushButton("Start")
        startButton.setToolTip(_("Start CART!"))

        @qt.Slot()
        def onStartClicked():
            if jobSelectorComboBox.isEnabled():
                self.start(jobSelectorComboBox.currentText)
            else:
                self.start()

        startButton.clicked.connect(onStartClicked)
        layout.addWidget(startButton)

        return mainWidget

    def _setupJobWidget(self) -> Tuple[qt.QWidget, qt.QWidget]:
        # Setup
        mainWidget = qt.QWidget(self.parent)
        layout = qt.QVBoxLayout(mainWidget)

        # Add the iteration panel
        caseSelectionPanel = self._caseSelectionPanel()
        layout.addWidget(caseSelectionPanel)

        # Add the save button w/ proper padding
        savePanel = self._savePanel()
        layout.addWidget(savePanel)

        # Add the layout panel
        layoutPanel = self._layoutPanel()
        layout.addWidget(layoutPanel)

        # Add the widget in which the task's GUI will be inserted
        taskWidget = qt.QWidget(mainWidget)
        layout.addWidget(taskWidget)

        # Add a stretch to push everything to the top
        layout.addStretch()

        return mainWidget, taskWidget

    def _caseSelectionPanel(self) -> qt.QWidget:
        ## Setup ##
        buttonPanel = qt.QWidget(None)
        layout = qt.QHBoxLayout(buttonPanel)

        # TODO: Replace these with custom icons to ensure standardization
        UNKNOWN_ICON = buttonPanel.style().standardIcon(qt.QStyle.SP_FileIcon)
        COMPLETED_ICON = buttonPanel.style().standardIcon(qt.QStyle.SP_DialogApplyButton)
        FAILED_ICON = buttonPanel.style().standardIcon(qt.QStyle.SP_MessageBoxCritical)
        ERROR_ICON = buttonPanel.style().standardIcon(qt.QStyle.SP_MessageBoxWarning)

        # Wrapper util for marking cases which had an error
        def marksErrorCases(f):
            @qt.Slot(None)
            def _f():
                # Run the function, tracking its start and end point
                original_idx = self.logic.current_case_idx
                f()
                new_idx = self.logic.current_case_idx
                # If there was no change, end here; another function updated the icon
                if new_idx == original_idx:
                    pass
                # Otherwise, iterate through all cases and see if they're now marked as errors
                min_idx = min([original_idx, new_idx])
                max_idx = max([original_idx, new_idx])
                print([i for i in range(min_idx, max_idx)])
                for idx in range(min_idx, max_idx):
                    if idx in self.logic.data_manager.failed_indices:
                        caseSelector.setItemIcon(idx, ERROR_ICON)
            return _f

        ## Previous Incomplete ##
        previousIncompleteButton = qt.QToolButton(None)
        previousIncompleteButton.setText("<<")
        previousIncompleteButton.setToolTip(
            _(
                f"Jump to the Previous Incomplete Case [{self.PREVIOUS_INCOMPLETE_CASE_HOTKEY}]"
            )
        )

        _previousIncompleteCaseFunc = marksErrorCases(self.logic.previous_incomplete_case)
        previousIncompleteButton.clicked.connect(_previousIncompleteCaseFunc)

        ## Previous Button ##
        previousButton = qt.QToolButton(None)
        previousButton.setText("<")
        previousButton.setToolTip(
            _(f"Switch to the Previous Case [{self.PREVIOUS_CASE_HOTKEY}]")
        )
        _previousCaseFunc = marksErrorCases(self.logic.previous_case)
        previousButton.clicked.connect(_previousCaseFunc)

        ## Next Button ##
        nextButton = qt.QToolButton(None)
        nextButton.setText(">")
        nextButton.setToolTip(_(f"Switch to the Next Case [{self.NEXT_CASE_HOTKEY}]"))
        _nextCaseFunc = marksErrorCases(self.logic.next_case)
        nextButton.clicked.connect(_nextCaseFunc)

        ## Next Incomplete ##
        nextIncompleteButton = qt.QToolButton(None)
        nextIncompleteButton.setText(">>")
        nextIncompleteButton.setToolTip(
            _(f"Jump to the Next Incomplete Case [{self.NEXT_INCOMPLETE_HOTKEY}]")
        )
        _nextIncompleteCaseFunc = marksErrorCases(self.logic.next_incomplete_case)
        nextIncompleteButton.clicked.connect(_nextIncompleteCaseFunc)

        ## Case Viewer/Selector ##
        caseSelector: qt.QComboBox = ctk.ctkComboBox(None)

        @qt.Slot(int)
        def selectCaseAt(idx: int):
            # Track the original case as a backup
            prior_case_idx = self.logic.current_case_idx
            # Try to load the requested case
            try:
                self.logic.select_case(idx)
            # If it failed, rollback to the original case and mark the case as causing an error
            except Exception as e:
                self.logic.select_case(prior_case_idx)
                caseSelector.setItemIcon(idx, ERROR_ICON)
                raise e

        caseSelector.currentIndexChanged.connect(selectCaseAt)

        # Add them each to the panel
        layout.addWidget(previousIncompleteButton, 1)
        layout.addWidget(previousButton, 1)
        layout.addWidget(caseSelector, 10)
        layout.addWidget(nextButton, 1)
        layout.addWidget(nextIncompleteButton, 1)

        ## Logic Connections ##
        @qt.Slot(int)
        def updateCaseIcon(idx: int):
            # Update the previous case's state to match
            case_completed = self.logic.is_case_completed(idx)
            if case_completed:
                # True -> task saved correctly
                caseSelector.setItemIcon(idx, COMPLETED_ICON)
                self.saveButton.setText(self.SAVE_BUTTON_SUCCESS_TEXT)
                self.saveStateTimer.start(3000)  # 3 seconds
            elif case_completed is None:
                # None -> the task isn't sure (the default)
                caseSelector.setItemIcon(idx, UNKNOWN_ICON)
                self.saveButton.setText(self.SAVE_BUTTON_UNKNOWN_TEXT)
                self.saveStateTimer.start(5000)  # 5 seconds
            else:
                # False -> a failure to save when the case swapped over
                caseSelector.setItemIcon(idx, FAILED_ICON)
                self.saveButton.setText(self.SAVE_BUTTON_FAILURE_TEXT)
                self.saveStateTimer.start(5000)  # 5 seconds
        self.logic.caseSaved.connect(updateCaseIcon)

        @qt.Slot()
        def updateCaseOptions():
            # Block signals to prevent accidental cyclic chains
            caseSelector.blockSignals(True)
            try:
                caseSelector.clear()
                for i, u in enumerate(self.logic.data_manager.valid_uids):
                    caseSelector.addItem(u)
                    # Update the previous case's state to match
                    updateCaseIcon(i)
                # Immediately set our save button's text back to default
                self.saveButton.setText(self.SAVE_BUTTON_DEFAULT_TEXT)
            # Re-enable signals no matter what
            finally:
                caseSelector.blockSignals(False)
        self.logic.jobChanged.connect(updateCaseOptions)

        @qt.Slot(int, int)
        def updatePriorButtons(__, ___):
            has_prior = self.logic.has_previous_case()
            previousIncompleteButton.setEnabled(has_prior)
            previousButton.setEnabled(has_prior)
        self.logic.caseChanged.connect(updatePriorButtons)

        @qt.Slot(int, int)
        def updateNextButtons(__, ___):
            has_next = self.logic.has_next_case()
            nextIncompleteButton.setEnabled(has_next)
            nextButton.setEnabled(has_next)
        self.logic.caseChanged.connect(updateNextButtons)

        @qt.Slot(int, int)
        def updateSelectedCase(__: int, new_idx: int):
            # Block signals to prevent it from causing an infinite loop
            caseSelector.blockSignals(True)
            try:
                # Update our case selector to match the newly chosen case
                caseSelector.setCurrentIndex(new_idx)
            # Re-enable signals
            finally:
                caseSelector.blockSignals(False)
        self.logic.caseChanged.connect(updateSelectedCase)

        # Return the result
        return buttonPanel

    SAVE_BUTTON_DEFAULT_TEXT = _("Save")
    SAVE_BUTTON_SUCCESS_TEXT = _("Saved!")
    SAVE_BUTTON_FAILURE_TEXT = _("Failed to Save!")
    SAVE_BUTTON_UNKNOWN_TEXT = _("Save Status Unknown")

    def _savePanel(self) -> qt.QWidget:
        # The main content panel
        buttonPanel = qt.QWidget(None)
        buttonPanelLayout = qt.QHBoxLayout(buttonPanel)

        # The primary "save" button
        saveButton = qt.QPushButton(self.SAVE_BUTTON_DEFAULT_TEXT)
        saveButtonToolTip = f"Save the current case to file [{self.SAVE_HOTKEY}]."
        saveButton.setToolTip(saveButtonToolTip)
        saveButton.clicked.connect(self.logic.save_case)
        self.saveButton = saveButton

        # A "Save an Iterate" button, as requested by collaborators
        saveAndNextButton = qt.QPushButton(_(
            "Save and Next Case"
        ))
        saveAndNextButtonToolTip = (
            f"Save the current case to file and continue [{self.SAVE_AND_NEXT_HOTKEY}]."
        )
        saveAndNextButton.setToolTip(saveAndNextButtonToolTip)
        saveAndNextButton.clicked.connect(self.logic.save_case_and_iterate)

        # Timer which will automatically "reset" the button's text when it expires
        self.saveStateTimer = qt.QTimer(None)
        self.saveStateTimer.setSingleShot(True)  # Stop after being triggered
        @qt.Slot()
        def resetSaveButtonText():
            saveButton.setText(self.SAVE_BUTTON_DEFAULT_TEXT)
        self.saveStateTimer.timeout.connect(resetSaveButtonText)

        # Lay them out side-by-side with some padding.
        buttonPanelLayout.addStretch(1)
        buttonPanelLayout.addWidget(saveButton, 10)
        buttonPanelLayout.addStretch(1)
        buttonPanelLayout.addWidget(saveAndNextButton, 10)
        buttonPanelLayout.addStretch(1)

        return buttonPanel

    def _layoutPanel(self):
        layoutPanel = OrientationButtonArrayWidget()

        @qt.Slot(int, int)
        def onNewCase(__: int, ___: int):
            new_unit = self.logic.data_manager.current_data_unit()
            layoutPanel.changeLayoutHandler(new_unit.layout_handler, True)
            new_unit.layout_handler.apply_layout()

        self.logic.caseChanged.connect(onNewCase)

        return layoutPanel

    ## Connections ##
    def start(self, job_name=None):
        # Check if a user profile exists, prompting the user to create one if not.
        if not self.logic.has_run_before():
            if self._noProfileFoundPrompt() != qt.QMessageBox.Yes:
                return
            if not self.runProfileEdit(show_walkthrough=True):
                return
        # If no job was specified, ask if they want to create one.
        if job_name is None:
            if self._createFirstJobPrompt() != qt.QMessageBox.Yes:
                return
            job_name = self.runNewJobSetup()
            if job_name is None:
                return
        # If the corresponding job path doesn't exist on file, prompt the user to "edit" the job instead.
        job_path = self.logic.registered_jobs.get(job_name, None)
        if job_path is None or not Path(job_path).exists():
            # If the user backs out of re-creating the new job, end here
            if not self.editJob(job_name):
                return
        # Finally, initialize the job
        self.logic.set_active_job(job_name)

    def profileChanged(self):
        # Update the text in the profile to match the current config settings
        if (author := self.logic.master_profile_config.author) is not None:
            position = self.logic.master_profile_config.position
            if position is None:
                new_text = author
            else:
                new_text = f"{author} ({position})"
            self.userText.setText(new_text)
        else:
            self.userText.clear()

    ## User Prompts ##
    @staticmethod
    def _noProfileFoundPrompt():
        return qt.QMessageBox.question(
            None,
            _("Initialize Profile?"),
            _(
                "You have not set up your user profile yet. Would you like to do so now?"
            ),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes,
        )

    @staticmethod
    def _createFirstJobPrompt():
        return qt.QMessageBox.question(
            None,
            _("Create Job?"),
            _("You have not run a CART job before. Would you like to set up a job now?"),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes,
        )

    @staticmethod
    def _jobMissingPrompt(job_name: str):
        return qt.QMessageBox.warning(
            None,
            _(f"Job '{job_name}' Not Found"),
            _(
                f"The configuration for {job_name} was deleted or is unavailable; "
                "would you like to create a new job of the same name instead?"
            ),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes,
        )

    ## Setup Workflows ##
    @qt.Slot()
    def runProfileEdit(self, show_walkthrough: bool = False) -> bool:
        """
        Run the cart profile editor, only applying its changes if the user confirms them.

        :param show_walkthrough: Whether introductory and conclusion pages should be displayed.
          Usually only needed when the user is "brand new", and just clicked 'start' without
          knowing any better.

        :return: If the setup was successful or not.
        """
        profileWizard = CARTSetupWizard(None, self.logic.master_profile_config, show_walkthrough)
        result = profileWizard.exec()
        if result == qt.QDialog.Accepted:
            # Save the results and report the user made changes
            self.logic.save_master_config()
            self.profileChanged()
            return True
        else:
            # Otherwise, reset the config to what it was and report no changes made
            self.logic.reload_master_config()
            return False

    @qt.Slot()
    def runNewJobSetup(self) -> Optional[str]:
        """
        Run CART job creation, prompting the user to provide the following:
            * The data they want to use, and where to save the results.
            * The task they want to run.
            * How they want to iterate through the data (the "cohort").
            * Relevant configurations for each of the previous options.

        :return: The name of the new job; None if the setup was terminated.
        """

        jobSetupWizard = JobSetupWizard(
            None, taken_names=self.logic.registered_jobs.keys()
        )
        result = jobSetupWizard.exec()

        # If we got an "accept" signal, create the job config and initialize it
        if result == qt.QDialog.Accepted:
            new_config = jobSetupWizard.save_config(self.logic)
            return new_config.name
        return None

    def editJob(self, job_name: str) -> bool:
        """
        Begin editing the job with the provided name. If no such job exists,
        the user will be prompted to create a job of the same name instead.

        :return: True if the job was successfully edited, False otherwise.
        """
        job_path = self.logic.registered_jobs.get(job_name, None)
        # If the specified job's path is missing, ask if they want to re-create it!
        if job_path is None or not Path(job_path).exists():
            # If they don't, end here
            if self._jobMissingPrompt(job_name) != qt.QMessageBox.Yes:
                return False
            # Create a new config w/ the same name
            job_config = JobProfileConfig()
            job_config.name = job_name
        # Otherwise, load the previous job's configuration
        else:
            job_config = JobProfileConfig(file_path=Path(job_path))
            job_config.reload()

        # Initialize the wizard which will walk the user through the edits.
        jobSetupWizard = JobSetupWizard(
            None, taken_names=self.logic.registered_jobs.keys(), config=job_config
        )

        # If we got an "accept" signal, register the changes and return True
        if jobSetupWizard.exec() == qt.QDialog.Accepted:
            jobSetupWizard.save_config(self.logic)
            return True
        # Otherwise the user backed out, return False
        return False

    ## Job Management ##
    @qt.Slot(str)
    def _onJobChanged(self):
        # Initialize our GUI
        self.logic.init_task_gui(self.taskSubWidget)

        # Swap to this new job widget
        self.mainWidget.setCurrentIndex(self.jobWidgetIndex)

    ## View Management ##
    def cleanup(self) -> None:
        """
        Called when the application closes and this widget is about to be destroyed.
        """
        # Disconnect from the signals we hooked into so Slicer can close cleanly
        self.logic.jobChanged.disconnect()
        self.logic.jobListChanged.disconnect()
        self.logic.caseSaved.disconnect()
        self.logic.caseChanged.disconnect()
        self.saveStateTimer.timeout.disconnect()

    def enter(self):
        # Delegate to our logic to have tasks properly update
        self.logic.enter()

        # Install our keyboard shortcuts
        self.installKeyboardShortcuts()

    def exit(self):
        # Delegate to our logic to have tasks properly update
        self.logic.exit()

        # Remove our keyboard shortcuts
        self.uninstallKeyboardShortcuts()


#
# CARTLogic
#
# noinspection PyUnresolvedReferences
class CARTLogic(ScriptedLoadableModuleLogic, qt.QObject):

    # Emitted when the active job has been changed;
    # currently only happens once, when the first job is initialized.
    jobChanged = qt.Signal()

    # Emitted when the list of jobs managed by CART has changed
    # (a job was added, removed, or renamed)
    jobListChanged = qt.Signal()

    # Signal for when a given case (the first int) is changed to another (the second)
    # The first int is -1 when no prior case exists (this is the first case loaded)
    caseChanged = qt.Signal(int, int)

    # Emitted when the case at a given index just tried to save
    caseSaved = qt.Signal(int)

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

        # Attribute declaration
        self.master_profile_config: MasterProfileConfig = MasterProfileConfig()
        self.active_job_config: Optional[JobProfileConfig] = None
        self._data_manager: Optional[DataManager] = None
        self._task_instance: Optional[TaskBaseClass] = None

        # Logging
        self.logger = logging.getLogger("CARTLogic")

        # Attempt to load the config into memory
        self.reload_master_config()

        # Attempt to fetch all loaded tasks
        self.load_registered_tasks()

    ## Attributes
    @property
    def author(self) -> str:
        return self.master_profile_config.author

    @author.setter
    def author(self, new_author: str):
        self.master_profile_config.author = new_author

    @property
    def position(self) -> str:
        return self.master_profile_config.position

    @position.setter
    def position(self, new_position: str):
        self.master_profile_config.position = new_position

    @property
    def data_manager(self):
        # Get only to prevent horrific bugs
        return self._data_manager

    @property
    def current_case_idx(self):
        return self._data_manager.current_case_index

    ## Job Management ##
    @property
    def registered_jobs(self) -> dict[str, str]:
        return self.master_profile_config.registered_jobs

    @property
    def registered_jobs_names(self) -> list[str]:
        # Shortcut function for easy reference.
        return list(self.master_profile_config.registered_jobs.keys())

    def delete_job_config(self, job_name: str):
        # Remove the job entry from our registered jobs
        job_path = self.registered_jobs.pop(job_name, None)
        # If there was a corresponding job w/ a valid config path, delete it too
        if job_path and (job_path := Path(job_path)).exists():
            job_path.unlink()
        # Save our master config to preserve the change
        self.master_profile_config.has_changed = True
        self.master_profile_config.save()
        # Emit the appropriate signal
        self.jobListChanged()

    def set_active_job(self, job_name: str):
        """
        Loads the specified job, based on its associated config
        """
        # Confirm the requested job is registered
        if not job_name in self.registered_jobs.keys():
            raise ValueError(
                f"Cannot set job '{job_name}' as active; it has not been registered!"
            )

        # Confirm the job config file exist
        job_file = Path(self.registered_jobs.get(job_name))
        if not job_file.exists() or not job_file.is_file():
            raise ValueError(
                f"Cannot set job '{job_name}' as active; its corresponding config file does not exist!"
            )

        # Get and load the job's config
        job_profile = JobProfileConfig(file_path=job_file)
        job_profile.reload()

        # Initialize the job's task
        new_task_cls = CART_TASK_REGISTRY.get(job_profile.task, None)
        if new_task_cls is None:
            raise ValueError(
                f"Could not load job '{job_profile.name}', "
                f"no task of name '{job_profile.task}' has been registered."
            )
        duf = new_task_cls.getDataUnitFactory()

        # Initialize a new data manager
        data_manager = DataManager(
            cohort_file=job_profile.cohort_path,
            data_source=job_profile.data_path,
            data_unit_factory=duf,
            # TODO: Allow user configuration of this
            cache_size=2,
        )

        # Initialize the new task
        new_task = new_task_cls(
            self.master_profile_config, job_profile, data_manager.feature_labels
        )

        # Unload the previous task
        # TODO

        if self.master_profile_config.load_previous_outputs:
            # If the user has requested we load previous outputs, pass
            # the task to the data manager so it can "seek" them.
            data_manager.reference_task = new_task

        # Install the new task and give it its first data unit!
        self._data_manager = data_manager
        self._task_instance = new_task

        # Pass the appropriate case to the task, skipping to the first "incomplete" if requested
        if self.master_profile_config.skip_to_first_incomplete:
            try:
                unit = self.data_manager.first_incomplete(self._task_instance)
            except Exception as e:
                logging.error(
                    "Failed loading first incomplete case, loading first available case instead.",
                    exc_info=e
                )
                unit = self.data_manager.first()
        else:
            unit = self.data_manager.first()
        self._task_instance.receive(unit)

        # Initialize the new task
        self.active_job_config = job_profile

        # Update the config to use this as our last job
        self.master_profile_config.set_last_job(job_name)
        self.master_profile_config.save()

        # Emit our job changed + a syncing case changed signal
        self.jobChanged()
        self.caseChanged(-1, self.data_manager.current_case_index)

    def register_job_config(self, job_config: JobProfileConfig):
        self.master_profile_config.register_new_job(job_config)
        self.master_profile_config.save()
        # Emit the appropriate signal
        self.jobListChanged()

    def has_run_before(self):
        # Just checks if we've defined an author before or not
        return self.author is not None

    ## Task Management ##
    def load_registered_tasks(self):
        """
        Attempt to load all registered tasks for reference throughout the program
        """
        registered_tasks = self.master_profile_config.registered_task_paths
        # If there are no registered tasks, rebuild the registry from scratch
        if registered_tasks is None:
            self.logger.warning(
                f"No registered task entry found in config file! "
                f"Resetting the config to use only example tasks."
            )
            self.reset_task_registry()
            return
        # Otherwise, load each of our registered tasks
        else:
            # Load all task paths
            for p in set(registered_tasks.values()):
                # Skip the "None" case for now
                if p is None:
                    continue
                # Load the task
                new_tasks = self.load_tasks_from_file(p)
                # Filter out tasks which were loaded, but not registered
                for k in [x for x in new_tasks if x not in registered_tasks.keys()]:
                    CART_TASK_REGISTRY.pop(k)
                    self.logger.warning(
                        f"Task '{k}' was loaded alongside another task, "
                        f"but has not been registered and was filtered out."
                    )
            # Mark tasks which have an invalid associated file in the registry!
            for task_key in [k for k, p in registered_tasks.items() if p is None]:
                self.logger.warning(
                    f"The file for task '{task_key}' was unavailable, and therefore could not "
                    f"be loaded into CART. Check that drive with the file is mounted, and "
                    f"that the file on the drive is accessible to a Python program."
                )
                CART_TASK_REGISTRY[task_key] = None

    def load_tasks_from_file(self, task_path):
        # Confirm the path exists and can be read as a (python) file
        if not task_path.exists():
            raise ValueError(f"File '{task_path}' does not exist; cannot load task!")
        elif not task_path.is_file():
            raise ValueError(
                f"Path '{task_path}' is not a file; cannot load directories!"
            )
        elif ".py" not in task_path.suffixes:
            self.logger.warning(
                f"Registered task file '{task_path}' was not a Python file; "
                f"will attempt to load it anyways!"
            )

        # Track the list of tasks already registered for later
        prior_tasks = set(CART_TASK_REGISTRY.keys())

        # Add the parent of the path to our Python path
        module_path = str(task_path.parent.resolve())
        sys.path.append(module_path)
        module_name = task_path.name.split(".")[0]

        try:
            # Try to load the module in question
            spec = importlib.util.spec_from_file_location(module_name, task_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            # If something went wrong, roll back our changes to `sys.path`
            sys.path.remove(module_path)
            raise e

        # Get the list of tasks that were registered by the decorator
        new_tasks = set(CART_TASK_REGISTRY.keys()) - prior_tasks

        # If no new tasks were registered, roll back the changes and raise an error
        if len(new_tasks) < 1:
            sys.path.remove(module_path)
            raise ValueError(
                f"No tasks were registered when importing the file '{task_path}'; "
                f"Rolling everything back!"
            )
        # Otherwise, keep the module loaded!
        sys.modules[module_name] = module

        # Return the list of (now-loaded) tasks!
        return new_tasks

    def register_new_task(self, task_path: Path):
        # Load the task(s) within the task file
        new_tasks = self.load_tasks_from_file(task_path)

        # Keep track of the task(s) in our configuration file
        for k in new_tasks:
            self.master_profile_config.add_task_path(k, task_path)

        # Save the configuration immediately
        self.master_profile_config.save()
        return new_tasks

    def reset_task_registry(self):
        # Try to load all the example tasks
        examples_path = CART_PATH / "CARTLib/examples"
        example_task_paths = [
            examples_path / "Segmentation/SegmentationTask.py",
            examples_path / "GenericClassification/GenericClassificationTask.py",
            examples_path / "Markup/Markup.py",
        ]

        # Make sure the example tasks all exist before doing anything!
        missing_paths = []
        for p in example_task_paths:
            if not p.exists():
                missing_paths.append(p)

        if len(missing_paths) > 0:
            err_msg = (
                "CART seems to have been corrupted; was missing the following paths!\n"
            )
            err_msg += f"\n  * ".join([str(p) for p in missing_paths])
            raise ValueError(err_msg)

        # Completely reset our task registry and configuration
        self.master_profile_config.clear_task_paths()
        CART_TASK_REGISTRY.clear()

        # Register each example task again, one-by-one
        for p in example_task_paths:
            self.register_new_task(p)

        # Save the config immediately to preserve the changes
        self.master_profile_config.save()

    def init_task_gui(self, containerWidget: qt.QWidget):
        # Return early (with a message) if there's no task to use
        if self._task_instance is None:
            self.logger.warning(
                f"Tried to initialize a task's GUI before the task was created!"
            )
            return

        # Initialize the task's GUI itself
        self._task_instance.setup(containerWidget)

    ## Case Management ##
    def is_case_completed(self, idx: int) -> bool:
        # Confirm we're in a valid state first; if not, the case is not complete
        if self.data_manager is None or self._task_instance is None:
            self.logger.warning("Could not check for case completion, CART has not initialized!")
            return False
        # Check if the selected case is completed or not
        case = self.data_manager.case_data[idx]
        return self._task_instance.isTaskComplete(case)

    def has_next_case(self):
        if self._data_manager is None:
            return False
        return self._data_manager.has_next_case()

    def next_case(self, should_autosave=True) -> bool:
        # If we're in an invalid state, return False
        if not (
            self._data_manager
            and self.has_next_case()
            and self._task_instance
        ):
            return False
        # Tell the task to save its current unit, if autosaving is enabled
        if should_autosave:
            self._autosave_case()
        # Iterate to the next data unit and proceed
        old_idx = self._data_manager.current_case_index
        try:
            new_unit = self._data_manager.next()
            # If there wasn't one, the index was invalid (should never happen).
            if new_unit is None:
                raise ValueError("Manager could not iterate to desired unit.")
            self._task_instance.receive(new_unit)
            self.caseChanged(old_idx, self._data_manager.current_case_index)
        except Exception as e:
            # Roll back to the previous case if the task failed to receive the new unit
            self.select_case(old_idx)
            raise e
        return True

    def next_incomplete_case(self):
        # If we're in an invalid state, return False
        if not (
            self._data_manager
            and self._data_manager.has_next_case()
            and self._task_instance
        ):
            return
        # Tell the task to save its current unit
        self._autosave_case()
        # Iterate to the next incomplete data unit and proceed
        old_idx = self._data_manager.current_case_index
        try:
            new_unit = self._data_manager.next_incomplete(self._task_instance)
            # If there wasn't one, the index was invalid (should never happen).
            if new_unit is None:
                raise ValueError("Manager could not iterate to desired unit.")
            self._task_instance.receive(new_unit)
            self.caseChanged(old_idx, self._data_manager.current_case_index)
        except Exception as e:
            # Roll back to the previous case if the task failed to receive the new unit
            self.select_case(old_idx)
            raise e

    def has_previous_case(self):
        if self._data_manager is None:
            return False
        return self._data_manager.has_previous_case()

    def previous_case(self) -> bool:
        # If we're in an invalid state, return False
        if not (
            self._data_manager
            and self.has_previous_case()
            and self._task_instance
        ):
            return False
        # Tell the task to save its current unit
        self._autosave_case()
        # Iterate to the previous data unit and proceed
        old_idx = self._data_manager.current_case_index
        try:
            new_unit = self._data_manager.previous()
            # If there wasn't one, the index was invalid (should never happen).
            if new_unit is None:
                raise ValueError("Manager could not iterate to desired unit.")
            self._task_instance.receive(new_unit)
            self.caseChanged(old_idx, self._data_manager.current_case_index)
        except Exception as e:
            # Roll back to the previous case if the task failed to receive the new unit
            self.select_case(old_idx)
            raise e
        return True

    def previous_incomplete_case(self) -> bool:
        # If we're in an invalid state, return False
        if not (
            self._data_manager
            and self.has_previous_case()
            and self._task_instance
        ):
            return False
        # Tell the task to save its current unit
        self._autosave_case()
        # Iterate to the previous data unit and proceed
        old_idx = self._data_manager.current_case_index
        try:
            new_unit = self._data_manager.previous_incomplete(self._task_instance)
            # If there wasn't one, the index was invalid (should never happen).
            if new_unit is None:
                raise ValueError("Manager could not iterate to desired unit.")
            self._task_instance.receive(new_unit)
            self.caseChanged(old_idx, self._data_manager.current_case_index)
        except Exception as e:
            # Roll back to the previous case if the task failed to receive the new unit
            self.select_case(old_idx)
            raise e
        return True

    def select_case(self, idx: int):
        # If we aren't in a state to swap cases, raise an error
        if self._data_manager is None:
            raise ValueError("CART cannot change cases; we do not have a data manager yet!")
        if self._task_instance is None:
            raise ValueError("CART cannot change cases; there is no task to receive the new one!")
        # Auto-save the case, if the user has configured it
        self._autosave_case()
        # Swap to the new unit
        prior_idx = self._data_manager.current_case_index
        new_unit = self._data_manager.select_unit_at(idx)
        # If there wasn't one, the given index was invalid.
        if new_unit is None:
            raise ValueError("Manager could not iterate to desired unit.")
        self._task_instance.receive(new_unit)
        self.caseChanged(prior_idx, idx)

    def _autosave_case(self):
        # Just checks the profile's configuration option before proceeding
        if self.master_profile_config.autosave_on_switch:
            self.save_case()

    def save_case(self):
        try:
            # If we don't have what we need to save, raise an error
            if self._task_instance is None:
                raise ValueError("CART could not save; no task has been initialized!")
            if self._data_manager is None:
                raise ValueError(
                    "CART could not save; the data manager has not been initialized!"
                )
            self._task_instance.save()
        finally:
            # Always emit a signal so any GUIs can sync properly
            self.caseSaved(self.data_manager.current_case_index)

    def save_case_and_iterate(self):
        self.save_case()
        # Don't try and save the case again
        self.next_case(should_autosave=False)

    ## Config Management ##
    def save_master_config(self):
        self.master_profile_config.save()

    def reload_master_config(self):
        # Pull the data from the config file
        self.master_profile_config.reload()
        # If the config version doesn't match the current CART version, warn the user
        current_cart_version = get_cart_version()
        config_cart_version = self.master_profile_config.version
        if config_cart_version != current_cart_version:
            # Warn the user the versions are being updated.
            # TODO: Prompt the user directly!
            logging.warning(
                f"Current CART version ({current_cart_version}) is not the same that was used to "
                f"generate the user profile ({config_cart_version}). This may result in unexpected "
                f"behaviour!"
            )
            # Update the config to use the new version
            self.master_profile_config.version = current_cart_version

    ## GUI Management ##
    def enter(self):
        """
        Called when the CART module is loaded (through our CARTWidget).

        Just signals to the current task that CART is now in view again, and it
        should synchronize its state to the MRML scene. This can include:
          * Installing any shortcuts
          * Restoring any active processes
          * Re-synchronizing with the MRML scene
        """
        if self._task_instance:
            self._task_instance.enter()

    def exit(self):
        """
        Called when the CART module is un-loaded (through our CARTWidget).

        Just signals to the current task that CART is no longer in view, and it
        should pause any active processes in the GUI. This can include:
          * Uninstalling any shortcuts
          * Pausing/killing any active processes
        """
        if self._task_instance:
            self._task_instance.exit()
