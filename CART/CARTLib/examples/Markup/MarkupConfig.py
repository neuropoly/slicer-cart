from typing import Optional

import qt
from slicer.i18n import tr as _

from CARTLib.utils.config import DictBackedConfig, JobProfileConfig

from MarkupIO import MarkupOutputStructure, MarkupOutputFormat


class MarkupConfig(DictBackedConfig):
    CONFIG_KEY = "markup"

    def __init__(self, parent_config: JobProfileConfig = None):
        super().__init__(parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    OUTPUT_STRUCTURE_KEY = "output_structure"

    @property
    def output_structure(self) -> "MarkupOutputStructure":
        str_val = self.get_or_default(
            self.OUTPUT_STRUCTURE_KEY, MarkupOutputStructure.BIDS.value
        )
        return MarkupOutputStructure(str_val)

    @output_structure.setter
    def output_structure(self, new_val: MarkupOutputStructure):
        self.backing_dict[self.OUTPUT_STRUCTURE_KEY] = new_val.value
        self.has_changed = True

    OUTPUT_FORMAT_KEY = "output_format"

    @property
    def output_format(self):
        str_val = self.get_or_default(
            self.OUTPUT_FORMAT_KEY, MarkupOutputFormat.CSV.value
        )
        return MarkupOutputFormat(str_val)

    @output_format.setter
    def output_format(self, new_val: MarkupOutputFormat):
        self.backing_dict[self.OUTPUT_FORMAT_KEY] = new_val.value
        self.has_changed = True

    # ALLOW_DUPLICATES_KEY = "allow_duplicates"
    #
    # @property
    # def allow_duplicates(self) -> bool:
    #     return self.get_or_default(self.ALLOW_DUPLICATES_KEY, False)
    #
    # @allow_duplicates.setter
    # def allow_duplicates(self, new_val: bool):
    #     self.backing_dict[self.ALLOW_DUPLICATES_KEY] = new_val
    #     self.has_changed = True
    #
    # HIDE_TO_EDIT = "hide_to_edit"
    #
    # @property
    # def hide_to_edit(self) -> bool:
    #     return self.get_or_default(self.HIDE_TO_EDIT, False)
    #
    # @hide_to_edit.setter
    # def hide_to_edit(self, new_val: bool):
    #     self.backing_dict[self.HIDE_TO_EDIT] = new_val
    #     self.has_changed = True
    #
    def generateGUILayout(self) -> Optional[tuple[str, qt.QLayout]]:
        return _("Markup Configuration"), MarkupConfigGUILayout(self)


class MarkupConfigGUILayout(qt.QFormLayout):
    def __init__(self, config: MarkupConfig, parent = None):
        super().__init__(parent)

        # Output folder structure selection
        fileStructureComboBox = qt.QComboBox(None)
        fileStructureToolTip = _(
            "How the folders within the output directory should be organized."
        )
        fileStructureComboBox.setToolTip(fileStructureToolTip)
        fileStructureComboBox.addItems([x.value for x in MarkupOutputStructure])
        fileStructureComboBox.setCurrentText(config.output_structure.value)
        fileStructureLabel = qt.QLabel(_("Output File Structure:"))
        fileStructureLabel.setToolTip(fileStructureToolTip)
        self.addRow(fileStructureLabel, fileStructureComboBox)

        # Output file structure selection
        fileFormatComboBox = qt.QComboBox(None)
        fileFormatToolTip = _(
            "What file format (of Slicer's supported options) the markups should be saved in."
        )
        fileFormatComboBox.setToolTip(fileFormatToolTip)
        fileFormatComboBox.addItems([x.value for x in MarkupOutputFormat])
        fileFormatComboBox.setCurrentText(config.output_structure.value)
        fileFormatLabel = qt.QLabel(_("Output File Format:"))
        fileFormatLabel.setToolTip(fileFormatToolTip)
        self.addRow(fileFormatLabel, fileFormatComboBox)

        # Toggle-able options
        toggleLayout = qt.QFormLayout(None)
        self.addRow(toggleLayout)

        ## TODO
        # ## Duplicate Markups
        # duplicateMarkupsCheckBox = qt.QCheckBox()
        # duplicateMarkupsCheckBox.setChecked(config.allow_duplicates)
        # duplicateMarkupsLabel = qt.QLabel(_("Allow Duplicate Markups"))
        # toggleLayout.addRow(duplicateMarkupsCheckBox, duplicateMarkupsLabel)
        #
        # ## Hide To-Edit Segments on Load
        # hideEditSegmentsCheckBox = qt.QCheckBox()
        # hideEditSegmentsCheckBox.setChecked(config.hide_to_edit)
        # hideEditSegmentsLabel = qt.QLabel(
        #     _("Initially Hide To-Edit Markups")
        # )
        # toggleLayout.addRow(
        #     hideEditSegmentsCheckBox, hideEditSegmentsLabel
        # )

        # Connections
        @qt.Slot(str)
        def onStructureChanged(new_val: str):
            config.output_structure = MarkupOutputStructure(new_val)
        fileStructureComboBox.currentTextChanged.connect(onStructureChanged)
        fileStructureComboBox.setCurrentText(config.output_structure.value)

        @qt.Slot(str)
        def onFormatChanged(new_val: str):
            config.output_format = MarkupOutputFormat(new_val)
        fileFormatComboBox.currentTextChanged.connect(onFormatChanged)
        fileFormatComboBox.setCurrentText(config.output_format.value)

        ## TODO
        # @qt.Slot(None)
        # def onDuplicatesToggled():
        #     config.allow_duplicates = duplicateMarkupsCheckBox.isChecked()
        # duplicateMarkupsCheckBox.toggled.connect(onDuplicatesToggled)
        # duplicateMarkupsCheckBox.setChecked(config.allow_duplicates)
        #
        # @qt.Slot(None)
        # def onHideEditsToggled():
        #     config.hide_to_edit = hideEditSegmentsCheckBox.isChecked()
        # hideEditSegmentsCheckBox.toggled.connect(onHideEditsToggled)
        # hideEditSegmentsCheckBox.setChecked(config.hide_to_edit)
