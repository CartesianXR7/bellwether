"""Tasks. One module per task. Each module exports a class satisfying Task."""

from bellwether.tasks.function_call_routing import FunctionCallRoutingTask
from bellwether.tasks.structured_extraction import StructuredExtractionTask
from bellwether.tasks.synthetic_rag import SyntheticRagTask

__all__ = [
    "FunctionCallRoutingTask",
    "StructuredExtractionTask",
    "SyntheticRagTask",
]
