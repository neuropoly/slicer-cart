from typing import Optional

from .core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from .core.DataUnitBase import DataUnitBase
from .VolumeOnlyDataIO import VolumeOnlyDataUnit
from .LayoutLogic import CaseIteratorLayoutLogic

import ctk
import qt
import slicer
import csv
import time

from pathlib import Path


class OrganLabellingDemoTask(TaskBaseClass[VolumeOnlyDataUnit]):

    def __init__(self, user: str):
        """
        Constructor for the OrganLabellingDemoTask.

        This initializes the task with a given DataUnitBase instance.
        """
        super().__init__(user)

        self.load_all_volumes = True  # Flag to control volume loading
        self.layoutLogic = CaseIteratorLayoutLogic()  # Layout logic instance
        self.volumeNodes = []  # Store loaded volume nodes

        self.data_unit: DataUnitBase = None  # The currently managed data unit

        self.output_file = None  # Placeholder for output file path
        self.saveButton = None  # Placeholder for save button
        self.organText = None  # Placeholder for organ label text field

    def setup(self, container: qt.QWidget):
        print(f"Running {self.__class__.__name__} setup!")

        # Outermost frame
        formLayout = qt.QFormLayout()
        container.setLayout(formLayout)

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

    def receive(self, data_unit: VolumeOnlyDataUnit):
        print(f"Received new data unit: {hash(data_unit)}")

        if data_unit is not None:
            self.data_unit = data_unit

        # Clear existing volumes
        self.volumeNodes = []

        # Track the data unit for later
        self.data_unit = data_unit

        # Load all resources from the data unit
        for key, value in data_unit.case_data.items():
            if key == "uid":
                continue
            print(f"Data Unit {hash(data_unit)} ({key}): {value}")
            self.uid = value

            # Get the volume node for this resource
            volumeNode = data_unit.get_resource(key)
            if volumeNode:
                self.volumeNodes.append(volumeNode)

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

        if self.load_all_volumes:
            # Show all volumes in multi-row layout
            self.showAllVolumes()

        print(f"Loaded {len(self.volumeNodes)} volume nodes")

    def showAllVolumes(self):
        """
        Display all volumes in separate rows with axial/sagittal/coronal views
        """
        self.load_all_volumes= True  # Enable loading all volumes in multi-row layout
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
        self.load_all_volumes = False  # Disable loading all volumes in multi-row layout
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

    def save(self) -> Optional[str]:
        print(f"Running {self.__class__} save!")

        # Validate we have an output folder to actually save to
        print(f"Output file: {self.output_file}")
        if not self.output_file:
            err_msg = "No output file specified."
            return err_msg

        # Validate that the user has actually entered an organ
        organText = self.organTextInput.text
        if not organText:
            err_msg = "No organ text specified."
            return err_msg

        # TODO

        # Setup
        field_names = [
            "uid",
            "organ",
            "Timestamp"
        ]
        csv_data = []

        # If the file already exists, update its contents if possible
        uid = self.data_unit.get_data_uid()
        if Path(self.output_file).exists():
            entry_found = False
            with open(self.output_file, 'r') as fp:
                csv_reader = csv.DictReader(fp)
                # if an entry exists, update it
                for r in csv_reader:
                    # Track the entry for later
                    csv_data.append(r)
                    print(r)
                    # If we have an entry, update its contents with the current state
                    if r.get('uid', '') == uid:
                        r['organ'] = organText
                        r['Timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                        entry_found = True

            # Otherwise, create a new entry
            if not entry_found:
                new_entry = {
                    "uid": uid,
                    "organ": organText,
                    "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                }
                csv_data.append(new_entry)

        # Otherwise, create a new entry and save it instead
        else:
            new_entry = {
                "uid": uid,
                "organ": organText,
                "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            csv_data.append(new_entry)

        # Overwrite the file with the new data
        with open(self.output_file, 'w') as fp:
            csv_writer = csv.DictWriter(fp, field_names)
            csv_writer.writeheader()
            csv_writer.writerows(csv_data)

        print(f"Saved organ label '{organText}' for UID {self.data_unit.uid}")
        return None

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

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        return {
            "Default": VolumeOnlyDataUnit
        }
