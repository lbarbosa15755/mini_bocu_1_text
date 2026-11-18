"""Decoder for the BOCU-1 compression scheme.

BOCU-1 is described in Unicode Technical Note #191.  It encodes Unicode
code points as a sequence of bytes using a stateful differential scheme.
The decoder must therefore process bytes strictly left to right and maintain
the previous code point so that it can reconstruct the delta that each byte
represents.

This module implements the decoder only.  The encoder is intentionally not
provided: the library's stated purpose is to read BOCU-1 data produced by
other tools.  Implementing only one direction keeps the state machine small
and avoids the risk of an encoder and decoder that disagree.
"""

from __future__ import annotations

__all__ = ["decode_bocu1", "BOCU1DecodeError"]


class BOCU1DecodeError(ValueError):
    """Raised when a byte sequence is not valid BOCU-1."""


# BOCU-1 uses a fixed set of initial byte values to indicate the length of a
# code point's encoding.  The byte value ranges are documented in UTN #191.
# A leading byte in [0x00, 0x20) is special: it is either a reset byte
# (0xFF is the only reset byte) or a single-byte encoding of a code point
# whose delta is small.  The constants below name the boundaries so the
# decoder body reads as prose rather than magic numbers.

_RESET_BYTE = 0xFF

# The first byte of a multi-byte sequence determines how many continuation
# bytes follow.  Continuation bytes are always in [0x00, 0x40) and carry six
# bits each.  The leading byte carries the high bits of the delta.
_LEAD_BYTE_1 = 0x00  # single byte, values 0x00..0x20 (excluding 0xFF)
_LEAD_BYTE_2 = 0x21  # two bytes, lead in 0x21..0x4A
_LEAD_BYTE_3 = 0x4B  # three bytes, lead in 0x4B..0x94
_LEAD_BYTE_4 = 0x95  # four bytes, lead in 0x95..0xDE
_LEAD_BYTE_5 = 0xDF  # five bytes, lead in 0xDF..0xFF (0xFF is reset, not a lead)

# The maximum Unicode code point.  BOCU-1 can encode values outside the
# Unicode range in theory, but the decoder rejects them because they cannot
# be represented as Python strings.
_MAX_UNICODE = 0x10FFFF

# Surrogate code points are not valid in Unicode scalar values.  Python's
# ``chr`` accepts them, but they cannot be encoded in UTF-8 and are not
# valid text.  The decoder rejects them so that a successful decode always
# yields a string that can be re-encoded as UTF-8.
_SURROGATE_MIN = 0xD800
_SURROGATE_MAX = 0xDFFF


def _decode_continuation(byte: int) -> int:
    """Return the six-bit value carried by a continuation byte.

    Continuation bytes are in ``[0x00, 0x40)``.  The value is simply the
    byte itself; the range restriction is what distinguishes a continuation
    from a lead byte.  This helper exists to make the call sites read clearly
    and to centralise the range check.
    """
    if not 0x00 <= byte < 0x40:
        raise BOCU1DecodeError(
            f"continuation byte out of range: 0x{byte:02X}"
        )
    return byte


def _delta_from_lead(lead: int) -> tuple[int, int]:
    """Return ``(base_delta, extra_bytes)`` for a lead byte.

    ``base_delta`` is the signed value contributed by the lead byte alone;
    ``extra_bytes`` is the number of continuation bytes that must follow.
    The caller adds the continuation values shifted into place.

    The mapping is taken directly from UTN #191 table 1.  The lead byte
    ranges are contiguous and the base deltas are chosen so that the
    full delta range is covered without gaps.
    """
    if lead < _LEAD_BYTE_2:
        # Single byte.  The delta is the lead byte value minus 0x20, giving
        # a range of -32..-1 for 0x00..0x1F.  (0x20 is handled as a lead
        # for a two-byte sequence below.)
        return lead - 0x20, 0
    if lead < _LEAD_BYTE_3:
        # Two bytes.  The lead byte encodes a base delta in [-32, 31].
        return lead - 0x40, 1
    if lead < _LEAD_BYTE_4:
        # Three bytes.  The lead byte encodes a base delta in [-32, 31]
        # scaled by 64, plus the high bits of the low six bits.
        return (lead - 0x80) * 64, 2
    if lead < _LEAD_BYTE_5:
        # Four bytes.  Scale by 64^2.
        return (lead - 0x100) * 64 * 64, 3
    # Five bytes.  Scale by 64^3.  The lead byte 0xFF is the reset byte
    # and is handled by the caller before this function is reached.
    return (lead - 0x180) * 64 * 64 * 64, 4


def decode_bocu1(data: bytes) -> str:
    """Decode a BOCU-1 byte string into a Python ``str``.

    Parameters
    ----------
    data:
        The bytes to decode.  A ``bytes`` object is expected; ``bytearray``
        and ``memoryview`` are also accepted because they support the same
        integer indexing protocol.

    Returns
    -------
    str
        The decoded text.

    Raises
    ------
    BOCU1DecodeError
        If the input is not valid BOCU-1.  This includes truncated sequences,
        continuation bytes outside their allowed range, and decoded code
        points that are not valid Unicode scalar values (surrogates or
        values above ``0x10FFFF``).

    Notes
    -----
    BOCU-1 is a stateful encoding: each code point is stored as a signed
    delta from the previous code point.  The decoder therefore cannot skip
    around in the input; it must walk the bytes in order.  The initial state
    is code point ``0``, as required by the specification.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("decode_bocu1 expects a bytes-like object")

    out: list[str] = []
    prev = 0  # the previous code point, used as the delta base
    i = 0
    n = len(data)

    while i < n:
        lead = data[i]
        i += 1

        if lead == _RESET_BYTE:
            # A reset byte sets the previous code point back to zero.  It
            # does not itself produce output.  This is how BOCU-1 recovers
            # from a corrupt stream and how encoders can resynchronise.
            prev = 0
            continue

        base_delta, extra = _delta_from_lead(lead)

        # Collect the continuation bytes.  Each contributes six bits.  The
        # first continuation byte is the most significant of the low bits.
        delta = base_delta
        for _ in range(extra):
            if i >= n:
                raise BOCU1DecodeError(
                    "truncated BOCU-1 sequence: expected continuation byte"
                )
            cont = data[i]
            i += 1
            delta = delta * 64 + _decode_continuation(cont)

        # Reconstruct the code point.  The delta is signed and the result
        # must be a valid Unicode scalar value.
        code_point = prev + delta
        if code_point < 0 or code_point > _MAX_UNICODE:
            raise BOCU1DecodeError(
                f"decoded code point out of Unicode range: U+{code_point:04X}"
            )
        if _SURROGATE_MIN <= code_point <= _SURROGATE_MAX:
            raise BOCU1DecodeError(
                f"decoded surrogate code point: U+{code_point:04X}"
            )

        out.append(chr(code_point))
        prev = code_point

    return "".join(out)
