#!/usr/bin/env python3
"""Reconcile edge-cloud P2P message sequences from diagnostic logs.

For each (edge, cloud) pair and each direction, aligns the sender's posted
isend/isend_draft sequence against the receiver's posted irecv/irecv_draft
sequence (both are logged at POST time via the EC diagnostics) and reports
the first position where the two sequences diverge (different head_token,
different draft step, or one side longer).  That position is the first
channel desync — the hang itself is only where the bill comes due.

Usage:
    python ec_reconcile.py \
        --cloud 0 /path/to/cloud.log \
        --edge 0 /path/to/edge0.log \
        --edge 1 /path/to/edge1.log \
        --edge 2 /path/to/edge2.log

Notes:
- Log lines come from vllm_ascend/distributed/parallel_state.py diagnostics:
    [PD] edge_cloud_isend:       ... dst_global=G ... ctx=bt=BT ht=HT ds=DS
    [PD] edge_cloud_isend_draft: ... dst_global=G ... ctx=bt=BT ht=HT ds=DS
    [PD] edge_cloud_irecv:       ... src_global=G ... ctx=bt=BT ht=HT ds=DS
    [PD] edge_cloud_irecv_draft: ... expect=[('hidden_states', (N, H))]
- Cloud-side head_tokens are wrapped as "{edge_id}:{token}"; the wrapper is
  stripped before comparison.
- Only pair members (2-rank pp_ranks) post real P2P ops; singleton-rank
  lines (cloud TP1..3 workers) are ignored.
"""

import argparse
import re
import sys
from collections import defaultdict

RE_ISEND = re.compile(
    r"edge_cloud_isend: seq=(\d+) channel=(\S+) active_pair=\((\d+),\s*(\d+)\) "
    r"pp_ranks=\[(\d+), (\d+)\] dst_idx=\d+ dst_global=(\d+) num_tokens=(\d+) "
    r"ctx=bt=(\S+) ht=(\S+) ds=(\S+)")
RE_ISEND_DRAFT = re.compile(
    r"edge_cloud_isend_draft: seq=(\d+) channel=(\S+) active_pair=\((\d+),\s*(\d+)\) "
    r"pp_ranks=\[(\d+), (\d+)\] dst_global=(\d+) ctx=bt=(\S+) ht=(\S+) ds=(\S+)")
RE_IRECV = re.compile(
    r"edge_cloud_irecv: seq=(\d+) channel=(\S+) active_pair=\((\d+),\s*(\d+)\) "
    r"pp_ranks=\[(\d+), (\d+)\] src_idx=\d+ src_global=(\d+) num_tokens=(\d+) "
    r"ctx=bt=(\S+) ht=(\S+) ds=(\S+)")
# Guard-thread early-recv variant: ctx=early_recv ht=... ch=...
RE_IRECV_EARLY = re.compile(
    r"edge_cloud_irecv: seq=(\d+) channel=(\S+) active_pair=\((\d+),\s*(\d+)\) "
    r"pp_ranks=\[(\d+), (\d+)\] src_idx=\d+ src_global=(\d+) num_tokens=(\d+) "
    r"ctx=early_recv ht=(\S+) ch=(\S+)")
RE_IRECV_DRAFT = re.compile(
    r"edge_cloud_irecv_draft: seq=(\d+) channel=(\S+) "
    r"active_pair=(?:\((\d+),\s*(\d+)\)|(None)) "
    r"pp_ranks=\[([^\]]+)\] is_pp_npu0=(\S+) ctx=bt=(\S+) ht=(\S+) ds=(\S+) "
    r"expect=(.*)")


def norm_ht(ht: str) -> str:
    """Strip the cloud-side '{edge_id}:' wrapper and the 'e{id}-' prefix."""
    m = re.match(r"^\d+:(.+)$", ht)
    if m:
        return m.group(1)
    m = re.match(r"^e\d+-(.+)$", ht)
    if m:
        return m.group(1)
    return ht


class Msg:
    __slots__ = ("seq", "kind", "channel", "pair", "ht", "ds", "bt", "shape")

    def __init__(self, seq, kind, channel, pair, ht, ds, bt, shape):
        self.seq = int(seq)
        self.kind = kind            # 'send' | 'recv'
        self.channel = channel
        self.pair = pair            # (edge_id, cloud_id)
        self.ht = norm_ht(ht)
        self.ds = ds
        self.bt = bt
        self.shape = shape

    def label(self):
        return (f"seq={self.seq} bt={self.bt} ht={self.ht[:12]} ds={self.ds} "
                f"shape={self.shape}")


def parse_file(path, sends, recvs):
    """Append messages from one log file into sends/recvs (keyed by pair+channel)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RE_ISEND.search(line)
            if m:
                seq, ch, e, c, _r0, _r1, _dst, ntok, bt, ht, ds = m.groups()
                sends[(int(e), int(c), ch)].append(
                    Msg(seq, "send", ch, (int(e), int(c)), ht, ds, bt,
                        f"({ntok},...)"))
                continue
            m = RE_ISEND_DRAFT.search(line)
            if m:
                seq, ch, e, c, _r0, _r1, _dst, bt, ht, ds = m.groups()
                sends[(int(e), int(c), ch)].append(
                    Msg(seq, "send", ch, (int(e), int(c)), ht, ds, bt, "?"))
                continue
            m = RE_IRECV.search(line)
            if m:
                seq, ch, e, c, _r0, _r1, _src, ntok, bt, ht, ds = m.groups()
                recvs[(int(e), int(c), ch)].append(
                    Msg(seq, "recv", ch, (int(e), int(c)), ht, ds, bt,
                        f"({ntok},...)"))
                continue
            m = RE_IRECV_EARLY.search(line)
            if m:
                seq, ch, e, c, _r0, _r1, _src, ntok, ht, _ch2 = m.groups()
                recvs[(int(e), int(c), ch)].append(
                    Msg(seq, "recv", ch, (int(e), int(c)), ht, "-",
                        "EARLY_RECV", f"({ntok},...)"))
                continue
            m = RE_IRECV_DRAFT.search(line)
            if m:
                (seq, ch, e_s, c_s, none_s, ranks, is_npu0, bt, ht, ds,
                 expect) = m.groups()
                # Only 2-rank pair members post real P2P recvs; skip the
                # TP-broadcast-only singleton lines from cloud TP1..3.
                if none_s or len([r for r in ranks.split(",")
                                  if r.strip()]) != 2:
                    continue
                e, c = int(e_s), int(c_s)
                recvs[(int(e), int(c), ch)].append(
                    Msg(seq, "recv", ch, (int(e), int(c)), ht, ds, bt, expect))
                continue


def _ds_mismatch(a: str, b: str) -> bool:
    """Compare draft step idx; '-'/'None' are unknown placeholders."""
    if a in ("-", "None") or b in ("-", "None"):
        return False
    return a != b


def reconcile(tag, send_seq, recv_seq, tail=5):
    """Align two ordered sequences; print the first divergence with context."""
    n = min(len(send_seq), len(recv_seq))
    diverged = None
    for i in range(n):
        s, r = send_seq[i], recv_seq[i]
        if s.ht != r.ht or _ds_mismatch(s.ds, r.ds):
            diverged = i
            break
    print(f"\n=== {tag}: sends={len(send_seq)} recvs={len(recv_seq)} "
          f"matched_prefix={diverged if diverged is not None else n} ===")
    if diverged is None and len(send_seq) == len(recv_seq):
        print("  OK: fully aligned")
        return True
    idx = diverged if diverged is not None else n
    lo = max(0, idx - tail)
    print(f"  first divergence at position {idx}:")
    for j in range(lo, min(idx, len(send_seq))):
        print(f"    [{j}] send  {send_seq[j].label()}")
        print(f"    [{j}] recv  {recv_seq[j].label()}")
    if idx < len(send_seq):
        print(f"  > [{idx}] send  {send_seq[idx].label()}   <-- sender posted this")
    else:
        print(f"  > [{idx}] send  (none — sender has no message #{idx})")
    if idx < len(recv_seq):
        print(f"  > [{idx}] recv  {recv_seq[idx].label()}   <-- receiver expected this")
    else:
        print(f"  > [{idx}] recv  (none — receiver has no expectation #{idx})")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud", nargs=2, action="append", metavar=("ID", "LOG"),
                    required=True)
    ap.add_argument("--edge", nargs=2, action="append", metavar=("ID", "LOG"),
                    required=True)
    args = ap.parse_args()

    # (pair, channel) -> ordered messages, per direction and side.
    e2c_sends = defaultdict(list)   # posted by edges
    e2c_recvs = defaultdict(list)   # posted by cloud
    c2e_sends = defaultdict(list)   # posted by cloud
    c2e_recvs = defaultdict(list)   # posted by edges

    for cid, path in args.cloud:
        s, r = defaultdict(list), defaultdict(list)
        parse_file(path, s, r)
        for k, v in s.items():
            c2e_sends[k].extend(v)
        for k, v in r.items():
            e2c_recvs[k].extend(v)
    for eid, path in args.edge:
        s, r = defaultdict(list), defaultdict(list)
        parse_file(path, s, r)
        for k, v in s.items():
            e2c_sends[k].extend(v)
        for k, v in r.items():
            c2e_recvs[k].extend(v)

    keys = sorted(set(e2c_sends) | set(e2c_recvs) | set(c2e_sends) | set(c2e_recvs))
    all_ok = True
    for (e, c, ch) in keys:
        ok1 = reconcile(f"pair=({e},{c}) channel={ch} e2c",
                        e2c_sends.get((e, c, ch), []),
                        e2c_recvs.get((e, c, ch), []))
        ok2 = reconcile(f"pair=({e},{c}) channel={ch} c2e",
                        c2e_sends.get((e, c, ch), []),
                        c2e_recvs.get((e, c, ch), []))
        all_ok = all_ok and ok1 and ok2
    print("\n" + ("ALL CHANNELS ALIGNED" if all_ok
                  else "DESYNC FOUND — first divergence above is the prime suspect"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
