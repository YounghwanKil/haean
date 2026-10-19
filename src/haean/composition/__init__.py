"""Optional whole-exam design from explicitly supplied, local rule profiles."""

from .profiles import load_profile
from .service import design, load_design

__all__ = ["load_profile", "design", "load_design"]
