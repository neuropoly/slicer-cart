from CARTLib.utils.config import DictBackedConfig, JobProfileConfig


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

    def show_gui(self) -> None:
        pass

    ## CONFIG ENTRIES ##
    SHOULD_INTERPOLATE_KEY = "should_interpolate"

    @property
    def should_interpolate(self) -> bool:
        return self.get_or_default(self.SHOULD_INTERPOLATE_KEY, True)

    @should_interpolate.setter
    def should_interpolate(self, new_val: bool):
        self.backing_dict[self.SHOULD_INTERPOLATE_KEY] = new_val
        self.has_changed = True

    HIDE_EDITABLE_ON_START_KEY = "hide_editable_on_start"

    @property
    def hide_editable_on_start(self) -> bool:
        return self.get_or_default(self.HIDE_EDITABLE_ON_START_KEY, False)

    @hide_editable_on_start.setter
    def hide_editable_on_start(self, new_val: bool):
        self.backing_dict[self.HIDE_EDITABLE_ON_START_KEY] = new_val
        self.has_changed = True

    SAVE_BLANK_SEGMENTATIONS_KEY = "save_blanks"

    @property
    def save_blank_segmentations(self) -> bool:
        return self.get_or_default(self.SAVE_BLANK_SEGMENTATIONS_KEY, True)

    @save_blank_segmentations.setter
    def save_blank_segmentations(self, new_val: bool):
        self.backing_dict[self.SAVE_BLANK_SEGMENTATIONS_KEY] = new_val
        self.has_changed = True

    CUSTOM_SEGMENTATIONS_KEY = "custom_segmentations"
    CUSTOM_SEG_PATH_KEY = "path_string"
    CUSTOM_SEG_COLOR_KEY = "color"

    @property
    def custom_segmentations(self) -> dict[str, dict]:
        return self.get_or_default(self.CUSTOM_SEGMENTATIONS_KEY, dict())

    @custom_segmentations.setter
    def custom_segmentations(self, new_vals: dict[str, dict]):
        self.backing_dict[self.CUSTOM_SEGMENTATIONS_KEY] = new_vals
        self.has_changed = True

    def add_custom_segmentation(self, new_name: str, output_str: str, color_hex: str):
        sub_dict = {
            self.CUSTOM_SEG_PATH_KEY: output_str,
            self.CUSTOM_SEG_COLOR_KEY: color_hex
        }
        self.custom_segmentations[new_name] = sub_dict
        self.has_changed = True

    SEGMENTATIONS_TO_SAVE_KEY = "segmentations_to_save"

    @property
    def segmentations_to_save(self) -> list[str]:
        return self.get_or_default(self.SEGMENTATIONS_TO_SAVE_KEY, list())

    @segmentations_to_save.setter
    def segmentations_to_save(self, new_segs: list[str]):
        self._backing_dict[self.SEGMENTATIONS_TO_SAVE_KEY] = new_segs
        self.has_changed = True

    EDIT_OUTPUT_PATH_KEY = "edit_output_path"

    @property
    def edit_output_path(self) -> str:
        return self.get_or_default(self.EDIT_OUTPUT_PATH_KEY, "")

    @edit_output_path.setter
    def edit_output_path(self, new_val: str):
        self.backing_dict[self.EDIT_OUTPUT_PATH_KEY] = new_val
        self.has_changed = True

    DEFAULT_CUSTOM_OUTPUT_PATH_KEY = "default_custom_output_path"

    @property
    def default_custom_output_path(self) -> str:
        return self.get_or_default(self.DEFAULT_CUSTOM_OUTPUT_PATH_KEY, "")

    @default_custom_output_path.setter
    def default_custom_output_path(self, new_val: str):
        self.backing_dict[self.DEFAULT_CUSTOM_OUTPUT_PATH_KEY] = new_val
        self.has_changed = True
