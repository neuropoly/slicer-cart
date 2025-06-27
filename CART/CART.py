from pathlib import Path
from textwrap import dedent

import vtk

import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.util import VTKObservationMixin

import json

from CARTLib.DataManager import DataManager
from CARTLib.TaskBaseClass import TaskBaseClass

# TODO: Remove this explicit import
from CARTLib.OrganLabellingDemo import OrganLabellingDemoTask

CURRENT_DIR = Path(__file__).parent
CONFIGURATION_FILE_NAME = CURRENT_DIR / "configuration.json"
this_file_path = Path(__file__).parent
sample_data_path = this_file_path.parent / "sample_data"
sample_data_cohort_csv = sample_data_path / "example_cohort.csv"


#
# CART
#


class CART(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("CART")  # TODO: make this more human readable by adding spaces
        # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Examples")]
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["John Doe (AnyWare Corp.)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        # _() function marks text as translatable to other languages
        self.parent.helpText = _("""
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https://github.com/organization/projectname#CART">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

        # Additional initialization step after application startup is complete




#
# CARTParameterNode
#



#
# CARTWidget
#


class CARTWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    ## Initialization ##

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

        with open(CONFIGURATION_FILE_NAME, "r") as cf:
          self.configuration_data = json.load(cf)
        cf.close()

        self.cohort_csv_path = None
        self.current_case = None
        self.DataManagerInstance = DataManager()
        self.base_path = None  # Base path for relative paths in CSV

        # TODO: Dynamically load this dictionary instead
        self.task_map = {
            "Organ Labels": OrganLabellingDemoTask,
            "N/A": None  # Placeholder for testing
        }
        self.current_task: type(TaskBaseClass) = None
        self.current_task_instance: TaskBaseClass = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Set up the over-arching collapsible container to hold our GUIs in
        mainGUI = ctk.ctkCollapsibleButton()
        # Not the best translation, but it'll do...
        mainGUI.text = "CART" + _("Setup")
        mainLayout = qt.QFormLayout(mainGUI)

        # Base Path input UI
        self.basePathUIWidget = self.buildBasePathUI()
        mainLayout.addWidget(self.basePathUIWidget)

        # Cohort UI
        self.cohortUIWidget = self.buildCohortUI()
        mainLayout.addWidget(self.cohortUIWidget)

        # User UI
        self.userUIWidget = self.buildUserUI()
        # self.userUIWidget.setMRMLScene(slicer.mrmlScene)
        mainLayout.addWidget(self.userUIWidget)

        # Task UI
        self.taskUIWidget = self.buildTaskUI()
        mainLayout.addWidget(self.taskUIWidget)

        # Add this "main" widget to our panel
        self.layout.addWidget(mainGUI)

        # Case Iterator UI
        self.caseIteratorUI = self.buildCaseIteratorUI()

        # Make the GUI accessible
        self.mainGUI = mainGUI

        # Add the case iterator as a "buffer" between our main and task GUIs
        self.layout.addWidget(self.caseIteratorUI)

        # Add a (currently empty) collapsable tab, in which the Task GUI will be placed later
        taskGUI = ctk.ctkCollapsibleButton()

        # As its empty, and meaningless to the user, start it out collapsed
        #  and disabled; it will be re-enabled (and expanded) when a task
        #  is selected and the iterator set up.
        # KO: While the header for the associated CTK class has a `setCollapsed`
        #  function to match the pattern of every other attribute, it doesn't
        #  work for some reason, hence use breaking the pattern here.
        taskGUI.collapsed = True
        taskGUI.setEnabled(False)

        # Not the best translation, but it'll do...
        taskGUI.text = _("Task Steps")

        self.layout.addWidget(taskGUI)
        self.taskGUI = taskGUI

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CARTLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    ## GUI builders ##

    def buildBasePathUI(self):
        """
        Builds the GUI for the base path selection section of the Widget
        :return:
        """
        # Layout management
        basePathCollapsibleButton = ctk.ctkCollapsibleButton()
        basePathCollapsibleButton.text = _("Base Path Selection")
        formLayout = qt.QFormLayout(basePathCollapsibleButton)

        # Base path selection
        basePathSelectionWidget = ctk.ctkPathLineEdit()
        basePathSelectionWidget.filters = ctk.ctkPathLineEdit.Dirs
        basePathSelectionWidget.toolTip = _("Select the base directory path. Leave empty to use None as base path.")


        formLayout.addRow(_("Base Path:"), basePathSelectionWidget)

        # Connect the signal to handle base path changes
        basePathSelectionWidget.currentPathChanged.connect(self.onBasePathChanged)

        # Make it accessible
        self.basePathSelectionWidget = basePathSelectionWidget

        return basePathCollapsibleButton

    def buildUserUI(self):
        """
        Builds the GUI for the user management section of the Widget
        :return:
        """
        # Layout management
        userCollapsibleButton = ctk.ctkCollapsibleButton()
        userCollapsibleButton.text = _("User Selection")
        formLayout = qt.QFormLayout(userCollapsibleButton)

        # User entry
        newUserHBox = qt.QHBoxLayout()
        newUserTextWidget = qt.QLineEdit()
        newUserTextWidget.toolTip = _("Your name, or an equivalent identifier")
        newUserHBox.addWidget(newUserTextWidget)
        formLayout.addRow(_("New User:"), newUserHBox)

        # When the user confirms their entry (with enter), add it to the
        #  prior users list
        newUserTextWidget.returnPressed.connect(self.newUserEntered)

        # Make it accessible
        self.newUserTextWidget = newUserTextWidget

        # Prior users list
        priorUsersCollapsibleButton = qt.QComboBox()
        priorUsersCollapsibleButton.placeholderText = _("[Not Selected]")

        priorUsersCollapsibleButton.addItems(self.configuration_data["contributors"])
        formLayout.addRow(_("Prior User"), priorUsersCollapsibleButton)

        # When the user selects an existing entry, update the program to match
        priorUsersCollapsibleButton.currentIndexChanged.connect(self.userSelected)

        # Make it accessible
        self.priorUsersCollapsibleButton = priorUsersCollapsibleButton

        return userCollapsibleButton

    def buildCohortUI(self):
        # Layout management
        cohortCollapsibleButton = ctk.ctkCollapsibleButton()
        cohortCollapsibleButton.text = _("Cohort Selection")
        formLayout = qt.QFormLayout(cohortCollapsibleButton)

        # Directory selection button
        cohortFileSelectionButton = ctk.ctkPathLineEdit()
        # TODO Fix/ Ensure this works as expected
        # Set file filters to only show readable file types
        cohortFileSelectionButton.filters = ctk.ctkPathLineEdit.Files
        cohortFileSelectionButton.nameFilters = [
            "CSV files (*.csv)",
        ]

        # Optionally set a default filter
        # TODO

        formLayout.addRow(_("Cohort File:"), cohortFileSelectionButton)

        # Set default value but don't auto-load
        default_value = sample_data_cohort_csv.as_posix() if sample_data_cohort_csv.exists() else ""
        cohortFileSelectionButton.currentPath = default_value

        # Make the button easy-to-access
        self.cohortFileSelectionButton = cohortFileSelectionButton

        # Add explicit load button
        loadCohortButton = qt.QPushButton(_("Load Cohort"))
        loadCohortButton.toolTip = _("Load the selected cohort CSV file")
        loadCohortButton.clicked.connect(self.onLoadCohortClicked)
        formLayout.addRow("", loadCohortButton)

        # Make load button accessible
        self.loadCohortButton = loadCohortButton

        return cohortCollapsibleButton

    def buildTaskUI(self):
        # Layout management
        taskSelectionCollapsibleButton = ctk.ctkCollapsibleButton()
        taskSelectionCollapsibleButton.text = _("Task Selection")
        formLayout = qt.QFormLayout(taskSelectionCollapsibleButton)

        # Prior users list
        taskOptions = qt.QComboBox()
        taskOptions.placeholderText = _("[Not Selected]")

        # TODO: Have this pull from configuration instead
        taskOptions.addItems(list(self.task_map.keys()))
        formLayout.addRow(_("Task"), taskOptions)

        # Make it accessible
        self.taskOptions = taskOptions

        # When the task is changed, update everything to match
        taskOptions.currentIndexChanged.connect(self.onTaskChanged)

        return taskSelectionCollapsibleButton

    def buildCaseIteratorUI(self):
      # Layout
      self.groupBox = qt.QGroupBox("Iteration Manager")
      mainLayout = qt.QVBoxLayout(self.groupBox)

      # Hide this by default, only showing it when we're ready to iterate
      self.groupBox.setEnabled(False)

      # Next + previous buttons in a horizontal layout
      buttonLayout = qt.QHBoxLayout()
      previousButton = qt.QPushButton(_("Previous"))
      previousButton.toolTip = _("Return to the previous case.")

      nextButton = qt.QPushButton(_("Next"))
      nextButton.toolTip = _("Move onto the next case.")

      # Add them to the layout "backwards" so previous is on the left
      buttonLayout.addWidget(previousButton)
      buttonLayout.addWidget(nextButton)

      # Add the button layout to the main vertical layout
      mainLayout.addLayout(buttonLayout)

      # Add a text field to display the current case name under the buttons
      self.currentCaseNameLabel = qt.QLineEdit()
      self.currentCaseNameLabel.readOnly = True
      self.currentCaseNameLabel.placeholderText = _("Current case name will appear here")
      mainLayout.addWidget(self.currentCaseNameLabel)

      # Make the buttons easy-to-access
      self.nextButton = nextButton
      self.previousButton = previousButton

      # Connections
      nextButton.clicked.connect(self.nextCase)
      previousButton.clicked.connect(self.previousCase)

      return self.groupBox


    ## Connected Functions ##

    ### Setup Widgets ###

    def newUserEntered(self):
        # New user added
        new_user_name = self.newUserTextWidget.text
        if not new_user_name:
            return

        if new_user_name in self.configuration_data["contributors"]:
            print(f"User '{new_user_name}' already exists.")
            self.newUserTextWidget.text = ""
            return

        self.configuration_data["contributors"].append(new_user_name)
        with open(CONFIGURATION_FILE_NAME, "w") as cf:
            json.dump(self.configuration_data, cf, indent=2)
        print(f"NEW USER: {new_user_name}")

        self.newUserTextWidget.text = ""
        # Update the prior users dropdown
        self.priorUsersCollapsibleButton.addItem(new_user_name)

        # Try to load the task, if we're ready
        self.loadTaskWhenReady()

    def onBasePathChanged(self):
        """
        Handles changes to the base path selection.
        Sets self.base_path to None if empty, otherwise to the Path object.
        """
        current_path = self.basePathSelectionWidget.currentPath
        if current_path.strip():  # If not empty after stripping whitespace
            self.base_path = Path(current_path)
            print(f"Base path set to: {self.base_path}")
        else:
            self.base_path = None
            print("Base path set to: None")

    def getBasePath(self):
        """
        Returns the current base path (Path object or None)
        """
        # TODO Make this match the code style of the rest of the module better dont love this
        return self.base_path

    def userSelected(self):
        index = self.priorUsersCollapsibleButton.currentIndex
        text = self.priorUsersCollapsibleButton.currentText
        print(f"User selected: {text} ({index})")

        # Attempt to load the task, if we're now ready
        self.loadTaskWhenReady()

    def getCohortSelectedFile(self) -> Path:
        return Path(self.cohortFileSelectionButton.currentPath)

    def onCohortChanged(self):
        """
        Runs when a new cohort CSV is selected.
        """
        # Attempt to create a DataManager from the file
        self.cohort_csv_path = self.getCohortSelectedFile()
        self.DataManagerInstance.set_base_path(self.getBasePath())
        self.DataManagerInstance.load_data(self.cohort_csv_path)

        # Prepare the iterator for use
        self.DataManagerInstance.set_data_cohort_csv(self.cohort_csv_path)
        self.DataManagerInstance.load_data(self.cohort_csv_path)
        self.groupBox.setEnabled(True)
        # Show the first case immediately
        if self.DataManagerInstance.raw_data:
            self.current_case = self.DataManagerInstance.current_item().resources
            print(self.current_case)
            self.currentCaseNameLabel.text = str(self.current_case)

        # Attempt to load the task, if we're now ready
        self.loadTaskWhenReady()

    def onLoadCohortClicked(self):
        """
        Handles the explicit load cohort button click.
        """
        cohort_file = self.getCohortSelectedFile()

        if not cohort_file.exists():
            print(f"Error: Cohort file does not exist: {cohort_file}")
            return

        if cohort_file.suffix.lower() != ".csv":
            print(f"Error: Selected file is not a CSV: {cohort_file}")
            return

        print(f"Loading cohort from: {cohort_file}")
        self.onCohortChanged()

    def onTaskChanged(self):
        # Update the currently selected task
        task_name = self.taskOptions.currentText
        self.current_task = self.task_map.get(task_name, None)

        # Check if we're now ready to iterate
        self.loadTaskWhenReady()

    def isReady(self) -> bool:
        # List of things left for the user to do
        todo_list = []

        # Check if there is a valid user selected
        if self.priorUsersCollapsibleButton.currentIndex == -1:
            todo_list.append(
                _("You need to select who's doing this analysis.")
            )

        # Check if a cohort CSV has been selected
        # TODO: Replace this long check with something more elegant
        if not (self.getCohortSelectedFile().exists() and self.getCohortSelectedFile().suffix == ".csv"):
            todo_list.append(_("You need to select a cohort file."))

        # Check if a task has been selected
        if self.current_task is None:
            todo_list.append(_("You need to select a task to run."))

        # If there are items in the list, print a warning and return false
        if len(todo_list) > 0:
            spacer = '\n  * '
            print(f"Things left to do:{spacer}{spacer.join(todo_list)}")
            return False

        # Otherwise, return True; we're ready!
        return True

    ### Iterator Widgets ###

    def nextCase(self):
        print("NEXT CASE!")

        next_case = self.DataManagerInstance.next_item()
        self.current_case = next_case
        print(self.current_case.uid)

        self.currentCaseNameLabel.text = str(self.current_case.resources)

    def previousCase(self):
        print("PREVIOUS CASE!")

        previous_case = self.DataManagerInstance.next_item()
        self.current_case = previous_case
        print(self.current_case.uid)


        self.currentCaseNameLabel.text = str(self.current_case.resources)


    ### Task Related ###

    def loadTaskWhenReady(self):
        # If we're not ready to load a task, leave everything untouched
        if not self.isReady():
            return

        # Initialize an instance of the Task class
        self.current_task_instance: TaskBaseClass = self.current_task()

        # Initialize its GUI, which adds it to our collapsible Task button
        self.current_task_instance.buildGUI(self.taskGUI)

        # TODO: Instantiate the DataManager

        # Expand the task GUI and enable it
        self.taskGUI.collapsed = False
        self.taskGUI.setEnabled(True)

        # Collapse the main (setup) GUI
        self.mainGUI.collapsed = True

        # Step through our DataUnits until we find one that is not complete
        # TODO

        # Update the GUI using the contents of the current DataUnit
        # TODO
        self.current_task_instance.setup(self.DataManagerInstance.current_item())


    ## Management ##

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        pass

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        pass

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        pass


#
# CARTLogic
#


class CARTLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)


