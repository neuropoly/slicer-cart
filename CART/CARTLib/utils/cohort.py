import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Protocol, TYPE_CHECKING, Callable

import numpy as np
from numpy import typing as npt

import ctk
import qt
from slicer.i18n import tr as _

from .widgets import CSVBackedTableModel, CSVBackedTableWidget

## Type Utils ##
if TYPE_CHECKING:
    # Avoid potential cyclic imports
    from CARTLib.core.TaskBaseClass import TaskBaseClass

    # NOTE: this isn't perfect (this only exposes Widgets, and Slicer's QT impl
    # isn't the same as PyQT5 itself), but it's a LOT better than constant
    # cross-referencing
    import PyQt5.Qt as qt

# Typing aliases for commonly used dictionary mappings
CaseMap = dict[str, list[Path]]
FilterEntry = dict[str, list[str]]
FilterMap = dict[str, FilterEntry]


# Current version of the cohort manager
COHORT_VERSION = "0.1.0"


## Core ##
class CohortModel(CSVBackedTableModel):
    """
    More specialized version of the CSV-backed model w/ additional checks
    and features specific to cohort editing.
    """

    ## Constructors ##
    def __init__(
        self,
        # NOTE: These are "optional mandatory" to force devs to consider why they're doing this!
        csv_path: Optional[Path],
        data_path: Optional[Path],
        editable: bool = True,
        reference_task: "type[TaskBaseClass]" = None,
        use_sidecar: bool = True,
        parent: qt.QObject = None
    ):
        # Disable editing explicitly if no data path is provided
        if data_path is None:
            editable = False

        super().__init__(csv_path, editable, parent)

        # Try to move the UID column to the front of the array
        if self._csv_path is not None:
            if not self._move_uid_to_index():
                raise ValueError("No UID column found, cannot set up Cohort model!")

        # Track the data path and reference task for later
        self.data_path = data_path
        self.reference_task = reference_task

        # Track whenever anything about this model changes!
        self.dataChanged.connect(self._mark_changed)
        self.headerDataChanged.connect(self._mark_changed)
        self.rowsInserted.connect(self._mark_changed)
        self.rowsMoved.connect(self._mark_changed)
        self.rowsRemoved.connect(self._mark_changed)
        self.columnsInserted.connect(self._mark_changed)
        self.columnsMoved.connect(self._mark_changed)
        self.columnsRemoved.connect(self._mark_changed)

        # Load (or initialize) our sidecar data
        self.use_sidecar = use_sidecar
        if use_sidecar:
            self._load_sidecar()
        else:
            # If no sidecar is to be used, generate blank cohort/filter entries
            self._case_map: CaseMap = dict()
            self._feature_map: FilterMap = dict()

        # Set ourselves to "not changed"
        self.has_changed = False

    @classmethod
    def from_case_map(
        cls,
        csv_path: Path,
        data_path: Path,
        case_map: CaseMap,
        editable: bool = True,
        reference_task: "TaskBaseClass" = None,
        use_sidecar: bool = True
    ):
        # Exit immediately if the case-map is empty
        if len(case_map) < 1:
            raise ValueError("Cannot create a cohort from an empty case map!")
        # Generate the backing CSV immediately using the case map's contents
        row_data = [["uid"], *[[k] for k in case_map.keys()]]
        with open(csv_path, "w") as fp:
            csv.writer(fp).writerows(row_data)
        # Generate a new cohort instance, backed by this new CSV file
        cohort = cls(csv_path, data_path, editable, reference_task, use_sidecar)
        # Manually update its case map to match
        cohort._case_map = case_map
        # Immediately save the sidecar as well, for parity
        cohort._save_sidecar()

        return cohort

    ## Setup Utilities ##
    def _mark_changed(self):
        self.has_changed = True

    def _move_uid_to_index(self) -> bool:
        # If the UID is already in the index position, do nothing
        if self._csv_data[0, 0].lower() == "uid":
            return True
        # Otherwise, find and move the UID column to the front
        for i, c in enumerate(self.header):
            if c.lower() == "uid":
                # Model "reset", as this changes more than just one column's pos
                self.beginResetModel()
                uid_arr = self._csv_data[:, i]
                np.delete(self._csv_data, i, axis=1)
                np.insert(self._csv_data, 0, uid_arr, axis=1)
                self.endResetModel()
                return True
        # If that fails (there's no UID column), return False for handling
        return False

    ## Attributes/Properties ##
    @property
    def sidecar_path(self) -> Path:
        # Get-only to avoid desync
        return self.csv_path.with_suffix(".json")

    @property
    def case_map(self):
        # Get only; use the set/remove functions instead
        return self._case_map

    @property
    def feature_map(self):
        # Get only; use the set/remove functions instead
        return self._feature_map

    ## Sidecar Management ##
    def set_case_data(self, case_label: str, search_paths: list[Path]):
        """
        Set the search paths for a given case in the cohort

        :param case_label: The label for the case (and its search paths).
            If a case already exists with this label, replaces it; otherwise, a new case is created.
        :param search_paths: The paths that should be searched when finding files for this case.
        """
        # Get the list of paths for this case
        new_paths = self.find_row_files(search_paths)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new case, create a new column to match
        if case_label not in self.case_map.keys():
            # Create a new row at the end of the dataset
            row_idx = self.rowCount()
            self.addRow(row_idx, new_paths)
            # Set the header to this new label
            self.setHeaderData(
                row_idx, qt.Qt.Vertical, case_label, qt.Qt.EditRole
            )
        # Otherwise, replace the row's values with the newly found paths
        else:
            # Find the column position which matches our feature label
            row_idx = np.argwhere(self.indices == case_label).flatten()[0]
            # Change the column's contents to our new list of paths
            self.setRow(row_idx, new_paths)

        # Save the new filter for later
        self.case_map[case_label] = search_paths

    def rename_case(self, old_name: str, new_name: str):
        # Check if a case map with this name already exists
        if old_name not in self.case_map.keys():
            raise ValueError(f"Cannot rename case '{old_name}'; it doesn't exist!")
        # Update the backing model
        row_idx = np.argwhere(self.indices == old_name).flatten()[0]
        self.setHeaderData(row_idx, qt.Qt.Vertical, new_name, qt.Qt.EditRole)
        # Update the case map to reflect the change
        case_map_entry = self.case_map.pop(old_name)
        self.case_map[new_name] = case_map_entry

    def drop_cases(self, names: list[str]):
        # Check the names before proceeding
        for name in names:
            # Check if a case map with this name exists
            if name not in self.case_map.keys():
                raise ValueError(f"Cannot delete case '{name}'; it doesn't exist!")

        # Do everything in one go to avoid partial corruption
        for name in names:
            # Update the backing model
            row_idx = np.argwhere(self.indices == name).flatten()[0]
            self.dropRow(row_idx)
            # Update the case map
            self.case_map.pop(name)

    FILTER_INCLUDE_KEY = "include"
    FILTER_EXCLUDE_KEY = "exclude"

    def set_feature_data(self, feature_label: str, filter_entry: FilterEntry):
        """
        Set the filters for a given feature in the cohort.

        :param feature_label: The label of the feature to update/create.
            If a filter already exists with this label, replaces it; otherwise, a new filter is created
        :param filter_entry: The filter entry to associate with the new/updated feature.
        """
        # Validate the new filter entry
        keyset = set(filter_entry.keys())
        if len(keyset - {self.FILTER_INCLUDE_KEY, self.FILTER_EXCLUDE_KEY}) > 0:
            raise ValueError(
                "Filter maps can only have two entries: 'include' and 'exclude'"
            )

        # Find and process the list of paths associated with this filter
        new_paths = self.find_column_files(filter_entry)
        new_paths = np.array([str(k) if k is not None else "" for k in new_paths])

        # If this is a new feature, create a new column to match
        if feature_label not in self.header:
            # Add a new column to the end of the dataset
            col_idx = self.columnCount()
            self.addColumn(col_idx, new_paths)
            # Set the header to this new label
            self.setHeaderData(
                col_idx, qt.Qt.Horizontal, feature_label, qt.Qt.EditRole
            )
        # Otherwise, replace the column's values with the newly found paths
        else:
            # Find the column position which matches our feature label
            col_idx = np.argwhere(self.header == feature_label).flatten()[0]
            # Change the model's contents to our new list of paths
            self.setColumn(col_idx, new_paths)

        # Save the new filter for later
        self.feature_map[feature_label] = filter_entry

    def rename_filter(self, old_name: str, new_name: str):
        # Check that there's actually a filter to rename
        if old_name not in self.feature_map.keys():
            raise ValueError(f"Cannot rename feature '{old_name}'; it doesn't exist!")
        # Update the backing model
        col_idx = np.argwhere(self.header == old_name).flatten()[0]
        self.setHeaderData(col_idx, qt.Qt.Horizontal, new_name, qt.Qt.EditRole)
        # Update the filter map to reflect the change
        filter_map = self.feature_map.pop(old_name)
        self.feature_map[new_name] = filter_map

    def drop_filters(self, names: list[str]):
        # Check the names before proceeding
        for name in names:
            # Check if a case map with this name exists
            if name not in self.feature_map.keys():
                raise ValueError(f"Cannot delete feature '{name}'; it doesn't exist!")

        # Do everything in one go to avoid partial corruption
        for name in names:
            # Update the backing model
            col_idx = np.argwhere(self.header == name).flatten()[0]
            self.dropColumn(col_idx)
            # Update the case map
            self.feature_map.pop(name)

    ## Data Management ##
    @property
    def csv_data(self) -> "Optional[npt.NDArray]":
        if self._csv_data is None:
            return None
        # Suppressed because PyCharm went mad for some reason here
        # noinspection PyTypeChecker
        return self._csv_data[1:, 1:]

    @property
    def header(self) -> "npt.NDArray[str]":
        return self._csv_data[0, 1:]

    @property
    def indices(self) -> "npt.NDArray[str]":
        data = self._csv_data[1:, 0]
        return data

    def data(self, index: qt.QModelIndex, role=qt.Qt.DisplayRole):
        # If this is a tooltip role, add the corresponding tooltip
        if role == qt.Qt.ToolTipRole and self.is_editable():
            row_name = self.indices[index.row()]
            col_name = self.header[index.column()]
            return _(
                "Double-click to manually set the value of this cell.\n"
                "Right click to edit the settings for the entire case "
                f"({row_name}) or feature ({col_name});\n"
                "This will update ALL cells for that row/column!"
            )
        # Otherwise, delegate to the superclass
        return super().data(index, role)

    def headerData(self, section: int, orientation: qt.Qt.Orientation, role: int = ...):
        # Note; "section" -> column for Horizontal, row for Vertical
        if role == qt.Qt.DisplayRole:
            if orientation == qt.Qt.Horizontal:
                return self.header[section]
            elif orientation == qt.Qt.Vertical:
                return self.indices[section]
        return None

    def removeColumns(self, column, count, parent = ...):
        self.beginRemoveColumns(parent, column, column + count - 1)
        # Offset by 1 to account for the new UID column
        idx = [column + i + 1 for i in range(count)]
        self._csv_data = np.delete(self._csv_data, idx, axis=1)
        self.endRemoveColumns()

    def setHeaderData(self, section, orientation, value, role=...):
        if role == qt.Qt.EditRole:
            if orientation == qt.Qt.Horizontal:
                self.header[section] = value
            elif orientation == qt.Qt.Vertical:
                self.indices[section] = value
            self.headerDataChanged(orientation, section, section)

    ## File Searching/Filtering ##
    def find_first_valid_file(
        self, search_paths: list[Path], filters: FilterEntry
    ) -> Optional[Path]:
        # Isolate the filters from one another
        include_values = filters[self.FILTER_INCLUDE_KEY]
        exclude_values = filters[self.FILTER_EXCLUDE_KEY]

        # Search every path in turn
        result = None
        for p in search_paths:
            # If the path isn't absolute, root it to our data path
            if not p.is_absolute():
                p = self.data_path / p
            # Only look at files; directories (such as DICOM) are currently not supported for automated cohorts
            # TODO: Replace with path.walk when it becomes available
            for r, __, fs in os.walk(p, topdown=True):
                r = Path(r)
                for f in fs:
                    f = r / f
                    file_string = str(f)
                    all_includes = len(include_values) == 0 or all(
                        [i in file_string for i in include_values]
                    )
                    no_excludes = len(exclude_values) == 0 or not any(
                        [i in file_string for i in exclude_values]
                    )
                    if all_includes and no_excludes:
                        result = f
                        break
                # Else-continue-break chain, allowing for the break to chain up the loops
                else:
                    continue
                break
            else:
                continue

        # If no valid files were found, return empty-handed
        if result is None:
            return None
        # If the result is within the data dir, make it relative
        elif self.data_path in result.parents:
            return result.relative_to(self.data_path)
        else:
            return result

    def find_row_files(self, search_paths: list[Path]) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.feature_map.items():
            result_map[k] = self.find_first_valid_file(search_paths, v)
        sorted_pathlist = [result_map.get(k, None) for k in self.header]
        return sorted_pathlist

    def find_column_files(self, column_filters: FilterEntry) -> list[Optional[Path]]:
        result_map = {}
        for k, v in self.case_map.items():
            result_map[k] = self.find_first_valid_file(v, column_filters)
        sorted_pathlist = [result_map.get(k, None) for k in self.indices]
        return sorted_pathlist

    ## I/O ##
    VERSION_KEY = "cohort_version"
    CASE_PATH_KEY = "case_paths"
    FILTERS_KEY = "filters"

    def save(self):
        # Only save if we have changed
        if self.has_changed:
            # Save the CSV (super-class delegate)
            super().save()
            # Save the sidecar as well
            self._save_sidecar()
            # Mark ourselves as unchanged
            self.has_changed = False

    def _save_sidecar(self):
        # Save the sidecar data on its own.
        sidecar_data = {
            self.VERSION_KEY: COHORT_VERSION,
            self.CASE_PATH_KEY: {
                k: [str(x) for x in v] for k, v in self.case_map.items()
            },
            self.FILTERS_KEY: self.feature_map,
        }

        with open(self.sidecar_path, "w") as fp:
            json.dump(sidecar_data, fp, indent=2)

    def load(self):
        # Load the CSV contents
        super().load()
        # Load the sidecar contents as well
        self._load_sidecar()
        # Mark ourselves as unchanged
        self.has_changed = False

    def _load_sidecar(self):
        # If this is for a not-yet-created cohort...
        if not self.csv_path:
            # ... reset everything and end
            self._case_map = {}
            self._feature_map = {}
            self._csv_data = None
            return
        # If we're just missing the sidecar...
        elif not self.sidecar_path.exists():
            # ... just reset the relevant contents instead
            self._case_map = {}
            self._feature_map = {}
            return
        # Otherwise, use the sidecar's contents to update ourselves
        with open(self.sidecar_path, "r") as fp:
            case_path_data = json.load(fp)

        # Update the case map
        case_data = case_path_data.get(self.CASE_PATH_KEY)
        if type(case_data) is not dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.CASE_PATH_KEY}' was malformed!"
            )
        self._case_map = {k: [Path(x) for x in v] for k, v in case_data.items()}

        # Update the filters
        filter_data = case_path_data.get(self.FILTERS_KEY, {})
        if type(filter_data) is not dict:
            raise ValueError(
                f"Cannot load sidecar, '{self.FILTERS_KEY}' was malformed!"
            )
        self._feature_map = {k: v for k, v in filter_data.items()}

## Generators ##
class CaseGenerator(Protocol):
    """
    Function-like Protocol class for generating an initial set of cases.

    Allows for type-hinting, aiding in the registration of custom case generators for future extensions.
    """

    def __call__(self, data_path: Path) -> CaseMap: ...


# Default generators; simple BIDS support + blank slate
def _bids_cases_by_subject(data_path: Path) -> CaseMap:
    # Identify the initial "source" paths
    case_map = {}
    for p in data_path.glob("sub*/"):
        # Add this path initially (the "source" path)
        case_map[p.name] = [p.relative_to(data_path)]
    # Add associated derivative paths, if a derivatives folder already exists
    derivative_path = data_path / "derivatives"
    if not derivative_path.exists():
        logging.warning("No derivatives path found for BIDS directory, skipping.")
    else:
        for s, v in case_map.items():
            v.extend(
                [p.relative_to(data_path) for p in derivative_path.glob(f"*/{s}/")]
            )
    # Sort the results to make them easier to work with
    case_map = {k: case_map[k] for k in sorted(case_map.keys())}
    return case_map


def _bids_cases_by_session(data_path: Path) -> CaseMap:
    # Identify the initial "source" paths
    data_map = {}
    for p in data_path.glob("sub*/ses*/"):
        # Add this path initially (the "source" path)
        name = tuple(p.parts[-2:])
        data_map[name] = [p.relative_to(data_path)]
    # Add associated derivative paths, if such a directory exists
    derivative_path = data_path / "derivatives"
    if not derivative_path.exists():
        logging.warning("No derivatives path found for BIDS directory, skipping.")
        case_map = {"_".join(k): v for k, v in data_map.items()}
    else:
        case_map = {}
        for (subject, session), val_list in data_map.items():
            val_list.extend([
                p.relative_to(data_path)
                for p in derivative_path.glob(f"*/{subject}/{session}/")
            ])
            case_map[f"{subject}_{session}"] = val_list
    # Sort the results to make them easier to work with
    case_map = {k: case_map[k] for k in sorted(case_map.keys())}
    return case_map


def _blank(__: Path) -> CaseMap:
    return dict()


# Registry for cases to be displayed during Cohort init
CASE_GENERATORS: dict[str, CaseGenerator] = {
    "BIDS (Case By Subject)": _bids_cases_by_subject,
    "BIDS (Case By Session)": _bids_cases_by_session,
    "Blank Slate": _blank,
}


def register_case_generator(label: str, generator: CaseGenerator):
    if label in CASE_GENERATORS.keys():
        raise ValueError(
            f"Cannot register generator '{label}', an existing generator with that label already exists!"
        )
    CASE_GENERATORS[label] = generator


def cohort_from_generator(
    cohort_name: str, data_path: Path, output_path: Path, generator: CaseGenerator
) -> CohortModel:
    """
    Generate a cohort from scratch, using the provided generator and input dataset.

    :param cohort_name: The name the cohort (file) should have
    :param data_path: The data path to reference when finding cases
    :param output_path: The path the resulting cohort's files should be placed within
    :param generator: The generator to user.
    """
    case_map = generator(data_path)
    # Keep Windows from having a stroke + backslashes begone
    cleaned_name = re.sub('[<>:"/|?*\\\\]', "-", cohort_name)
    # Keep adding underscores until a valid file path is found
    suffix = ""
    csv_path = output_path / f"{cleaned_name}.csv"
    while csv_path.exists():
        suffix += "_"
        csv_path = output_path / f"{cleaned_name}{suffix}.csv"
    cohort = CohortModel.from_case_map(csv_path, data_path, case_map)
    return cohort


## Related Widgets ##
class CohortTableView(qt.QTableView):
    """
    Provides a default context menu for use w/ this class of widgets.

    Generally, however, you should use CohortTableWidget (below) instead.
    """

    def __init__(self, parent: qt.QObject = None):
        super().__init__(parent)

        # Change the layout to be more sensible
        self.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.verticalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
        self.setHorizontalScrollMode(qt.QAbstractItemView.ScrollPerPixel)

    def contextMenuEvent(self, event: "qt.QContextMenuEvent"):
        # If the table we're viewing isn't editable, skip
        if not self.model().is_editable():
            return

        # If the corresponding index is invalid, end here
        pos = event.pos()
        idx = self.indexAt(pos)
        if not idx.isValid():
            return

        # Otherwise, build a menu of actions to do
        menu = qt.QMenu(self)
        self.installRowActions(menu, idx)
        self.installColActions(menu, idx)

        # Show it to the user
        menu.popup(self.viewport().mapToGlobal(pos))

    def installRowActions(self, menu: qt.QMenu, idx: qt.QModelIndex):
        # Get the case label for ease-of-use
        row_id = self.model().indices[idx.row()]

        # Modification action
        editAction = menu.addAction(_(f"Modify {row_id}"))
        def _modifyRow():
            dialog = CaseEditorDialog(self.model(), row_id)
            dialog.exec()
        editAction.triggered.connect(_modifyRow)

    def installColActions(self, menu: qt.QMenu, idx: qt.QModelIndex):
        # Get the case label for ease-of-use
        col_id = self.model().header[idx.column()]

        # Modification action
        editAction = menu.addAction(_(f"Modify {col_id}"))
        def _modifyColumn():
            dialog = FeatureEditorDialog(self.model(), col_id)
            dialog.exec()
        editAction.triggered.connect(_modifyColumn)


class CohortTableWidget(CSVBackedTableWidget):
    """
    Simple implementation for viewing the contents of a CSV file in Qt.

    Shows an error message when the backing CSV cannot be read.
    """

    def __init__(self, model: CohortModel, parent: qt.QWidget = None):
        super().__init__(model, parent)

        # Swap to our (contex-menu providing) table view class.
        self.tableView = CohortTableView()
        self.tableView.setModel(model)
        self.refresh()

    @classmethod
    def from_path(
            cls,
            csv_path: Optional[Path] = None,
            data_path: Optional[Path] = None,
            editable: bool = True
    ):
        # Explicitly disable editing if no data path was provided
        if data_path is None:
            editable = False
        model = CohortModel(csv_path, data_path, editable=editable)
        return cls(model)


## Related Dialogues ##
class NewCohortDialog(qt.QDialog):
    def __init__(
        self,
        data_path: Path,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # Track the data path for later
        self.data_path = data_path

        # Initial setup
        self.setWindowTitle(_("New Cohort"))
        layout = qt.QFormLayout(self)

        # Name to give the cohort
        cohortNameLabel = qt.QLabel(_("Name: "))
        cohortNameTooltip = _(
            "The name the cohort should have. Should follow your OS's file naming conventions."
        )
        cohortNameLabel.setToolTip(cohortNameTooltip)
        cohortNameEdit = qt.QLineEdit()
        cohortNameEdit.setToolTip(cohortNameTooltip)
        self.cohortNameEdit = cohortNameEdit
        layout.addRow(cohortNameLabel, cohortNameEdit)

        # Type of cohort to generate
        cohortTypeComboBox = qt.QComboBox()
        cohortTypeLabel = qt.QLabel(_("Cohort Type: "))
        cohortTypeComboBox.addItems(list(CASE_GENERATORS.keys()))
        self.cohortTypeComboBox = cohortTypeComboBox
        layout.addRow(cohortTypeLabel, cohortTypeComboBox)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

    @property
    def cohort_name(self):
        # Flip back-slashes to prevent horrific bugs
        name = self.cohortNameEdit.text.replace("\\", "/")
        return name

    @property
    def current_generator(self) -> CaseGenerator:
        return CASE_GENERATORS[self.cohortTypeComboBox.currentText]


class CohortEditorDialog(qt.QDialog):
    """
    GUI Dialog for editing a given cohort file.

    Using the button panel, users can add, edit, or delete rows/columns within the cohort.

    The user can manually add, remove, edit the rows/columns within the table widget itself.
    """

    def __init__(
        self,
        cohort: CohortModel,
        parent: qt.QObject = None,
    ):
        super().__init__(parent)

        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Backing cohort manager
        self._cohort = cohort

        # Initial setup
        self.setWindowTitle(_("Cohort Editor"))
        self.setMinimumSize(900, 700)
        layout = qt.QVBoxLayout(self)

        # Main table widget
        cohortWidget = CohortTableWidget(self._cohort)
        cohortWidget.setFrameShape(qt.QFrame.Panel)
        cohortWidget.setFrameShadow(qt.QFrame.Sunken)
        cohortWidget.setLineWidth(3)
        layout.addWidget(cohortWidget)

        # Cohort Management Buttons
        self._addButtons(layout, cohortWidget)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                # Confirm the user wants to reject any changes first
                if self.confirmReject():
                    self.reject()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Only save changes to the cohort when confirmed!
                self._cohort.save()
                self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

    def _addButtons(self, layout: "qt.QVBoxLayout", cohortWidget: "CohortTableWidget") -> qt.QGridLayout:
        # Add Case (Row) + Add Feature (Column) buttons
        newCaseButton = qt.QPushButton(_("New Case"))
        newCaseButton.setToolTip(
            _(
                "Add a new case (row) to the cohort. All features (columns) "
                "will be automatically populated with corresponding files "
                "wherever possible."
            )
        )

        def newCaseClicked():
            dialog = CaseEditorDialog(self._cohort)
            if dialog.exec():
                # Without this, the cells rapidly bloat for some reason
                cohortWidget.tableView.resizeColumnsToContents()
                cohortWidget.tableView.resizeRowsToContents()
        newCaseButton.clicked.connect(newCaseClicked)

        newFeatureButton = qt.QPushButton(_("New Feature"))
        newFeatureButton.setToolTip(
            _(
                "Add a new feature (column) to the cohort. All cases (rows) "
                "will be automatically populated with corresponding files "
                "wherever possible"
            )
        )

        def newFeatureClicked():
            dialog = FeatureEditorDialog(self._cohort)
            if dialog.exec():
                # Without this, the cells rapidly bloat for some reason
                cohortWidget.tableView.resizeColumnsToContents()
                cohortWidget.tableView.resizeRowsToContents()
        newFeatureButton.clicked.connect(newFeatureClicked)

        # Drop Cases (Rows) + Drop Features (Columns) Buttons
        dropCasesButton = qt.QPushButton(_("Drop Case(s)"))
        dropCasesButton.setToolTip(
            _(
                "Drop the selected case(s) (rows) in the cohort. THIS CANNOT BE UNDONE!"
            )
        )

        def dropCasesClicked():
            # Prompt the user to confirm this is what they want to do
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            case_names = list({
                self._cohort.indices[idx.row()]
                for idx in cohortWidget.selectedIndices
            })
            case_points = "\n".join(["  * " + c for c in case_names])
            msg.setText(
                "You are about to delete the following cases:\n"
                f"{case_points}\n"
                f"Are you sure?"
            )
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            # Only apply the deletion if confirmed by the user
            if msg.exec() == qt.QMessageBox.Yes:
                self._cohort.drop_cases(case_names)
        dropCasesButton.clicked.connect(dropCasesClicked)

        dropFeatureButton = qt.QPushButton(_("Drop Feature(s)"))
        dropFeatureButton.setToolTip(
            _("Drop the selected feature(s) (columns) in the cohort. THIS CANNOT BE UNDONE!")
        )

        def dropFeatureClicked():
            # Prompt the user to confirm this is what they want to do
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            feature_names = list({
                self._cohort.header[idx.column()]
                for idx in cohortWidget.selectedIndices
            })
            feature_points = "\n".join(["  * " + c for c in feature_names])
            msg.setText(
                "You are about to delete the following features:\n"
                f"{feature_points}\n"
                f"Are you sure?"
            )
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            # Only apply the deletion if confirmed by the user
            if msg.exec() == qt.QMessageBox.Yes:
                self._cohort.drop_filters(feature_names)
        dropFeatureButton.clicked.connect(dropFeatureClicked)

        buttonPanel = qt.QGridLayout()
        buttonPanel.addWidget(newCaseButton, 0, 0)
        buttonPanel.addWidget(newFeatureButton, 0, 1)
        buttonPanel.addWidget(dropCasesButton, 1, 0)
        buttonPanel.addWidget(dropFeatureButton, 1, 1)
        layout.addLayout(buttonPanel)

    def closeEvent(self, event):
        # Confirm that the user wants to reject any changes they made first
        if self.confirmReject():
            event.accept()
        # Otherwise, boot them back
        else:
            event.ignore()

    def confirmReject(self) -> bool:
        # If we have changed anything, confirm we want to exit first
        if self._cohort.has_changed:
            reply = qt.QMessageBox.question(
                self,
                "Are you sure?",
                "You have unsaved changes. Do you want to close anyways?",
                qt.QMessageBox.Yes | qt.QMessageBox.No,
                qt.QMessageBox.No,
            )
            return reply == qt.QMessageBox.Yes
        # Otherwise always proceed (as there's nothing to be lost)
        return True

    @classmethod
    def from_paths(
        cls,
        csv_path: Path,
        data_path: Path,
        editable: bool = True,
        reference_task: "type[TaskBaseClass]" = None,
    ):
        # Generate the cohort manager using the provided paths
        cohort = CohortModel(csv_path, data_path, editable, reference_task)
        return cls(cohort)


class FeatureEditorDialog(qt.QDialog):

    def __init__(
        self,
        cohort: CohortModel,
        feature_name: str = None,
        parent: qt.QObject = None,
    ):
        """
        Dialog for editing (or creating) new Features within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param feature_name: The name of the feature to edit. If None, will create a feature with
            the user specified name instead.
        :param parent: Parent widget, as required by QT.
        """
        super().__init__(parent)

        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Backing cohort manager
        self._cohort = cohort

        # Reference feature name
        self._reference_feature = feature_name

        # Initial setup
        if feature_name:
            self.setWindowTitle(_(f"Editing Feature '{feature_name}'"))
        else:
            self.setWindowTitle(_("Add New Feature"))
        self.setMinimumSize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # The feature name itself (prior to formatting)
        nameLabel = qt.QLabel(_("Feature Name:"))
        nameField = qt.QLineEdit()
        if feature_name:
            nameField.setText(feature_name)
        nameField.setPlaceholderText(_("e.g. disk_labels, spinal_T2w, liver_segmentation"))
        nameTooltip = _(
            "The name should represent what this feature contains at-a-glance. "
            "You can use any text you like, with the EXCEPTION of commas; any commas "
            "will be automatically replaced with underscores!"
            "\n\n"
            "If the task provides it, you can also select a 'feature type' from the "
            "drop-down above; doing so will provide a description for that type, and "
            "ensure this feature's name is formatted in the correct way for the task. "
            "The feature's label after this formatting has been applied can be seen found below."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        layout.addRow(nameLabel, nameField)

        # Other input fields
        includeLabel = qt.QLabel(_("Include:"))
        includeField = qt.QLineEdit()
        if feature_name:
            include_vals = self._cohort.feature_map.get(feature_name, {}).get(
                CohortModel.FILTER_INCLUDE_KEY, []
            )
            includeField.setText(", ".join(include_vals))
        includeField.textChanged.connect(self.mark_changed)
        includeTooltip = _(
            "Comma-separated elements that a file MUST have to be used for this feature. "
            "This incudes the directory the file is contained within!"
        )
        includeLabel.setToolTip(includeTooltip)
        includeField.setToolTip(includeTooltip)
        includeField.setPlaceholderText(_("e.g. T1w, nii, lesion_seg"))
        self.includeField = includeField
        layout.addRow(includeLabel, includeField)

        excludeLabel = qt.QLabel(_("Exclude:"))
        excludeField = qt.QLineEdit()
        if feature_name:
            exclude_vals = self._cohort.feature_map.get(feature_name, {}).get(
                CohortModel.FILTER_EXCLUDE_KEY, []
            )
            excludeField.setText(", ".join(exclude_vals))
        excludeField.textChanged.connect(self.mark_changed)
        excludeTooltip = _(
            "Comma-separated elements that a file MUST NOT have to be used for this feature. "
            "This incudes the directory the file is contained within!"
        )
        excludeLabel.setToolTip(excludeTooltip)
        excludeField.setToolTip(excludeTooltip)
        excludeField.setPlaceholderText(_("e.g. derivatives, masked, brain"))
        self.excludeField = excludeField
        layout.addRow(excludeLabel, excludeField)

        # Field type selection GUI
        self._generate_field_type_gui(layout, nameField)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                # Delegate to "onCancel" to prevent immediate closing
                self.onCancel()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Attempt to apply the requested changes before closing
                if self.apply_changes():
                    self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

        # Track whether changes have been made since this dialog was created
        self.has_changed = False

    def mark_changed(self):
        self.has_changed = True

    def _generate_field_type_gui(
            self,
            layout: "qt.QFormLayout",
            nameField: "qt.QLineEdit"
    ):
        # Feature type selector and description
        featureTypeLabel = qt.QLabel(_("Feature Type:"))
        featureTypeSelector = qt.QComboBox(None)
        feature_map = {
            "None": "Do not treat this feature as any specific feature type."
        }
        task = self._cohort.reference_task
        # TODO; Make this user selectable
        duf_type = list(task.getDataUnitFactories().keys())[0]
        for k, v in task.feature_types(duf_type).items():
            feature_map[k] = v
        featureTypeSelector.addItems(list(feature_map.keys()))
        featureTypeToolTip = _(
            "The feature type for this column."
            "\n\n"
            "Most tasks will use the name of each feature to determine "
            "how to process the corresponding resource for each case; "
            "selecting the correct feature type ensures the task can "
            "do so successfully."
        )
        featureTypeLabel.setToolTip(featureTypeToolTip)
        featureTypeSelector.setToolTip(featureTypeToolTip)
        layout.addRow(featureTypeLabel, featureTypeSelector)

        # Add it to the overall layout
        layout.addRow(featureTypeLabel, featureTypeSelector)

        # Description for the selected feature to help inform the user
        featureTypeDescriptionBox = ctk.ctkCollapsibleGroupBox()
        featureTypeDescriptionBox.setTitle(_("Type Description"))
        featureTypeDescriptionBoxLayout = qt.QVBoxLayout()
        featureTypeDescriptionBox.setLayout(featureTypeDescriptionBoxLayout)
        featureTypeDescription = qt.QLabel(_("[PLEASE WAIT]"))
        featureTypeDescription.setWordWrap(True)
        featureTypeDescriptionBoxLayout.addWidget(featureTypeDescription)

        def syncDescriptionText(__):
            new_type = str(featureTypeSelector.currentText)
            new_desc = feature_map.get(new_type, _("No Description Available"))
            featureTypeDescription.setText(new_desc)

        featureTypeSelector.currentIndexChanged.connect(syncDescriptionText)

        # Add it to the layout
        layout.addRow(featureTypeDescriptionBox)

        # Preview of the feature name after processing
        previewFieldLabel = qt.QLabel(_("Final Name: "))
        previewField = qt.QLabel("[PLEASE WAIT]")
        previewFont = qt.QFont()
        previewFont.setBold(True)
        previewField.setFont(previewFont)
        def syncPreviewField():
            prior_text = str(previewField.text)
            user_text = nameField.text.strip()
            t = self._cohort.reference_task
            # TODO: make this user-selectable
            duf = list(t.getDataUnitFactories().keys())[0]
            feature_type = str(featureTypeSelector.currentText)
            new_text = t.format_feature_label_for_type(user_text, duf, feature_type)
            if prior_text != new_text:
                previewField.setText(new_text)
                self.mark_changed()
        nameField.textChanged.connect(syncPreviewField)
        featureTypeSelector.currentIndexChanged.connect(syncPreviewField)

        # Track and add it to our layout
        self.namePreviewField = previewField
        w = qt.QWidget(None)
        l = qt.QHBoxLayout(w)
        l.addWidget(previewFieldLabel)
        l.addWidget(previewField)
        l.addStretch()
        layout.addRow(w)

        # Run a "sync" to update everything correctly
        syncDescriptionText(-1)  # Variable is unused, but required.
        syncPreviewField()

        # Disable feature-type widgets for tasks which do not specify feature types
        if len(feature_map) < 2:
            featureTypeSelector.setEnabled(False)
            featureTypeDescriptionBox.setEnabled(False)
            disabledToolTip = _("The selected task did specify any feature types.")
            featureTypeSelector.setToolTip(disabledToolTip)
            featureTypeDescriptionBox.setToolTip(disabledToolTip)

    def onCancel(self):
        # If we have changed anything, confirm we want to exit first
        if self.has_changed:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            msg.setText("You have unsaved changes. Do you want to close anyways?")
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            result = msg.exec()
            # If the user backs out, return early to do nothing.
            if result != qt.QMessageBox.Yes:
                return
        # Otherwise, exit the program with a "rejection" signal
        self.reject()

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        if not self.has_changed:
            return True

        # Make sure a feature of this name doesn't already exist
        label = self.namePreviewField.text.strip()
        if self._reference_feature is None and label in self._cohort.feature_map.keys():
            # If it does, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                "Invalid Feature Name",
                f"A feature of the name '{label}' already exists; please change it to be unique.",
                qt.QMessageBox.Ok,
            )
            return False

        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        filter_entry: FilterEntry = {
            CohortModel.FILTER_INCLUDE_KEY: [
                s.strip() for s in self.includeField.text.split(",")
            ],
            CohortModel.FILTER_EXCLUDE_KEY: [
                s.strip() for s in self.excludeField.text.split(",")
            ],
        }

        # Clean up "blank" filters which may have slipped through
        filter_entry[CohortModel.FILTER_INCLUDE_KEY] = [
            x for x in filter_entry[CohortModel.FILTER_INCLUDE_KEY] if x != ""
        ]
        filter_entry[CohortModel.FILTER_EXCLUDE_KEY] = [
            x for x in filter_entry[CohortModel.FILTER_EXCLUDE_KEY] if x != ""
        ]

        # If this an updated feature, rename the feature to this new name
        if self._reference_feature:
            self._cohort.rename_filter(self._reference_feature, label)

        # Update cohort to use the new filter
        self._cohort.set_feature_data(label, filter_entry)

        # Signal that everything ran successfully
        return True


class CaseEditorDialog(qt.QDialog):
    def __init__(self, cohort: CohortModel, case_id: str = None, parent: qt.QObject = None):
        """
        Dialog for editing (or creating) new Features within a cohort.

        :param cohort: The Cohort to apply the edits to
        :param case_id: The name of the case to edit. If None, will create a feature with
            the user specified name instead.
        :param parent: Parent widget, as required by QT.
        """
        super().__init__(parent)

        # If the cohort is not editable, reject attempts to edit it
        if not cohort.is_editable():
            raise ValueError("Cannot edit a un-editable Cohort!")

        # Backing cohort manager
        self._cohort = cohort

        # Reference feature name
        self._reference_case = case_id

        # Initial setup
        # Initial setup
        if case_id:
            self.setWindowTitle(_(f"Editing Case '{case_id}'"))
        else:
            self.setWindowTitle(_("Add New Case"))
        self.setMinimumSize(500, self.minimumHeight)
        layout = qt.QFormLayout(self)

        # Name Field
        nameLabel = qt.QLabel(_("Case Name:"))
        nameField = qt.QLineEdit()
        if case_id:
            nameField.setText(case_id)
        nameField.setPlaceholderText(_("e.g. sub-001, sub001_ses002"))
        nameField.textChanged.connect(self.mark_changed)
        nameTooltip = _(
            "An identifier for this case. Should be unique to the cohort; ideally, it should also "
            "implicitly reference the data it will refer to as well "
            "(i.e. sub-001 refers to data in sub-001 associated directories)."
        )
        nameLabel.setToolTip(nameTooltip)
        nameField.setToolTip(nameTooltip)
        self.nameField = nameField
        layout.addRow(nameLabel, nameField)

        # Search path list
        searchPathLabels = qt.QLabel(_("Search Paths: "))
        searchPathList = qt.QListWidget(None)
        if case_id:
            path_entries = cohort.case_map.get(case_id, [])
            for p in path_entries:
                if p.is_absolute():
                    searchPathList.addItem(str(p))
                else:
                    searchPathList.addItem(str(cohort.data_path / p))
        searchPathList.model().rowsInserted.connect(self.mark_changed)
        searchPathList.model().rowsRemoved.connect(self.mark_changed)
        layout.addRow(searchPathLabels)
        layout.addRow(searchPathList)
        self.searchPathList = searchPathList

        # Button panel
        addButton = qt.QPushButton("Add")
        removeButton = qt.QPushButton("Remove")
        removeButton.setEnabled(False)

        def onAddClicked():
            fileDialog = qt.QFileDialog()
            fileDialog.setDirectory(str(cohort.data_path))
            fileDialog.setFileMode(qt.QFileDialog.Directory)
            if fileDialog.exec():
                d = fileDialog.selectedFiles()[0]
                d = qt.QListWidgetItem(d)
                searchPathList.addItem(d)

        addButton.clicked.connect(onAddClicked)

        def onItemSelectionChanged():
            removeButton.setEnabled(len(searchPathList.selectedIndexes()) > 0)

        searchPathList.itemSelectionChanged.connect(onItemSelectionChanged)

        def onRemoveClicked():
            for i in searchPathList.selectedItems():
                searchPathList.takeItem(searchPathList.row(i))

        removeButton.clicked.connect(onRemoveClicked)

        # Make them side-by-side and add them to the layout
        w = qt.QWidget()
        l = qt.QHBoxLayout(w)
        l.addWidget(addButton)
        l.addWidget(removeButton)
        layout.addRow(w)

        # Ok/Cancel Buttons
        buttonBox = qt.QDialogButtonBox()
        buttonBox.setStandardButtons(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel
        )

        def onButtonClicked(button: qt.QPushButton):
            button_role = buttonBox.buttonRole(button)
            if button_role == qt.QDialogButtonBox.RejectRole:
                # Delegate to "onCancel" to prevent immediate closing
                self.onCancel()
            elif button_role == qt.QDialogButtonBox.AcceptRole:
                # Apply the requested changes to the cohort before closing.
                if self.apply_changes():
                    self.accept()
            else:
                raise ValueError("Pressed a button with an invalid role!")

        buttonBox.clicked.connect(onButtonClicked)
        layout.addWidget(buttonBox)

        self.has_changed = False

    def mark_changed(self):
        self.has_changed = True

    def onCancel(self):
        # If we have changed anything, confirm we want to exit first
        if self.has_changed:
            msg = qt.QMessageBox()
            msg.setWindowTitle("Are you sure?")
            msg.setText("You have unsaved changes. Do you want to close anyways?")
            msg.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
            result = msg.exec()
            # If the user backs out, return early to do nothing.
            if result != qt.QMessageBox.Yes:
                return
        # Otherwise, exit the program with a "rejection" signal
        self.reject()

    def apply_changes(self):
        # Only run the (relatively) expensive update if something has changed
        if not self.has_changed:
            return True

        # Make sure a case with this name doesn't already exist
        label = self.nameField.text.strip()
        if self._reference_case is None and label in self._cohort.case_map.keys():
            # If it does, show an error and return "False" (no changes made)
            qt.QMessageBox.critical(
                None,
                "Invalid Case Name",
                f"A case with the name '{label}' already exists; please change it to be unique.",
                qt.QMessageBox.Ok,
            )
            return False

        # Parse the contents of our GUI elements, stripping leading/trailing whitespace
        search_paths: list[Path] = []
        for i in range(self.searchPathList.count):
            p = Path(self.searchPathList.item(i).text())
            if self._cohort.data_path in p.parents:
                search_paths.append(p.relative_to(self._cohort.data_path))
            else:
                search_paths.append(p)

        # If this is an updated case, rename it to match
        if self._reference_case:
            self._cohort.rename_case(self._reference_case, label)

        # Insert it into our cohort
        self._cohort.set_case_data(label, search_paths)

        # Confirm that the changes went through
        return True
