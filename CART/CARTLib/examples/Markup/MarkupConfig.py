from collections import namedtuple
from typing import Optional, TYPE_CHECKING

import ctk
import qt
from slicer.i18n import tr as _

from CARTLib.utils.config import DictBackedConfig, JobProfileConfig

from MarkupIO import MarkupOutputStructure, MarkupOutputFormat

if TYPE_CHECKING:
    # Provide some type references for QT, even if they're not
    #  perfectly useful.
    import PyQt5.Qt as qt


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

    def generateGUILayout(self) -> Optional[tuple[str, qt.QLayout]]:
        return _("Markup Configuration"), MarkupConfigGUILayout(self)


class EditableMarkupResourceConfig(DictBackedConfig):
    @classmethod
    def default_config_label(cls) -> str:
        raise ValueError("You should use `config_key_override` instead!")

    ## CONFIG OPTIONS ##
    MARKUPS_KEY = "markups"
    MARKUP_VALUES = {
        "label": 0,
        "value": 1,
        "color": 2
    }
    MarkupPointEntry = namedtuple(
        "MarkupPoint",
        MARKUP_VALUES.keys()
    )

    @property
    def markups(self) -> list[MarkupPointEntry]:
        """
        Map tracking fiducials the user expects to find within this a markup node.
        """
        return [
            self.MarkupPointEntry(**x) for x in self._raw_markup_data
        ]

    @property
    def _raw_markup_data(self) -> list[dict]:
        """
        Protected accessor for the "raw" (read/write directly to JSON) data
        """
        return self.get_or_default(self.MARKUPS_KEY, list())

    @qt.Slot()
    def mark_changed(self):
        self.has_changed = True

    def add_markup(
        self, label: str, color: str, value: Optional[int] = None
    ) -> MarkupPointEntry:
        """
        Add a new markup, from scratch, to the end of the configuration list
        """
        # Use the namedtuple to ensure organization
        new_markup = self.MarkupPointEntry(label, value, color)
        # Add its contents to our configuration list
        self._raw_markup_data.append(
            new_markup._asdict()
        )
        # Mark ourselves as having been changed
        self.mark_changed()
        # Return the result
        return new_markup

    def drop_markup(self, idx: int):
        """
        Drop the specified markup from the configuration list
        """
        self.mark_changed()
        self._raw_markup_data.pop(idx)

    ## CONFIG GUI ##
    def buildMarkupTableGUI(self, layout: qt.QFormLayout):
        ## MAIN TABLE ##
        table: qt.QTableWidget = qt.QTableWidget(None)

        # Give ourselves 3 columns, as QT is too dumb to figure it out otherwise
        table.setColumnCount(3)

        # Translate and display the header values
        header_labels = [_(f"Markup {k.capitalize()}") for k in self.MARKUP_VALUES.keys()]
        table.setHorizontalHeaderLabels(header_labels)

        # Sensible default behaviour, as QT doesn't provide it
        table.setSizeAdjustPolicy(qt.QAbstractScrollArea.AdjustToContents)
        table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        table.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        table.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)
        table.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

        # Hide the vertical header, as its (probably) not relevant
        table.verticalHeader().setVisible(False)

        # Make the columns stretch to fill available space
        table.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Stretch)

        # Helper functions to avoid duplicate code
        def _setItemColor(
            item: qt.QTableWidgetItem, newColor: qt.QColor
        ):
            # Update our item to have the new value
            item.setText(newColor.name())
            item.setBackground(newColor)
            # Update the text to "stand out" from this new background
            if newColor.lightness() > 100:
                item.setForeground(qt.QBrush(qt.QColor("#000000")))
            else:
                item.setForeground(qt.QBrush(qt.QColor("#FFFFFF")))

        def _setTableDataFor(
            idx: int, markup: "EditableMarkupResourceConfig.MarkupPointEntry"
        ):
            ## INIT ##
            # If this index is out of range, extend the table to support it
            if idx >= table.rowCount:
                table.setRowCount(idx + 1)

            # Convert the markup point into QT's format
            itemMap = {}
            colorItem = None
            for k, v in self.MARKUP_VALUES.items():
                itemMap[v] = qt.QTableWidgetItem(markup[v])
                # Track the color item for later
                if v == self.MARKUP_VALUES["color"]:
                    colorItem = itemMap[v]

            ## COLOR ##
            # Disable the color from being edited directly, we handle it differently
            colorItem.setFlags(
                colorItem.flags() & ~qt.Qt.ItemIsEditable
            )

            # Update the cell to use the new color
            _setItemColor(colorItem, qt.QColor(markup.color))

            ## FINALIZATION ##
            for k, v in itemMap.items():
                table.setItem(idx, k, v)

        # Instantiate the table with our initial values
        for i, markup in enumerate(self.markups):
            _setTableDataFor(i, markup)

        # Add the table to our layout
        layout.addRow(table)

        ## TABLE INTERACTION ##
        # Add Button
        addButton = qt.QPushButton(_("Add Markup"))
        addToolTip = _(
            "Add a new markup type you want to find or place within the resource. "
            "If none are defined, no markups are managed and CART will not manage "
            "newly placed markups either."
        )
        addButton.setToolTip(addToolTip)

        # Delete button
        deleteButton = qt.QPushButton(_("Delete Markup(s)"))
        deleteToolTip = _(
            "Remove the selected markups from the table; they will no longer be tracked "
            "by CART."
        )
        deleteButton.setToolTip(addToolTip)
        deleteButton.setToolTip(deleteToolTip)

        # Button Panel
        buttonPanel = qt.QWidget(None)
        buttonLayout = qt.QHBoxLayout(buttonPanel)
        buttonLayout.addWidget(addButton)
        buttonLayout.addWidget(deleteButton)
        layout.addRow(buttonPanel)

        ## CONNECTIONS ##
        # When the selection changes, enable/disable the delete button
        @qt.Slot()
        def selectionChanged():
            selected_indices = table.selectedIndexes()
            selected_rows = len({idx.row() for idx in selected_indices})
            deleteButton.setEnabled(selected_rows > 0)

        table.itemSelectionChanged.connect(selectionChanged)
        selectionChanged()

        # When the table's contents are changed, update this config to match
        @qt.Slot(int, int)
        def onCellChanged(row: int, col: int):
            # Get the new value added
            item: qt.QTableWidgetItem = table.item(row, col)
            new_val = item.text()

            # If this was the "value" column, parse it to int or null form
            if col == self.MARKUP_VALUES["value"]:
                try:
                    # Null is allowed in this context
                    if new_val == '':
                        new_val = None
                    # Any integer value is allowed as well
                    else:
                        new_val = int(new_val)
                except ValueError:
                    # If we couldn't, restore the original value and tell the user what happened
                    old_val = self.markups[row][col]
                    item.setText(str(old_val))
                    qt.QMessageBox.critical(
                        table,
                        _("Invalid Value") + f" '{new_val}'",
                        _(
                            f"Value must be either null or non-zero! Previous value {old_val} was restored."
                        ),
                        qt.QMessageBox.Ok,
                    )
                    return

            # Update our config to match
            old_data = self._raw_markup_data[row]
            new_data = [
                v if i != col else new_val for i, v in enumerate(old_data)
            ]
            new_markup = self.MarkupPointEntry(*new_data)
            self._raw_markup_data[row] = new_markup._asdict()

        table.cellChanged.connect(onCellChanged)

        # When the add button is clicked, add a new (empty) row
        @qt.Slot()
        def addClicked():
            # Default values
            label = ""
            color = "#fadd00"  # Gold-ish
            value = ""  # Null in text form

            # Add this "initial" markup to the markup values
            new_markup = self.add_markup(label, color, value)

            # Update the table w/ the new markup
            try:
                _setTableDataFor(table.rowCount, new_markup)
            except Exception as e:
                # If that failed, clean up the (likely malformed) new markup entry
                self.drop_markup(table.rowCount)
                raise e

        addButton.clicked.connect(addClicked)

        # Delete button drops all selecte markup entries simultaneously
        @qt.Slot()
        def deleteClicked():
            selected_rows = {idx.row() for idx in table.selectedIndexes()}
            for r in selected_rows:
                # Drop the row in the table itself
                table.removeRow(r)

                # If that worked correctly, remove it from our backing config too
                self.drop_markup(r)

        deleteButton.clicked.connect(deleteClicked)

        # Double-clicking a color cell should bring up the color picker instead
        @qt.Slot(int, int)
        def onCellDoubleClicked(row: int, col: int):
            # If this row does not correspond to the color column, do nothing
            if col != self.MARKUP_VALUES["color"]:
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
            _setItemColor(item, qColor)

        table.cellDoubleClicked.connect(onCellDoubleClicked)


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
