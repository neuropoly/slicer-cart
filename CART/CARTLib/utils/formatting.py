from pathlib import Path
from typing import TYPE_CHECKING, Optional

import ctk
import qt
from slicer.i18n import tr as _

if TYPE_CHECKING:
    # Give some help when working with QT
    import PyQt5.Qt as qt


class FilePathFormatter:
    # Type alias to avoid the verbose type signature
    PlaceholderMap = dict[str, tuple[str, str]]

    # Default Replacement Characters
    DEFAULT_UID_PLACEHOLDER = "%u"
    DEFAULT_SHORT_NAME_PLACEHOLDER = "%n"
    DEFAULT_LONG_NAME_PLACEHOLDER = "%N"
    DEFAULT_JOBNAME_PLACEHOLDER = "%j"
    DEFAULT_FILENAME_PLACEHOLDER = "%f"

    DEFAULT_DESCRIPTIONS = {
        DEFAULT_UID_PLACEHOLDER: _(
            "The UID of the case, as specified in the cohort file."
        ),
        DEFAULT_SHORT_NAME_PLACEHOLDER: _(
            "The 'short' name for to-be-saved object. "
            "Usually its full name with metadata elements stripped "
            "(i.e. 'Segmentation_T2w' -> 'T2w')"
        ),
        DEFAULT_LONG_NAME_PLACEHOLDER: _(
            "The 'long' name for to-be-saved object. "
            "Usually its full name, including any metadata elements."
        ),
        DEFAULT_JOBNAME_PLACEHOLDER: _(
            "The job's name, as specified during its initial setup."
        ),
        DEFAULT_FILENAME_PLACEHOLDER: _(
            "The filename use to load the to-be-saved object, with "
            "file type suffixes stripped. "
            "If the object was not loaded from file, this becomes an "
            "alias for '%u_%n'"
        ),
    }

    ## Construction Utils ##
    @classmethod
    def build_default_placeholder_map(
        cls,
        uid: str = "sub-abc123",
        uid_desc: str = DEFAULT_DESCRIPTIONS[DEFAULT_UID_PLACEHOLDER],
        long_name: str = None,
        long_name_desc: str = DEFAULT_DESCRIPTIONS[DEFAULT_LONG_NAME_PLACEHOLDER],
        short_name: str = "Example",
        short_name_desc: str = DEFAULT_DESCRIPTIONS[DEFAULT_SHORT_NAME_PLACEHOLDER],
        job_name: str = "Job_Name",
        job_name_desc: str = DEFAULT_DESCRIPTIONS[DEFAULT_JOBNAME_PLACEHOLDER],
        file_name: str = None,
        file_name_desc: str = DEFAULT_DESCRIPTIONS[DEFAULT_FILENAME_PLACEHOLDER],
    ) -> "PlaceholderMap":
        """
        Generate a "placeholder character" map for this object w/ entries for the
        "standard" suite of placeholder characters (%u, %n, %N, %j, and %f).

        Any values you do not provide will be replaced with smart 'default' values;
        you can also add to, replace, or delete elements of this map after creation
        to further customize it.
        """
        # Use a placeholder full name if none was provided
        if long_name is None:
            long_name = f"Prefix_{long_name}"

        # Use a placeholder filename if it was not provided
        if file_name is None:
            file_name = f"{uid}_{short_name}"
        else:
            file_name = file_name.split(".")[0]

        # Build the placeholder map
        placeholder_map = {
            cls.DEFAULT_UID_PLACEHOLDER: (uid, uid_desc),
            cls.DEFAULT_SHORT_NAME_PLACEHOLDER: (short_name, short_name_desc),
            cls.DEFAULT_LONG_NAME_PLACEHOLDER: (long_name, long_name_desc),
            cls.DEFAULT_JOBNAME_PLACEHOLDER: (job_name, job_name_desc),
            cls.DEFAULT_FILENAME_PLACEHOLDER: (file_name, file_name_desc),
        }

        # Return the result
        return placeholder_map

    def __init__(
        self,
        root_path: Path = None,
        placeholder_map: "FilePathFormatter.PlaceholderMap" = None,
        extension: str = ".abc",
        truncate_root: bool = False
    ):
        """
        TODO
        """
        # Track the provided path, using a default "..." if none was given
        self.root_path: Path
        if root_path is None:
            self.root_path = Path("...")
        else:
            self.root_path = root_path

        self.truncate_root = truncate_root

        # Generate a "default" map if the user did not provide an explicit one
        self.placeholder_map: "FilePathFormatter.PlaceholderMap"
        if placeholder_map is None:
            self.placeholder_map = self.build_default_placeholder_map()
        else:
            self.placeholder_map = placeholder_map

        # Track the extension to append to the resulting preview
        self.extension = extension

    ## Utils ##
    def update_placeholder(self, placeholder_char: str, new_val: str, new_desc: str = None):
        # Try to use the old description if no new description was provided
        if new_desc is None:
            __, new_desc = self.placeholder_map.get(placeholder_char, "")

        self.placeholder_map[placeholder_char] = (new_val, new_desc)

    def format_string(self, init_str: str) -> Optional[str]:
        """
        Apply the formatting used by this formatter to the provided string.

        :returns: The formatted string; None if the result would be invalid
            (Empty string or
        """
        # Empty strings are invalid
        if len(init_str) < 1 or (init_str[-1] in {"/", "\\"}):
            return None

        # Format the string
        formatted_str = init_str
        for k, (v, __) in self.placeholder_map.items():
            formatted_str = formatted_str.replace(k, v)
        formatted_str += self.extension

        # Return the path as-is if the path is absolute
        if Path(formatted_str).is_absolute():
            return formatted_str
        # If we're truncating the root, prefix with '...'
        elif self.truncate_root:
            return str(Path('...') / formatted_str)
        # Otherwise, prepend the provided output root
        else:
            return str(self.root_path / formatted_str)


## Convenience Widget ##
class FilePathEditorWidget(qt.QWidget):
    def __init__(
        self,
        formatter: FilePathFormatter = None,
        labelFont: qt.QFont = None,
        placeholderFont: qt.QFont = None,
        truncateRoot: bool = True,
        showPlaceholderList: bool = False,
        parent=None,
    ):
        """
        TODO
        """
        super().__init__(parent)

        # Initialize this widget element as None
        # KO: For reasons beyond comprehension, QT will trump Python's
        #  error handling if used within a `property` context; WHY?!?!
        self.pathFormatEditor = None

        # Generate a default formatter if none was provided
        self.formatter: FilePathFormatter
        if formatter is None:
            self.formatter = FilePathFormatter()
        else:
            self.formatter = formatter

        # Use a standard bold font for labels if one was not provided
        if labelFont is None:
            labelFont = qt.QFont()
            labelFont.setBold(True)
        self._labelFont: qt.QFont = labelFont

        # Style sheets for valid/invalid paths
        self.validStyleSheet = None
        self.invalidStyleSheet = None
        self.validPalette: qt.QPalette = qt.QPalette()
        self.invalidPalette: qt.QPalette = qt.QPalette()
        self.invalidPalette.setColor(
            qt.QPalette.Text, qt.Qt.red
        )

        # Use a monospaced font for placeholder characters if one was not provided
        if placeholderFont is None:
            placeholderFont = qt.QFont("Monospace")
            placeholderFont.setStyleHint(qt.QFont.TypeWriter)
            placeholderFont.setBold(True)
        self._placeholderFont: qt.QFont = placeholderFont

        self.truncateRoot: bool = truncateRoot
        self._showPlaceholderList = showPlaceholderList

        # Build the layout of this widget
        layout = qt.QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.__buildLayout(layout)

    def __buildLayout(self, layout: qt.QFormLayout):
        """
        DO NOT USE THIS OUTSIDE THE CONSTRUCTOR!!!
        """
        # The "path formatting" widget
        pathFormatLabel = qt.QLabel(_("File Format: "))
        pathFormatLabel.setFont(self._labelFont)
        pathFormatEditor = qt.QLineEdit()
        savePathToolTip = _("The formatting string to use for the path.")
        pathFormatLabel.setToolTip(savePathToolTip)
        pathFormatEditor.setToolTip(savePathToolTip)
        layout.addRow(pathFormatLabel, pathFormatEditor)

        # Preview of the full output path
        previewLabel = qt.QLabel(_("Preview: "))
        previewLabel.setFont(self._labelFont)
        previewOutput = qt.QLabel()
        # Keep track of the "original" valid font for later
        previewOutput.setTextInteractionFlags(
            qt.Qt.TextSelectableByMouse
        )
        previewToolTip = _(
            "A preview of the full output after processing will appear here."
        )
        previewOutput.setToolTip(previewToolTip)
        previewOutput.setWordWrap(True)
        layout.addRow(previewLabel, previewOutput)

        # Collapsible descriptions of the placeholder characters
        placeholderListBox = ctk.ctkCollapsibleGroupBox()
        placeholderListBox.collapsedHeight = 1
        placeholderListBox.setTitle(_("Placeholder Character Reference"))
        placeholderLayout = qt.QFormLayout(placeholderListBox)
        self._placeholderLabels: list[qt.QLabel] = list()
        for k, (__, v) in self.formatter.placeholder_map.items():
            characterLabel = qt.QLabel(k)
            characterLabel.setFont(self._placeholderFont)
            descriptionLabel = qt.QLabel(_(v))
            descriptionLabel.setWordWrap(True)
            placeholderLayout.addRow(characterLabel, descriptionLabel)
            self._placeholderLabels.append(characterLabel)
        placeholderListBox.collapsed = True
        placeholderListBox.setVisible(self.showPlaceholderList)
        layout.addRow(placeholderListBox)

        # Preview updating functions
        pathFormatEditor.textChanged.connect(self.updatePreview)

        # Track everything publicly so other functions/devs can access them
        self.pathFormatLabel = pathFormatLabel
        self.pathFormatEditor = pathFormatEditor
        self.previewLabel = previewLabel
        self.previewOutput = previewOutput
        self.placeholderListBox = placeholderListBox

    ## Properties ##
    @property
    def pathFormat(self) -> str:
        # noinspection PyTypeChecker
        return self.pathFormatEditor.text

    @pathFormat.setter
    def pathFormat(self, new_str: str):
        self.pathFormatEditor.setText(new_str)

    @property
    def labelFont(self) -> qt.QFont:
        return self._labelFont

    @labelFont.setter
    def labelFont(self, newFont: qt.QFont):
        # Update the font of each of our labels
        for l in [self.pathFormatLabel]:
            l.setFont(newFont)
        # Track the new font
        self._labelFont = newFont

    @property
    def placeHolderFont(self) -> qt.QFont:
        return self._placeholderFont

    @placeHolderFont.setter
    def placeHolderFont(self, newFont: qt.QFont):
        # Update the font of each of our labels
        for l in self._placeholderLabels:
            l.setFont(newFont)
        # Track the new font
        self._placeholderFont = newFont

    @property
    def truncateRoot(self):
        return self.formatter.truncate_root

    @truncateRoot.setter
    def truncateRoot(self, new_val: bool):
        self.formatter.truncate_root = new_val
        if self.pathFormatEditor is not None:
            # noinspection PyTypeChecker
            self.updatePreview(self.pathFormatEditor.text)

    @property
    def showPlaceholderList(self) -> bool:
        return self._showPlaceholderList

    @showPlaceholderList.setter
    def showPlaceholderList(self, new_val: bool):
        self.placeholderListBox.setVisible(new_val)
        self._showPlaceholderList = new_val

    ## QT Hookups ##
    @property
    def pathFormatChanged(self) -> "qt.QSignal":
        return self.pathFormatEditor.textChanged

    @qt.Slot(str)
    def updatePreview(self, init_str: str) -> None:
        formatted_str = self.formatter.format_string(init_str)
        if formatted_str is None:
            self.previewOutput.setText("[INVALID]")
        else:
            self.previewOutput.setText(formatted_str)

    @qt.Slot(None)
    def refresh(self):
        init_str = self.pathFormatEditor.text
        self.updatePreview(init_str)
