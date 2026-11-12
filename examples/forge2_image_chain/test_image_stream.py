import importlib.util
from pathlib import Path

import numpy as np
import pytest
from forge_msgs import Image

spec = importlib.util.spec_from_file_location("image_stream", Path(__file__).with_name("image_stream.py"))
stream = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream)


@pytest.mark.parametrize("encoding,dtype,channels", [("rgb8", np.uint8, 3), ("32FC1", np.float32, None)])
def test_fixture_checks_full_rgb_and_depth_content(encoding, dtype, channels):
    value = 7 if dtype == np.uint8 else 0.08
    shape = (4, 8, channels) if channels else (4, 8)
    pixels = np.full(shape, value, dtype=dtype)
    assert stream.validate_image(Image.from_numpy(pixels, encoding=encoding).to_arrow(), {"fixture_sequence": 7}) == shape
    pixels.flat[-1] = 99
    with pytest.raises(ValueError, match="content differs"):
        stream.validate_image(Image.from_numpy(pixels, encoding=encoding).to_arrow(), {"fixture_sequence": 7})


def test_real_frames_do_not_require_synthetic_metadata():
    pixels = np.zeros((4, 8, 3), dtype=np.uint8)
    assert stream.validate_image(Image.from_numpy(pixels, encoding="rgb8").to_arrow(), {}) == pixels.shape


@pytest.mark.parametrize("stream_id,encoding,dtype,value,shape", [
    ("rgb", "32FC1", np.float32, 0.08, (4, 8)),
    ("depth", "rgb8", np.uint8, 7, (4, 8, 3)),
])
def test_wrong_stream_type_cannot_pass_using_its_own_dtype(stream_id, encoding, dtype, value, shape):
    pixels = np.full(shape, value, dtype=dtype)
    with pytest.raises(ValueError, match="requires"):
        stream.validate_image(Image.from_numpy(pixels, encoding=encoding).to_arrow(), {"fixture_sequence": 7}, stream_id)
