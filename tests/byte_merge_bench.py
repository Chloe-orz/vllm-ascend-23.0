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
- Payload start is aligned to 8 bytes so view(dtype) works for any dtype.
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

import numpy as np
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
#   [ P bytes ]  padding to 8-byte alignment
#   [ …       ]  raw tensor bytes (concatenated)
#
# Alignment is required because PyTorch view(dtype) demands that the tensor's
# storage_offset be divisible by the target dtype's element size.

_MAGIC = 0x42544D52
_VERSION = 1
_HEADER_FMT = "<III"          # magic, version, json_meta_len
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)
_ALIGNMENT = 8                 # int64 / float64 element size


def _payload_start(meta_len: int) -> int:
    """Return byte offset where tensor payloads begin (8-byte aligned)."""
    raw = _HEADER_SIZE + meta_len
    pad = (_ALIGNMENT - raw % _ALIGNMENT) % _ALIGNMENT
    return raw + pad


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
    - 8-byte payload alignment so view(dtype) works for any dtype.
    """
    # Ensure contiguous before reinterpretation
    pieces: List[torch.Tensor] = []
    for t in tensors:
        if not t.is_contiguous():
            t = t.contiguous()
        flat = t.view(torch.uint8).reshape(-1)
        pieces.append(flat)

    meta_bytes = _build_meta_json(tensors)
    meta_len = len(meta_bytes)
    payload_off = _payload_start(meta_len)
    total_bytes = payload_off + sum(p.numel() for p in pieces)

    device = tensors[0].device
    merged = torch.empty(total_bytes, dtype=torch.uint8, device=device)

    # Write header (small, CPU -> device copy)
    header = struct.pack(_HEADER_FMT, _MAGIC, _VERSION, meta_len)
    header_cpu = torch.tensor(list(header), dtype=torch.uint8)
    merged[:_HEADER_SIZE].copy_(header_cpu.to(device, non_blocking=False))

    # Write meta
    meta_cpu = torch.tensor(list(meta_bytes), dtype=torch.uint8)
    merged[_HEADER_SIZE:_HEADER_SIZE + meta_len].copy_(meta_cpu.to(device, non_blocking=False))

    # Zero padding (if any)
    if payload_off > _HEADER_SIZE + meta_len:
        merged[_HEADER_SIZE + meta_len:payload_off].zero_()

    # Write payloads
    offset = payload_off
    for flat in pieces:
        n = flat.numel()
        merged[offset:offset + n].copy_(flat)
        offset += n

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

    payload_off = _payload_start(meta_len)
    out = []
    for item in meta:
        dtype = get_dtype(item["dtype"])
        shape = item["shape"]
        nbytes = item["nbytes"]
        offset = payload_off + item["offset"]

        chunk = merged[offset:offset + nbytes]
        # chunk is a contiguous 1-D slice of a 1-D tensor.
        # payload_off is 8-byte aligned and each tensor's nbytes is a multiple
        # of its own element_size, so offset is always aligned for view().
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
    """Build deterministic tensors so both ranks generate identical data.

    Random seeds are per-process and per-device; using torch.randn on rank 0
    and rank 1 produces different values, which breaks the torch.equal
    validation.  Instead we use a deterministic arange-based pattern that is
    identical on every rank.
    """
    tensors = []
    global_idx = 0
    for item in config:
        shape = item["shape"]
        dtype = get_dtype(item["dtype"])
        numel = math.prod(shape)
        if dtype.is_floating_point:
            # Deterministic float pattern: arange -> mod -> scale to (-1, 1)
            t = torch.arange(
                global_idx, global_idx + numel,
                dtype=torch.float32, device=device,
            )
            t = ((t % 1000) - 500) / 500.0  # range (-1.0, 1.0)
            if dtype != torch.float32:
                t = t.to(dtype)
        else:
            # Deterministic integer pattern
            t = torch.arange(
                global_idx, global_idx + numel,
                dtype=dtype, device=device,
            )
            t = (t % 2000) - 1000  # range [-1000, 999]
        t = t.reshape(shape).contiguous()
        tensors.append(t)
        global_idx += numel
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
        dummy = serialize(tensors)
        recv_buffer = torch.empty(dummy.shape, dtype=torch.uint8, device=device)

    # Extra reference buffers for full-validation (only on first iter)
    ref_recv_bufs: list[torch.Tensor] = []
    if rank == 1:
        for t in tensors:
            ref_recv_bufs.append(torch.empty_like(t))

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

        # --- HCCL P2P (byte-merge) ---
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

            # Full validation on first iteration:
            # 1) Ask rank 0 to send raw tensors (ground truth via HCCL)
            # 2) Receive raw tensors
            # 3) Compare byte-merge result vs raw result
            if i == 0:
                # Signal rank 0 to send raw tensors
                signal = torch.tensor([1], dtype=torch.int32, device=device)
                dist.send(signal, dst=0)

                for ref_buf in ref_recv_bufs:
                    handle = dist.irecv(ref_buf, src=0)
                    handle.wait()

                if len(out_tensors) != len(ref_recv_bufs):
                    print(f"[Rank1] FATAL: tensor count mismatch!")
                else:
                    all_ok = True
                    for idx, (recv, ref) in enumerate(zip(out_tensors, ref_recv_bufs)):
                        if recv.dtype != ref.dtype:
                            print(f"[Rank1] FATAL [{idx}] dtype mismatch: {recv.dtype} vs {ref.dtype}")
                            all_ok = False
                            continue
                        if recv.shape != ref.shape:
                            print(f"[Rank1] FATAL [{idx}] shape mismatch: {tuple(recv.shape)} vs {tuple(ref.shape)}")
                            all_ok = False
                            continue
                        if not torch.equal(recv.cpu(), ref.cpu()):
                            # Strict element-by-element comparison failed.
                            # Find the first mismatch and print it precisely.
                            recv_cpu = recv.cpu()
                            ref_cpu = ref.cpu()
                            flat_recv = recv_cpu.reshape(-1)
                            flat_ref = ref_cpu.reshape(-1)
                            mismatch_positions = (flat_recv != flat_ref).nonzero(as_tuple=False)
                            total_mismatch = mismatch_positions.numel()
                            first_pos = int(mismatch_positions[0].item())
                            first_idx = np.unravel_index(first_pos, recv_cpu.shape)
                            print(
                                f"[Rank1] FATAL [{idx}] VALUE mismatch! "
                                f"total_mismatched_elements={total_mismatch} / {recv.numel()}, "
                                f"first_mismatch_at_index={first_idx}, "
                                f"recv_value={flat_recv[first_pos].item()}, "
                                f"ref_value={flat_ref[first_pos].item()}"
                            )
                            # Print head / mid / tail for manual inspection
                            n = flat_recv.numel()
                            head = 30
                            tail = 30
                            mid_start = max(head, n // 2 - 15)
                            mid_end = min(n - tail, mid_start + 30)
                            print(
                                f"[Rank1] [{idx}] recv_head({head})={flat_recv[:head].tolist()}, "
                                f"mid({mid_start}-{mid_end})={flat_recv[mid_start:mid_end].tolist()}, "
                                f"tail({tail})={flat_recv[-tail:].tolist()}"
                            )
                            print(
                                f"[Rank1] [{idx}] ref_head ({head})={flat_ref[:head].tolist()}, "
                                f"mid({mid_start}-{mid_end})={flat_ref[mid_start:mid_end].tolist()}, "
                                f"tail({tail})={flat_ref[-tail:].tolist()}"
                            )
                            all_ok = False
                        else:
                            print(f"[Rank1] [{idx}] dtype={dtype_name(recv.dtype)} shape={tuple(recv.shape)}  OK")
                            # Print head / mid / tail for manual inspection
                            flat_recv = recv.cpu().reshape(-1)
                            flat_ref = ref.cpu().reshape(-1)
                            n = flat_recv.numel()
                            head = 30
                            tail = 30
                            mid_start = max(head, n // 2 - 15)
                            mid_end = min(n - tail, mid_start + 30)
                            print(
                                f"[Rank1] [{idx}] recv_head({head})={flat_recv[:head].tolist()}, "
                                f"mid({mid_start}-{mid_end})={flat_recv[mid_start:mid_end].tolist()}, "
                                f"tail({tail})={flat_recv[-tail:].tolist()}"
                            )
                            print(
                                f"[Rank1] [{idx}] ref_head ({head})={flat_ref[:head].tolist()}, "
                                f"mid({mid_start}-{mid_end})={flat_ref[mid_start:mid_end].tolist()}, "
                                f"tail({tail})={flat_ref[-tail:].tolist()}"
                            )
                    if all_ok:
                        print("[Rank1] === All tensors validated successfully ===")

        # Rank 0: wait for validation request and send raw tensors as ground truth
        if rank == 0 and i == 0:
            signal = torch.tensor([0], dtype=torch.int32, device=device)
            dist.recv(signal, src=1)
            for t in tensors:
                handle = dist.isend(t.contiguous(), dst=1)
                handle.wait()

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
