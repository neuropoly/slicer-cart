from pathlib import Path
from typing import TYPE_CHECKING

import ctk
import qt
from slicer.i18n import tr as _

from CARTLib.utils.formatting import FilePathFormatter, FilePathEditorWidget
from CARTLib.utils.widgets import CARTSegmentationEditorWidget

from SegmentationConfig import SegmentationConfig

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're perfect
    import PyQt5.Qt as qt
    # Avoid a cyclic reference
    from SegmentationTask import SegmentationTask


class SegmentationGUI:
    def __init__(self, bound_task: "SegmentationTask"):
        self.bound_task = bound_task

        # TODO: Make this configurable
        extension = ".nii.gz"

        # Output file formatters; tracked so they can be dynamically updated
        self.editFileFormatter: FilePathFormatter = FilePathFormatter()
        self.editFileFormatter.extension = extension
        self.editFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_UID_PLACEHOLDER, bound_task.data_unit.uid
        )
        self.customFileFormatter: FilePathFormatter = FilePathFormatter()
        self.customFileFormatter.extension = extension
        self.customFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_UID_PLACEHOLDER, bound_task.data_unit.uid
        )
        self.customFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_SHORT_NAME_PLACEHOLDER, "custom"
        )
        self.customFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_LONG_NAME_PLACEHOLDER, "segmentation_custom"
        )
        self.customFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_FILENAME_PLACEHOLDER,
            f"{bound_task.data_unit.uid}_custom",
        )

        # Segment editor; tracked so it can be refreshed
        self._segmentEditorWidget: CARTSegmentationEditorWidget = None

    def setup(self) -> qt.QFormLayout:
        # Initialize the layout we'll insert everything into
        formLayout = qt.QFormLayout(None)

        # "Edits to Save" selector
        editsToSaveLabel = qt.QLabel(_("Edits to Save: "))
        editsToSaveSelector = ctk.ctkCheckableComboBox()
        editsToSaveToolTip = _(
            "Only edits made to the segmentations selected here will be saved; "
            "all others can be viewed and modified, but their edits will NOT be saved!"
        )
        editsToSaveLabel.setToolTip(editsToSaveToolTip)
        editsToSaveSelector.setToolTip(editsToSaveToolTip)
        for i, k in enumerate(self.bound_task.segmentation_features):
            editsToSaveSelector.addItem(k)
            # Sync the check-state
            checkModel = editsToSaveSelector.checkableModel()
            idx = checkModel.index(i, 0)
            # KO: PythonQT is not forthcoming about where the "real" enum is,
            #  so we hard code it here. If you find the enum, please fix this garbage.
            checked = (k in self.bound_task.segmentations_to_save) * 2
            editsToSaveSelector.setCheckState(idx, checked)

        # When the selection changes, update our logic to match
        def selectionChanged():
            checkedSegments = [
                editsToSaveSelector.itemText(i.row())
                for i in editsToSaveSelector.checkedIndexes()
            ]
            self.bound_task.segmentations_to_save = checkedSegments
        editsToSaveSelector.checkedIndexesChanged.connect(selectionChanged)

        # Add them to the layout
        formLayout.addRow(editsToSaveLabel, editsToSaveSelector)

        # Save timer; prevents spam-saving to disk every time the text is edited
        saveDelayTimer = qt.QTimer(None)
        saveDelayTimer.setSingleShot(True)
        saveDelayTimer.setInterval(1000)  # 1 second

        # Edited file output format
        editPathFormatWidget = FilePathEditorWidget(self.editFileFormatter)
        editPathFormatWidget.pathFormatLabel.setText("Edited Files: ")
        editPathToolTip = _(
            "The destination specified here determines where edited segmentations will be saved."
        )
        editPathFormatWidget.pathFormatLabel.setToolTip(editPathToolTip)
        editPathFormatWidget.pathFormatEditor.setToolTip(editPathToolTip)
        formLayout.addRow(editPathFormatWidget)
        # Initialize the widget and hook everything together
        editPathFormatWidget.pathFormat = self.bound_task.edit_output_path
        editPathFormatWidget.pathFormatChanged.connect(lambda __: saveDelayTimer.start())

        # Custom file output format (default)
        customPathFormatWidget = FilePathEditorWidget(
            self.customFileFormatter, showPlaceholderList=True
        )
        customPathFormatWidget.pathFormatLabel.setText("Custom Files: ")
        customPathToolTip = _(
            "The destination specified here determines where custom (from-scratch) "
            "segmentation will be saved by default. This includes missing segmentations!"
        )
        customPathFormatWidget.pathFormatLabel.setToolTip(customPathToolTip)
        customPathFormatWidget.pathFormatEditor.setToolTip(customPathToolTip)
        formLayout.addRow(customPathFormatWidget)
        # Initialize the widget and hook everything together
        customPathFormatWidget.pathFormat = self.bound_task.default_custom_output_path
        customPathFormatWidget.pathFormatChanged.connect(
            lambda __: saveDelayTimer.start()
        )

        # Save the changes to the output path strings at-most once per second
        def saveNewPathFormats():
            # Update the edited file path
            new_str = editPathFormatWidget.pathFormat
            result_str = self.editFileFormatter.format_string(new_str)
            if result_str is None:
                new_str = ""
            self.bound_task.edit_output_path = new_str

            # Update the default custom file path
            new_str = customPathFormatWidget.pathFormat
            result_str = self.customFileFormatter.format_string(new_str)
            if result_str is None:
                new_str = ""
            self.bound_task.default_custom_output_path = new_str
        saveDelayTimer.timeout.connect(saveNewPathFormats)

        # Segmentation editor
        segmentEditorWidget = CARTSegmentationEditorWidget()
        formLayout.addRow(segmentEditorWidget)
        self._segmentEditorWidget = segmentEditorWidget

        # When the selected segmentation changes, update the formatter
        def onSelectedSegmentationChanged(__: int = None):
            # Update the file editor
            current_seg_name = segmentEditorWidget.proxySegNodeComboBox.currentText
            long_name = "_".join(current_seg_name.split(" ")[:1])
            short_name = long_name
            if long_name.lower().startswith("segmentation_"):
                short_name = short_name[len("segmentation_") :]
            self.editFileFormatter.update_placeholder(
                FilePathFormatter.DEFAULT_SHORT_NAME_PLACEHOLDER, short_name
            )
            self.editFileFormatter.update_placeholder(
                FilePathFormatter.DEFAULT_LONG_NAME_PLACEHOLDER, long_name
            )
            file_path = self.bound_task.data_unit.segmentation_paths.get(long_name)
            if file_path is None:
                file_name = f"{self.bound_task.data_unit.uid}_{short_name}"
            else:
                file_name = file_path.name.split(".")[0]
            self.editFileFormatter.update_placeholder(
                FilePathFormatter.DEFAULT_FILENAME_PLACEHOLDER, file_name
            )

            # Update the custom path editor
            self.customFileFormatter.update_placeholder(
                FilePathFormatter.DEFAULT_FILENAME_PLACEHOLDER,
                f"{self.bound_task.data_unit.uid}_custom",
            )

            # Refresh both
            editPathFormatWidget.refresh()
            customPathFormatWidget.refresh()
        segmentEditorWidget.proxySegNodeComboBox.currentIndexChanged.connect(
            onSelectedSegmentationChanged
        )
        onSelectedSegmentationChanged()

        # Add Custom Button
        # TODO: Move this to an on-init prompt instead
        addButton = qt.QPushButton("Add Custom Segmentation")
        def addCustomSeg():
            # Prompt the user with details
            ref_uid = (
                "sub-abc123"
                if self.bound_task.data_unit is None
                else self.bound_task.data_unit.uid
            )

            # Build the placeholder character set
            placeholderMap = FilePathFormatter.build_default_placeholder_map(
                uid=ref_uid,
                job_name=self.bound_task.job_profile.name
            )
            # Prompt the user with details
            # TODO; make the file extension configurable
            prompt = CustomSegmentationDialog(
                placeholder_map=placeholderMap,
                task_config=self.bound_task.local_config,
                root_path=self.bound_task.job_profile.output_path,
                extension=".nii.gz",
                initial_path_str=self.bound_task.default_custom_output_path
            )
            # If the user confirms the changes, add the custom seg.
            if prompt.exec():
                # Register the new custom segmentation
                self.bound_task.new_custom_segmentation(prompt.name, prompt.save_path, prompt.color_hex)
        addButton.clicked.connect(addCustomSeg)
        formLayout.addRow(addButton)

        # Options panel
        optionsPanel = self._buildOptionsPanel()
        formLayout.addRow(optionsPanel)

        return formLayout

    def _buildOptionsPanel(self) -> ctk.ctkCollapsibleGroupBox:
        # Group box to store everything in
        groupBox = ctk.ctkCollapsibleGroupBox()
        groupBox.setTitle(_("Options"))
        groupBoxLayout = qt.QFormLayout(None)
        groupBox.setLayout(groupBoxLayout)

        # Interpolation toggle
        interpToggle = qt.QCheckBox()
        interpLabel = qt.QLabel(_("Interpolate Volumes"))
        interpToolTip = _(
            "Whether volumes should be visualized with interpolation (smoothing)."
        )
        interpLabel.setToolTip(interpToolTip)
        interpToggle.setToolTip(interpToolTip)
        def setInterp():
            self.bound_task.should_interpolate = interpToggle.isChecked()
            self.bound_task.apply_interp()
        interpToggle.setChecked(self.bound_task.should_interpolate)
        interpToggle.toggled.connect(setInterp)
        groupBoxLayout.addRow(interpToggle, interpLabel)

        # Save blank segmentations toggle
        blankSavedToggle = qt.QCheckBox()
        blankSavedLabel = qt.QLabel(_("Save Blank Segmentations"))
        blankSavedToolTip = _(
            'Whether to create a "blank" file when a case is save with no segments.'
        )
        blankSavedLabel.setToolTip(blankSavedToolTip)
        blankSavedToggle.setToolTip(blankSavedToolTip)
        def setBlankSaved():
            self.bound_task.save_blank_segments = blankSavedToggle.isChecked()
        blankSavedToggle.setChecked(self.bound_task.save_blank_segments)
        blankSavedToggle.toggled.connect(setBlankSaved)
        groupBoxLayout.addRow(blankSavedToggle, blankSavedLabel)

        # Hide-on-start toggle
        hideOnStartToggle = qt.QCheckBox()
        hideOnStartLabel = qt.QLabel(_("Hide Editable Segments On Load"))
        hideOnStartToolTip = _(
            "Whether segments you intend to correct/review should be hidden when "
            "a new case is first loaded."
        )
        hideOnStartLabel.setToolTip(hideOnStartToolTip)
        hideOnStartToggle.setToolTip(hideOnStartToolTip)
        def setHideOnStart():
            self.bound_task.hide_editable_on_start = hideOnStartToggle.isChecked()
        hideOnStartToggle.setChecked(self.bound_task.hide_editable_on_start)
        hideOnStartToggle.toggled.connect(setHideOnStart)
        groupBoxLayout.addRow(hideOnStartToggle, hideOnStartLabel)

        return groupBox

    def selectSegmentationNode(self, node):
        self._segmentEditorWidget.setSegmentationNode(node)

    def onSavePrompt(
        self,
        saved_edited: dict[str, str],
        saved_customs: dict[str, str],
        error_edited: dict[str, str],
        error_customs: dict[str, str],
    ):
        """
        Show the user a prompt notifying them that the data unit was saved.

        Provide (hidden by default) details if the user requests it.
        """
        # The core message box
        msgBox = qt.QMessageBox()
        msgBox.setWindowTitle(_("Saved!"))
        msgBox.setStandardButtons(qt.QMessageBox.Ok)

        # Build the "main" user message
        no_saved_edited = len(saved_edited)
        no_saved_customs = len(saved_customs)
        no_error_edited = len(error_edited)
        no_error_customs = len(error_customs)
        successes = no_saved_edited + no_saved_customs
        failures = no_error_edited + no_error_customs
        msg = f"Saved data unit {self.bound_task.data_unit.uid}! {successes} segmentations were saved"
        if failures > 0:
            msg += f", {failures} segmentations were not"
        msg += "."
        msgBox.setText(_(msg))

        # Detailed text w/ save paths + error causes
        bullet_txt = "\n  ○ "
        detailed_text_cmps = []
        if no_saved_edited > 0:
            saved_custom_txt = f"Saved the following edited segmentations:"
            saved_custom_txt = bullet_txt.join([
                saved_custom_txt, *[f"{k}: {v}" for k, v in saved_edited.items()]
            ])
            detailed_text_cmps.append(saved_custom_txt)
        if no_saved_customs > 0:
            saved_custom_txt = f"Saved the following custom segmentations:"
            saved_custom_txt = bullet_txt.join([
                saved_custom_txt, *[f"{k}: {v}" for k, v in saved_customs.items()]
            ])
            detailed_text_cmps.append(saved_custom_txt)
        if no_error_edited > 0:
            saved_custom_txt = f"Did not save the following edited segmentations:"
            saved_custom_txt = bullet_txt.join([
                saved_custom_txt, *[f"{k}: {v}" for k, v in error_edited.items()]
            ])
            detailed_text_cmps.append(saved_custom_txt)
        if no_error_customs > 0:
            saved_custom_txt = f"Did not save the following custom segmentations:"
            saved_custom_txt = bullet_txt.join([
                saved_custom_txt, *[f"{k}: {v}" for k, v in error_customs.items()]
            ])
            detailed_text_cmps.append(saved_custom_txt)
        separator = "\n" + "=" * 40 + "\n"
        detailed_text = separator.join(detailed_text_cmps)
        msgBox.setDetailedText(detailed_text)

        msgBox.exec()

    def enter(self):
        self._segmentEditorWidget.enter()

    def exit(self):
        self._segmentEditorWidget.exit()

    def refresh(self):
        self.editFileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_UID_PLACEHOLDER, self.bound_task.data_unit.uid
        )
        self._segmentEditorWidget.refresh()


class CustomSegmentationDialog(qt.QDialog):
    """
    Prompt the user to created/edit a custom segmentation.
    """

    # Default to a gold-ish color
    DEFAULT_COLOR = "#fadd00"

    def __init__(
        self,
        placeholder_map: FilePathFormatter.PlaceholderMap,
        task_config: SegmentationConfig,
        root_path: Path = Path('...'),
        extension: str = ".abc",
        initial_path_str: str = "",
        parent=None
    ):
        super().__init__(parent)

        # Initial setup
        self.setWindowTitle(_("Custom Segmentation"))
        layout = qt.QFormLayout(self)
        self.setMinimumSize(400, self.minimumHeight)

        # Make all labels bold
        labelFont = qt.QFont()
        labelFont.setBold(True)

        # Name to give the new segmentation
        nameLabel = qt.QLabel(_("Name: "))
        nameLabel.setFont(labelFont)
        nameEdit = qt.QLineEdit()
        nameToolTip = _("The name this segmentation should be labelled with.")
        nameLabel.setToolTip(nameToolTip)
        nameEdit.setToolTip(nameToolTip)
        layout.addRow(nameLabel, nameEdit)
        self._nameEdit = nameEdit

        # Color picker
        colorLabel = qt.QLabel(_("Color: "))
        colorLabel.setFont(labelFont)
        colorPicker = ctk.ctkColorPickerButton()
        colorPicker.setColor(qt.QColor(self.DEFAULT_COLOR))
        colorToolTip = _(
            "The color the segmentation will display as in the editor."
        )
        colorLabel.setToolTip(colorToolTip)
        colorPicker.setToolTip(colorToolTip)
        layout.addRow(colorLabel, colorPicker)
        self.colorPicker = colorPicker

        # Output path specifier
        fileFormatter = FilePathFormatter(root_path, placeholder_map, extension)
        uid_packet = fileFormatter.placeholder_map.get(
            fileFormatter.DEFAULT_UID_PLACEHOLDER
        )
        if uid_packet is None:
            raise ValueError(
                f"{type(self).__name__} was initialized without a UID entry somehow."
            )
        uid = uid_packet[0]
        fileFormatter.update_placeholder(
            FilePathFormatter.DEFAULT_FILENAME_PLACEHOLDER, f"{uid}_custom"
        )
        pathEditorWidget = FilePathEditorWidget(
            fileFormatter, showPlaceholderList=True
        )
        pathEditorWidget.pathFormat = initial_path_str
        layout.addRow(pathEditorWidget)
        self.editPathFormatWidget = pathEditorWidget

        # When the name changes, update the preview widget as well
        def nameTextChanged(long_name: str):
            short_name = long_name
            if long_name.lower().startswith("segmentation_"):
                short_name = long_name[len("segmentation_"):]
            fileFormatter.update_placeholder(
                fileFormatter.DEFAULT_SHORT_NAME_PLACEHOLDER, short_name
            )
            fileFormatter.update_placeholder(
                fileFormatter.DEFAULT_LONG_NAME_PLACEHOLDER, long_name
            )
            uid_packet = fileFormatter.placeholder_map.get(fileFormatter.DEFAULT_UID_PLACEHOLDER)
            if uid_packet is None:
                raise ValueError(f"{type(self).__name__} was initialized without a UID entry somehow.")
            uid = uid_packet[0]
            fileFormatter.update_placeholder(
                fileFormatter.DEFAULT_FILENAME_PLACEHOLDER, f"{uid}_{short_name}"
            )
            pathEditorWidget.refresh()
        nameEdit.textChanged.connect(nameTextChanged)
        nameTextChanged("")

        # "Pseudo-Stretch" to push the buttons to the bottom
        stretch = qt.QWidget(None)
        policy = stretch.sizePolicy
        policy.setVerticalStretch(1)
        stretch.setSizePolicy(policy)
        layout.addRow(stretch)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Apply | qt.QDialogButtonBox.Cancel
        )
        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.ApplyRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")
        buttonBox.clicked.connect(onButtonClicked)
        layout.addRow(buttonBox)

        # Ensure the user can only confirm if the name is valid
        applyButton: qt.QPushButton = buttonBox.button(qt.QDialogButtonBox.Apply)
        def validatePath(*__):
            # It's immediately invalid if the name is blank or already taken
            if (
                nameEdit.text.strip() == ""
                or nameEdit.text in task_config.custom_segmentations
            ):
                applyButton.setEnabled(False)
                return
            # Confirm the updated, formatted name is valid as well
            formatted_str = fileFormatter.format_string(pathEditorWidget.pathFormat)
            applyButton.setEnabled(formatted_str is not None)
        nameEdit.textChanged.connect(validatePath)
        pathEditorWidget.pathFormatChanged.connect(validatePath)
        validatePath()

    @property
    def name(self) -> str:
        # noinspection PyTypeChecker
        return self._nameEdit.text

    @property
    def save_path(self) -> str:
        return self.editPathFormatWidget.pathFormat

    @property
    def color_hex(self):
        return self.colorPicker.color.name()
