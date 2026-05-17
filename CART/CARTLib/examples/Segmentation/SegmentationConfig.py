from enum import Enum
from typing import Optional, TYPE_CHECKING

import ctk
import qt

from slicer.i18n import tr as _

from CARTLib.utils.config import DictBackedConfig, JobProfileConfig
from CARTLib.utils.data import SegmentationResourceConfig

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


class SegmentationFileStructure(Enum):
    BIDS = "BIDS"
    FolderPerCase = "Folder-per-Case"


class SegmentationFileFormat(Enum):
    NIFTI = "NIfTI"
    NRRD = "NRRD"


class SegmentationConfig(DictBackedConfig):
    """
    Configuration manager for the MultiContrast task
    """

    CONFIG_KEY = "multi_contrast_segmentation"

    def __init__(self, parent_config: JobProfileConfig):
        super().__init__(parent_config=parent_config)

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## CONFIG ENTRIES ##
    SHOULD_INTERPOLATE_KEY = "should_interpolate"

    @property
    def should_interpolate(self) -> bool:
        return self.get_or_default(self.SHOULD_INTERPOLATE_KEY, True)

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self.backing_dict[self.SHOULD_INTERPOLATE_KEY] = new_val
        self.has_changed = True

    SAVE_BLANK_SEGMENTATIONS_KEY = "save_blanks"

    @property
    def save_blank_segmentations(self) -> bool:
        return self.get_or_default(self.SAVE_BLANK_SEGMENTATIONS_KEY, True)

    @save_blank_segmentations.setter
    def save_blank_segmentations(self, new_val: bool):
        self.backing_dict[self.SAVE_BLANK_SEGMENTATIONS_KEY] = new_val
        self.has_changed = True

    FILE_STRUCTURE_KEY = "file_structure"

    @property
    def file_structure(self) -> SegmentationFileStructure:
        val = self.get_or_default(
            self.FILE_STRUCTURE_KEY, SegmentationFileStructure.BIDS.value
        )
        return SegmentationFileStructure(val)

    @file_structure.setter
    def file_structure(self, new_structure: SegmentationFileStructure):
        self.backing_dict[self.FILE_STRUCTURE_KEY] = new_structure.value
        self.has_changed = True

    FILE_FORMAT_KEY = "file_format"

    @property
    def file_format(self) -> SegmentationFileFormat:
        val = self.get_or_default(
            self.FILE_FORMAT_KEY, SegmentationFileFormat.NIFTI.value
        )
        return SegmentationFileFormat(val)

    @file_format.setter
    def file_format(self, new_format: SegmentationFileFormat):
        self.backing_dict[self.FILE_FORMAT_KEY] = new_format.value
        self.has_changed = True

    ## OVERRIDES ##
    def generateGUILayout(self) -> tuple[str, Optional[qt.QLayout]]:
        return _("Segmentation Configuration"), SegmentationConfigGUILayout(self)


class ExtendedSegmentationResourceConfig(SegmentationResourceConfig):
    """
    Configuration manager for a specific segmentation resource, tuned for this task.
    """

    SEGMENTS_KEY = "segments"

    @property
    def segments(self) -> list[dict]:
        # Map of the segments this resource is handling;
        # Maps value (with the segmentation) to segment name and color (in hex format)
        return self.get_or_default(
            self.SEGMENTS_KEY, list()
        )

    @qt.Slot()
    def mark_changed(self):
        # Written as a slot to make GUI connections easier.
        self.has_changed = True

    NAME_KEY = "Name"
    VALUE_KEY = "Value"
    COLOR_KEY = "Color"

    def add_segment(self, label: str, value: int, color: str):
        """
        Add a new segment with the given values
        """
        self.segments.append({
            self.NAME_KEY: label,
            self.VALUE_KEY: value,
            self.COLOR_KEY: color
        })
        self.mark_changed()

    def drop_segment(self, idx: int) -> dict:
        """
        Drop configuration options associated with the provided segment
        """
        self.mark_changed()
        return self.segments.pop(idx)

    HEADER_MAP = {
        NAME_KEY: 0,
        VALUE_KEY: 1,
        COLOR_KEY: 2
    }

    def buildSegmentTableGUI(self, layout: qt.QFormLayout):
        # Table widget to place the results within
        # TODO: Make QT model/view wrappers for this to ensure sync is maintained
        table: qt.QTableWidget = qt.QTableWidget(0, 3, None)
        # Update the headers to be clearer + translated
        header_labels = [_(f"Segment {k}") for k in self.HEADER_MAP.keys()]
        table.setHorizontalHeaderLabels(header_labels)

        # Make the table behave in a sensible manner
        table.setSizeAdjustPolicy(qt.QAbstractScrollArea.AdjustToContents)
        table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        table.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        table.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)
        table.setSizePolicy(
            qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding
        )

        # Hide the vertical header, as it's not relevant to the users
        table.verticalHeader().setVisible(False)

        # Make the columns stretch to fill available space
        table.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Stretch)

        # Give ourselves 3 columns, as QT is too dumb to figure it out otherwise
        table.setColumnCount(3)

        # Simple helper function to avoid duplicate code
        def _setTableDataFor(idx, name, value, color):
            # If this index is larger than the current number of rows, give ourselves a new row
            if idx >= table.rowCount:
                table.setRowCount(table.rowCount + 1)

            nameItem = qt.QTableWidgetItem(name)
            valueItem = qt.QTableWidgetItem(str(value))
            colorItem = qt.QTableWidgetItem(color)

            # Disable the color from being edited; its handled another way
            colorItem.setFlags(
                colorItem.flags() & ~qt.Qt.ItemIsEditable
            )

            # Set the color background + text color
            qColor = qt.QColor(color)
            colorItem.setBackground(qColor)
            # Make the text black or white depending on how bright the new color is
            if qColor.lightness() > 100:
                colorItem.setForeground(qt.QBrush(qt.QColor("#000000")))
            else:
                colorItem.setForeground(qt.QBrush(qt.QColor("#FFFFFF")))

            # Add it to the table
            table.setItem(idx, self.HEADER_MAP[self.NAME_KEY], nameItem)
            table.setItem(idx, self.HEADER_MAP[self.VALUE_KEY], valueItem)
            table.setItem(idx, self.HEADER_MAP[self.COLOR_KEY], colorItem)

        # Instantiate w/ our starting values
        for i, val_dict in enumerate(self.segments):
            _setTableDataFor(
                i,
                val_dict.get(self.NAME_KEY),
                val_dict.get(self.VALUE_KEY),
                val_dict.get(self.COLOR_KEY),
            )

        # Add the table to the layout
        layout.addRow(table)

        # Add buttons add, edit, and remove entries in the table
        addButton = qt.QPushButton(_("New Class"))
        addToolTip = _(
            "Adds a new segmentation class for multi-class segmentations. "
            "If none are defined, will use a single class of 1 instead."
        )
        addButton.setToolTip(addToolTip)
        deleteButton = qt.QPushButton(_("Delete Class"))
        deleteToolTip = _(
            "Deletes the selected segmentation class from the table above."
        )
        deleteButton.setToolTip(deleteToolTip)
        buttonPanel = qt.QWidget(None)
        buttonLayout = qt.QHBoxLayout(buttonPanel)
        buttonLayout.addWidget(addButton)
        buttonLayout.addWidget(deleteButton)
        layout.addRow(buttonPanel)

        # When the selections change, enable/disable the edit and delete buttons
        @qt.Slot()
        def selectionChanged():
            selected_indices = table.selectedIndexes()
            selected_rows = len({idx.row() for idx in selected_indices})
            deleteButton.setEnabled(selected_rows > 0)

        table.itemSelectionChanged.connect(selectionChanged)
        selectionChanged()

        # When the contents of the table change, update our backing dict to match
        @qt.Slot(int, int)
        def onCellChanged(row: int, col: int):
            # Get the new value inserted into this location
            item: qt.QTableWidgetItem = table.item(row, col)
            new_val = item.text()
            key = list(self.HEADER_MAP.keys())[col]

            # If the item is our "value" column, make sure it's an integer before proceeding
            if key == self.VALUE_KEY:
                try:
                    new_val = int(new_val)
                    if new_val == 0:
                        raise ValueError()
                except ValueError:
                    # If we couldn't, restore the original value and tell the user what happened
                    old_val = self.segments[row].get(self.VALUE_KEY)
                    item.setText(str(old_val))
                    qt.QMessageBox.critical(
                        table,
                        _("Invalid Value") + f" '{new_val}'",
                        _(f"Value must be a non-zero integer! Previous value {old_val} was restored."),
                        qt.QMessageBox.Ok,
                    )
                    return

            # Update ourselves to match
            segment_dict = self.segments[row]
            segment_dict[key] = new_val

            # Mark ourselves as being changed
            self.has_changed = True

        table.cellChanged.connect(onCellChanged)

        # Add button simply creates a new row w/ default values the user can edit later
        @qt.Slot()
        def addClicked():
            # Find the smallest positive value not already taken
            value = 1
            taken_vals = {x[self.VALUE_KEY] for x in self.segments}
            while value in taken_vals:
                value += 1

            # The other defaults
            name = ""
            color = "#fadd00"  # Gold-ish

            # Create an (empty) dictionary and place it into our segments;
            # it will be populated when the table updates
            self.segments.append(dict())

            # Update the table
            try:
                _setTableDataFor(table.rowCount, name, value, color)
            except Exception as e:
                # If that failed somehow, clean up the (likely malformed) new segment
                self.segments.pop(table.rowCount)
                raise e

        addButton.clicked.connect(addClicked)

        # Delete button deletes all selected rows
        @qt.Slot()
        def deleteClicked():
            selected_rows = {idx.row() for idx in table.selectedIndexes()}
            for r in selected_rows:
                # Drop the row in the table itself
                table.removeRow(r)

                # If that worked correctly, remove it from our backing config too
                self.drop_segment(r)

        deleteButton.clicked.connect(deleteClicked)

        # Double-clicking on a color cell brings up the color picker instead
        @qt.Slot(int, int)
        def onCellDoubleClicked(row: int, col: int):
            # If this row does not correspond to the color column, do nothing
            if self.HEADER_MAP[self.COLOR_KEY] != col:
                return

            # Get the item at this location
            item: qt.QTableWidgetItem = table.item(row, col)

            # Close the (now open) persistent editor
            table.closePersistentEditor(item)

            # Request the user provide a new color w/ CTK's color dialog
            init_color = qt.QColor(item.text())
            color_dialog = ctk.ctkColorDialog()
            # If the user backed out, return without proceeding further
            qColor: qt.QColor = color_dialog.getColor(init_color, None)
            if qColor.value() == 0:
                # KO: Note that this also represents pure-black, which a user could
                #  theoretically select. Slicer doesn't provide an easy way to
                #  distinguish between these, however, and given how unlikely it
                #  is that a user would do so, this code should suffice for now,
                #  even if it isn't perfect.
                return

            # Update our item to have this new value
            item.setText(qColor.name())
            item.setBackground(qColor)

            # Make the text black or white depending on how bright the new color is
            if qColor.lightness() > 100:
                item.setForeground(qt.QBrush(qt.QColor("#000000")))
            else:
                item.setForeground(qt.QBrush(qt.QColor("#FFFFFF")))

        table.cellDoubleClicked.connect(onCellDoubleClicked)

        # Any contents changing should mark ourselves as being changed
        table.cellChanged.connect(self.mark_changed)


class SegmentationConfigGUILayout(qt.QFormLayout):
    def __init__(self, config: SegmentationConfig, parent = None, ):
        super().__init__(parent)

        # Output folder structure selection
        fileStructureComboBox = qt.QComboBox(None)
        fileStructureComboBox.addItems([x.value for x in SegmentationFileStructure])
        fileStructureComboBox.setCurrentText(config.file_structure.value)
        fileStructureLabel = qt.QLabel(_("Output File Structure:"))
        self.addRow(fileStructureLabel, fileStructureComboBox)

        # Output file structure selection
        fileFormatComboBox = qt.QComboBox(None)
        fileFormatComboBox.addItems([x.value for x in SegmentationFileFormat])
        fileFormatComboBox.setCurrentText(config.file_format.value)
        fileFormatLabel = qt.QLabel(_("Output File Format:"))
        self.addRow(fileFormatLabel, fileFormatComboBox)

        # Toggle-able options
        toggleLayout = qt.QFormLayout(None)
        self.addRow(toggleLayout)

        ## Whether to interpolate volumes on-load
        interpolateVolumesCheckBox = qt.QCheckBox()
        interpolateVolumesLabel = qt.QLabel(
            _("Interpolate (smooth out) pixels in volumes.")
        )
        toggleLayout.addRow(interpolateVolumesCheckBox, interpolateVolumesLabel)
        interpolateVolumesCheckBox.setChecked(config.should_interpolate)

        ## Whether to save blank segmentations
        saveEmptySegmentsCheckBox = qt.QCheckBox()
        saveEmptySegmentsLabel = qt.QLabel(
            _("Save Empty Segmentations (will create 'blank' output files).")
        )
        toggleLayout.addRow(saveEmptySegmentsCheckBox, saveEmptySegmentsLabel)
        saveEmptySegmentsCheckBox.setChecked(config.save_blank_segmentations)

        # Connections
        @qt.Slot(str)
        def fileStructureChanged(new_val: str):
            config.file_structure = SegmentationFileStructure(new_val)
        fileStructureComboBox.currentTextChanged.connect(fileStructureChanged)

        @qt.Slot(str)
        def fileFormatChanged(new_val: str):
            config.file_format = SegmentationFileFormat(new_val)
        fileFormatComboBox.currentTextChanged.connect(fileFormatChanged)

        @qt.Slot()
        def interpolationChanged():
            config.should_interpolate = interpolateVolumesCheckBox.isChecked()
        interpolateVolumesCheckBox.toggled.connect(interpolationChanged)

        @qt.Slot()
        def saveEmptySegmentsChanged():
            config.save_blank_segmentations = saveEmptySegmentsCheckBox.isChecked()
        saveEmptySegmentsCheckBox.toggled.connect(saveEmptySegmentsChanged)
