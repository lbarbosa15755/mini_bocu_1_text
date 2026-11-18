"""BOCU-1 text decoder.

This package exposes a single public function, :func:`decode_bocu1`, which
transforms a ``bytes`` object containing BOCU-1 encoded data into a Python
``str``.  The implementation is deliberately small and dependency free; see
``core.py`` for the algorithm details.
"""

from .core import decode_bocu1, BOCU1DecodeError

__all__ = ["decode_bocu1", "BOCU1DecodeError"]
