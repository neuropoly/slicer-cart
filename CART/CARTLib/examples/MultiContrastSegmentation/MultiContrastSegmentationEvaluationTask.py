import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import ctk
import qt
import slicer
from slicer.i18n import tr as _
from .MultiContrastSegmentationEvaluationDataUnit import (
    MultiContrastSegmentationEvaluationDataUnit,
)
from CARTLib.core.TaskBaseClass import TaskBaseClass, DataUnitFactory
from CARTLib.utils.widgets import CARTSegmentationEditorWidget
from CARTLib.utils.data import save_segmentation_to_nifti
from CARTLib.utils.layout import LayoutHandler, Orientation


VERSION = 0.01


# TODO Allow for the user to select "All" which will create a row instead of a single view
class MultiContrastSegmentationEvaluationGUI:
    def __init__(self, bound_task: "MultiContrastSegmentationEvaluationTask"):
        self.bound_task = bound_task
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

        # Layout logic for creating linked slice views
        # self.layoutLogic = CaseIteratorLayoutLogic()
        self.layoutHandler = None
        self.currentOrientation: Orientation = Orientation.AXIAL

        # Widgets we'll need to reference later:
        self.segmentEditorWidget: Optional[CARTSegmentationEditorWidget] = None
        self.saveButton: Optional[qt.QPushButton] = None

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning the resulting layout for use.
        """
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout()

        # 2) Orientation buttons
        self._addOrientationButtons(formLayout)

        # 3) Segmentation editor
        self.segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(self.segmentEditorWidget)

        # 4) Save controls
        self._addOutputSelectionButton(formLayout)
        self._addSaveButton(formLayout)

        # TODO Make this more general and allow for a "None" selection where it saves to original input location
        self.promptSelectOutput()

        return formLayout

    def _addOrientationButtons(self, layout: qt.QFormLayout) -> None:
        """
        Buttons to set Axial/Sagittal/Coronal for all slice views.
        """
        hbox = qt.QHBoxLayout()
        for ori in Orientation.TRIO:
            label = ori.as_slicer()
            btn = qt.QPushButton(label)
            btn.clicked.connect(lambda _, o=ori: self.onOrientationChanged(o))
            hbox.addWidget(btn)
        layout.addRow(qt.QLabel("View Orientation:"), hbox)

    def _addOutputSelectionButton(self, layout: qt.QFormLayout) -> None:
        btn = qt.QPushButton("Change Output Directory")
        btn.clicked.connect(self.promptSelectOutput)
        layout.addRow(btn)

    def _addSaveButton(self, layout: qt.QFormLayout) -> None:
        btn = qt.QPushButton("Save")
        btn.clicked.connect(self._save)
        layout.addRow(btn)
        self.saveButton = btn

    #
    # Handlers
    #

    def onOrientationChanged(self, orientation: Orientation) -> None:
        # Update our currently tracked orientation + the layout handler's
        self.currentOrientation = orientation
        self.layoutHandler.set_orientation(orientation)

        # If we don't have a data unit at this point, end here
        if not self.data_unit:
            return

        # Otherwise, apply the new orientation to our layout
        self.layoutHandler.apply_layout()

    ## USER PROMPTS ##
    def promptSelectOutput(self):
        """
        Prompt the user to select an output directory.

        The prompt will validate that the chosen output directory is valid,
         and lock the save button if the user cancel's out of it without
         selecting such a directory.
        """
        # Initialize the prompt
        prompt = self._buildOutputDirPrompt()

        # Show the prompt with "exec", blocking the main window until resolved
        result = prompt.exec()

        # If the user cancelled out of the prompt, notify them that they will
        #  need to specify an output directory later!
        if result == 0:
            notif = qt.QErrorMessage()
            if self.bound_task.can_save():
                notif.setWindowTitle(_("REVERTING!"))
                notif.showMessage(
                    _(
                        "Cancelled out of window; falling back to previous "
                        "output directory "
                        f"({str(self.bound_task.output_dir)})"
                    )
                )
                notif.exec()
            else:
                notif.setWindowTitle(_("NO OUTPUT!"))
                notif.showMessage(
                    _(
                        "No output directory selected! You will need to "
                        "specify this before segmentations can be saved."
                    )
                )
                notif.exec()

        # Update the save button to match the current saving capability
        self._updatedSaveButtonState()

    def _buildOutputDirPrompt(self):
        prompt = qt.QDialog()
        prompt.setWindowTitle("Select Output Directory")
        # Add a basic layout to hold widgets in this prompt
        layout = qt.QVBoxLayout()
        prompt.setLayout(layout)

        # Add a label describing what's being asked
        label = qt.QLabel("Please select an output directory:")
        layout.addWidget(label)

        # Add an output file selection widget
        outputFileEdit = ctk.ctkPathLineEdit()
        outputFileEdit.setToolTip(
            _(
                "The directory the modified segmentations (and corresponding "
                "metadata) will be placed."
            )
        )
        # Set the widget to only accept directories
        outputFileEdit.filters = ctk.ctkPathLineEdit.Dirs
        # Add it to our layout
        layout.addWidget(outputFileEdit)

        # Add a button box to confirm/cancel out
        buttonBox = qt.QDialogButtonBox()
        buttonBox.addButton(_("Confirm"), qt.QDialogButtonBox.AcceptRole)
        layout.addWidget(buttonBox)

        # When the user confirms, ensure we have a valid path first
        buttonBox.accepted.connect(
            lambda: self._attemptOutputPathUpdate(prompt, outputFileEdit)
        )

        # Resize the prompt to be wider, as by default its very tiny
        prompt.resize(500, prompt.minimumHeight)

        return prompt

    def _linkedPathErrorPrompt(self, err_msg, prompt):
        """
        Prompt the user with an error message
        """
        # Prompt the user with the error, locking the original prompt until
        #  acknowledged by the user
        failurePrompt = qt.QErrorMessage(prompt)

        # Add some details on what's happening for the user
        failurePrompt.setWindowTitle("PATH ERROR!")

        # Show the message
        failurePrompt.showMessage(err_msg)
        failurePrompt.exec()

    def _attemptOutputPathUpdate(self, prompt: qt.QDialog, widget: ctk.ctkPathLineEdit):
        """
        Validates the output path provided by a user, only closing the
        associated prompt if it was valid.
        """
        # Strip whitespace to avoid a "space" path
        output_path_str = widget.currentPath.strip()

        if not output_path_str:
            # Prompt the user with the error
            err_msg = "Output path was empty"
            self._linkedPathErrorPrompt(err_msg, prompt)

            # Reset it to our prior managed directory for convenience sakes
            widget.currentPath = str(self.bound_task.output_dir)

            # Return early, which keeps the prompt active
            return

        # Convert it to a Path for ease of use
        output_path = Path(output_path_str)

        # Otherwise, try to update the task's path; we rely on its validation
        #  to ensure parity with any other checks
        err_msg = self.bound_task.set_output_dir(output_path)

        # If we got an error message, prompt the user about why and return
        if err_msg:
            self._linkedPathErrorPrompt(err_msg, prompt)

            # Return, keeping the prompt alive
            return
        # Otherwise, close the prompt with an "accepted" signal
        else:
            prompt.accept()

    def update(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        """
        Called whenever a new data-unit is in focus.
        Populate the volume combo, select primary, and fire off initial layers.
        """
        self.data_unit = data_unit
        # sync segmentation editor
        self.segmentEditorWidget.setSegmentationNode(self.data_unit.segmentation_node)
        print(f"Orientation: {self.currentOrientation}")
        print(
            f"list(data_unit.volume_nodes.values()) = {list(self.data_unit.volume_nodes.values())}"
        )

        self.layoutHandler = LayoutHandler(
            list(self.data_unit.volume_nodes.values()),
            self.currentOrientation
        )
        self.layoutHandler.apply_layout()
        self._updatedSaveButtonState()

    def _save(self) -> None:
        err = self.bound_task.save()
        self.saveCompletePrompt(err)

    def saveCompletePrompt(self, err_msg: Optional[str]) -> None:
        if err_msg is None:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Success!")
            seg_out, __ = self.bound_task.output_manager.get_output_destinations(
                self.bound_task.data_unit
            )
            msg.setText(
                f"Segmentation '{self.bound_task.data_unit.uid}' saved to:\n{seg_out.resolve()}"
            )
            msg.addButton(_("Confirm"), qt.QMessageBox.AcceptRole)
            msg.exec()
        else:
            errBox = qt.QErrorMessage()
            errBox.setWindowTitle("ERROR!")
            errBox.showMessage(err_msg)
            errBox.exec()

    ## GUI SYNCHRONIZATION ##
    def enter(self) -> None:
        # Ensure the segmentation editor widget it set up correctly
        if self.segmentEditorWidget:
            self.segmentEditorWidget.enter()

    def exit(self) -> None:
        # Ensure the segmentation editor widget handles itself before hiding
        if self.segmentEditorWidget:
            self.segmentEditorWidget.exit()

    def _updatedSaveButtonState(self) -> None:
        # Ensure the button is active on when we're ready to save
        can_save = self.bound_task.can_save()
        self.saveButton.setEnabled(can_save)
        tip = (
            _("Saves the current segmentation!")
            if can_save
            else _("Cannot save: no valid output directory.")
        )
        self.saveButton.setToolTip(tip)


class MultiContrastSegmentationEvaluationTask(
    TaskBaseClass[MultiContrastSegmentationEvaluationDataUnit]
):
    def __init__(self, user: str):
        super().__init__(user)
        self.gui: Optional[MultiContrastSegmentationEvaluationGUI] = None
        self.output_dir: Optional[Path] = None
        self.output_manager: Optional[_MultiContrastOutputManager] = None
        self.data_unit: Optional[MultiContrastSegmentationEvaluationDataUnit] = None

    def setup(self, container: qt.QWidget) -> None:
        print(f"Running {self.__class__.__name__} setup!")
        self.gui = MultiContrastSegmentationEvaluationGUI(self)
        layout = self.gui.setup()
        container.setLayout(layout)
        if self.data_unit:
            self.gui.update(self.data_unit)
        self.gui.enter()

    def receive(self, data_unit: MultiContrastSegmentationEvaluationDataUnit) -> None:
        # Track the data unit for later
        self.data_unit = data_unit
        # Display primary volume + segmentation overlay
        slicer.util.setSliceViewerLayers(
            background=data_unit.primary_volume_node,
            foreground=data_unit.segmentation_node,
            fit=True,
        )
        # If we have GUI, update it as well
        if self.gui:
            self.gui.update(data_unit)

    def cleanup(self) -> None:
        # Break the cyclical link with our GUI so garbage collection can run
        self.gui = None

    def save(self) -> Optional[str]:
        if self.can_save():
            return self.output_manager.save_segmentation(self.data_unit)
        return None

    def can_save(self) -> bool:
        """
        Shortcut for checking whether we can save the current segmentation or
         not. Checks three things:
        * We have set an output path,
        * That output path exists, and
        * That output path is a directory (and thus, files can be placed within it)
        :return: True if we are ready to save, false otherwise
        """
        return self.output_dir and self.output_dir.exists() and self.output_dir.is_dir()

    def autosave(self) -> Optional[str]:
        result = super().autosave()
        if self.gui:
            self.gui.saveCompletePrompt(result)

    def enter(self) -> None:
        if self.gui:
            self.gui.enter()

    def exit(self) -> None:
        if self.gui:
            self.gui.exit()

    @classmethod
    def getDataUnitFactories(cls) -> dict[str, DataUnitFactory]:
        """
        We currently only support one data unit type, so we only provide it to
         the user
        """
        return {"Segmentation": MultiContrastSegmentationEvaluationDataUnit}

    ## Utils ##
    def set_output_dir(self, new_path: Path) -> Optional[str]:
        """
        Update the output directory; returns an error message if it failed!
        """
        # Confirm the directory exists
        if not new_path.exists():
            err = f"Error: Data path does not exist: {new_path}"
            return err

        # Confirm that it is a directory
        if not new_path.is_dir():
            err = f"Error: Data path was not a directory: {new_path}"
            return err

        # If that all ran, update our data path to the new data path
        self.output_dir = new_path
        print(f"Output path set to: {self.output_dir}")
        self.output_manager = _MultiContrastOutputManager(self.output_dir, self.user)
        return None


class _MultiContrastOutputManager:
    # TODO Make this more general as it is nearly identical to the original "OutputManager"
    def __init__(self, output_dir: Path, user: str):
        self.output_dir = output_dir
        self.user = user

    def save_segmentation(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> Optional[str]:
        # Calculate the designation paths for our files
        segmentation_out, sidecar_out = self.get_output_destinations(data_unit)

        # Create the directories needed for these outputs
        segmentation_out.parent.mkdir(parents=True, exist_ok=True)
        sidecar_out.parent.mkdir(parents=True, exist_ok=True)

        # Attempt to save our results
        try:
            # Save the node
            self._save_segmentation(data_unit, segmentation_out)

            # Save/update the side-car file, if it exists
            self._save_sidecar(data_unit, sidecar_out)

            # Return nothing, indicating a successful save
            return None
        except Exception as e:
            # If any error occurred, return a string version of it for reporting
            return str(e)

    def get_output_destinations(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit
    ) -> (Path, Path):
        """
        Get the output paths for the files managed by this manager
        :param data_unit: The data unit whose data will be saved
        :return: Two paths, one per output file:
            * The path to the (.nii.gz) segmentation file
            * The path to the (.json) sidecar file, corresponding to the prior
        """
        # Define the "target" output directory
        target_dir = self.output_dir / f"{data_unit.uid}/anat/"

        # File name, before extensions
        fname = f"{data_unit.uid}_{self.user}_seg"

        # Define the target output file placement
        segmentation_out = target_dir / f"{fname}.nii.gz"

        # Define the path for our side-care
        sidecar_out = target_dir / f"{fname}.json"

        return segmentation_out, sidecar_out

    @staticmethod
    def _save_segmentation(
        data_unit: MultiContrastSegmentationEvaluationDataUnit, target_file: Path
    ):
        """
        Save the data unit's currently tracked segmentation to the designated
        output
        """
        # Extract the relevant node data from the data unit
        seg_node = data_unit.segmentation_node
        vol_node = (
            data_unit.primary_volume_node
        )  # THIS IS THE MAIN DIFFERENCE BETWEEN THIS MULTICONTRAST OUTPUT MANAGER
        # AND THE ORIGINAL OUTPUT MANAGER

        # Try to save the segmenattion using them
        save_segmentation_to_nifti(seg_node, vol_node, target_file)

    def _save_sidecar(
        self, data_unit: MultiContrastSegmentationEvaluationDataUnit, target_file: Path
    ):
        # Check for an existing sidecar, and use it as our basis if it exists
        fname = str(data_unit.segmentation_path).split(".")[0]

        # Read in the existing side-car file first, if possible
        sidecar_file = Path(f"{fname}.json")
        if sidecar_file.exists():
            with open(sidecar_file) as fp:
                sidecar_data = json.load(fp)
        else:
            sidecar_data = dict()

        # New entry
        entry_time = datetime.now()
        new_entry = {
            "Name": "Segmentation Review [CART]",
            "Author": self.user,
            "Version": VERSION,
            "Date": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Add a new entry to the side-car's contents
        generated_by = sidecar_data.get("GeneratedBy", [])
        generated_by.append(new_entry)
        sidecar_data["GeneratedBy"] = generated_by

        # Write the sidecar file to our target file
        with open(target_file, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)
