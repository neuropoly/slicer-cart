from pathlib import Path

EXAMPLES_PATH = Path(__file__).parent

EXAMPLE_TASK_PATHS = {
    "Segmentation": EXAMPLES_PATH / "Segmentation/SegmentationTask.py",
    "Generic Classification": EXAMPLES_PATH / "GenericClassification/GenericClassificationTask.py",
    "Markup": EXAMPLES_PATH / "Markup/MarkupTask.py",
}