#!/usr/bin/env python3
"""解析 vllm-ascend PP 打点日志：按角色+步分组，算相邻间隔，标含义。

用法:
    python parse_pp_timing.py <logfile>
    python parse_pp_timing.py <logfile> --ms          # 间隔用毫秒
    python parse_pp_timing.py <logfile> --summary-only # 只输出跨步汇总
    cat vllm.log | python parse_pp_timing.py -         # 从 stdin 读

输出: 每角色每步的相邻间隔表 + 跨步 min/avg/max 汇总 + 瓶颈段标注。
阶段语义见同目录 ../reference/interval-meaning.md。
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass

# Windows 控制台默认 GBK, 强制 stdout 用 utf-8 避免中文乱码。
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# [PP_TIMING][<role>][<stage>] <ts>  —— stage 名可含空格(到 ] 为止)
LINE_RE = re.compile(
    r"\[PP_TIMING\]\[(?P<role>[^\]]+)\]\[(?P<stage>[^\]]+)\]\s+(?P<ts>[\d.]+)"
)
# [PP_BATCH][step=N] ...  —— 仅用于辅助标注步号/类型(可选)
BATCH_STEP_RE = re.compile(r"\[PP_BATCH\]\[step=(\d+)\]")


@dataclass
class Mark:
    role: str
    stage: str
    ts: float


# 各角色单步期望序列(顺序); 用于步边界检测与完整性检查。
# worker_entry 是步首。
ROLE_SEQUENCE = {
    "standard": [
        "worker_entry", "forward_entry", "forward_done",
    ],
    "edge": [
        "worker_entry", "send_to_cloud done", "recv_from_cloud",
        "segment_a_entry", "segment_a_done",
        "segment_e_entry", "segment_e_done",
    ],
    "cloud": [
        "worker_entry", "pp_recv_done",
        "segment_c_entry", "segment_c_done",
    ],
}


def parse_lines(lines):
    """返回 marks: list[Mark]。忽略非 PP_TIMING 行。"""
    marks = []
    for ln in lines:
        m = LINE_RE.search(ln)
        if not m:
            continue
        marks.append(Mark(role=m["role"], stage=m["stage"], ts=float(m["ts"])))
    return marks


def group_by_role_steps(marks):
    """按 role 分流, 每个角色内按 worker_entry 切步。

    返回 {role: list[list[Mark]]} —— 每个内层 list 是一步。
    若首条不是 worker_entry, 作为"未闭合前段"单独成步(标 step 0)。
    """
    by_role: dict[str, list[Mark]] = defaultdict(list)
    for mk in marks:
        by_role[mk.role].append(mk)

    out: dict[str, list[list[Mark]]] = {}
    for role, seq in by_role.items():
        steps: list[list[Mark]] = []
        cur: list[Mark] = []
        for mk in seq:
            if mk.stage == "worker_entry" and cur:
                steps.append(cur)
                cur = []
            cur.append(mk)
        if cur:
            steps.append(cur)
        out[role] = steps
    return out


def check_completeness(role, step):
    """检查单步阶段序列是否符合期望(只警告, 不阻断)。"""
    expected = ROLE_SEQUENCE.get(role, [])
    if not expected:
        return None
    actual = [m.stage for m in step]
    # 允许末尾不完整(日志被截断), 只检查前缀是否乱序/缺关键阶段
    issues = []
    if actual[0] != "worker_entry":
        issues.append(f"步首非 worker_entry(实际 {actual[0]!r})")
    # 检查期望阶段是否都出现
    missing = [s for s in expected if s not in actual]
    if missing:
        issues.append(f"缺阶段 {missing}")
    return "; ".join(issues) if issues else None


def step_intervals(step, unit_factor):
    """返回 [(from_stage, to_stage, delta_in_unit), ...] 步内相邻间隔。"""
    out = []
    for i in range(len(step) - 1):
        a, b = step[i], step[i + 1]
        delta = (b.ts - a.ts) * unit_factor
        out.append((a.stage, b.stage, delta))
    return out


def summarize(all_intervals):
    """跨步汇总每类间隔: { (role, from, to): [deltas] } -> 聚合。"""
    bucket: dict[tuple, list[float]] = defaultdict(list)
    for role, intervals in all_intervals:
        for frm, to, d in intervals:
            bucket[(role, frm, to)].append(d)
    summary = []
    for (role, frm, to), ds in sorted(bucket.items()):
        if not ds:
            continue
        summary.append({
            "role": role, "from": frm, "to": to,
            "n": len(ds),
            "min": min(ds), "avg": statistics.fmean(ds), "max": max(ds),
        })
    return summary


# ── 含义提示(精简版, 完整表见 reference/interval-meaning.md) ──────────────
MEANING = {
    # edge
    ("edge", "worker_entry", "send_to_cloud done"):
        "入口+SP聚合+isend+wait发送完成; 大=SP聚合/网络发送慢",
    ("edge", "send_to_cloud done", "recv_from_cloud"):
        "等cloud算完segment_c并回传; 大=cloud中段慢或网络往返大",
    ("edge", "recv_from_cloud", "segment_a_entry"):
        "收回后到head前向前的准备; 应很小",
    ("edge", "segment_a_entry", "segment_a_done"):
        "edge head段前向; prefill步大属正常",
    ("edge", "segment_a_done", "segment_e_entry"):
        "head→tail衔接(layer_idx重置等); 应极小",
    ("edge", "segment_e_entry", "segment_e_done"):
        "edge tail段前向(尾层+norm); edge本地计算主体",
    # cloud
    ("cloud", "worker_entry", "pp_recv_done"):
        "入口+irecv+wait接收完成+预准备(与edge seg_a重叠); 大=等edge发送晚",
    ("cloud", "pp_recv_done", "segment_c_entry"):
        "收完到中段前向前准备(图参数更新); 应小",
    ("cloud", "segment_c_entry", "segment_c_done"):
        "cloud中段前向(层最多); cloud算力核心指标",
    # standard
    ("standard", "worker_entry", "forward_entry"):
        "入口+PP接收(非首rank)+输入准备; PP时含跨stage接收",
    ("standard", "forward_entry", "forward_done"):
        "完整模型前向(全层); 计算主体",
}


def fmt(v, unit):
    if v is None:
        return "-"
    return f"{v:.3f}{unit}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logfile", help="PP 打点日志文件路径, '-' 读 stdin")
    ap.add_argument("--ms", action="store_true", help="间隔用毫秒(默认秒)")
    ap.add_argument("--summary-only", action="store_true", help="只输出跨步汇总")
    args = ap.parse_args()

    unit = "ms" if args.ms else "s"
    factor = 1e3 if args.ms else 1.0

    src = sys.stdin if args.logfile == "-" else open(
        args.logfile, encoding="utf-8", errors="replace"
    )
    try:
        marks = parse_lines(src)
    finally:
        if src is not sys.stdin:
            src.close()

    if not marks:
        print("未找到任何 [PP_TIMING] 行。确认打点已开启", file=sys.stderr)
        print("  echo 1 > /tmp/vllm_pp_timing_enable  或  PP_TIMING_ENABLE=1 启动",
              file=sys.stderr)
        sys.exit(1)

    grouped = group_by_role_steps(marks)

    all_intervals = []  # (role, step_intervals)

    if not args.summary_only:
        for role in ["standard", "edge", "cloud"]:
            steps = grouped.get(role, [])
            if not steps:
                continue
            print(f"\n== role={role}  ({len(steps)} steps) ==")
            # 表头: 用各步的阶段对(以首步为准)
            header_iv = step_intervals(steps[0], factor) if len(steps[0]) > 1 else []
            cols = [f"{f}→{t}" for f, t, _ in header_iv]
            if not cols:
                cols = ["(单点步)"]
            # 截短列名便于对齐
            short = [c if len(c) <= 22 else c[:19] + "..." for c in cols]
            print("step  " + "  ".join(f"{c:>22}" for c in short))
            for i, step in enumerate(steps, 1):
                iv = step_intervals(step, factor)
                row = "  ".join(f"{d:>22.3f}" for _, _, d in iv) if iv else "(单点)"
                comp = check_completeness(role, step)
                flag = f"  ⚠ {comp}" if comp else ""
                print(f"{i:>4}  {row}{flag}")
                all_intervals.append((role, iv))
        # 补: summary_only=False 时也要收集所有步的间隔给汇总
        # (上面已 append; standard/edge/cloud 都进了)
    else:
        for role in ["standard", "edge", "cloud"]:
            for step in grouped.get(role, []):
                all_intervals.append((role, step_intervals(step, factor)))

    # 跨步汇总
    summary = summarize(all_intervals)
    print("\n== per-interval summary (min/avg/max) ==")
    print(f"{'role':<9} {'from→to':<42} {'n':>4} {'min':>10} {'avg':>10} {'max':>10}  meaning")
    # 找瓶颈(avg 最大)
    bottlenecks = []
    for s in summary:
        pair = f"{s['from']}→{s['to']}"
        short = pair if len(pair) <= 40 else pair[:37] + "..."
        meaning = MEANING.get((s["role"], s["from"], s["to"]), "")
        print(f"{s['role']:<9} {short:<42} {s['n']:>4} "
              f"{fmt(s['min'], unit):>10} {fmt(s['avg'], unit):>10} "
              f"{fmt(s['max'], unit):>10}  {meaning}")
        bottlenecks.append((s["avg"], s["role"], short, meaning))

    bottlenecks.sort(reverse=True)
    print("\n== top bottlenecks by avg ==")
    for avg, role, pair, meaning in bottlenecks[:5]:
        print(f"  {fmt(avg, unit):>10}  {role:<7} {pair}  {meaning}")

    # 完整性告警汇总
    print("\n== completeness check ==")
    any_issue = False
    for role in ["standard", "edge", "cloud"]:
        for i, step in enumerate(grouped.get(role, []), 1):
            comp = check_completeness(role, step)
            if comp:
                any_issue = True
                print(f"  {role} step {i}: {comp}")
    if not any_issue:
        print("  all steps complete (每步以 worker_entry 起、阶段齐全)")
    print(f"\n注: 间隔单位={unit}; 时间戳来自 time.perf_counter(进程本地单调钟), "
          f"不可跨角色相减。")


if __name__ == "__main__":
    main()
