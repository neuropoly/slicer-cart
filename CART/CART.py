from pathlib import Path
from typing import Optional

import vtk

import ctk
import qt
import slicer
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.util import VTKObservationMixin

from CARTLib.Config import Config
from CARTLib.core.DataManager import DataManager
from CARTLib.core.DataUnitBase import DataUnitBase
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
        self.parent.helpText = _("""
                CART (Collaborative Annotation and Review Tool) provides a set 
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

        # Load our configuration
        Config.load()


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
    # TODO: Remove when we swap the button to be a QToolButton
    MICRO_BUTTON_WIDTH = 24
    MICRO_BUTTON_HEIGHT = 25

    ## Initialization ##

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation

        # Initialize our logic instance
        self.logic: CARTLogic = CARTLogic()
        self._parameterNode = None
        self._parameterNodeGuiTag = None

        # A "dummy" widget, which holds the TaskGUI. Allows us to swap tasks on the fly.
        self.dummyTaskWidget: qt.QWidget = None

        # TODO: Dynamically load this dictionary instead
        self.task_map = {
            "Organ Labels": OrganLabellingDemoTask,
            "N/A": None  # Placeholder for testing
        }

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

        # Button panel
        self.buildButtonPanel(mainLayout)

        # Add this "main" widget to our panel
        self.layout.addWidget(mainGUI)

        # Make the GUI accessible
        self.mainGUI = mainGUI

        ## Progress Tracker ##
        # Case Iterator UI
        self.buildCaseIteratorUI(self.layout)

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

        # Using a stacked layout, in preparation for future multitask setups
        qt.QStackedLayout(taskGUI)

        self.layout.addWidget(taskGUI)
        self.taskGUI = taskGUI

        # Add a vertical "stretch" at the bottom, forcing everything to the top;
        #  now it doesn't look like garbage!
        self.layout.addStretch()

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

        # Load it up with the list of users in the configuration file
        users = Config.get_users()
        userSelectButton.addItems(Config.get_users())

        # If there are users, use the first (most recent) as the default
        if users:
            userSelectButton.currentIndex = 0

        # When the user selects an existing entry, update the program to match
        userSelectButton.activated.connect(self.userSelected)

        # Add it to the HBox
        userHBox.addWidget(userSelectButton)

        # Make the spacing between widgets (the button and dropdown) 0
        userHBox.spacing = 0

        # New user button
        # TODO: Make this a QToolButton instead
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

        # Make the user selection button accessible
        self.userSelectButton = userSelectButton

    def buildCohortUI(self, mainLayout: qt.QFormLayout):
        # Directory selection button
        cohortFileSelectionButton = ctk.ctkPathLineEdit()

        # Set file filters to only show readable file types
        cohortFileSelectionButton.filters = ctk.ctkPathLineEdit.Files
        cohortFileSelectionButton.nameFilters = [
            "CSV files (*.csv)",
        ]

        # When the cohort is changed, update accordingly
        cohortFileSelectionButton.connect.parameterNames
        cohortFileSelectionButton.currentPathChanged.connect(self.onCohortChanged)

        # TODO: Optionally set a default filter

        # Add it to our layout
        mainLayout.addRow(_("Cohort File:"), cohortFileSelectionButton)

        # Set default value but don't auto-load
        default_value = sample_data_cohort_csv.as_posix() if sample_data_cohort_csv.exists() else ""
        cohortFileSelectionButton.currentPath = default_value

        # Make the button easy-to-access
        self.cohortFileSelectionButton = cohortFileSelectionButton

    def buildBasePathUI(self, mainLayout: qt.QFormLayout):
        """
        Extends the GUI to add widgets for data directory selection
        """
        # Base path selection
        dataPathSelectionWidget = ctk.ctkPathLineEdit()
        dataPathSelectionWidget.filters = ctk.ctkPathLineEdit.Dirs
        dataPathSelectionWidget.toolTip = _("Select the base directory path. Leave empty to use None as base path.")

        mainLayout.addRow(_("Data Path:"), dataPathSelectionWidget)

        # Connect the signal to handle base path changes
        dataPathSelectionWidget.currentPathChanged.connect(self.onDataPathChanged)

        # Make it accessible
        self.dataPathSelectionWidget = dataPathSelectionWidget

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

    def buildButtonPanel(self, mainLayout: qt.QFormLayout):
        # A button to preview the cohort, without starting on a task
        previewButton = qt.QPushButton(_("Preview"))
        previewButton.toolTip = _("""
        Reads the contents of the cohort.csv for review, without starting the task
        """)

        # On click, attempt to load the cohort file and its contents into the GUI
        previewButton.clicked.connect(self.onPreviewCohortClicked)

        # Disable the button by default; we need a valid cohort first!
        previewButton.setEnabled(False)

        # A button which confirms the current settings and attempts to start
        #  task iteration!
        confirmButton = qt.QPushButton(_("Confirm"))
        confirmButton.toolTip = _("Begin doing this task on your cases.")

        # Disable the button by default; the user needs to fill out everything first!
        confirmButton.setEnabled(False)

        # Attempt to load the task, assuming everything is ready
        confirmButton.clicked.connect(self.loadTaskWhenReady)

        # Add them to our layout
        mainLayout.addRow(previewButton, confirmButton)

        # Make them accessible
        self.previewButton = previewButton
        self.confirmButton = confirmButton

    def buildCaseIteratorUI(self, mainLayout: qt.QFormLayout):
        # Layout
        iteratorWidget = qt.QWidget()
        taskLayout = qt.QVBoxLayout(iteratorWidget)

        # Add the task "widget" (just a frame to hold everything in) to the global layout
        mainLayout.addWidget(iteratorWidget)

        # Hide this by default, only showing it when we're ready to iterate
        iteratorWidget.setVisible(False)

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
        taskLayout.addLayout(buttonLayout)

        # Add a text field to display the current case name under the buttons
        self.currentCaseNameLabel = qt.QLineEdit()
        self.currentCaseNameLabel.readOnly = True
        self.currentCaseNameLabel.placeholderText = _("Current case name will appear here")
        taskLayout.addWidget(self.currentCaseNameLabel)

        # Table for displaying cohort resources
        self.cohortTable = qt.QTableWidget()
        self.cohortTable.setRowCount(10)
        self.cohortTable.setColumnCount(2)
        self.cohortTable.setHorizontalHeaderLabels([_("Resource"), _("Resource Type")])
        self.cohortTable.horizontalHeader().setStretchLastSection(True)
        self.cohortTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.cohortTable.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
        self.cohortTable.setWordWrap(False)
        self.cohortTable.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

        # Set a subtle contrasting style for dark backgrounds
        self.cohortTable.setStyleSheet("""
          QTableWidget {
        background-color: #2b2b2b;
        alternate-background-color: #353535;
        color: #e0e0e0;
        border: 1px solid #444;
        gridline-color: #444;
          }
          QHeaderView::section {
        background-color: #393939;
        color: #e0e0e0;
        border: 1px solid #444;
          }
          QTableWidget::item {
        selection-background-color: #44475a;
        selection-color: #ffffff;
          }
        """)

        for row in range(10):
            filePathItem = qt.QTableWidgetItem("")
            filePathItem.setTextAlignment(qt.Qt.AlignLeft | qt.Qt.AlignVCenter)
            filePathItem.setToolTip(_("Loaded Resource"))
            # Make item not editable, selectable, or enabled
            filePathItem.setFlags(qt.Qt.NoItemFlags)
            self.cohortTable.setItem(row, 0, filePathItem)

            resourceTypeItem = qt.QTableWidgetItem("")
            resourceTypeItem.setTextAlignment(qt.Qt.AlignCenter)
            resourceTypeItem.setToolTip(_("Resource type"))
            # Make item not editable, selectable, or enabled
            resourceTypeItem.setFlags(qt.Qt.NoItemFlags)
            self.cohortTable.setItem(row, 1, resourceTypeItem)

        # Make the table itself unselectable and uneditable
        self.cohortTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.cohortTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.cohortTable.setSelectionMode(qt.QAbstractItemView.NoSelection)
        self.cohortTable.setAlternatingRowColors(True)
        self.cohortTable.setShowGrid(True)
        self.cohortTable.verticalHeader().setVisible(False)

        taskLayout.addWidget(self.cohortTable)

        # Make the groupbox accessible elsewhere, so it can be made visible later
        self.iteratorWidget = iteratorWidget

        # Connections
        nextButton.clicked.connect(self.nextCase)
        previousButton.clicked.connect(self.previousCase)


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

        # Attempt to add the new user to the Logic
        success = self.logic.add_new_user(new_name)

        # If we succeeded, update the GUI to match
        if success:
            self._refreshUserList()
            # Check if we're ready to proceed
            self.updateButtons()
        else:
            # TODO: Add a user prompt
            print(f"Failed to add user '{new_name}'.")

    def userSelected(self):
        # Update the logic with this newly selected user
        idx = self.userSelectButton.currentIndex
        self.logic.set_most_recent_user(idx)

        # Rebuild the GUI to match
        self._refreshUserList()

        # Update the button states to match our current state
        self.updateButtons()

    def _refreshUserList(self):
        """
        Rebuild the list in the GUI from scratch, ensuring everything is
        maintained in order.

        KO: an insertion policy only applies to insertions made into an
         editable combo-box; insertions made by us are always inserted
         last. Therefore, this song and dance is needed
        """
        # Clear all entries
        self.userSelectButton.clear()

        # Rebuild its contents from scratch
        self.userSelectButton.addItems(self.logic.get_users())

        # Select the first (most recent) entry in the list
        self.userSelectButton.currentIndex = 0

    def onDataPathChanged(self):
        """
        Handles changes to the base path selection.
        Falls back the previous base path if the user specified an empty space.
        """
        # Get the current path from the GUI
        current_path = self.dataPathSelectionWidget.currentPath

        # Strip it of leading/trailing whitespace
        current_path = current_path.strip()

        # If a path still exists, update everything to use it
        if current_path:
            self.logic.set_data_path(Path(current_path))

        else:
            print("Error: Base path was empty, retaining previous base path.")
            self.dataPathSelectionWidget.currentPath = str(self.logic.data_path)

        # Update the state of our buttons to match
        self.updateButtons()

    def onCohortChanged(self):
        # Get the currently selected cohort file from the widget
        new_cohort = Path(self.cohortFileSelectionButton.currentPath)

        # Attempt to update the cohort in our logic instance
        success = self.logic.set_current_cohort(new_cohort)

        # If we succeeded, update our state to match
        if success:
            self.updateButtons()

    def onPreviewCohortClicked(self):
        """
        Load the cohort explicitly, so it can be reviewed.
        """
        # Load the file's cases into memory
        self.logic.load_cohort()

        # Update the resources table to match the new cohort's contents
        self.fillResourcesTable()

    def onTaskChanged(self):
        # Update the currently selected task
        task_name = self.taskOptions.currentText
        new_task = self.task_map.get(task_name, None)
        self.logic.set_task_type(new_task)

        # Purge the current task widget, and replace it with a new one
        if self.dummyTaskWidget:
            # Disconnect the widget, and all of its children, from the GUI
            self.dummyTaskWidget.setParent(None)
            # Delete our reference to it as well
            self.dummyTaskWidget = None

        # Re-hide the task GUI, as its no longer relevant until the new task GUI is loaded
        self.taskGUI.collapsed = True
        self.taskGUI.setEnabled(False)

        # Update our button panel to match the new state
        self.updateButtons()
      
    def fillResourcesTable(self):
        return

        # TODO: Replace this so that it previews the cohort data instead
        for row_index, (key, value) in enumerate(self.logic.get_current_case().data.items()):
            if key == "uid":
                continue
            self.cohortTable.setItem(row_index, 0, qt.QTableWidgetItem(str(value)))
            self.cohortTable.setItem(row_index, 1, qt.QTableWidgetItem(str(key) + " : Placholder Type"))

        # Make the task box visible, if it was not already.
        # TODO: Separate the cohort table from the task iterator, so one can be
        #  view/hidden without the other
        self.iteratorWidget.setVisible(True)


    ### Iterator Widgets ###

    def nextCase(self):
        # TODO: Actually implement this
        print("NEXT CASE!")
        return


        next_case = self.logic.data_manager.next_data_unit()
        self.current_case = next_case
        print(self.current_case.uid)
        
        if self.isReady():
            self.currentCaseNameLabel.text = "Data Unit " + str(self.current_case.uid)
            self.fillResourcesTable()
            self.current_task_instance.setup(self.logic.data_manager.current_data_unit())

    def previousCase(self):
        # TODO: Actually implement this
        print("PREVIOUS CASE!")
        return

        # HACK REMOVE THIS AND MAKE IT CLEANER WHEN IMPLEMENTING THE MULTI-SCENE LAZY LOADING
        slicer.mrmlScene.Clear()

        previous_case = self.logic.data_manager.previous_data_unit()
        self.current_case = previous_case
        print(self.current_case.uid)
        
        if self.isReady():
            self.currentCaseNameLabel.text = "Data Unit " + str(self.current_case.uid)
            self.fillResourcesTable()
            self.current_task_instance.setup(self.logic.data_manager.current_data_unit())

    ### Task Related ###
    def updateButtons(self):
        # If we have a cohort file, it can be previewed
        if self.logic.cohort_path:
            self.previewButton.setEnabled(True)

        # If the logic says we're ready to start, we can start
        if self.logic.is_ready():
            self.confirmButton.setEnabled(True)

    def loadTaskWhenReady(self):
        # If we're not ready to load a task, leave everything untouched
        if not self.logic.is_ready():
            return

        # Initialize the new task
        self.logic.init_task()

        # Create a "dummy" widget that the task can fill
        self.dummyTaskWidget = qt.QWidget()
        # Build the Task GUI, using the prior widget as a foundation
        self.logic.current_task_instance.setup(self.dummyTaskWidget)
        # Add the widget to our layout
        self.taskGUI.layout().addWidget(self.dummyTaskWidget)

        # Expand the task GUI and enable it, if it wasn't already
        self.taskGUI.collapsed = False
        self.taskGUI.setEnabled(True)

        # Reveal the iterator GUI, if it wasn't already
        self.iteratorWidget.setVisible(True)

        # Update the current UID in the iterator
        self.currentCaseNameLabel.text = str(self.logic.current_uid())

        # Collapse the main (setup) GUI, if it wasn't already
        self.mainGUI.collapsed = True


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

        # Path to the cohort file currently in use
        self.cohort_path: Path = None

        # Path to where the user specified their data is located
        self.data_path: Path = None

        # The data manager currently managing case iteration
        self.data_manager: DataManager = None

        # The currently selected task type
        self.current_task_type: type(TaskBaseClass) = None

        # The current task instance
        self.current_task_instance: Optional[TaskBaseClass] = None

    ## User Management ##
    def get_users(self) -> list[str]:
        # Simple wrapper for our config
        return Config.get_users()

    def get_current_user(self) -> str:
        """
        Gets the currently selected user, if there is one
        """
        users = Config.get_users()
        if users:
            return users[0]
        else:
            return None

    def set_most_recent_user(self, idx: int) -> bool:
        """
        Change the most recent user to the one specified
        """
        users = Config.get_users()

        # If the index is out of bounds, exit early with a failure
        if len(users) <= idx or idx < 0:
            return False

        # Otherwise, move the user to the front of the list
        selected_user = users[idx]
        users.pop(idx)
        users.insert(0, selected_user)

        # Immediately save the Config and return
        Config.save()
        return True

    def add_new_user(self, user_name: str) -> bool:
        """
        Attempt to add a new user to the list.

        Returns True if this was successful, False otherwise
        """
        # Strip leading and trailing whitespace in the username
        user_name = user_name.strip()

        # Confirm they actually provided a (non-whitespace only) string
        if not user_name:
            print("Something must be entered as a name!")
            return False

        # Check if the user already exists
        current_users = Config.get_users()
        if user_name in current_users:
            print("User name already exists!")
            return False

        # Add the username to the list at the top
        current_users.insert(0, user_name)

        # Save the configuration
        Config.save()

        # Return that this has been done successfully
        return True

    ## Cohort Path/Data Path Management ##
    def set_current_cohort(self, new_path: Path) -> bool:
        # Confirm the file exists
        if not new_path.exists():
            print(f"Error: Cohort file does not exist: {new_path}")
            return False

        # Confirm it is a CSV
        if new_path.suffix.lower() != ".csv":
            print(f"Error: Selected file is not a CSV: {new_path}")
            return False

        # Warn the user if they're reloading the same file
        if (
            self.cohort_path is not None and
            str(new_path.resolve()) == str(self.cohort_path.resolve())
        ):
            print(f"Warning: Reloaded the same cohort file!")

        # If all checks pass, update our state
        self.cohort_path = new_path
        self.data_manager = DataManager(
            cohort_file=self.cohort_path,
            data_source=self.data_path,
        )
        return True

    def set_data_path(self, new_path: Path) -> bool:
        # Confirm the directory exists
        if not new_path.exists():
            print(f"Error: Data path does not exist: {new_path}")
            return False

        # Confirm that it is a directory
        if not new_path.is_dir():
            print(f"Error: Data path was not a directory: {new_path}")
            return False

        # If that all ran, update our data path to the new data path
        self.data_path = new_path
        print(f"Data path set to: {self.data_path}")

        # and replace the previous data manager
        del self.data_manager
        self.data_manager = DataManager(
            cohort_file=self.cohort_path,
            data_source=self.data_path,
        )

        return True

    def load_cohort(self):
        """
        Load the contents of the currently selected cohort file into memory
        """
        self.data_manager.load_cases()

    ## Task Management ##
    def set_task_type(self, task_type: type(TaskBaseClass)):
        # Set the task type
        self.current_task_type = task_type

        # If we have a task built already, delete it
        if self.current_task_instance:
            self.current_task_instance.cleanup()
            self.current_task_instance = None

    def is_ready(self) -> bool:
        """
        Check if we're ready to run a task!
        :return: True if so, False otherwise.
        """
        # We can't proceed if we don't have a selected user
        if not self.get_current_user():
            print("Missing a valid user!")
            return False
        # We can't proceed if a data path has not been specified
        elif not self.data_path:
            print("Missing a valid data path!")
            return False
        # We can't proceed if we're missing a cohort path
        elif not self.cohort_path:
            print("Missing a valid cohort path!")
            return False
        # We can't proceed if we don't have a selected task type
        elif not self.current_task_type:
            print("No task has been selected!")
            return False

        # If all checks passed, we can proceed!
        return True

    def init_task(self) -> Optional[TaskBaseClass]:
        """
        Initialize a new Task instance using current settings.

        :return: The Task instance, None if one cannot be created.
        """
        # Safety gate: if we're not ready to start a task, return None
        if not self.is_ready():
            return None

        # Load the cohort file into memory again, as it may not already be so
        #  (or the user made edits to it after a preview)
        self.load_cohort()

        # Create the new task instance and return it.
        self.current_task_instance = self.current_task_type(self.get_current_case())
        return self.current_task_instance

    ## DataUnit Management ##
    def current_uid(self):
        if self.data_manager:
            return self.data_manager.current_uid()
        # In the off chance where we don't have cases loaded, return none
        else:
            return ""

    def get_current_case(self) -> Optional[DataUnitBase]:
        """
        Get the DataUnit currently indexed by the data manager.

        Returns None if a DataManager has not been initialized, or if its
          empty (somehow)
        """
        # If we don't have a data manager yet, return none
        if not self.data_manager:
            return None

        # Otherwise, return the data manager's current item
        return self.data_manager.current_data_unit()

    def next_case(self) -> Optional[DataUnitBase]:
        """
        Try to step into the next case managed by the cohort, pulling it
          into memory if needed.

        :return: The next valid case. 'None' if no valid case could be found.
        """
        # Get the next valid case
        next_case = self.data_manager.next_data_unit()

        # Return it; the data manager is self-managing, no need to do any further checks
        return next_case

    def previous_case(self):
        """
        Try to step into the previous case managed by the cohort, pulling it
          into memory if needed.

        :return: The previous valid case. 'None' if no valid case could be found.
        """
        # Get the previous valid case
        previous_case = self.data_manager.previous_data_unit()

        # Return it; the data manager is self-managing, no need to do any further checks
        return previous_case
