"""PSAT grade 5 verbal composition from explicitly supplied dictionaries.

Only the upstream 40-slot algorithm is supported; grade 7 is not synthesized.
Reference labels are retained on the instance. The composition sampler uses
only the explicit format profile's taxonomy, not a file-backed label cache.
"""

from .l_contract import EngineContract
from .v_content import ContentAlgorithms
from .v_format import FormatAlgorithms


class Engine(EngineContract, FormatAlgorithms, ContentAlgorithms):
    track = "psat_verbal"
    supported_sizes = (40,)
    sample_options = frozenset({"base"})
