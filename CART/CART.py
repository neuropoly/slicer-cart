from pathlib import Path
from textwrap import dedent

import vtk

import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

import json

from CARTLib.core.DataManager import DataManager
from CARTLib.core.TaskBaseClass import TaskBaseClass

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
        self.parent.title = "CART"  # It's an acronym title, not really translate-able
        self.parent.categories = ['Utilities']
        self.parent.dependencies = []  # No dependencies
        # TODO: Move these metadata contents into a standalone file which can
        #  be updated automatically as new PRs are made
        self.parent.contributors = [
            "Kalum Ost (Montréal Polytechnique)",
            "Kuan Yi (Montréal Polytechnique)",
            "Ivan Johnson-Eversoll (University of Iowa)"
        ]
        self.parent.helpText = _(dedent("""
                CART (Collaborative Annotation and Review Tool) provides a set 
                of abstract base classes for creating streamlined annotation 
                workflows in 3D Slicer. The framework enables efficient 
                iteration through medical imaging cohorts with customizable 
                tasks and flexible data loading strategies.
                
                See more information on the 
                <a href="https://github.com/SomeoneInParticular/CART/tree/main">GitHub repository</a>.
            """))
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _(dedent("""
                Originally created during Slicer Project Week #43.
                
                Special thanks the many members of the Slicer community who
                contributed to this work, including the many projects which 
                were used as reference. Of note:
                <a href="https://github.com/neuropoly/slicercart">SlicerCART</a> (the name and general framework),
                <a href="https://github.com/JoostJM/SlicerCaseIterator">SlicerCaseIterator</a> (inspired much of our logic),
                <a href="https://github.com/SlicerUltrasound/SlicerUltrasound">SlicerUltrasound/AnnotateUltrasound</a> (basis for our UI design),
                and the many other projects discussed during the breakout session (notes 
                <a href="https://docs.google.com/document/d/12XuYPVuRgy4RTuIabSIjy_sRrYSliewKhcbB1zJgXVI/">here.</a>
            """))




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

    ## Utils ##

    # The size constraints which should be used for small buttons;
    #  these match the size of the '...' button in a ctk.ctkPathLineEdit
    MICRO_BUTTON_WIDTH = 24
    MICRO_BUTTON_HEIGHT = 25

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

        ## Setup ##

        # The collapsible button to contain everything in
        mainGUI = ctk.ctkCollapsibleButton()
        # Not the best translation, but it'll do...
        mainGUI.text = "CART " + _("Setup")
        mainLayout = qt.QFormLayout(mainGUI)

        # User selection/registration
        self.buildUserUI(mainLayout)

        # Cohort Selection
        self.buildCohortUI(mainLayout)

        # Base Path input UI
        self.buildBasePathUI(mainLayout)

        # Task UI
        self.buildTaskUI(mainLayout)

        # Add this "main" widget to our panel
        self.layout.addWidget(mainGUI)

        # Make the GUI accessible
        self.mainGUI = mainGUI

        ## Progress Tracker ##
        # Case Iterator UI
        self.caseIteratorUI = self.buildCaseIteratorUI()

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

        # Add a vertical "stretch" at the bottom, forcing everything to the top;
        #  now it doesn't look like garbage!
        self.layout.addStretch()

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CARTLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    ## GUI builders ##

    def buildUserUI(self, mainLayout: qt.QFormLayout):
        """
        Builds the GUI for the user management section of the Widget
        :return:
        """
        # HBox to ensure everything is draw horizontally
        userHBox = qt.QHBoxLayout()

        # Insert this layout in the "main" GUI
        mainLayout.addRow(_("User:"), userHBox)

        # Prior users list
        userSelectButton = qt.QComboBox()
        userSelectButton.placeholderText = _("[Not Selected]")

        # Set the name of the button to the "UserSelectionButton"
        userSelectButton.toolTip = _("Select a previous user.")

        # By default, load it with the list of contributors in the config file
        userSelectButton.addItems(self.configuration_data["contributors"])

        # When the user selects an existing entry, update the program to match
        userSelectButton.currentIndexChanged.connect(self.userSelected)

        # Add it to the HBox
        userHBox.addWidget(userSelectButton)

        # Make the spacing between widgets (the button and dropdown) 0
        userHBox.spacing = 0

        # New user button
        newUserButton = qt.QPushButton("+")

        # When the button is pressed, prompt them to fill out a form
        newUserButton.clicked.connect(self.promptNewUser)

        # Force its size to not change dynamically
        newUserButton.setSizePolicy(
            qt.QSizePolicy.Fixed,
            qt.QSizePolicy.Fixed
        )

        # Force it to be square
        # KO: We can't just use "resize" here, because either Slicer or QT
        #  overrides it later; really appreciate 2 hours of debugging to figure
        #  that out!
        newUserButton.setMaximumWidth(CARTWidget.MICRO_BUTTON_WIDTH)
        newUserButton.setMaximumHeight(CARTWidget.MICRO_BUTTON_HEIGHT)

        # Add it to the layout!
        userHBox.addWidget(newUserButton)

        # Make it accessible
        self.priorUsersCollapsibleButton = userSelectButton

    def buildCohortUI(self, mainLayout: qt.QFormLayout):
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

        mainLayout.addRow(_("Cohort File:"), cohortFileSelectionButton)

        # Set default value but don't auto-load
        default_value = sample_data_cohort_csv.as_posix() if sample_data_cohort_csv.exists() else ""
        cohortFileSelectionButton.currentPath = default_value

        # Make the button easy-to-access
        self.cohortFileSelectionButton = cohortFileSelectionButton

        # Add explicit load button
        loadCohortButton = qt.QPushButton(_("Load Cohort"))
        loadCohortButton.toolTip = _("Load the selected cohort CSV file")
        loadCohortButton.clicked.connect(self.onLoadCohortClicked)
        mainLayout.addRow("", loadCohortButton)

        # Make load button accessible
        self.loadCohortButton = loadCohortButton

    def buildBasePathUI(self, mainLayout: qt.QFormLayout):
        """
        Extends the GUI to add widgets for data directory selection
        """
        # Base path selection
        basePathSelectionWidget = ctk.ctkPathLineEdit()
        basePathSelectionWidget.filters = ctk.ctkPathLineEdit.Dirs
        basePathSelectionWidget.toolTip = _("Select the base directory path. Leave empty to use None as base path.")

        mainLayout.addRow(_("Data Path:"), basePathSelectionWidget)

        # Connect the signal to handle base path changes
        basePathSelectionWidget.currentPathChanged.connect(self.onBasePathChanged)

        # Make it accessible
        self.basePathSelectionWidget = basePathSelectionWidget

    def buildTaskUI(self, mainLayout: qt.QFormLayout):
        # Prior users list
        taskOptions = qt.QComboBox()
        taskOptions.placeholderText = _("[Not Selected]")

        # TODO: Have this pull from configuration instead
        taskOptions.addItems(list(self.task_map.keys()))
        mainLayout.addRow(_("Task"), taskOptions)

        # Make it accessible
        self.taskOptions = taskOptions

        # When the task is changed, update everything to match
        taskOptions.currentIndexChanged.connect(self.onTaskChanged)

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

    def promptNewUser(self):
        """
        Creates a pop-up, prompting the user to enter their name into a
        text box to register themselves as a new user.
        """
        # Create a new widget
        new_name = qt.QInputDialog().getText(
            self.mainGUI,
            _("Add New User"),
            _("New User Name:")
        )

        if new_name:
            self.addNewUser(new_name)

    def addNewUser(self, user_name):
        print(user_name)

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

        self.loadTaskWhenReady()

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

        # Attempt to load the task, if we're now ready
        self.loadTaskWhenReady()

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
        # HACK REMOVE THIS AND MAKE IT CLEANER WHEN IMPLEMENTING THE MULTI-SCENE LAZY LOADING
        slicer.mrmlScene.Clear()

        print("NEXT CASE!")

        next_case = self.DataManagerInstance.next_item()
        self.current_case = next_case
        print(self.current_case.uid)
        self.currentCaseNameLabel.text = str(self.current_case.resources)
        if self.isReady():
            self.current_task_instance.setup(self.DataManagerInstance.current_item())


    def previousCase(self):
        # HACK REMOVE THIS AND MAKE IT CLEANER WHEN IMPLEMENTING THE MULTI-SCENE LAZY LOADING
        slicer.mrmlScene.Clear()
        print("PREVIOUS CASE!")

        previous_case = self.DataManagerInstance.next_item()
        self.current_case = previous_case
        print(self.current_case.uid)
        if self.isReady():
            self.current_task_instance.setup(self.DataManagerInstance.current_item())


        self.currentCaseNameLabel.text = str(self.current_case.resources)


    ### Task Related ###

    def loadTaskWhenReady(self):
        # If we're not ready to load a task, leave everything untouched
        if not self.isReady():
            return

        self.current_task_instance: TaskBaseClass = self.current_task(self.DataManagerInstance.current_item())

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


