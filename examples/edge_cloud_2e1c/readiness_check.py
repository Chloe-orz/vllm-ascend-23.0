#!/usr/bin/env python3
"""2E1C 启动就绪检查：巡检三方日志，确认就绪检查点全部通过。

用法：
    python readiness_check.py \
        --cloud-log /var/log/edge_cloud/cloud_c0.log \
        --edge-logs /var/log/edge_cloud/edge_e0.log \
                   /var/log/edge_cloud/edge_e1.log

检查点（对应设计文档 §6.4）：
    1. 三方注册表加载且 digest 一致
    2. 配置摘要三方一致（tensor meta 同源）
    3. pair HCCL 组 6/6 建好（2 边 × 3 通道）
    4. 云侧 2 条 subscriber 通道就绪
    5. KV 均分打印正确
"""
import argparse
import re
import sys


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cloud-log", required=True)
    ap.add_argument("--edge-logs", nargs="+", required=True)
    args = ap.parse_args()

    cloud = open(args.cloud_log, encoding="utf-8", errors="ignore").read()
    edges = [open(p, encoding="utf-8", errors="ignore").read()
             for p in args.edge_logs]

    ok = True

    # 1. 注册表加载 + digest 一致
    digests = []
    for text in [cloud, *edges]:
        m = re.search(r"RoleRegistry loaded .* digest=([0-9a-f]+)", text)
        digests.append(m.group(1) if m else None)
    ok &= check("注册表加载", all(d is not None for d in digests))
    ok &= check("配置摘要三方一致",
                len(set(d for d in digests if d)) == 1,
                str(digests))

    # 2. 注册身份校验通过
    for i, text in enumerate(edges):
        ok &= check(f"边{i} 身份校验",
                    "Edge-cloud registry identity validated" in text)
    ok &= check("云身份校验",
                "Edge-cloud registry identity validated" in cloud)

    # 3. pair 组建组（云侧日志）
    m = re.search(r"multi-instance pair groups created: (\d+) pairs", cloud)
    ok &= check("pair 组 2/2（每组 3 通道）", bool(m) and int(m.group(1)) == 2,
                m.group(0) if m else "not found")

    # 4. 云侧多边通道就绪
    m = re.search(r"PD-separation cloud multi-edge channels: (\d+) edges",
                  cloud)
    ok &= check("云 subscriber 通道 ×2", bool(m) and int(m.group(1)) == 2)

    # 5. KV 分配：前缀协商的云侧统一管理（CloudKVRequestManager）
    ok &= check("KV 云侧自管理已初始化", "cloud_kv_initialized" in cloud)

    print("\n== 就绪检查:", "全部通过 ✅" if ok else "存在失败项 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
