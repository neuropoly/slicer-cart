from contextlib import contextmanager

import qt

from GenericClassificationUnit import GenericClassificationUnit


# Type hint guard; only risk the cyclic import if type hints are running
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # noinspection PyUnusedImports
    from GenericClassificationTask import GenericClassificationTask


class NewClassDialog(qt.QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Add New Class")

        self._build_ui()

    def _build_ui(self):
        # Create a simple VBox layout
        layout = qt.QVBoxLayout(self)

        # Add a small text widget for the class name
        self._buildClassEntry(layout)

        # Add a large text widget for the (optional) description
        self._buildDescEntry(layout)

        # Add button panel
        self._addButtons(layout)

    def _buildDescEntry(self, layout):
        descLabel = qt.QLabel("Description:")
        self.descEntry = qt.QTextEdit()
        self.descEntry.placeholderText = \
            "Optional. Will become the tooltip to the list entry if given."
        layout.addWidget(descLabel)
        layout.addWidget(self.descEntry)

    def _buildClassEntry(self, layout):
        classLabel = qt.QLabel("Class Name:")
        self.classEntry = qt.QLineEdit()
        self.classEntry.placeholderText = \
            "Required. The name of this classification."
        layout.addWidget(classLabel)
        layout.addWidget(self.classEntry)

    def _addButtons(self, layout):
        # The button box itself
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Cancel | qt.QDialogButtonBox.Ok
        )

        # Function to map the button press to our functionality
        def onButtonPressed(button: qt.QPushButton):
            # Get the role of the button
            button_role = buttonBox.buttonRole(button)
            # Match it to our corresponding function
            # TODO: Replace this with a `match` statement when porting to Slicer 5.9
            if button_role == qt.QDialogButtonBox.AcceptRole:
                self.onConfirm()
            elif button_role == qt.QDialogButtonBox.RejectRole:
                self.onCancel()
            else:
                raise ValueError("Pressed a button with an invalid role somehow...")

        buttonBox.clicked.connect(onButtonPressed)

        layout.addWidget(buttonBox)

    @property
    def class_name(self):
        return self.classEntry.text

    @property
    def description(self):
        return self.descEntry.toPlainText()

    def onConfirm(self):
        if not self.class_name:
            # Show a warning message and do nothing
            msg = qt.QMessageBox()
            msg.setWindowTitle("Missing Name")
            msg.setText("Cannot register a classification without it having a name!")
            msg.exec()
        else:
            self.accept()

    def onCancel(self):
        # If we have any content, confirm we want to exit first
        if self.class_name or self.description:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            msg.setText("You are about to exit without registering the class details you have entered. "
                        "Are you sure?")
            msg.setStandardButtons(
                qt.QMessageBox.Yes | qt.QMessageBox.No
            )
            result = msg.exec()
            # If the user backs out, return early to do nothing.
            if result != qt.QMessageBox.Yes:
                return
        # Otherwise, exit the program with a "rejection" signal
        self.reject()


class GenericClassificationGUI:
    def __init__(self, bound_task: "GenericClassificationTask"):
        # The task (logic) this GUI should be bound too
        self.bound_task = bound_task

    def setup(self) -> qt.QFormLayout:
        """
        Build the GUI's contents, returning its layout for later use
        """
        # Initialize the layout
        formLayout = qt.QFormLayout()

        # Build the button panel
        self._setupButtonPanel(formLayout)

        # Build the class checklist
        self._setupCheckboxList(formLayout)

        # Build the "other remarks" entry widget
        self._setupRemarksWidget(formLayout)

        # Initialize the list entries to match our bound task
        self._syncListEntriesWithTask()

        # Return the layout
        return formLayout

    def _setupButtonPanel(self, layout: qt.QFormLayout):
        # Sub-layout to make the buttons equally sized
        subLayout = qt.QHBoxLayout()

        # Add an "addition" button
        addButton = qt.QPushButton()
        addButton.setText("Add New Class")

        # When the button is pressed, generate the new class prompt
        def promptNewClass():
            # Show a prompt asking for a new class entry
            newClassDialog = NewClassDialog()
            accepted = newClassDialog.exec()

            # If the prompt was confirmed, try to add the new class
            if accepted:
                # Raise an error if the class already exists
                if (class_name := newClassDialog.class_name) in self.bound_task.class_map.keys():
                    raise ValueError(
                        f"Cannot add class {class_name}; a class with that name "
                        f"was already registered!"
                    )
                with self.block_signals():
                    self.addNewClass(
                        class_name,
                        newClassDialog.description
                    )

        addButton.clicked.connect(
            promptNewClass
        )

        # Add it to our layout
        subLayout.addWidget(addButton)

        # Add a "Drop" button, allowing existing classes to be removed
        dropButton = qt.QPushButton()
        dropButton.setText("Drop Selected Class")

        # Initially disable
        dropButton.enabled = False

        # When the button is pressed, drop the currently selected class
        dropButton.clicked.connect(self.dropSelectedClass)

        # Track it for later, and add it to the sub-layout
        self.dropButton = dropButton
        subLayout.addWidget(dropButton)

        # Place the buttons into a dummy widget and place it in the layout
        dummyWidget = qt.QWidget()
        dummyWidget.setLayout(subLayout)
        layout.addWidget(dummyWidget)

    def _setupCheckboxList(self, layout: qt.QFormLayout):
        # Generate a label for this list
        label = qt.QLabel("Classifications:")
        layout.addWidget(label)

        # Create the list widget
        listWidget = qt.QListWidget()

        # Ensure that any changes to each item in the list sync with the current data unit
        def onItemChanged(item: qt.QListWidgetItem):
            self.current_unit.toggle_class(
                item.text(),
                item.checkState()
            )
        listWidget.itemChanged.connect(onItemChanged)

        # Enable the "drop selected" button only when a row is selected
        listWidget.currentRowChanged.connect(
            lambda i: self.dropButton.setEnabled(i != -1)
        )

        # Add it to the layout and track it for later
        layout.addWidget(listWidget)
        self.classList = listWidget

    def _setupRemarksWidget(self, layout: qt.QFormLayout):
        remarksLabel = qt.QLabel("Other Remarks:")
        self.remarksEntry = qt.QTextEdit()
        self.remarksEntry.placeholderText = \
            "Other relevant remarks for this case. Optional."

        def onTextChanged():
            self.current_unit.remarks = self.remarksEntry.toPlainText()
        self.remarksEntry.textChanged.connect(onTextChanged)

        layout.addWidget(remarksLabel)
        layout.addWidget(self.remarksEntry)

    def _syncListEntriesWithTask(self):
        # Block signals to avoid error spam
        with self.block_signals():
            # Add each entry in the class map to our list widget
            for k, v in self.bound_task.class_map.items():
                self._addListEntry(k, v)

    @property
    def current_unit(self) -> GenericClassificationUnit:
        # Shortcut to avoid repeated chained calls
        return self.bound_task.current_unit

    @contextmanager
    def block_signals(self):
        # Disable the list from sending signals
        self.classList.blockSignals(True)
        self.remarksEntry.blockSignals(True)

        # Do whatever we need
        yield

        # Restore signal emission
        self.classList.blockSignals(False)
        self.remarksEntry.blockSignals(False)

    def _addListEntry(self, label: str, desc: str = None):
        # Add the entry to the list directly
        newEntry = qt.QListWidgetItem(label, self.classList)

        # Ensure it has a checkbox
        newEntry.setFlags(
            newEntry.flags() | qt.Qt.ItemIsUserCheckable
        )
        newEntry.setCheckState(
            qt.Qt.Unchecked
        )

        # Make its tooltip the description, if one was provided
        if desc:
            newEntry.setToolTip(desc)

        # Return the new entry for further processing
        return newEntry

    def syncWithDataUnit(self):
        with self.block_signals():
            # Calculate the sets of items to check in the GUI
            checked_items = self.current_unit.classes
            for i in range(self.classList.count):
                item = self.classList.item(i)
                if item.text() in checked_items:
                    item.setCheckState(
                        qt.Qt.Checked
                    )
                else:
                    item.setCheckState(
                        qt.Qt.Unchecked
                    )

            # Update the remarks contents
            remarks_text = self.current_unit.remarks
            self.remarksEntry.setPlainText(remarks_text)

    def addNewClass(self, label: str, desc: str = None):
        # Skip if we already have a class with this label
        if label in self.bound_task.class_map.keys():
            raise ValueError(f"Cannot add class {label}, already exists!")

        # Add it to our list
        self._addListEntry(label, desc)

        # Add it to our bound logic as well
        self.bound_task.class_map[label] = desc

    def dropSelectedClass(self):
        # "Pop" the currently selected from the list widget
        row_idx = self.classList.currentRow
        droppedItem = self.classList.takeItem(row_idx)

        # Remove the corresponding class from our logic as well
        class_label = droppedItem.text()
        del self.bound_task.class_map[class_label]

        # De-select other entries in the list to avoid "double-click double-delete"
        self.classList.currentRow = -1
