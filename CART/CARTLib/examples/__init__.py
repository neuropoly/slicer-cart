from pathlib import Path

EXAMPLES_PATH = Path(__file__).parent

EXAMPLE_TASK_PATHS = {
    "Segmentation": EXAMPLES_PATH / "Segmentation/SegmentationTask.py",
    "Classification": EXAMPLES_PATH / "Classification/ClassificationTask.py",
    "Markup": EXAMPLES_PATH / "Markup/MarkupTask.py",
}