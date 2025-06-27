from .TaskBaseClass import TaskBaseClass, D
from .VolumeOnlyDataIO import VolumeOnlyDataUnit

import ctk
import qt
import slicer

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

    def buildGUI(self, container: ctk.ctkCollapsibleButton):
        # Outermost frame
        formLayout = qt.QFormLayout(container)

        # Output file designation
        self.outputFileInput = ctk.ctkPathLineEdit()
        self.outputFileInput.setToolTip("The file to save the organ label to.")


        # Organ Label Field
        organBox = qt.QHBoxLayout()
        saveButton = qt.QPushButton()
        organText = qt.QLineEdit()
        saveButton.text = "Save Organ"
        saveButton.toolTip = "Save the organ label to the data unit."
        self.saveButton = saveButton

        organText.toolTip = "The name of the organ in this image."
        organBox.addWidget(organText)
        formLayout.addRow("Organ:", organBox)
        organBox.addWidget(saveButton)
        formLayout.addRow("Output File:", self.outputFileInput)

        # Connect the save button to the save method
        saveButton.clicked.connect(lambda: self.save())
        self.outputFileInput.currentPathChanged.connect(self.onOutputFileChanged)




        # TODO: Add connections

    def setup(self, data_unit: D):
        # TODO
        print(f"Running {self.__class__} setup!")
        print(f"data_unit: {data_unit}")
        for key, value in data_unit.data.items():
            print(f"Data Unit Key: {key}, Value: {value}")

        # Set up the scene with the provided data unit resources

        slicer.util.setSliceViewerLayers(background=data_unit.get_resource("adc"), foreground=data_unit.get_resource("hbv"), label=None, fit=True)




    def save(self) -> bool:
        # TODO
        print(f"Running {self.__class__} save!")

        print(f"Output file: {self.output_file}")
        if not self.output_file:
            print("No output file specified.")
            return False
        if not self.organText or not self.organText.text:
            print("No organ label specified.")
            return False
        organ_label = self.organText.text
        print(f"Saving organ label '{organ_label}' to file '{self.output_file}'")



    def onOutputFileChanged(self):
        """
        Update the output file path.

        Args:
            file_path (str): The new output file path.
        """
        output_path = self.outputFileInput.currentPath
        print(f"Output file updated to: {output_path}")
        if output_path:
            self.output_file = output_path
        else:
            self.output_file = None





