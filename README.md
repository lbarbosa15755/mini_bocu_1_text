# mini_bocu_1_text

Decode BOCU-1 compressed byte sequences into Python strings.

## Usage

```python
from mini_bocu_1_text import decode_bocu1

# BOCU-1 for the ASCII text "Hi".
data = bytes([0x41, 0x08, 0x40, 0x21])
text = decode_bocu1(data)
assert text == "Hi"
```

The package exports exactly two names:

- `decode_bocu1(data: bytes) -> str` — decode a BOCU-1 byte string.
- `BOCU1DecodeError` — raised on malformed input.

`decode_bocu1` accepts `bytes`, `bytearray`, and `memoryview`.  It raises
`BOCU1DecodeError` (a subclass of `ValueError`) for truncated sequences,
continuation bytes outside their allowed range, and decoded code points
that are not valid Unicode scalar values.

## Why this exists

BOCU-1 is a stateful compression scheme from Unicode Technical Note #191.
It encodes each code point as a signed delta from the previous one, so a
decoder must walk the input in order and cannot random-access it.  The
scheme is compact for text with small code point deltas, which is why it
was used in some older Unicode tooling.

This library implements only the decoder.  The encoder is deliberately
absent: the problem being solved is reading BOCU-1 data produced elsewhere.
Writing an encoder as well would double the state machine and create the
risk of a pair that disagree.  One direction, carefully tested, is the
trade-off.

## The awkward edge

The initial state is code point `0`.  A reset byte (`0xFF`) also sets the
state back to `0` and produces no output.  This means a stream that begins
with `0xFF` is equivalent to one that does not; the decoder treats them
the same.  If you are looking for a byte-for-byte round trip, this decoder
will not give you one, because it does not preserve reset bytes in its
output.  It only produces the text.
