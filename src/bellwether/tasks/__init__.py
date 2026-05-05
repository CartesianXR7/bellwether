"""Tasks. One module per task. Each module exports a class satisfying Task."""

from bellwether.tasks.structured_extraction import StructuredExtractionTask

__all__ = ["StructuredExtractionTask"]
