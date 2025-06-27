from .TaskBaseClass import TaskBaseClass, D
from .VolumeOnlyDataIO import VolumeOnlyDataUnit
from .LayoutLogic import *

import ctk
import qt
import slicer
import csv
import time


class OrganLabellingDemoTask(TaskBaseClass):

    def __init__(self, data_unit: VolumeOnlyDataUnit):
        """
        Constructor for the OrganLabellingDemoTask.

        This initializes the task with a given DataUnitBase instance.
        """
        super().__init__(data_unit)

        self.output_file = None  # Placeholder for output file path
        self.saveButton = None  # Placeholder for save button
        self.organText = None  # Placeholder for organ label text field
        self.layoutLogic = CaseIteratorLayoutLogic()  # Layout logic instance
        self.volumeNodes = []  # Store loaded volume nodes

    def buildGUI(self, container: ctk.ctkCollapsibleButton):
        # Outermost frame
        formLayout = qt.QFormLayout(container)

        # Output file designation
        self.outputFileInput = ctk.ctkPathLineEdit()
        self.outputFileInput.setToolTip("The file to save the organ label to.")

        # Organ Label Field
        organBox = qt.QHBoxLayout()
        saveButton = qt.QPushButton()
        self.organTextInput = qt.QLineEdit()
        saveButton.text = "Save Organ"
        saveButton.toolTip = "Save the organ label to the data unit."
        self.saveButton = saveButton

        self.organTextInput.toolTip = "The name of the organ in this image."
        organBox.addWidget(self.organTextInput)
        formLayout.addRow("Organ:", organBox)
        organBox.addWidget(saveButton)
        formLayout.addRow("Output File:", self.outputFileInput)

        # Add layout controls
        layoutBox = qt.QHBoxLayout()

        # Button to show all volumes in separate rows
        self.showAllVolumesButton = qt.QPushButton("Show All Volumes")
        self.showAllVolumesButton.toolTip = "Display all volumes in separate rows with axial/sagittal/coronal views"
        layoutBox.addWidget(self.showAllVolumesButton)

        # Button to reset to default layout
        self.resetLayoutButton = qt.QPushButton("Reset Layout")
        self.resetLayoutButton.toolTip = "Reset to default slice layout"
        layoutBox.addWidget(self.resetLayoutButton)

        formLayout.addRow("Layout Controls:", layoutBox)

        # Connect buttons
        saveButton.clicked.connect(lambda: self.save())
        self.outputFileInput.currentPathChanged.connect(self.onOutputFileChanged)
        self.showAllVolumesButton.clicked.connect(self.showAllVolumes)
        self.resetLayoutButton.clicked.connect(self.resetLayout)

    def setup(self, data_unit: D):
        print(f"Running {self.__class__} setup!")
        print(f"data_unit: {data_unit}")

        # Clear existing volumes
        self.volumeNodes = []

        # Load all resources from the data unit
        for key, value in data_unit.data.items():
            if key == "uid":
                continue
            print(f"Data Unit Key: {key}, Value: {value}")

            # Get the volume node for this resource
            volumeNode = data_unit.get_resource(key)
            if volumeNode:
                self.volumeNodes.append(volumeNode)
                print(f"Loaded volume node: {volumeNode.GetName()} for key: {key}")

        # Set up initial default view
        if len(self.volumeNodes) >= 2:
            # Set up with first volume as background, second as foreground
            slicer.util.setSliceViewerLayers(
                background=self.volumeNodes[0],
                foreground=self.volumeNodes[1] if len(self.volumeNodes) > 1 else None,
                label=None,
                fit=True
            )
        elif len(self.volumeNodes) == 1:
            slicer.util.setSliceViewerLayers(
                background=self.volumeNodes[0],
                foreground=None,
                label=None,
                fit=True
            )

        print(f"Loaded {len(self.volumeNodes)} volume nodes")

    def showAllVolumes(self):
        """Display all volumes in separate rows with axial/sagittal/coronal views"""
        if not self.volumeNodes:
            print("No volumes loaded")
            return

        print("Showing all volumes in multi-row layout")
        sliceNodesByViewName = self.layoutLogic.viewersPerVolume(self.volumeNodes, include3D=False)

        # Rotate each volume to its own planes - don't use volumeNodes[0] for all
        orientations = ('Axial', 'Sagittal', 'Coronal')
        for volumeNode in self.volumeNodes:
            # Get slice nodes for this specific volume
            volumeSliceNodes = []
            for orientation in orientations:
                viewName = volumeNode.GetName() + '-' + orientation
                if viewName in sliceNodesByViewName:
                    volumeSliceNodes.append(sliceNodesByViewName[viewName])

            # Rotate only this volume's slice nodes to this volume's planes
            if volumeSliceNodes:
                self.layoutLogic.rotateToVolumePlanes(volumeNode, volumeSliceNodes)

        # Snap all to IJK for better alignment
        self.layoutLogic.snapToIJK()

    def resetLayout(self):
        """Reset to default slice layout"""
        print("Resetting to default layout")
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

        # Reset to show volumes in default viewers
        if len(self.volumeNodes) >= 2:
            slicer.util.setSliceViewerLayers(
                background=self.volumeNodes[0],
                foreground=self.volumeNodes[1],
                label=None,
                fit=True
            )
        elif len(self.volumeNodes) == 1:
            slicer.util.setSliceViewerLayers(
                background=self.volumeNodes[0],
                foreground=None,
                label=None,
                fit=True
            )

    def save(self) -> bool:
        print(f"Running {self.__class__} save!")

        print(f"Output file: {self.output_file}")
        if not self.output_file:
            print("No output file specified.")
            return False

        organText = self.organTextInput.text
        if not organText:
            print("No organ text specified.")
            return False

        TaskReviewer = slicer.app.layoutManager()
        print(f"TaskReviewer: {TaskReviewer}")

        output_dict = {
            "uid": self.data_unit.uid,
            "organ": organText,
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }

        # Check if file exists and has headers
        overwrite = False
        try:
            with open(self.output_file, "r", newline='') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    overwrite = True
                elif all(field not in reader.fieldnames for field in output_dict.keys()):
                    overwrite = True
        except FileNotFoundError:
            overwrite = True

        mode = "a"
        if overwrite:
            print(f"Overwriting {self.output_file}")
            mode = "w"

        with open(self.output_file, mode, newline='') as f:
            writer = csv.DictWriter(f, fieldnames=output_dict.keys())
            if overwrite:
                writer.writeheader()
            writer.writerow(output_dict)

        print(f"Saved organ label '{organText}' for UID {self.data_unit.uid}")
        return True

    def onOutputFileChanged(self):
        """
        Update the output file path.
        """
        output_path = self.outputFileInput.currentPath
        print(f"Output file updated to: {output_path}")
        if output_path:
            self.output_file = output_path
        else:
            self.output_file = None