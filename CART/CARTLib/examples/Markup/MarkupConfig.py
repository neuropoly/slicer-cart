from collections import namedtuple
from typing import Optional, TYPE_CHECKING

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
        "required": 2
    }
    MarkupPointEntry = namedtuple(
        "MarkupPoint",
        MARKUP_VALUES.keys(),
        defaults=[None, True]
    )
    PRETTY_HEADER = [
        "Label",
        "NIfTI Value",
        "Required"
    ]

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
        self, label: str, value: Optional[int] = None, unique: bool = False
    ) -> MarkupPointEntry:
        """
        Add a new markup, from scratch, to the end of the configuration list
        """
        # Use the namedtuple to ensure organization
        new_markup = self.MarkupPointEntry(label, value, unique)
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

    COLOR_KEY = "color"
    DEFAULT_COLOR = "#fadd00"  # Gold-ish

    @property
    def color(self) -> str:
        return self.get_or_default(self.COLOR_KEY, self.DEFAULT_COLOR)

    @color.setter
    def color(self, new_color: str):
        self.backing_dict[self.COLOR_KEY] = new_color

    ## CONFIG GUI ##
    def buildMarkupTableGUI(self, layout: qt.QFormLayout):
        ## MAIN TABLE ##
        table: qt.QTableWidget = qt.QTableWidget(None)

        # Give ourselves 2 columns, as QT is too dumb to figure it out otherwise
        n_cols = len(self.MARKUP_VALUES)
        table.setColumnCount(n_cols)

        # Translate and display the header values
        table.setHorizontalHeaderLabels(self.PRETTY_HEADER)

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
        for i in range(1, n_cols):
            table.horizontalHeader().setSectionResizeMode(i, qt.QHeaderView.ResizeToContents)

        # Helper functions to avoid duplicate code
        def _setTableDataFor(
            idx: int, markup: "EditableMarkupResourceConfig.MarkupPointEntry"
        ):
            ## INIT ##
            # If this index is out of range, extend the table to support it
            if idx >= table.rowCount:
                table.setRowCount(idx + 1)

            # Convert the markup point into QT's format
            itemMap = {}
            for k, v in self.MARKUP_VALUES.items():
                # Required nodes are checkboxes instead
                if k == "required":
                    item = qt.QTableWidgetItem()
                    item.setFlags(
                        qt.Qt.ItemIsEnabled | qt.Qt.ItemIsUserCheckable
                    )
                    checkState = markup[v] * 2
                    item.setCheckState(checkState)
                # Everything else is a string (for now)
                else:
                    item = qt.QTableWidgetItem(markup[v])
                itemMap[v] = item

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
            # Boolean values ("required") need to be extracted differently
            elif col == self.MARKUP_VALUES["required"]:
                new_val = bool(item.checkState())

            # Update our config to match
            old_data = self._raw_markup_data[row]
            new_data = [
                v if i != col else new_val for i, v in enumerate(old_data.values())
            ]
            new_markup = self.MarkupPointEntry(*new_data)
            self._raw_markup_data[row] = new_markup._asdict()
            self.mark_changed

        table.cellChanged.connect(onCellChanged)

        # When the add button is clicked, add a new (empty) row
        @qt.Slot()
        def addClicked():
            # Default values
            label = ""
            value = ""  # Null in text form

            # Add this "initial" markup to the markup values
            new_markup = self.add_markup(label, value)

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
