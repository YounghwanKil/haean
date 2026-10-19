"""LEET reasoning composition from explicitly supplied profile dictionaries.

The pure engine preserves upstream 40- and 20-slot algorithms. The full-exam
adapter may impose its narrower supported size independently.
"""

from .l_contract import EngineContract
from .l_content import ContentAlgorithms
from .l_format import FormatAlgorithms


class Engine(EngineContract, FormatAlgorithms, ContentAlgorithms):
    track = "leet_reasoning"
    supported_sizes = (40, 20)
    sample_options = frozenset({"variant", "size"})
