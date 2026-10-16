from typing import Optional

import qt
from CARTLib.examples.Classification.ClassificationGUI import NewClassDialog
from slicer.i18n import tr as _

from CARTLib.utils.config import DictBackedConfig

class ClassificationConfig(DictBackedConfig):
    """
    Configuration managed for the Classification task
    """

    CONFIG_KEY = "classification_config"

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY

    ## Attributes ##

    CLASSES_KEY = "classes"

    @property
    def classes(self) -> dict[str, str]:
        return self.get_or_default(self.CLASSES_KEY, {})

    def update_class(self, name: str, description: str = ""):
        self.classes[name] = description
        self.has_changed = True

    def drop_class(self, name):
        self.classes.pop(name, None)
        self.has_changed = True

    def generateGUILayout(self) -> Optional[tuple[str, qt.QLayout]]:
        return _("Classification Configuration"), ClassificationConfigGUI(self)


class ClassificationConfigGUI(qt.QFormLayout):
    def __init__(self, config: ClassificationConfig, parent = None):
        super().__init__(parent)

        ## Class Table ##
        # Create a header for the table
        label = qt.QLabel("Classifications:")
        self.addWidget(label)

        # Create the table itself
        classTable = ClassDescriptionTable(config, parent)

        # Add it to the layout and track it for later
        self.addWidget(classTable)
        self.classTable = classTable

        ## Buttons ##
        # Add a pair of buttons for adding and removing classes
        addClassButton = qt.QPushButton()
        addClassButton.clicked.connect(self.addClass)
        addClassButton.setText(_("New Class"))

        dropClassButton = qt.QPushButton()
        dropClassButton.clicked.connect(self.dropClasses)
        dropClassButton.setText(_("Drop Class(es)"))

        buttonLayout = qt.QHBoxLayout()
        buttonLayout.addWidget(addClassButton)
        buttonLayout.addWidget(dropClassButton)
        buttonWidget = qt.QWidget()
        buttonWidget.setLayout(buttonLayout)
        self.addWidget(buttonWidget)

        ## Misc ##
        # Track the config for later
        self.config = config

        # When a cell is double-clicked, bring up the editing dialog
        self.classTable.cellDoubleClicked.connect(self.updateClass)

    @qt.Slot()
    def addClass(self):
        # Prompt the user to provide the new classes details
        newClassDialog = NewClassDialog(set(self.config.classes.keys()))
        accepted = newClassDialog.exec()

        # If the prompt was confirmed, try to add the new class
        if accepted:
            self.classTable.add_entry(
                newClassDialog.class_name, newClassDialog.description
            )

    @qt.Slot(int, int)
    def updateClass(self, row: int, __):
        # Get the name and description for the clicked row
        prior_name = self.classTable.item(row, ClassDescriptionTable.NAME_IDX).text()
        prior_desc = self.classTable.item(row, ClassDescriptionTable.DESC_IDX).text()

        # Prompt the user to provide the new classes details
        classEditingDialog = NewClassDialog(
            set(self.config.classes.keys()),
            prior_name=prior_name,
            prior_desc=prior_desc,
        )
        accepted = classEditingDialog.exec()

        # If the prompt was accepted, update the table's contents
        if accepted:
            self.classTable.update_entry(
                row, classEditingDialog.class_name, classEditingDialog.description
            )

    @qt.Slot()
    def dropClasses(self):
        selectedItems = self.classTable.selectedItems()
        to_drop_rows = [item.row() for item in selectedItems]
        # Drop each row from the table (bottom to top to avoid index offsetting)
        for r in sorted(to_drop_rows, reverse=True):
            self.classTable.drop_entry(r)

class ClassDescriptionTable(qt.QTableWidget):

    NAME_IDX = 0
    DESC_IDX = 1

    def __init__(self, config: ClassificationConfig, parent = None):
        # Initialize w/ two columns only
        super().__init__(0, 2, parent)

        # Set our headers
        self.setHorizontalHeaderLabels([
            _("Name"), _("Description")
        ])

        # Make ourselves behave sensibly
        self.setSizeAdjustPolicy(qt.QAbstractScrollArea.AdjustToContents)
        self.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)
        self.setSizePolicy(qt.QSizePolicy.Minimum, qt.QSizePolicy.Minimum)

        # Disable editing to avoid desync
        # TODO: Fix this
        self.setEditTriggers(self.NoEditTriggers)

        # Hide the vertical header
        self.verticalHeader().setVisible(False)

        # Make the columns stretch to fill available space
        self.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Stretch)

        # Explicitly state we have 2 columns, as QT is moronic
        self.setColumnCount(2)

        # Update our row count to match as well
        self.setRowCount(len(config.classes))

        # Instantiate with our config's values
        for i, (name, desc) in enumerate(config.classes.items()):
            self.setItem(i, self.NAME_IDX, qt.QTableWidgetItem(name))
            self.setItem(i, self.DESC_IDX, qt.QTableWidgetItem(desc))

        # Track the config for later
        self.config = config

    def add_entry(self, name: str, desc: str):
        # If this name already exists, end here to avoid potential desync
        if name in self.config.classes.keys():
            raise ValueError(f"Cannot add class '{name}', it already exists!")

        # Try to add it to our table
        i = self.rowCount
        self.setRowCount(i + 1)
        nameItem = qt.QTableWidgetItem(name)
        descItem = qt.QTableWidgetItem(desc)
        self.setItem(i, self.NAME_IDX, nameItem)
        self.setItem(i, self.DESC_IDX, descItem)

        # Then add it to our config
        self.config.update_class(name, desc)

    def update_entry(self, row_idx: int, name: str, desc: str):
        # Get the name previously at that location
        prior_name = self.item(row_idx, self.NAME_IDX).text()

        # Update the table
        self.setItem(row_idx, self.NAME_IDX, qt.QTableWidgetItem(name))
        self.setItem(row_idx, self.DESC_IDX, qt.QTableWidgetItem(desc))

        # Update the config
        self.config.drop_class(prior_name)
        self.config.update_class(name, desc)

    def drop_entry(self, i: int):
        # Get the class name for this index
        name = self.item(i, self.NAME_IDX).text()

        # Drop the row
        self.removeRow(i)

        # Remove the entry from the config as well
        self.config.drop_class(name)
