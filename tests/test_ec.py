"""Tests for Reed-Solomon encode/decode (ec.py)."""

import math
import pytest

from tellmewords.ec import rs_encode, rs_decode, default_nsym, RSDecodeError


def test_roundtrip_no_errors():
    data = b"hello world, this is a test"
    nsym = default_nsym(len(data))
    encoded = rs_encode(data, nsym)
    assert rs_decode(encoded, nsym) == data


def test_roundtrip_at_threshold():
    data = b"BlackHat2025"
    nsym = default_nsym(len(data))
    encoded = bytearray(rs_encode(data, nsym))
    # Flip exactly floor(nsym/2) bytes (maximum correctable)
    max_errors = nsym // 2
    for i in range(max_errors):
        encoded[i] ^= 0xFF
    assert rs_decode(bytes(encoded), nsym) == data


def test_roundtrip_over_threshold():
    data = b"BlackHat2025"
    nsym = default_nsym(len(data))
    encoded = bytearray(rs_encode(data, nsym))
    # Flip floor(nsym/2) + 1 bytes — should fail
    over_threshold = nsym // 2 + 1
    for i in range(over_threshold):
        encoded[i] ^= 0xFF
    with pytest.raises(RSDecodeError):
        rs_decode(bytes(encoded), nsym)


def test_default_nsym_minimum():
    assert default_nsym(1) == 4
    assert default_nsym(0) == 4


def test_default_nsym_max():
    # Should never exceed 255
    assert default_nsym(10000) <= 255


def test_roundtrip_all_bytes():
    data = bytes(range(256))
    nsym = default_nsym(len(data))
    assert rs_decode(rs_encode(data, nsym), nsym) == data


def test_roundtrip_binary():
    import os
    data = os.urandom(200)
    nsym = default_nsym(len(data))
    assert rs_decode(rs_encode(data, nsym), nsym) == data
