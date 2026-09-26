"""Synthetic ONNX neural network model generation and model file scanning.

Generates reproducible MLP, Conv, and Attention models using exact FLOPs
and parameter formulas defined in SPEC Section 3.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from sqlmodel import Session, select

from app.config import MODELS_DIR, SEED
from app.db import AIModel

logger = logging.getLogger(__name__)


def compute_file_sha256(path: Path) -> str:
    """Compute the SHA256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_mlp(width: int, layers: int = 4) -> tuple[Path, int, float, int, str]:
    """Generate a multi-layer perceptron (MLP) ONNX model.

    Graph: L x (MatMul W[n x n] -> Relu) on input of shape [batch, width].
    FLOPs per sample: 2 * L * width^2.
    Params: L * width^2.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"mlp_{width}w_{layers}l"
    model_path = MODELS_DIR / f"{name}.onnx"

    params = layers * width * width
    flops_per_sample = float(2 * layers * width * width)
    weight_bytes = params * 4  # float32 = 4 bytes
    input_shape = ["batch", width]

    rng = np.random.default_rng(SEED)
    nodes = []
    initializers = []
    inputs = [helper.make_tensor_value_info("X", TensorProto.FLOAT, input_shape)]
    cur_var = "X"

    for i in range(layers):
        w_name = f"W_{i}"
        w_data = rng.standard_normal((width, width), dtype=np.float32) * (1.0 / np.sqrt(width))
        initializers.append(numpy_helper.from_array(w_data.astype(np.float32), name=w_name))

        mm_out = f"mm_{i}"
        nodes.append(helper.make_node("MatMul", [cur_var, w_name], [mm_out]))
        relu_out = f"relu_{i}"
        nodes.append(helper.make_node("Relu", [mm_out], [relu_out]))
        cur_var = relu_out

    outputs = [helper.make_tensor_value_info(cur_var, TensorProto.FLOAT, input_shape)]
    graph = helper.make_graph(nodes, name, inputs, outputs, initializer=initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8

    onnx.checker.check_model(model)
    onnx.save(model, str(model_path))

    return model_path, params, flops_per_sample, weight_bytes, json.dumps(input_shape)


def generate_conv(
    channels: int,
    h_w: int = 64,
    layers: int = 4,
) -> tuple[Path, int, float, int, str]:
    """Generate a Convolutional neural network ONNX model.

    Graph: L x (Conv 3x3, C->C, pad 1 -> Relu) on input of shape [batch, C, H, W].
    FLOPs per sample: 2 * L * H * W * C^2 * 9.
    Params: L * C * C * 3 * 3.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"conv_{channels}c_{h_w}hw_{layers}l"
    model_path = MODELS_DIR / f"{name}.onnx"

    params = layers * channels * channels * 9
    flops_per_sample = float(2 * layers * h_w * h_w * channels * channels * 9)
    weight_bytes = params * 4
    input_shape = ["batch", channels, h_w, h_w]

    rng = np.random.default_rng(SEED)
    nodes = []
    initializers = []
    inputs = [helper.make_tensor_value_info("X", TensorProto.FLOAT, input_shape)]
    cur_var = "X"

    for i in range(layers):
        w_name = f"W_{i}"
        w_data = rng.standard_normal((channels, channels, 3, 3), dtype=np.float32) * (1.0 / np.sqrt(channels * 9))
        initializers.append(numpy_helper.from_array(w_data.astype(np.float32), name=w_name))

        conv_out = f"conv_{i}"
        nodes.append(
            helper.make_node(
                "Conv",
                [cur_var, w_name],
                [conv_out],
                pads=[1, 1, 1, 1],
                strides=[1, 1],
            )
        )
        relu_out = f"relu_{i}"
        nodes.append(helper.make_node("Relu", [conv_out], [relu_out]))
        cur_var = relu_out

    outputs = [helper.make_tensor_value_info(cur_var, TensorProto.FLOAT, input_shape)]
    graph = helper.make_graph(nodes, name, inputs, outputs, initializer=initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8

    onnx.checker.check_model(model)
    onnx.save(model, str(model_path))

    return model_path, params, flops_per_sample, weight_bytes, json.dumps(input_shape)


def generate_attn(
    d: int,
    tokens: int = 128,
    layers: int = 2,
) -> tuple[Path, int, float, int, str]:
    """Generate a Self-Attention transformer ONNX model.

    Graph: L x (Q,K,V MatMul -> Softmax(QK^T / sqrt(d)) -> * V -> out MatMul) on [batch, T, d].
    FLOPs per sample: L * (8 * T * d^2 + 4 * T^2 * d).
    Params: 4 * L * d^2.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"attn_{d}d_{tokens}t_{layers}l"
    model_path = MODELS_DIR / f"{name}.onnx"

    params = 4 * layers * d * d
    flops_per_sample = float(layers * (8 * tokens * d * d + 4 * tokens * tokens * d))
    weight_bytes = params * 4
    input_shape = ["batch", tokens, d]

    rng = np.random.default_rng(SEED)
    nodes = []
    initializers = []
    inputs = [helper.make_tensor_value_info("X", TensorProto.FLOAT, input_shape)]

    scale_val = np.float32(1.0 / np.sqrt(d))
    initializers.append(numpy_helper.from_array(scale_val, name="attn_scale"))

    cur_var = "X"
    for i in range(layers):
        wq_name = f"Wq_{i}"
        wk_name = f"Wk_{i}"
        wv_name = f"Wv_{i}"
        wo_name = f"Wo_{i}"

        for w_name in [wq_name, wk_name, wv_name, wo_name]:
            w_data = rng.standard_normal((d, d), dtype=np.float32) * (1.0 / np.sqrt(d))
            initializers.append(numpy_helper.from_array(w_data.astype(np.float32), name=w_name))

        q = f"q_{i}"
        k = f"k_{i}"
        v = f"v_{i}"
        nodes.append(helper.make_node("MatMul", [cur_var, wq_name], [q]))
        nodes.append(helper.make_node("MatMul", [cur_var, wk_name], [k]))
        nodes.append(helper.make_node("MatMul", [cur_var, wv_name], [v]))

        kt = f"kt_{i}"
        nodes.append(helper.make_node("Transpose", [k], [kt], perm=[0, 2, 1]))
        scores = f"scores_{i}"
        nodes.append(helper.make_node("MatMul", [q, kt], [scores]))
        scaled = f"scaled_{i}"
        nodes.append(helper.make_node("Mul", [scores, "attn_scale"], [scaled]))
        attn_weights = f"attn_weights_{i}"
        nodes.append(helper.make_node("Softmax", [scaled], [attn_weights], axis=-1))
        ctx = f"ctx_{i}"
        nodes.append(helper.make_node("MatMul", [attn_weights, v], [ctx]))
        out_i = f"out_{i}"
        nodes.append(helper.make_node("MatMul", [ctx, wo_name], [out_i]))
        cur_var = out_i

    outputs = [helper.make_tensor_value_info(cur_var, TensorProto.FLOAT, input_shape)]
    graph = helper.make_graph(nodes, name, inputs, outputs, initializer=initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8

    onnx.checker.check_model(model)
    onnx.save(model, str(model_path))

    return model_path, params, flops_per_sample, weight_bytes, json.dumps(input_shape)


def create_and_register_synthetic(
    session: Session,
    family: str,
    size: int,
    layers: Optional[int] = None,
) -> AIModel:
    """Generate a synthetic ONNX model and register it in the AIModel table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if family == "mlp":
        num_layers = layers or 4
        path, params, flops, w_bytes, shape_json = generate_mlp(width=size, layers=num_layers)
        name = f"mlp-{size}w-{num_layers}l"
    elif family == "conv":
        num_layers = layers or 4
        path, params, flops, w_bytes, shape_json = generate_conv(channels=size, layers=num_layers)
        name = f"conv-{size}c-{num_layers}l"
    elif family == "attn":
        num_layers = layers or 2
        path, params, flops, w_bytes, shape_json = generate_attn(d=size, layers=num_layers)
        name = f"attn-{size}d-{num_layers}l"
    else:
        raise ValueError(f"Unknown synthetic model family: {family}")

    sha256 = compute_file_sha256(path)
    size_mb = round(path.stat().st_size / (1024 * 1024), 3)

    existing = session.exec(select(AIModel).where(AIModel.name == name)).first()
    if existing:
        existing.path = str(path.as_posix())
        existing.sha256 = sha256
        existing.params = params
        existing.flops_per_sample = flops
        existing.weight_bytes = w_bytes
        existing.size_mb = size_mb
        existing.input_shape_json = shape_json
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    ai_model = AIModel(
        name=name,
        family=family,
        source="synthetic",
        path=str(path.as_posix()),
        sha256=sha256,
        params=params,
        flops_per_sample=flops,
        weight_bytes=w_bytes,
        size_mb=size_mb,
        precision="fp32",
        input_shape_json=shape_json,
        created_at=now_iso,
    )
    session.add(ai_model)
    session.commit()
    session.refresh(ai_model)
    return ai_model


def scan_model_files(session: Session) -> list[AIModel]:
    """Scan models/ directory for real .onnx files and register them in SQLite."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    registered: list[AIModel] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for file_path in MODELS_DIR.glob("*.onnx"):
        if file_path.name == "probe.onnx":
            continue  # Internal hardware probe model

        name = file_path.stem
        existing = session.exec(select(AIModel).where(AIModel.name == name)).first()
        if existing:
            registered.append(existing)
            continue

        try:
            model = onnx.load(str(file_path))
            total_params = sum(int(np.prod(init.dims)) for init in model.graph.initializer)
            weight_bytes = sum(int(np.prod(init.dims)) * 4 for init in model.graph.initializer)
            size_mb = round(file_path.stat().st_size / (1024 * 1024), 3)
            sha256 = compute_file_sha256(file_path)

            input_shapes = []
            for inp in model.graph.input:
                dims = [d.dim_value if d.dim_value > 0 else (d.dim_param or "batch") for d in inp.type.tensor_type.shape.dim]
                input_shapes.append(dims)
            shape_json = json.dumps(input_shapes[0] if len(input_shapes) == 1 else input_shapes)

            entry = AIModel(
                name=name,
                family="file",
                source="file",
                path=str(file_path.as_posix()),
                sha256=sha256,
                params=total_params,
                flops_per_sample=None,
                weight_bytes=weight_bytes,
                size_mb=size_mb,
                precision="fp32",
                input_shape_json=shape_json,
                created_at=now_iso,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            registered.append(entry)
        except Exception as exc:
            logger.warning("Failed to parse ONNX model file %s: %s", file_path, exc)

    return registered
