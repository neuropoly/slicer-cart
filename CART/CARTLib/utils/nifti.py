"""
Reads orientation out of a NIfTI header, since Slicer discards the original when
it loads a file. Standard library only, to keep CART dependency-free.

Only NIfTI-1 is read here. A NIfTI-2 file raises instead, which leaves its
orientation unrecorded and its saving behaviour unchanged.
"""

import gzip
import struct
from math import sqrt
from pathlib import Path
from typing import Optional

# A NIfTI-1 header is always 348 bytes, and always starts with that number.
HEADER_SIZE = 348

# The NIfTI-1 header is a fixed layout, so the spec pins every field to a
# known byte offset within it.
_OFFSET_PIXDIM = 76
_OFFSET_QFORM_CODE = 252
_OFFSET_SFORM_CODE = 254
_OFFSET_QUATERN = 256
_OFFSET_QOFFSET = 268
_OFFSET_SROW_X = 280
_OFFSET_SROW_Y = 296
_OFFSET_SROW_Z = 312

_AXIS_LABELS = (("R", "L"), ("A", "P"), ("S", "I"))


def read_orientation(path: Path) -> Optional[str]:
    affine = read_affine(path)
    if affine is None:
        return None
    return affine_to_orientation(affine)


def read_affine(path: Path) -> Optional[list[list[float]]]:
    raw, endian = _read_header(path)

    # A code of 0 means that form was never set, so its contents are junk.
    # The sform wins when both are present, as most NIfTI tools do the same.
    if struct.unpack_from(endian + "h", raw, _OFFSET_SFORM_CODE)[0] > 0:
        return [
            list(struct.unpack_from(endian + "4f", raw, offset))
            for offset in (_OFFSET_SROW_X, _OFFSET_SROW_Y, _OFFSET_SROW_Z)
        ]

    if struct.unpack_from(endian + "h", raw, _OFFSET_QFORM_CODE)[0] > 0:
        return _qform_affine(raw, endian)

    return None


def affine_to_orientation(affine: list[list[float]]) -> str:
    code = ""
    for column in range(3):
        values = [affine[row][column] for row in range(3)]
        # The anatomical axis this voxel axis moves along fastest is the one
        # that names it. Anything left over is obliquity, which we ignore.
        dominant = max(range(3), key=lambda row: abs(values[row]))
        towards, away = _AXIS_LABELS[dominant]
        code += towards if values[dominant] > 0 else away
    return code


def _read_header(path: Path) -> tuple[bytes, str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as fp:
        raw = fp.read(HEADER_SIZE)

    if len(raw) < HEADER_SIZE:
        raise ValueError(
            f"File '{path.name}' is too small to contain a NIfTI-1 header; "
            "ensure it is a valid '.nii' file!"
        )

    # NIfTI files can store their numbers in either byte order (endianness), and
    # nothing in the header states which. The trick is that the first field is
    # the header's own size, so whichever byte order reads it back as 348 is the
    # one the file was written with.
    for endian in ("<", ">"):
        if struct.unpack_from(endian + "i", raw, 0)[0] == HEADER_SIZE:
            return raw, endian

    raise ValueError(
        f"File '{path.name}' is not a NIfTI-1 file; its header does not begin "
        f"with the expected size of {HEADER_SIZE}!"
    )


def _qform_affine(raw: bytes, endian: str) -> list[list[float]]:
    b, c, d = struct.unpack_from(endian + "3f", raw, _OFFSET_QUATERN)
    offset = struct.unpack_from(endian + "3f", raw, _OFFSET_QOFFSET)
    pixdim = struct.unpack_from(endian + "8f", raw, _OFFSET_PIXDIM)

    # Only three of the quaternion's four terms are stored, as it is always a
    # unit quaternion and so the first can be recovered from the other three.
    remainder = 1.0 - (b * b + c * c + d * d)
    a = sqrt(remainder) if remainder > 0 else 0.0

    rotation = [
        [a * a + b * b - c * c - d * d, 2 * (b * c - a * d), 2 * (b * d + a * c)],
        [2 * (b * c + a * d), a * a + c * c - b * b - d * d, 2 * (c * d - a * b)],
        [2 * (b * d - a * c), 2 * (c * d + a * b), a * a + d * d - b * b - c * c],
    ]

    # A quaternion can only describe a proper rotation, so a left handed volume
    # is flagged by a negative qfac which flips the third axis back around.
    qfac = -1.0 if pixdim[0] < 0 else 1.0
    scale = (pixdim[1], pixdim[2], pixdim[3] * qfac)

    return [
        [rotation[row][col] * scale[col] for col in range(3)] + [offset[row]]
        for row in range(3)
    ]
