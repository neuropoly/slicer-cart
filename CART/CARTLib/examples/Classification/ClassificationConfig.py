from CARTLib.utils.config import DictBackedConfig


class ClassificationConfig(DictBackedConfig):
    """
    Configuration managed for the Classification task
    """

    CONFIG_KEY = "classification_config"

    @classmethod
    def default_config_label(cls) -> str:
        return cls.CONFIG_KEY
