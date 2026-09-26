"""Tests for synthetic model generators and ONNX models."""

import numpy as np
import onnx
import onnxruntime as ort
import pytest

from app.models_gen import generate_attn, generate_conv, generate_mlp


def test_mlp_generation_and_shapes():
    """Verify MLP formulas, parameters, FLOPs, and dynamic batch execution."""
    width = 64
    layers = 3
    path, params, flops, weight_bytes, shape_json = generate_mlp(width=width, layers=layers)

    assert path.exists()
    assert params == layers * width * width
    assert flops == 2.0 * layers * width * width
    assert weight_bytes == params * 4

    # Count actual initializers in ONNX graph
    model = onnx.load(str(path))
    actual_params = sum(int(np.prod(init.dims)) for init in model.graph.initializer)
    assert actual_params == params

    # Test execution in ORT with batch=1 and batch=4
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    for b in [1, 4]:
        inp = np.ones((b, width), dtype=np.float32)
        out = sess.run(None, {"X": inp})[0]
        assert out.shape == (b, width)


def test_conv_generation_and_shapes():
    """Verify Conv formulas and dynamic batch execution."""
    channels = 8
    h_w = 16
    layers = 2
    path, params, flops, weight_bytes, shape_json = generate_conv(channels=channels, h_w=h_w, layers=layers)

    assert path.exists()
    assert params == layers * channels * channels * 9
    assert flops == 2.0 * layers * h_w * h_w * channels * channels * 9
    assert weight_bytes == params * 4

    # Test execution in ORT
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    for b in [1, 3]:
        inp = np.ones((b, channels, h_w, h_w), dtype=np.float32)
        out = sess.run(None, {"X": inp})[0]
        assert out.shape == (b, channels, h_w, h_w)


def test_attn_generation_and_shapes():
    """Verify Attention formulas and dynamic batch execution."""
    d = 32
    tokens = 16
    layers = 2
    path, params, flops, weight_bytes, shape_json = generate_attn(d=d, tokens=tokens, layers=layers)

    assert path.exists()
    assert params == 4 * layers * d * d
    assert flops == float(layers * (8 * tokens * d * d + 4 * tokens * tokens * d))
    assert weight_bytes == params * 4

    # Test execution in ORT
    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    for b in [1, 2]:
        inp = np.ones((b, tokens, d), dtype=np.float32)
        out = sess.run(None, {"X": inp})[0]
        assert out.shape == (b, tokens, d)
