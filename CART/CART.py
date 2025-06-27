from pathlib import Path

import vtk

import ctk
import qt
import slicer
from CARTLib.DataManager import DataManager
from slicer import vtkMRMLScalarVolumeNode
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.util import VTKObservationMixin

import json

from CARTLib.DataManager import DataManager

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

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # User UI
        self.userUIWidget = self.buildUserUI()
        # self.userUIWidget.setMRMLScene(slicer.mrmlScene)
        self.layout.addWidget(self.userUIWidget)

        # Cohort UI
        self.cohortUIWidget = self.buildCohortUI()
        self.layout.addWidget(self.cohortUIWidget)

        # Case Iterator UI
        self.caseIteratorUI = self.buildCaseIteratorUI()
        self.layout.addWidget(self.caseIteratorUI)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CARTLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.onCohortChanged()
    ## GUI builders ##

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

        # When the cohort selects a directory, update everything to match
        default_value = sample_data_cohort_csv.as_posix() if sample_data_cohort_csv.exists() else ""
        cohortFileSelectionButton.currentPath = default_value
        # Ensure that the default value is set BEFORE connecting the signal
        cohortFileSelectionButton.currentPathChanged.connect(self.onCohortChanged)
        # Make the button easy-to-access
        self.cohortFileSelectionButton = cohortFileSelectionButton


        return cohortCollapsibleButton

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

        # Show the hidden parts of the GUI if we're ready to proceed
        self.checkIteratorReady()

    def userSelected(self):
        index = self.priorUsersCollapsibleButton.currentIndex
        text = self.priorUsersCollapsibleButton.currentText
        print(f"User selected: {text} ({index})")
        self.checkIteratorReady()

    def getCohortSelectedFile(self) -> Path:
        return Path(self.cohortFileSelectionButton.currentPath)

    def onCohortChanged(self):
        """
        Runs when a new cohort CSV is selected.
        """
        # Attempt to create a DataManager from the file
        self.cohort_csv_path = self.getCohortSelectedFile()
        self.DataManagerInstance.load_data(self.cohort_csv_path)

        # Prepare the iterator for use
        self.checkIteratorReady()
        self.DataManagerInstance.set_data_cohort_csv(self.cohort_csv_path)
        self.DataManagerInstance.load_data(self.cohort_csv_path)
        self.groupBox.setEnabled(True)
        # Show the first case immediately
        if self.DataManagerInstance.raw_data:
            self.current_case = self.DataManagerInstance.current_item().resources
            print(self.current_case)
            self.currentCaseNameLabel.text = str(self.current_case)

    def checkIteratorReady(self):
        # If there is a specified user
        if self.priorUsersCollapsibleButton.currentIndex != -1:
            # If there is a valid cohort
            if self.getCohortSelectedFile().exists() and self.getCohortSelectedFile().suffix == ".csv":
                self.caseIteratorUI.setEnabled(True)

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


