#!/usr/bin/env python3
"""
Byte-merge bench for edge-cloud tensor transfer.

Measures serialization (cat-to-uint8), HCCL P2P transfer, and deserialization
overhead when heterogeneous tensors (different dtype/shape) are packed into a
single isend/irecv buffer.

Key correctness guarantees:
- Serialization uses raw byte reinterpretation (view), no precision loss.
- A small JSON metadata header is prepended so the receiver can reconstruct
  shape / dtype / offsets without prior agreement.
- Built-in validation (torch.equal) on the first iteration.

Usage (2 ranks on Ascend NPU):
    torchrun --nproc_per_node=2 byte_merge_bench.py \
        --tensor-config '[
            {"shape":[1024,4096],"dtype":"bfloat16"},
            {"shape":[1024,4096],"dtype":"bfloat16"},
            {"shape":[1024,3],  "dtype":"int64"}
        ]' \
        --warmup 10 --iter 50
"""

import argparse
import json
import math
import os
import struct
import time
from typing import Dict, List, Tuple

import torch
import torch.distributed as dist

# ---------------------------------------------------------------------------
# dtype helpers
# ---------------------------------------------------------------------------

_DTNAME_TO_TORCH = {
    "bool": torch.bool,
    "uint8": torch.uint8,
    "int8": torch.int8,
    "int16": torch.int16,
    "int32": torch.int32,
    "int64": torch.int64,
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
    "float32": torch.float32,
    "float64": torch.float64,
}

_TORCH_TO_DTNAME = {v: k for k, v in _DTNAME_TO_TORCH.items()}


def get_dtype(name: str) -> torch.dtype:
    if name not in _DTNAME_TO_TORCH:
        raise ValueError(f"Unsupported dtype '{name}'. Supported: {list(_DTNAME_TO_TORCH.keys())}")
    return _DTNAME_TO_TORCH[name]


def dtype_name(dt: torch.dtype) -> str:
    if dt not in _TORCH_TO_DTNAME:
        raise ValueError(f"Unsupported torch dtype {dt}")
    return _TORCH_TO_DTNAME[dt]


# ---------------------------------------------------------------------------
# Serialization format
# ---------------------------------------------------------------------------
#
#   [ 4 bytes ]  magic   = 0x4254_4D52  ("BRMR" – Byte-Reinterpret Merge)
#   [ 4 bytes ]  version = 1
#   [ 4 bytes ]  json_meta_len
#   [ N bytes ]  json_meta  (UTF-8)
#   [ …       ]  raw tensor bytes (concatenated)
#
# This small header removes the need for "out-of-band" meta agreement.

_MAGIC = 0x4254_4D52
_VERSION = 1
_HEADER_FMT = "<III"          # magic, version, json_meta_len
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


def _build_meta_json(tensors: List[torch.Tensor]) -> bytes:
    meta = []
    offset = 0
    for t in tensors:
        nbytes = t.numel() * t.element_size()
        meta.append({
            "shape": list(t.shape),
            "dtype": dtype_name(t.dtype),
            "nbytes": nbytes,
            "offset": offset,
        })
        offset += nbytes
    return json.dumps(meta, separators=(",", ":")).encode("utf-8")


def serialize(tensors: List[torch.Tensor]) -> torch.Tensor:
    """
    Pack a list of tensors into a single 1-D uint8 tensor.

    Guarantees:
    - No precision loss (raw byte reinterpretation via view).
    - Self-describing header so receiver does not need external config.
    """
    # Ensure contiguous before reinterpretation
    pieces: List[torch.Tensor] = []
    for t in tensors:
        if not t.is_contiguous():
            t = t.contiguous()
        # reinterpret as flat bytes
        flat = t.view(torch.uint8).reshape(-1)
        pieces.append(flat)

    meta_bytes = _build_meta_json(tensors)
    meta_len = len(meta_bytes)

    # Build header on CPU then move to target device
    header = struct.pack(_HEADER_FMT, _MAGIC, _VERSION, meta_len)
    header_t = torch.frombuffer(header, dtype=torch.uint8)
    meta_t = torch.frombuffer(meta_bytes, dtype=torch.uint8)

    # All pieces must live on the same device
    device = tensors[0].device
    header_t = header_t.to(device, non_blocking=False)
    meta_t = meta_t.to(device, non_blocking=False)

    merged = torch.cat([header_t, meta_t] + pieces)
    return merged


def deserialize(merged: torch.Tensor) -> List[torch.Tensor]:
    """
    Unpack a merged uint8 tensor back into typed tensors.

    Returns tensors on the same device as `merged`.
    """
    if merged.dim() != 1:
        raise ValueError(f"deserialize expects 1-D buffer, got shape {tuple(merged.shape)}")

    # Read header on CPU (tiny, negligible cost)
    header_bytes = merged[:_HEADER_SIZE].cpu().numpy().tobytes()
    magic, version, meta_len = struct.unpack(_HEADER_FMT, header_bytes)
    if magic != _MAGIC:
        raise ValueError(f"Bad magic {hex(magic)}, expected {hex(_MAGIC)}")
    if version != _VERSION:
        raise ValueError(f"Unsupported version {version}")

    meta_bytes = merged[_HEADER_SIZE:_HEADER_SIZE + meta_len].cpu().numpy().tobytes()
    meta = json.loads(meta_bytes.decode("utf-8"))

    payload_start = _HEADER_SIZE + meta_len
    out = []
    for item in meta:
        dtype = get_dtype(item["dtype"])
        shape = item["shape"]
        nbytes = item["nbytes"]
        offset = payload_start + item["offset"]

        chunk = merged[offset:offset + nbytes]
        # chunk is a 1-D contiguous slice of a 1-D tensor → always safe to view
        t = chunk.view(dtype).reshape(shape)
        # Force contiguous copy so downstream kernels do not fight strides.
        if not t.is_contiguous():
            t = t.contiguous()
        out.append(t)

    return out


# ---------------------------------------------------------------------------
# Tensor factory
# ---------------------------------------------------------------------------

def build_tensors(config: List[Dict], device: torch.device) -> List[torch.Tensor]:
    tensors = []
    for item in config:
        shape = item["shape"]
        dtype = get_dtype(item["dtype"])
        # For floating dtypes use randn so we can verify values;
        # for integer dtypes use randint so non-zero values survive.
        if dtype.is_floating_point:
            t = torch.randn(shape, dtype=torch.float32, device=device)
            if dtype != torch.float32:
                t = t.to(dtype)
        else:
            t = torch.randint(-1000, 1000, shape, dtype=dtype, device=device)
        t = t.contiguous()
        tensors.append(t)
    return tensors


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def benchmark(rank: int, config: List[Dict], args):
    device = torch.device(f"npu:{rank}")
    torch.npu.set_device(device)

    tensors = build_tensors(config, device)
    total_payload = sum(t.numel() * t.element_size() for t in tensors)

    if rank == 0:
        print(f"[Rank0] Tensor config:")
        for i, item in enumerate(config):
            print(f"  [{i}] shape={item['shape']} dtype={item['dtype']}")
        print(f"[Rank0] Total payload bytes: {total_payload} ({total_payload / 1024 / 1024:.2f} MiB)")

    # Pre-allocate recv buffer on rank 1
    if rank == 1:
        # We do not know the exact merged size yet, but we can over-allocate
        # (header is < 1 KiB for reasonable tensor counts).
        dummy = serialize(tensors)
        recv_buffer = torch.empty_like(dummy)
        recv_meta = None  # populated after first recv

    # Synchronize
    torch.npu.synchronize(device)

    # Warmup
    for _ in range(args.warmup):
        merged = serialize(tensors)
        torch.npu.synchronize(device)
        if rank == 0:
            handle = dist.isend(merged, dst=1)
            handle.wait()
        else:
            handle = dist.irecv(recv_buffer, src=0)
            handle.wait()
            _ = deserialize(recv_buffer)
        torch.npu.synchronize(device)

    # Measurement containers
    serialize_times = []
    deserialize_times = []
    comm_times = []

    for i in range(args.iter):
        # --- Serialize ---
        torch.npu.synchronize(device)
        t0 = time.perf_counter()
        merged = serialize(tensors)
        torch.npu.synchronize(device)
        t1 = time.perf_counter()
        serialize_times.append((t1 - t0) * 1000.0)

        # --- HCCL P2P ---
        start_evt = torch.npu.Event(enable_timing=True)
        end_evt = torch.npu.Event(enable_timing=True)

        if rank == 0:
            start_evt.record()
            handle = dist.isend(merged, dst=1)
            handle.wait()
            end_evt.record()
        else:
            start_evt.record()
            handle = dist.irecv(recv_buffer, src=0)
            handle.wait()
            end_evt.record()

        torch.npu.synchronize(device)
        comm_times.append(start_evt.elapsed_time(end_evt))

        # --- Deserialize ---
        if rank == 1:
            torch.npu.synchronize(device)
            t2 = time.perf_counter()
            out_tensors = deserialize(recv_buffer)
            torch.npu.synchronize(device)
            t3 = time.perf_counter()
            deserialize_times.append((t3 - t2) * 1000.0)

            # Strict validation on first iteration
            if i == 0:
                if len(out_tensors) != len(tensors):
                    print(f"[Rank1] FATAL: tensor count mismatch!")
                else:
                    all_ok = True
                    for idx, (orig, recv) in enumerate(zip(tensors, out_tensors)):
                        if orig.dtype != recv.dtype:
                            print(f"[Rank1] FATAL [{idx}] dtype mismatch: {orig.dtype} vs {recv.dtype}")
                            all_ok = False
                            continue
                        if orig.shape != recv.shape:
                            print(f"[Rank1] FATAL [{idx}] shape mismatch: {tuple(orig.shape)} vs {tuple(recv.shape)}")
                            all_ok = False
                            continue
                        if not torch.equal(orig.cpu(), recv.cpu()):
                            print(f"[Rank1] FATAL [{idx}] VALUE mismatch!")
                            all_ok = False
                        else:
                            print(f"[Rank1] [{idx}] dtype={dtype_name(recv.dtype)} shape={tuple(recv.shape)}  OK  "
                                  f"max_abs_diff=0.0")
                    if all_ok:
                        print("[Rank1] === All tensors validated successfully ===")

    # Report
    if rank == 0:
        avg_ser = sum(serialize_times) / len(serialize_times)
        avg_comm = sum(comm_times) / len(comm_times)
        overhead_ratio = avg_ser / avg_comm * 100 if avg_comm > 0 else float('inf')
        print(f"\n[Rank0] ===== Results ({args.iter} iters) =====")
        print(f"[Rank0] Avg serialize time      : {avg_ser:.4f} ms")
        print(f"[Rank0] Avg HCCL send time      : {avg_comm:.4f} ms")
        print(f"[Rank0] Ser / Comm overhead     : {overhead_ratio:.2f}%")
    else:
        avg_des = sum(deserialize_times) / len(deserialize_times)
        avg_comm = sum(comm_times) / len(comm_times)
        overhead_ratio = avg_des / avg_comm * 100 if avg_comm > 0 else float('inf')
        print(f"\n[Rank1] ===== Results ({args.iter} iters) =====")
        print(f"[Rank1] Avg deserialize time    : {avg_des:.4f} ms")
        print(f"[Rank1] Avg HCCL recv time      : {avg_comm:.4f} ms")
        print(f"[Rank1] Deser / Comm overhead   : {overhead_ratio:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Byte-merge serialization / HCCL bench")
    parser.add_argument(
        "--tensor-config", type=str, required=True,
        help='JSON list of {"shape": [...], "dtype": "bfloat16"}'
    )
    parser.add_argument("--warmup", type=int, default=10, help="Warmup iterations")
    parser.add_argument("--iter", type=int, default=50, help="Benchmark iterations")
    args = parser.parse_args()

    config = json.loads(args.tensor_config)

    rank = int(os.environ.get("RANK", 0))
    world_size = int(os.environ.get("WORLD_SIZE", 1))
    dist.init_process_group("hccl", rank=rank, world_size=world_size)

    if dist.get_world_size() != 2:
        raise RuntimeError("Requires exactly 2 ranks.")

    try:
        benchmark(rank, config, args)
    finally:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
