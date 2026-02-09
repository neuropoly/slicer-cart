import importlib
import logging
import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Tuple, Callable

import vtk

import qt
import slicer.util
from CARTLib.core.LayoutManagement import OrientationButtonArrayWidget
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

from CARTLib.core.DataManager import DataManager
from CARTLib.core.TaskBaseClass import TaskBaseClass
from CARTLib.core.SetupWizard import CARTSetupWizard, JobSetupWizard
from CARTLib.utils import CART_PATH, CART_VERSION
from CARTLib.utils.config import JobProfileConfig, MasterProfileConfig
from CARTLib.utils.task import CART_TASK_REGISTRY

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
        self.parent.helpText = _(
            """
                CART (Case Annotation and Review Tool) provides a set
                of abstract base classes for creating streamlined annotation
                workflows in 3D Slicer. The framework enables efficient
                iteration through medical imaging cohorts with customizable
                tasks and flexible data loading strategies.

                See more information on the
                <a href="https://github.com/SomeoneInParticular/CART/tree/main">GitHub repository</a>.
            """
        )
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _(
            """
                Originally created during Slicer Project Week #43.

                Special thanks the many members of the Slicer community who
                contributed to this work, including the many projects which
                were used as reference. Of note:
                <a href="https://github.com/neuropoly/slicercart">SlicerCART</a> (the name and general framework),
                <a href="https://github.com/JoostJM/SlicerCaseIterator">SlicerCaseIterator</a> (inspired much of our logic),
                <a href="https://github.com/SlicerUltrasound/SlicerUltrasound">SlicerUltrasound/AnnotateUltrasound</a> (basis for our UI design),
                and the many other projects discussed during the breakout session (notes
                <a href="https://docs.google.com/document/d/12XuYPVuRgy4RTuIabSIjy_sRrYSliewKhcbB1zJgXVI/">here.</a>)
            """
        )

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

        # Widget which holds the task-specific GUI elements
        self.taskSubWidget: qt.QWidget = None

        # List of things to do when the list of registered jobs changes
        # TODO: Make this a proper QT signal, or something similar
        self.onJobListChanged: list[Callable[[], None]] = list()

        # List of things to do when the job is changed
        # TODO: Make this a proper QT signal, or something similar
        self.onJobChanged: list[Callable[[str], None]] = list()

        # List of things to do when the case is changed
        # TODO: Make this a proper QT signal, or something similar
        self.onCaseChanged: list[Callable[[int], None]] = list()

        # List of keyboard shortcuts to be installed/uninstalled within this widget
        self.keyboardShortcuts = []

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

        # Button panel for creating, editing, or deleting jobs
        jobManagementPanel = self._jobManagementPanel()
        layout.addWidget(jobManagementPanel)

        # Add a stretch to push everything to the top
        layout.addStretch()

        return mainWidget

    def _jobManagementPanel(self) -> qt.QWidget:
        # Setup
        mainWidget = qt.QWidget(None)
        layout = qt.QVBoxLayout(mainWidget)

        # Job selection dropdown
        jobSelectorComboBoxLabel = qt.QLabel(_("Please Select or Create a Job:"))
        jobSelectorComboBox = qt.QComboBox(None)
        def updateJobSelector():
            jobSelectorComboBox.clear()
            jobSelectorComboBox.addItems(self.logic.registered_jobs_names)
            if len(self.logic.registered_jobs_names) > 0:
                jobSelectorComboBox.setEnabled(True)
                jobSelectorComboBox.setCurrentIndex(0)
            else:
                jobSelectorComboBox.setEnabled(False)
        self.onJobListChanged.append(updateJobSelector)

        layout.addWidget(jobSelectorComboBoxLabel)
        layout.addWidget(jobSelectorComboBox)

        # Button panel for Job editing operations
        buttonPanel = qt.QWidget(None)
        buttonPanelLayout = qt.QHBoxLayout(buttonPanel)
        layout.addWidget(buttonPanel)

        # "New" button
        newButton = qt.QPushButton(_("New"))
        newButton.setToolTip(_("Create a new Job"))
        def newButtonClicked():
            # Ask the user to run initial setup
            if not self.logic.has_run_before():
                # If they don't, end here
                if self._cartNotRunBeforePrompt() != qt.QMessageBox.Yes:
                    return
                self.runInitialSetup()
            # Otherwise, skip to job creation
            else:
                self.runNewJobSetup()

        newButton.clicked.connect(newButtonClicked)
        buttonPanelLayout.addWidget(newButton)

        # "Edit" button
        editButton = qt.QPushButton(_("Edit"))
        editButton.setToolTip(_("Edit the Job's configuration"))
        def onJobEdit():
            currentJob: str = jobSelectorComboBox.currentText
            jobPath = self.logic.registered_jobs.get(currentJob, None)
            # If the specified job's config is missing, ask if they want to re-create it!
            if jobPath is None:
                # If they don't, end here
                if self._jobMissingPrompt() != qt.QMessageBox.Yes:
                    return
                # Create a new config w/ the same name
                jobConfig = JobProfileConfig()
                jobConfig.name = currentJob
            # Otherwise, load the previous job's configuration
            else:
                jobConfig = JobProfileConfig(file_path=Path(jobPath))
                jobConfig.reload()
            # Have the user edit the job
            self.runJobEdit(jobConfig)
        editButton.clicked.connect(onJobEdit)
        buttonPanelLayout.addWidget(editButton)
        self.onJobListChanged.append(
            lambda: editButton.setEnabled(jobSelectorComboBox.isEnabled())
        )

        # "Delete" button
        deleteButton = qt.QPushButton(_("Delete"))
        deleteButton.setToolTip(_("Delete the Job configuration"))
        def onJobDelete():
            self.logic.delete_job_config(jobSelectorComboBox.currentText)
            self.jobListChanged()
        deleteButton.clicked.connect(onJobDelete)
        buttonPanelLayout.addWidget(deleteButton)
        self.onJobListChanged.append(
            lambda: deleteButton.setEnabled(jobSelectorComboBox.isEnabled())
        )

        # Start button; initializes the job, or walks the user through job setup if there isn't one
        startButton = qt.QPushButton("Start")
        startButton.setToolTip(_("Start CART!"))
        def onStartClicked():
            if jobSelectorComboBox.isEnabled():
                self.start(jobSelectorComboBox.currentText)
            else:
                self.start()
        startButton.clicked.connect(onStartClicked)
        layout.addWidget(startButton)

        # "Emit" our signal to sync everything up
        self.jobListChanged()

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
        # Setup
        buttonPanel = qt.QWidget(None)
        layout = qt.QHBoxLayout(buttonPanel)

        # Define each of the buttons
        previousIncompleteButton = qt.QToolButton(None)
        previousIncompleteButton.setText("<<")
        previousIncompleteButton.setToolTip(_("Jump to the Previous Incomplete Case"))
        previousIncompleteButton.clicked.connect(self.previousIncompleteCasePressed)
        self.onCaseChanged.append(
            lambda __: previousIncompleteButton.setEnabled(self.logic.has_previous_case())
        )

        previousButton = qt.QToolButton(None)
        previousButton.setText("<")
        previousButton.setToolTip(_("Switch to the Previous Case"))
        previousButton.clicked.connect(self.previousCasePressed)
        self.onCaseChanged.append(
            lambda __: previousButton.setEnabled(self.logic.has_previous_case())
        )

        nextButton = qt.QToolButton(None)
        nextButton.setText(">")
        nextButton.setToolTip(_("Switch to the Next Case"))
        nextButton.clicked.connect(self.nextCasePressed)
        self.onCaseChanged.append(
            lambda __: nextButton.setEnabled(self.logic.has_next_case())
        )

        nextIncompleteButton = qt.QToolButton(None)
        nextIncompleteButton.setText(">>")
        nextIncompleteButton.setToolTip(_("Jump to the Next Incomplete Case"))
        nextIncompleteButton.clicked.connect(self.nextIncompleteCasePressed)
        self.onCaseChanged.append(
            lambda __: nextIncompleteButton.setEnabled(self.logic.has_next_case())
        )

        # Define a selector/viewer for the current case
        caseSelector = qt.QComboBox(None)
        def updateCaseOptions(__):
            caseSelector.blockSignals(True)
            caseSelector.clear()
            caseSelector.addItems(self.logic.data_manager.valid_uids)
            caseSelector.blockSignals(False)
        self.onJobChanged.append(updateCaseOptions)
        def syncCaseSelector(idx: int):
            caseSelector.blockSignals(True)
            caseSelector.setCurrentIndex(idx)
            caseSelector.blockSignals(False)
        self.onCaseChanged.append(syncCaseSelector)
        caseSelector.currentIndexChanged.connect(self.selectCaseAt)

        # Add them each to the panel
        layout.addWidget(previousIncompleteButton, 1)
        layout.addWidget(previousButton, 1)
        layout.addWidget(caseSelector, 10)
        layout.addWidget(nextButton, 1)
        layout.addWidget(nextIncompleteButton, 1)

        # Return the result
        return buttonPanel

    def _savePanel(self) -> qt.QWidget:
        buttonPanel = qt.QWidget(None)
        buttonPanelLayout = qt.QHBoxLayout(buttonPanel)

        saveButton = qt.QPushButton(_("Save"))
        saveButton.clicked.connect(self.logic.save_case)

        buttonPanelLayout.addStretch(1)
        buttonPanelLayout.addWidget(saveButton, 10)
        buttonPanelLayout.addStretch(1)

        return buttonPanel

    def _layoutPanel(self):
        layoutPanel = OrientationButtonArrayWidget()
        def onNewCase(__: int):
            new_unit = self.logic.data_manager.select_current_unit()
            layoutPanel.changeLayoutHandler(new_unit.layout_handler, True)
        self.onCaseChanged.append(onNewCase)
        return layoutPanel

    ## Connections ##
    def start(self, job_name=None):
        # If this is the first time CART has been run, ask to initialize firest
        if not self.logic.has_run_before():
            if self._cartNotRunBeforePrompt() != qt.QMessageBox.Yes:
                return
            if not self.runInitialSetup():
                return
        # If no job was specified, ask if they want to create one.
        if job_name is None:
            if self._createFirstJobPrompt() != qt.QMessageBox.Yes:
                return
            job_name = self.runNewJobSetup()
            if job_name is None:
                return
        # or, if the job is corrupted (somehow), ask to re-build it
        elif self.logic.registered_jobs[job_name] is None:
            if self._jobMissingPrompt() != qt.QMessageBox.Yes:
                return
            config = JobProfileConfig()
            config.name = job_name
            job_name = self.runJobEdit(config)
            if not job_name:
                return
            job_name = config.name
        # Finally, initialize the job
        self.initJob(job_name)

    def nextCasePressed(self):
        # Request the logic switch to the next case
        self.logic.next_case()

        # Emit our case-changed signal
        self.caseChanged()

    def nextIncompleteCasePressed(self):
        # Request the logic switch to the next case
        self.logic.next_incomplete_case()

        # Emit our case-changed signal
        self.caseChanged()

    def previousCasePressed(self):
        # Request the logic switch to the next case
        self.logic.previous_case()

        # Emit our case-changed signal
        self.caseChanged()

    def previousIncompleteCasePressed(self):
        # Request the logic switch to the next case
        self.logic.previous_incomplete_case()

        # Emit our case-changed signal
        self.caseChanged()

    def selectCaseAt(self, idx):
        # Request the logic switch to the next case
        self.logic.select_case(idx)

        # Emit our case-changed signal
        self.caseChanged()

    def caseChanged(self):
        # Scuffed, but this doesn't crash at least!
        case_idx = self.logic.data_manager.current_case_index
        for f in self.onCaseChanged:
            f(case_idx)

        # Always refresh the layout afterward
        self.logic.refresh_layout()

    ## User Prompts ##
    @staticmethod
    def _cartNotRunBeforePrompt():
        return qt.QMessageBox.question(
            None,
            _("Initialize CART?"),
            _("CART has not been run before. Would you like to run setup now?"),
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
    def _jobMissingPrompt():
        return qt.QMessageBox.question(
            None,
            _("Job Cannot be Found"),
            _(
                "It seems the requested job's configuration was deleted or is unavailable; "
                "would you like to create a new job instead?"
            ),
            qt.QMessageBox.Yes | qt.QMessageBox.No,
            qt.QMessageBox.Yes,
        )

    ## Setup Workflows ##
    def runInitialSetup(self) -> bool:
        """
        Run initial CART setup, prompting the user for their name and role.

        :return: If the setup was successful or not.
        """
        initSetupWizard = CARTSetupWizard(None)
        result = initSetupWizard.exec()

        # If we got an "accept" signal, update our logic and begin job setup
        if result == qt.QDialog.Accepted:
            initSetupWizard.update_logic(self.logic)
            return True
        return False

    def runNewJobSetup(self) -> Optional[str]:
        """
        Run CART job creation, prompting the user to provide the following:
            * The data they want to use, and where to save the results
            * The task they want to run
            * How they want to iterate through the data (the "cohort")

        :return: The name of the new job; None if the setup was terminated
        """

        jobSetupWizard = JobSetupWizard(None, taken_names=self.logic.registered_jobs.keys())
        result = jobSetupWizard.exec()

        # If we got an "accept" signal, create the job config and initialize it
        if result == qt.QDialog.Accepted:
            new_config = jobSetupWizard.save_config(self.logic)
            self.jobListChanged()
            return new_config.name
        return None

    def runJobEdit(self, config: JobProfileConfig = None) -> bool:
        """
        Edits an existing job in-place. Re-uses the job creation wizard,
        skipping the introduction page and filling every field with
        the previous job's values (if present).

        :return: If the edit was successful or not.
        """

        jobSetupWizard = JobSetupWizard(
            None, taken_names=self.logic.registered_jobs.keys(), config=config
        )
        result = jobSetupWizard.exec()

        # If we got an "accept" signal, create the job config and exit
        if result == qt.QDialog.Accepted:
            new_config = jobSetupWizard.save_config(self.logic)
            self.jobListChanged()
            return True
        return False

    ## Job Management ##
    def initJob(self, job_name: str):
        # Initialize the job on the logic-side first
        self.logic.set_active_job(job_name)

        # Update the GUI to match
        self.logic.init_task_gui(self.taskSubWidget)

        # Expand the task widget's container, if any
        self.mainWidget.setCurrentIndex(self.jobWidgetIndex)

        # "Emit" the job-changed signal
        self.jobChanged()

        # "Emit" the case-changed signal
        self.caseChanged()

    def jobListChanged(self):
        # QT!!!!!!!!!!!!!!!
        for f in self.onJobListChanged:
            f()

    def jobChanged(self):
        # I love QT signals not working!
        job_name = self.logic.active_job_config.name
        for f in self.onJobChanged:
            f(job_name)

    ## Keyboard Shortcuts ##
    def installKeyboardShortcuts(self):
        # Next/Previous Case
        nextShortcut = qt.QShortcut(slicer.util.mainWindow())
        nextShortcut.setKey(qt.QKeySequence(qt.QKeySequence.MoveToNextPage))
        nextShortcut.activated.connect(
            self.nextCasePressed
        )
        self.keyboardShortcuts.append(nextShortcut)

        previousShortcut = qt.QShortcut(slicer.util.mainWindow())
        previousShortcut.setKey(qt.QKeySequence(qt.QKeySequence.MoveToPreviousPage))
        previousShortcut.activated.connect(
            self.previousCasePressed
        )

    def uninstallKeyboardShortcuts(self):
        for kbs in self.keyboardShortcuts:
            kbs.activated.disconnect()
            kbs.setParent(None)
        self.keyboardShortcuts = []

    ## View Management ##
    def cleanup(self) -> None:
        """
        Called when the application closes and this widget is about to be destroyed.
        """
        pass

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
class CARTLogic(ScriptedLoadableModuleLogic):
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

    def set_active_job(self, job_name: str):
        """
        Loads the specified job, based on its associated config
        """
        # Confirm the requested job is registered
        if not job_name in self.registered_jobs.keys():
            raise ValueError(f"Cannot set job '{job_name}' as active; it has not been registered!")

        # Confirm the job config file exist
        job_file = Path(self.registered_jobs.get(job_name))
        if not job_file.exists() or not job_file.is_file():
            raise ValueError(f"Cannot set job '{job_name}' as active; its corresponding config file does not exist!")

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
        # TODO: Allow user selection of this instead
        duf = list(new_task_cls.getDataUnitFactories().values())[0]

        # Initialize the data loader using the job's settings
        data_manager = DataManager(
            cohort_file=job_profile.cohort_path,
            data_source=job_profile.data_path,
            data_unit_factory=duf,
            # TODO: Allow user configuration of this
            cache_size=2
        )

        # Initialize the new task
        new_task = new_task_cls(self.master_profile_config, job_profile)

        # Unload the previous task
        # TODO

        # Install the new task and give it its first data unit!
        self._data_manager = data_manager
        self._task_instance = new_task
        self._task_instance.receive(self._data_manager.current_data_unit())

        # Initialize the new task
        self.active_job_config = job_profile

        # Update the config to use this as our last job
        self.master_profile_config.set_last_job(job_name)
        self.master_profile_config.save()

    def register_job_config(self, job_config: JobProfileConfig):
        self.master_profile_config.register_new_job(job_config)
        self.master_profile_config.save()

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
            raise ValueError(f"Path '{task_path}' is not a file; cannot load directories!")
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
        module_name = task_path.name.split('.')[0]

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
            raise ValueError(f"No tasks were registered when importing the file '{task_path}'; "
                             f"Rolling everything back!")
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
            examples_path / "SegmentationReview/SegmentationReviewTask.py",
            examples_path / "GenericClassification/GenericClassificationTask.py",
            examples_path / "RapidMarkup/RapidMarkupTask.py"
        ]

        # Make sure the example tasks all exist before doing anything!
        missing_paths = []
        for p in example_task_paths:
            if not p.exists():
                missing_paths.append(p)

        if len(missing_paths) > 0:
            err_msg = "CART seems to have been corrupted; was missing the following paths!\n"
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
    def has_next_case(self):
        if self._data_manager is None:
            return False
        return self._data_manager.has_next_case()

    def next_case(self):
        if self._data_manager and self._data_manager.has_next_case():
            # If this was somehow done without an active task, return
            if self._task_instance is None:
                return
            # Iterate to the next data unit and update everything
            # TODO: Restore configuration option for this
            self._task_instance.save()
            new_unit = self._data_manager.next()
            self._task_instance.receive(new_unit)

    def next_incomplete_case(self):
        if self._data_manager and self._data_manager.has_next_case():
            # If this was somehow done without an active task, return
            if self._task_instance is None:
                return
            # Iterate to the next incomplete data unit and update everything
            # TODO: Restore configuration option for this
            self._task_instance.save()
            new_unit = self._data_manager.next_incomplete(self._task_instance)
            self._task_instance.receive(new_unit)

    def has_previous_case(self):
        if self._data_manager is None:
            return False
        return self._data_manager.has_previous_case()

    def previous_case(self):
        if self._data_manager and self._data_manager.has_previous_case():
            # If this was somehow done without an active task, return
            if self._task_instance is None:
                return
            # Iterate to the prior data unit and update everything
            # TODO: Restore configuration option for this
            self._task_instance.save()
            new_unit = self._data_manager.previous()
            self._task_instance.receive(new_unit)

    def previous_incomplete_case(self):
        if self._data_manager and self._data_manager.has_previous_case():
            # If this was somehow done without an active task, return
            if self._task_instance is None:
                return
            # Iterate to the prior incomplete data unit and update everything
            # TODO: Restore configuration option for this
            self._task_instance.save()
            new_unit = self._data_manager.previous_incomplete(self._task_instance)
            self._task_instance.receive(new_unit)

    def select_case(self, idx: int):
        if self._data_manager and self._task_instance:
            # TODO: Restore configuration option for this
            self._task_instance.save()
            new_unit = self._data_manager.select_unit_at(idx)
            self._task_instance.receive(new_unit)

    def save_case(self):
        if self._data_manager and self._task_instance:
            self._task_instance.save()

    def refresh_layout(self):
        if self._data_manager is None:
            self.logger.warning(
                f"No data manager current exists, cannot apply a data unit layout!"
            )
            return

        # Apply the layout of the current data unit
        self._data_manager.current_data_unit().layout_handler.apply_layout()

    ## Config Management ##
    def save_master_config(self):
        self.master_profile_config.save()

    def reload_master_config(self):
        # Pull the data from the config file
        self.master_profile_config.reload()
        # If the config version doesn't match the current CART version, warn the user
        if self.master_profile_config.version != CART_VERSION:
            # TODO: Prompt the user directly!
            print("WARNING: Current CART version does not match that of the master profile! "
                  "CART may not work as expected!")
            self.master_profile_config.version = CART_VERSION

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
