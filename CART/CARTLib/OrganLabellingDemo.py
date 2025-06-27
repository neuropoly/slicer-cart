from .TaskBaseClass import TaskBaseClass, D

import ctk
import qt


class OrganLabellingDemoTask(TaskBaseClass):
    def buildGUI(self) -> qt.QLayout:
        # Outermost frame
        formLayout = qt.QBoxLayout()

        # Output file designation
        outputFile = ctk.ctkPathLineEdit()
        outputFile

        # Organ Label Field
        organBox = qt.QHBoxLayout()
        organText = qt.QLineEdit()
        organText.toolTip = "The name of the organ in this image."
        organBox.addWidget(organText)
        formLayout.addRow("Organ:", organBox)

        # TODO: Add connections

    def setup(self, data_unit: D):
        # TODO
        print(f"Running {self.__class__} setup!")

    def save(self) -> bool:
        # TODO
        print(f"Running {self.__class__} save!")
