# Claude Code Session

> **Resume in CLI:** `claude --resume de702c0d-1419-48ad-98bd-05986960da8b`

| Field | Value |
|---|---|
| **Project** | `c:\v0\23\0-lwd-acc-test-br` |
| **Session ID** | `de702c0d-1419-48ad-98bd-05986960da8b` |
| **Working Dir** | `c:\v0.23.0_lwd_acc_test_br` |
| **Started** | 2026/8/6 10:42:42 |
| **Last Updated** | 2026/8/6 23:18:15 |
| **Messages** | 564 |

---

## User <sup>2026/8/6 10:42:42</sup>

边云场景，存在精度问题，分析 C:\theroadtofree_github\vllm-ascend\仓的9772b349c9afe062aba6b1b180b9c395d52c9ec3和c19ac5b1e137765dce2181e51f2f8df575636cbc是否有关


---

## Assistant <sup>2026/8/6 10:42:55</sup>


---

## Assistant <sup>2026/8/6 10:42:56</sup>

I'll analyze both commits in the vllm-ascend repository to determine if they're related to the edge-cloud precision issue. Let me examine them in parallel.


---

## Assistant <sup>2026/8/6 10:42:57</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git log --oneline -1 9772b349c9afe062aba6b1b180b9c395d52c9ec3 2>&1 && echo \"===SEP===\" && git log --oneline -1 c19ac5b1e137765dce2181e51f2f8df575636cbc 2>&1",
  "description": "Check both commits exist and show oneline"
}
```

</details>


---

## User <sup>2026/8/6 10:50:28</sup>

<details>
<summary>Tool Result</summary>

```
9772b349 refactor(parallel_state): 拆分边缘云P2P的发送和接收流
===SEP===
c19ac5b1 refactor(worker): 新增wait参数优化_pp_send_work等待逻辑
Shell cwd was reset to c:\v0.23.0_lwd_acc_test_br
```

</details>


---

## Assistant <sup>2026/8/6 10:50:39</sup>


---

## Assistant <sup>2026/8/6 10:50:40</sup>

Both commits exist. Let me get the full details of each commit.


---

## Assistant <sup>2026/8/6 10:50:41</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git show --stat --format=\"FULL:%H%nAuthor: %an%nDate: %ad%nSubject: %s%n%nBody:%n%b%n===END===\" 9772b349c9afe062aba6b1b180b9c395d52c9ec3 2>&1",
  "description": "Show commit 9772 full metadata and stat"
}
```

</details>


---

## Assistant <sup>2026/8/6 10:50:42</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git show --stat --format=\"FULL:%H%nAuthor: %an%nDate: %ad%nSubject: %s%n%nBody:%n%b%n===END===\" c19ac5b1e137765dce2181e51f2f8df575636cbc 2>&1",
  "description": "Show commit c19ac full metadata and stat"
}
```

</details>


---

## User <sup>2026/8/6 10:51:37</sup>

<details>
<summary>Tool Result</summary>

```
FULL:9772b349c9afe062aba6b1b180b9c395d52c9ec3
Author: theroadtofree
Date: Fri Jul 31 20:11:41 2026 +0800
Subject: refactor(parallel_state): 拆分边缘云P2P的发送和接收流

Body:
更新了边缘云P2P通信的流管理逻辑，为每个通道按发送和接收方向创建独立的NPU流，避免同通道内发送和接收操作互相阻塞，解决潜在的死锁问题，同时更新了相关注释和调用点。

===END===

 vllm_ascend/distributed/parallel_state.py | 77 ++++++++++++++++++++++---------
 1 file changed, 56 insertions(+), 21 deletions(-)
Shell cwd was reset to c:\v0.23.0_lwd_acc_test_br
```

</details>


---

## User <sup>2026/8/6 10:51:39</sup>

<details>
<summary>Tool Result</summary>

```
FULL:c19ac5b1e137765dce2181e51f2f8df575636cbc
Author: theroadtofree
Date: Fri Jul 31 19:57:24 2026 +0800
Subject: refactor(worker): 新增wait参数优化_pp_send_work等待逻辑

Body:
添加wait参数以区分传统流水线和边云场景的发送等待行为，避免在边云部署时出现死锁，同时保留原有同步逻辑兼容旧版流水线。

===END===

 vllm_ascend/worker/worker.py | 42 ++++++++++++++++++++++++++++++++----------
 1 file changed, 32 insertions(+), 10 deletions(-)
Shell cwd was reset to c:\v0.23.0_lwd_acc_test_br
```

</details>


---

## Assistant <sup>2026/8/6 10:51:49</sup>


---

## Assistant <sup>2026/8/6 10:51:50</sup>

Both commits are by the same author, same day (Jul 31, 2026), minutes apart, and both touch edge-cloud (边云) P2P / pipeline-parallel send logic for deadlock avoidance. Let me examine the actual diffs to assess the technical relationship and any precision implications.


---

## Assistant <sup>2026/8/6 10:51:51</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git show 9772b349c9afe062aba6b1b180b9c395d52c9ec3 2>&1",
  "description": "Show full diff of commit 9772"
}
```

</details>


---

## Assistant <sup>2026/8/6 10:51:52</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git show c19ac5b1e137765dce2181e51f2f8df575636cbc 2>&1",
  "description": "Show full diff of commit c19ac"
}
```

</details>


---

## User <sup>2026/8/6 10:55:58</sup>

<details>
<summary>Tool Result</summary>

```
commit 9772b349c9afe062aba6b1b180b9c395d52c9ec3
Author: theroadtofree <hw.wangtongtong@huawei.com>
Date:   Fri Jul 31 20:11:41 2026 +0800

    refactor(parallel_state): 拆分边缘云P2P的发送和接收流
    
    更新了边缘云P2P通信的流管理逻辑，为每个通道按发送和接收方向创建独立的NPU流，避免同通道内发送和接收操作互相阻塞，解决潜在的死锁问题，同时更新了相关注释和调用点。

diff --git a/vllm_ascend/distributed/parallel_state.py b/vllm_ascend/distributed/parallel_state.py
index 960261d1..df4a4fd7 100644
--- a/vllm_ascend/distributed/parallel_state.py
+++ b/vllm_ascend/distributed/parallel_state.py
@@ -38,7 +38,7 @@ _FLASHCOMM2_OTP: GroupCoordinator | None = None
 _FLASHCOMM2_ODP: GroupCoordinator | None = None
 
 # ------------------------------------------------------------------ #
-# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #
+# Per-(channel, direction) dedicated streams for edge-cloud P2P.      #
 # ------------------------------------------------------------------ #
 # Each hidden channel (PREFILL_1, PREFILL_2) gets its own NPU stream
 # so that isend/
...(truncated)
```

</details>


---

## User <sup>2026/8/6 10:56:00</sup>

<details>
<summary>Tool Result</summary>

```
commit c19ac5b1e137765dce2181e51f2f8df575636cbc
Author: theroadtofree <hw.wangtongtong@huawei.com>
Date:   Fri Jul 31 19:57:24 2026 +0800

    refactor(worker): 新增wait参数优化_pp_send_work等待逻辑
    
    添加wait参数以区分传统流水线和边云场景的发送等待行为，避免在边云部署时出现死锁，同时保留原有同步逻辑兼容旧版流水线。

diff --git a/vllm_ascend/worker/worker.py b/vllm_ascend/worker/worker.py
index 34109523..7dabf52a 100644
--- a/vllm_ascend/worker/worker.py
+++ b/vllm_ascend/worker/worker.py
@@ -580,22 +580,44 @@ class NPUWorker(WorkerBase):
                         channel.value, len(handles))
             self._pp_send_work_by_channel[channel.value] = handles
 
-    def _wait_pp_send_work(self, channel: HiddenChannelType | None = None) -> None:
+    def _wait_pp_send_work(
+        self,
+        channel: HiddenChannelType | None = None,
+        wait: bool = True,
+    ) -> None:
+        # When wait=False (edge-cloud path), do NOT call handle.wait() on the
+        # isend handles - just drop them. ProcessGroupHCCL internally records
+       
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 10:56:47</sup>


---

## Assistant <sup>2026/8/6 10:56:47</sup>

Now I have both diffs. Let me check the ancestry relationship between the two commits and the surrounding history to confirm how they fit together.


---

## Assistant <sup>2026/8/6 10:56:49</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && echo \"=== Is c19ac an ancestor of 9772? ===\" && git merge-base --is-ancestor c19ac5b1e137765dce2181e51f2f8df575636cbc 9772b349c9afe062aba6b1b180b9c395d52c9ec3 && echo \"YES: c19ac is ancestor of 9772\" || echo \"NO\" && echo \"\" && echo \"=== Is 9772 an ancestor of c19ac? ===\" && git merge-base --is-ancestor 9772b349c9afe062aba6b1b180b9c395d52c9ec3 c19ac5b1e137765dce2181e51f2f8df575636cbc && echo \"YES\" || echo \"NO\" && echo \"\" && echo \"=== Commits between c19ac and 9772 (chronological) ===\" && git log --oneline c19ac5b1e137765dce2181e51f2f8df575636cbc..9772b349c9afe062aba6b1b180b9c395d52c9ec3 2>&1",
  "description": "Check ancestry and commits between the two"
}
```

</details>


---

## Assistant <sup>2026/8/6 10:56:50</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && echo \"=== Surrounding edge-cloud commits by same author on Jul 31 ===\" && git log --oneline --author=theroadtofree --since=\"2026-07-31 00:00\" --until=\"2026-08-01 00:00\" 2>&1 | head -40",
  "description": "List same-author commits that day"
}
```

</details>


---

## User <sup>2026/8/6 10:57:06</sup>

<details>
<summary>Tool Result</summary>

```
=== Is c19ac an ancestor of 9772? ===
YES: c19ac is ancestor of 9772

=== Is 9772 an ancestor of c19ac? ===
NO

=== Commits between c19ac and 9772 (chronological) ===
9772b349 refactor(parallel_state): 拆分边缘云P2P的发送和接收流
Shell cwd was reset to c:\v0.23.0_lwd_acc_test_br
```

</details>


---

## User <sup>2026/8/6 10:57:09</sup>

<details>
<summary>Tool Result</summary>

```
=== Surrounding edge-cloud commits by same author on Jul 31 ===
9772b349 refactor(parallel_state): 拆分边缘云P2P的发送和接收流
c19ac5b1 refactor(worker): 新增wait参数优化_pp_send_work等待逻辑
58a00160 Revert "refactor(ascend): 重构云侧调度器DP协调为快照差值跟随执行模式"
6a55508d fix(engine/passive_core): 打印队列时新增seq参数日志
b00bd663 refactor(engine/scheduler): 调整日志打印与初始化逻辑
850158f8 Merge pull request #14 from theroadtofree/v0.20.2_lwd_update_dpds_0730_mtp
c011696d fix(engine_core): 修复DP=1场景下MTP生成异常的问题
Shell cwd was reset to c:\v0.23.0_lwd_acc_test_br
```

</details>


---

## Assistant <sup>2026/8/6 10:57:40</sup>


---

## Assistant <sup>2026/8/6 10:57:41</sup>

Let me check whether any later commit revisits this edge-cloud P2P send logic (e.g., a precision follow-up), to complete the picture.


---

## Assistant <sup>2026/8/6 10:57:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && echo \"=== Commits after 9772 touching the same files/areas ===\" && git log --oneline 9772b349c9afe062aba6b1b180b9c395d52c9ec3..HEAD -- vllm_ascend/distributed/parallel_state.py vllm_ascend/worker/worker.py 2>&1 | head -30 && echo \"\" && echo \"=== Any precision/精度 commits near this range? ===\" && git log --oneline --all --since=\"2026-07-30\" --until=\"2026-08-03\" 2>&1 | grep -iE \"精度|precision|acc|准确|wait|send|stream|edge|cloud|边|云|p2p|deadlock|死锁\" | head -30",
  "description": "Check for later related/precision commits"
}
```

</details>


---

## User <sup>2026/8/6 10:58:13</sup>

<details>
<summary>Tool Result</summary>

```
=== Commits after 9772 touching the same files/areas ===
b8d002c6 fix(worker): 修复shared model edge下Cloud早期recv未指定src=0导致PP通信错配
8c224d1a style: 将多处error日志降级为info级别日志
ab0488d1 Merge pull request #18 from yulemao/v0.20.2_lwd_update_dpds_fix
afeb6a47 Merge pull request #15 from yulemao/v0.20.2_lwd_update_dpds_merge
c1eb29d1 scheduler_output增加original_seq调试

=== Any precision/精度 commits near this range? ===
3ac51ef4 Revert "feat(ascend): add segment-level DP coordination for edge-cloud PD separation"
e9f167fa feat(ascend): add segment-level DP coordination for edge-cloud PD separation
77d3705b fix(scheduler): 修复跨批次边缘-云调度死锁问题
266faf18 Revert "修复云侧Cloud draft metadata cache exceeded bound"
0a7ecb48 Revert "修复云侧Cloud draft metadata cache exceeded bound"
a49dd3f4 修复PD穿插下边云input_batch顺序发散导致多模态decode精度错误
fd421b86 尝试修复精度问题，edge侧也对batch进行重排
6fbd8606 临时修复qwen s1w1多模态精度，fast—path修好后需要去掉
9772b349 refactor(parallel_state): 拆分边缘云P2P的发送和接收流
c19ac5b1 refactor(worker): 新增wait参数优化_pp_send_work等待逻辑
58a00160 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 10:58:24</sup>


---

## Assistant <sup>2026/8/6 10:58:26</sup>

This reveals a cluster of precision-related commits in the same area. Notably `7222501b` ("修复default stream创建empty tensor但是接收流读的问题" — default-stream tensor read by the recv stream) is exactly the stream-race failure class these two commits touch. Let me determine whether these precision fixes came before or after c19ac/9772.


---

## Assistant <sup>2026/8/6 10:58:28</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && for c in 7222501b a49dd3f4 fd421b86 6fbd8606 b8d002c6 5cef82ab; do d=$(git log -1 --format=\"%ad %h %s\" --date=short $c 2>/dev/null); anc=$(git merge-base --is-ancestor $c 9772b349c9afe062aba6b1b180b9c395d52c9ec3 2>/dev/null && echo \"BEFORE_9772(ancestor)\" || echo \"AFTER_or_unrelated\"); echo \"$d  ||  $anc\"; done",
  "description": "Determine timing of precision fixes vs 9772"
}
```

</details>


---

## User <sup>2026/8/6 11:02:58</sup>

<details>
<summary>Tool Result</summary>

```
2026-07-31 7222501b 修复default stream创建empty tensor但是接收流读的问题  ||  AFTER_or_unrelated
2026-07-28 a49dd3f4 修复PD穿插下边云input_batch顺序发散导致多模态decode精度错误  ||  AFTER_or_unrelated
2026-07-24 fd421b86 尝试修复精度问题，edge侧也对batch进行重排  ||  AFTER_or_unrelated
2026-07-31 6fbd8606 临时修复qwen s1w1多模态精度，fast—path修好后需要去掉  ||  AFTER_or_unrelated
2026-08-03 b8d002c6 fix(worker): 修复shared model edge下Cloud早期recv未指定src=0导致PP通信错配  ||  AFTER_or_unrelated
2026-07-30 5cef82ab fix(ascend): 修复边缘云分段调度与通信同步问题  ||  BEFORE_9772(ancestor)
Shell cwd was reset to c:\v0.23.0_lwd_acc_test_br
```

</details>


---

## Assistant <sup>2026/8/6 11:03:47</sup>


---

## Assistant <sup>2026/8/6 11:04:06</sup>

## 分析结论：这两个 commit 强相关，是同一改动的一对连续提交

### 1. 血缘关系：连续提交、同一作者、同一天

| | c19ac5b1 | 9772b349 |
|---|---|---|
| 时间 | 2026-07-31 **19:57** | 2026-07-31 **20:11**（晚 14 分钟） |
| 作者 | theroadtofree | theroadtofree |
| 文件 | `vllm_ascend/worker/worker.py` | `vllm_ascend/distributed/parallel_state.py` |

关键证据：`git log c19ac..9772` 之间**没有任何提交** —— 9772 的直接父提交就是 c19ac。也就是说 9772 是紧贴着 c19ac 写的，后者建立在前者之上。

### 2. 它们是同一死锁问题的「两半」，互补缺一不可

两者都针对**边云 P2P 流水线并行 isend/irecv** 的死锁，但修的是不同层：

- **c19ac（句柄同步层）**：给 `_wait_pp_send_work` 加 `wait` 参数，边云路径传 `wait=False`，**不再调用 `handle.wait()`**。理由：`handle.wait()` 会做 `hcclEndEvent.block(compute stream)`，把 isend 完成重新钉回计算流，导致计算流卡住等对端 irecv → 在 2P1D / DP 调度失配下死锁。
- **9772（NPU 流层）**：把「每通道一条流」拆成「每(通道,方向)一条流」，让同通道的 send/recv 不再串行在一条流上。理由：单流时 isend（云→边 P尾）被慢的对端 irecv 阻塞，会连带阻塞该通道的 irecv（边→云 P首）→ 死锁。

两者都明确写了**对齐 MindIE 的设计**：MindIE 丢弃 isend 句柄 = c19ac 的 `wait=False`；MindIE 用 `[recv_stream, send_stream]` 一对 = 9772 的流拆分。**单独任一个仍会死锁**，合起来才把 isend/irecv 与计算流、彼此之间彻底解耦。

而且它们作用在**同一批发送**上：c19ac 不再 wait 的那些 isend 句柄，正是 9772 拆分流后经 `_hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, ...)` 提交的那些。

### 3. 与「精度问题」的关系（你关注的重点）

这两个 commit 本身是**死锁/同步重构**，不改变计算或发送的数值，不是直接的精度修改。但它们改了同步契约，是边云精度/正确性问题的**合理嫌疑来源**，且同区域有一簇精度修复：

- **c19ac 的 `wait=False` 是主要精度风险点。** 丢掉 `handle.wait()` 后，计算流不再等 isend 完成就进入下一轮迭代。安全性**完全依赖** `ProcessGroupHCCL` 内部 `recordStream(tensor, hcclStream)` 保活发送缓冲。一旦该保证不成立——例如发送的是复用激活缓冲的 view/slice（diff 里的 `merged[:num_tokens]`、`full_tensor[:num_tokens]`），或 NPU allocator 行为有差异——下一轮 forward 就会覆写仍在途中的发送内存 → **接收端读到半覆写的数据 → 张量错乱/精度下降**，且通常表现为偶发。
- **9772 的流拆分会放大这个窗口。** send/recv 独立流后发送可更晚完成，与 `wait=False` 叠加，扩大了「发送在途、计算已前进」的竞态窗口。单独不改变数值，但与 c19ac 强耦合。
- **仓库内旁证**：同期同区域有一串针对同类失败模式的精度修复：
  - `7222501b 修复default stream创建empty tensor但是接收流读的问题`（default 流建张量、接收流读——正是流读先于写的经典竞态）
  - `6fbd8606 临时修复qwen s1w1多模态精度`
  - `a49dd3f4 …input_batch顺序发散导致多模态decode精度错误`
  - `b8d002c6 …Cloud早期recv未指定src=0导致PP通信错配`

  注意 `7222501b` 和 `6fbd8606` 虽也标 2026-07-31，但**不是 9772 的祖先**（在并行分支上单独合入）——说明「流竞态修复」与「wait=False/流拆分重构」是**同一天并行推进的两条线**。

### 小结

**9772 与 c19ac 毫无疑问相关**：连续提交、同一作者、互补地修同一个边云 P2P 死锁（句柄 wait 半 + 流拆分半），共同对齐 MindIE 设计。它们本身不是精度修复，但 **c19ac 的 `wait=False` 移除了一项同步保证，其失效正是这对改动最可能引发边云精度问题的机理**（在途发送缓冲被复用覆写），9772 的流拆分会放大该窗口。若你在定位这个精度问题，建议重点核查：每个 isend 张量的 storage 是否真的经 `recordStream` 在 hccl 流上保活到发送排空——尤其是复用缓冲的 view/slice；并确认受测分支上是否已包含同期的 `7222501b` 流竞态修复。


---

## User <sup>2026/8/6 11:13:57</sup>

同步 C:\theroadtofree_github\vllm-ascend\仓的9772b349c9afe062aba6b1b180b9c395d52c9ec3修改到本分支


---

## Assistant <sup>2026/8/6 11:14:30</sup>


---

## Assistant <sup>2026/8/6 11:14:30</sup>

我会将提交 `9772b349` 的更改同步到当前分支。让我先确定“本分支”在哪个仓库中，并检查目标文件的状态。


---

## Assistant <sup>2026/8/6 11:14:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== Is c:/v0.23.0_lwd_acc_test_br a git repo? ===\" && git -C /c/v0.23.0_lwd_acc_test_br rev-parse --show-toplevel 2>&1; echo \"\"; echo \"=== branch/status ===\" && git -C /c/v0.23.0_lwd_acc_test_br status -sb 2>&1 | head -5",
  "description": "Check if primary dir is a git repo"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:14:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== Is c:/vllm_gitcode_new a git repo? ===\" && git -C /c/vllm_gitcode_new rev-parse --show-toplevel 2>&1; echo \"\"; echo \"=== branch/status ===\" && git -C /c/vllm_gitcode_new status -sb 2>&1 | head -5",
  "description": "Check if additional dir is a git repo"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:14:33</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== locate target file parallel_state.py in both dirs ===\" ; ls -la /c/v0.23.0_lwd_acc_test_br/vllm_ascend/distributed/parallel_state.py 2>&1; ls -la /c/vllm_gitcode_new/vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Locate target file in both dirs"
}
```

</details>


---

## User <sup>2026/8/6 11:14:36</sup>

<details>
<summary>Tool Result</summary>

```
=== Is c:/v0.23.0_lwd_acc_test_br a git repo? ===
fatal: not a git repository (or any of the parent directories): .git

=== branch/status ===
fatal: not a git repository (or any of the parent directories): .git
```

</details>


---

## User <sup>2026/8/6 11:14:41</sup>

<details>
<summary>Tool Result</summary>

```
=== Is c:/vllm_gitcode_new a git repo? ===
fatal: not a git repository (or any of the parent directories): .git

=== branch/status ===
fatal: not a git repository (or any of the parent directories): .git
```

</details>


---

## User <sup>2026/8/6 11:14:42</sup>

<details>
<summary>Tool Result</summary>

```
Exit code 2
=== locate target file parallel_state.py in both dirs ===
ls: cannot access '/c/v0.23.0_lwd_acc_test_br/vllm_ascend/distributed/parallel_state.py': No such file or directory
ls: cannot access '/c/vllm_gitcode_new/vllm_ascend/distributed/parallel_state.py': No such file or directory
```

</details>


---

## Assistant <sup>2026/8/6 11:14:48</sup>


---

## Assistant <sup>2026/8/6 11:14:48</sup>

这两个工作目录都不是 git 仓库，且目标文件并不在其中。让我探索一下目录结构，以找到实际的仓库。


---

## Assistant <sup>2026/8/6 11:14:49</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== c:/v0.23.0_lwd_acc_test_br contents ===\" && ls -la /c/v0.23.0_lwd_acc_test_br 2>&1 | head -40",
  "description": "List primary dir contents"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:14:49</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== c:/vllm_gitcode_new contents ===\" && ls -la /c/vllm_gitcode_new 2>&1 | head -40",
  "description": "List additional dir contents"
}
```

</details>


---

## User <sup>2026/8/6 11:14:51</sup>

<details>
<summary>Tool Result</summary>

```
=== c:/v0.23.0_lwd_acc_test_br contents ===
total 60
drwxr-xr-x 1 root 197121 0 Aug  6 11:14 .
drwxr-xr-x 1 root 197121 0 Aug  6 10:17 ..
drwxr-xr-x 1 root 197121 0 Aug  6 11:14 .claude
drwxr-xr-x 1 root 197121 0 Aug  6 10:18 vllm
drwxr-xr-x 1 root 197121 0 Aug  6 10:31 vllm-ascend
```

</details>


---

## User <sup>2026/8/6 11:14:52</sup>

<details>
<summary>Tool Result</summary>

```
=== c:/vllm_gitcode_new contents ===
total 68
drwxr-xr-x 1 root 197121 0 May 22 16:15 .
drwxr-xr-x 1 root 197121 0 Aug  6 10:17 ..
drwxr-xr-x 1 root 197121 0 Jun  4 17:25 .claude
drwxr-xr-x 1 root 197121 0 Jun  4 17:38 .claude-code-history
drwxr-xr-x 1 root 197121 0 May 21 21:53 vllm
drwxr-xr-x 1 root 197121 0 May 21 21:53 vllm-ascend
```

</details>


---

## Assistant <sup>2026/8/6 11:15:00</sup>


---

## Assistant <sup>2026/8/6 11:15:01</sup>

两个目录中都有嵌套的 `vllm-ascend/`。实际仓库位于 `c:\v0.23.0_lwd_acc_test_br\vllm-ascend`。我来检查一下它的 git 状态并定位目标文件。


---

## Assistant <sup>2026/8/6 11:15:03</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== git toplevel ===\" && git -C /c/v0.23.0_lwd_acc_test_br/vllm-ascend rev-parse --show-toplevel 2>&1; echo \"\"; echo \"=== branch/status ===\" && git -C /c/v0.23.0_lwd_acc_test_br/vllm-ascend status -sb 2>&1 | head -10; echo \"\"; echo \"=== HEAD ===\" && git -C /c/v0.23.0_lwd_acc_test_br/vllm-ascend log --oneline -1 2>&1",
  "description": "Check git status of nested vllm-ascend repo"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:15:04</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== target file in primary repo ===\" && ls -la /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Locate target file in primary repo"
}
```

</details>


---

## User <sup>2026/8/6 11:18:45</sup>

<details>
<summary>Tool Result</summary>

```
=== git toplevel ===
C:/v0.23.0_lwd_acc_test_br/vllm-ascend

=== branch/status ===
## v0.23.0_lwd_acc_test_br_wtt...origin/v0.23.0_lwd_acc_test_br_wtt

=== HEAD ===
9abf9e8f feat:增加日志
```

</details>


---

## User <sup>2026/8/6 11:18:47</sup>

<details>
<summary>Tool Result</summary>

```
=== target file in primary repo ===
-rw-r--r-- 1 root 197121 83353 Aug  6 10:31 /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py
```

</details>


---

## Assistant <sup>2026/8/6 11:19:11</sup>


---

## Assistant <sup>2026/8/6 11:19:13</sup>

"本分支"即位于 `C:/v0.23.0_lwd_acc_test_br/vllm-ascend` 的仓库，分支为 `v0.23.0_lwd_acc_test_br_wtt` (HEAD `9abf9e8f`)。提交 9772 存在于*另一个*仓库 (`theroadtofree_github\vllm-ascend`) 中。现在我来检查一下目标文件的当前状态，看看是否已经应用了 9772，以及是否存在该补丁所需的先决条件上下文。


---

## Assistant <sup>2026/8/6 11:19:15</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== Does 9772 already exist in target repo history? ===\" && git cat-file -t 9772b349c9afe062aba6b1b180b9c395d52c9ec3 2>&1; echo \"\"; echo \"=== markers in current parallel_state.py ===\" && grep -nE \"_hidden_channel_streams: dict|_get_hidden_channel_stream|_HC_STREAM_SEND|_HC_STREAM_RECV|direction: str|def _hidden_channel_stream_ctx\" vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Check if 9772 present and current markers"
}
```

</details>


---

## User <sup>2026/8/6 11:19:29</sup>

<details>
<summary>Tool Result</summary>

```
=== Does 9772 already exist in target repo history? ===
fatal: git cat-file: could not get object info

=== markers in current parallel_state.py ===
56:_hidden_channel_streams: dict[Any, Any] = {}
60:def _get_hidden_channel_stream(channel: Any) -> Any:
79:def _hidden_channel_stream_ctx(
94:    stream = _get_hidden_channel_stream(channel)
394:    direction: str | None = None,
```

</details>


---

## Assistant <sup>2026/8/6 11:19:59</sup>


---

## Assistant <sup>2026/8/6 11:20:00</sup>

目标仓库是一个独立的 git 仓库，其 `parallel_state.py` 文件目前处于 **pre-9772 状态**（即带有 `_get_hidden_channel_stream(channel)` 且没有 `direction` 参数的版本）。这正是 9772 版本所预期的前提条件。我来从源仓库生成补丁，并在应用前进行试运行（dry-run check）。


---

## Assistant <sup>2026/8/6 11:20:02</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git format-patch -1 --stdout 9772b349c9afe062aba6b1b180b9c395d52c9ec3 > /tmp/9772_sync.patch 2>&1 && echo \"patch written, lines:\" && wc -l /tmp/9772_sync.patch && echo \"\" && echo \"=== dry-run check in TARGET repo ===\" && git apply --check -v /tmp/9772_sync.patch 2>&1 && echo \"RESULT: applies cleanly\"",
  "description": "Generate patch and dry-run check in target"
}
```

</details>


---

## User <sup>2026/8/6 11:20:06</sup>

<details>
<summary>Tool Result</summary>

```
Exit code 1
patch written, lines:
181 /tmp/9772_sync.patch

=== dry-run check in TARGET repo ===
Checking patch vllm_ascend/distributed/parallel_state.py...
error: while searching for:
_FLASHCOMM2_ODP: GroupCoordinator | None = None

# ------------------------------------------------------------------ #
# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #
# ------------------------------------------------------------------ #
# Each hidden channel (PREFILL_1, PREFILL_2) gets its own NPU stream
# so that isend/irecv on different channels don't serialize on the

error: patch failed: vllm_ascend/distributed/parallel_state.py:38
error: vllm_ascend/distributed/parallel_state.py: patch does not apply
```

</details>


---

## Assistant <sup>2026/8/6 11:20:17</sup>


---

## Assistant <sup>2026/8/6 11:20:18</sup>

补丁应用失败——目标文件在 38 行附近的上下文与源文件预期的 9772 之前的状态不同。我来对比一下目标文件与源仓库在该区域的父状态。


---

## Assistant <sup>2026/8/6 11:20:19</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "offset": 30,
  "limit": 110
}
```

</details>


---

## User <sup>2026/8/6 11:20:19</sup>

<details>
<summary>Tool Result</summary>

```
30	# Module specific tensor parallel groups
31	_MLP_TP: GroupCoordinator | None = None
32	_OTP: GroupCoordinator | None = None
33	_LMTP: GroupCoordinator | None = None
34	_EMBED_TP: GroupCoordinator | None = None
35	
36	# flashcomm specific groups
37	_FLASHCOMM2_OTP: GroupCoordinator | None = None
38	_FLASHCOMM2_ODP: GroupCoordinator | None = None
39	
40	# ------------------------------------------------------------------ #
41	# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #
42	# ------------------------------------------------------------------ #
43	# Each hidden channel (PREFILL_1, PREFILL_2) gets its own NPU stream
44	# so that isend/irecv on different channels don't serialize on the
45	# default stream.  Without this, a guard-thread early-posted irecv on
46	# prefill_2 can block a busy_loop isend on prefill_1 (both on the
47	# default stream, FIFO), creating a circular deadlock at 2P request
48	# boundaries:
49	#   cloud  stream: [irecv hidden_P2 (prefill_2)]
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:20:20</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && echo \"=== source repo: parent-of-9772 (c19ac) version, lines 30-100 ===\" && git show c19ac5b1e137765dce2181e51f2f8df575636cbc:vllm_ascend/distributed/parallel_state.py 2>&1 | sed -n '30,100p'",
  "description": "Show source parent version lines 30-100"
}
```

</details>


---

## User <sup>2026/8/6 11:20:26</sup>

<details>
<summary>Tool Result</summary>

```
=== source repo: parent-of-9772 (c19ac) version, lines 30-100 ===
# Module specific tensor parallel groups
_MLP_TP: GroupCoordinator | None = None
_OTP: GroupCoordinator | None = None
_LMTP: GroupCoordinator | None = None
_EMBED_TP: GroupCoordinator | None = None

# flashcomm specific groups
_FLASHCOMM2_OTP: GroupCoordinator | None = None
_FLASHCOMM2_ODP: GroupCoordinator | None = None

# ------------------------------------------------------------------ #
# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #
# ------------------------------------------------------------------ #
# Each hidden channel (PREFILL_1, PREFILL_2) gets its own NPU stream
# so that isend/irecv on different channels don't serialize on the
# default stream.  Without this, a guard-thread early-posted irecv on
# prefill_2 can block a busy_loop isend on prefill_1 (both on the
# default stream, FIFO), creating a circular deadlock at 2P request
# boundaries:
#   cloud  stream: [irecv hidden_P2 (prefi
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:21:13</sup>


---

## Assistant <sup>2026/8/6 11:21:15</sup>

目标文件在此部分与源仓库的 9772 之前的状态在字节层面是一致的，因此补丁失败很可能是由于 Windows 下的换行符（CRLF/LF）不匹配导致的。让我确认一下，并尝试对空格不敏感的变体。


---

## Assistant <sup>2026/8/6 11:21:17</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== target file line endings (CRLF?) ===\" && file vllm_ascend/distributed/parallel_state.py 2>&1; echo \"--- CRLF count ---\"; grep -c $'\\r' vllm_ascend/distributed/parallel_state.py 2>&1; echo \"\"; echo \"=== patch line endings ===\" && file /tmp/9772_sync.patch 2>&1; echo \"--- patch CRLF count ---\"; grep -c $'\\r' /tmp/9772_sync.patch 2>&1",
  "description": "Check line endings of file and patch"
}
```

</details>


---

## User <sup>2026/8/6 11:22:47</sup>

<details>
<summary>Tool Result</summary>

```
=== target file line endings (CRLF?) ===
vllm_ascend/distributed/parallel_state.py: Python script, Unicode text, UTF-8 text executable
--- CRLF count ---
0

=== patch line endings ===
/tmp/9772_sync.patch: Mailbox text, 1st line "From 9772b349c9afe062aba6b1b180b9c395d52c9ec3 Mon Sep 17 00:00:00 2001"
--- patch CRLF count ---
0
```

</details>


---

## Assistant <sup>2026/8/6 11:23:05</sup>


---

## Assistant <sup>2026/8/6 11:23:07</sup>

两者都是 LF。内容在视觉上是相同的，但 `git apply` 仍然拒绝它——这指向了不可见的尾随空格填充。让我对源代码的父版本和目标文件进行完整的 diff，并使用 `cat -A` 检查原始字节。


---

## Assistant <sup>2026/8/6 11:23:09</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/theroadtofree_github/vllm-ascend && git show c19ac5b1e137765dce2181e51f2f8df575636cbc:vllm_ascend/distributed/parallel_state.py > /tmp/c19ac_parallel.py 2>&1 && echo \"=== FULL DIFF c19ac(parent) vs target file (empty = identical) ===\" && diff /tmp/c19ac_parallel.py /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 | head -60; echo \"=== exit: $? ===\"",
  "description": "Full diff of parent version vs target file"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:23:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== target file context lines raw (cat -A) lines 40-44 ===\" && sed -n '40,44p' /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py | cat -A; echo \"\"; echo \"=== patch context raw (first hunk header+context) ===\" && grep -n \"Per-channel dedicated streams\" /tmp/9772_sync.patch | cat -A; sed -n '/^@@ -38/,/^@@/p' /tmp/9772_sync.patch | head -12 | cat -A",
  "description": "Inspect raw bytes of context lines"
}
```

</details>


---

## User <sup>2026/8/6 11:23:12</sup>

<details>
<summary>Tool Result</summary>

```
=== FULL DIFF c19ac(parent) vs target file (empty = identical) ===
6a7
> import vllm_ascend.envs as envs
23d23
< import vllm_ascend.envs as envs
155,233c155,161
< 
< 
< @dataclass(frozen=True)
< class ScheduledDraftTensorMeta:
<     """Locally-derived schema for one scheduled draft transfer.
< 
<     Unlike ``EdgeCloudTensorMeta``, this schema is built per draft step because
<     Eagle3's edge-to-cloud payload changes after step 0. Both peers receive the
<     same ``SchedulerOutput``, so they can construct this object independently
<     and transfer only tensor bodies over the device process group.
<     """
< 
<     metadata_list: tuple[tuple[str, Any], ...]
<     send_tensor_keys: tuple[str, ...]
< 
< 
< def build_scheduled_draft_tensor_meta(
<     *,
<     method: str,
<     direction: str,
<     draft_step_idx: int,
<     num_tokens: int,
<     hidden_size: int,
<     dtype: torch.dtype,
<     device: str = "npu",
< ) -> ScheduledDraftTensorMeta | None:
<     """Build a metadata
...(truncated)
```

</details>


---

## User <sup>2026/8/6 11:23:17</sup>

<details>
<summary>Tool Result</summary>

```
=== target file context lines raw (cat -A) lines 40-44 ===
# ------------------------------------------------------------------ #$
# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #$
# ------------------------------------------------------------------ #$
# Each hidden channel (PREFILL_1, PREFILL_2) gets its own NPU stream$
# so that isend/irecv on different channels don't serialize on the$

=== patch context raw (first hunk header+context) ===
24:-# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #$
@@ -38,7 +38,7 @@ _FLASHCOMM2_OTP: GroupCoordinator | None = None$
 _FLASHCOMM2_ODP: GroupCoordinator | None = None$
 $
 # ------------------------------------------------------------------ #$
-# Per-channel dedicated streams for edge-cloud P2P (isend/irecv).     #$
+# Per-(channel, direction) dedicated streams for edge-cloud P2P.      #$
 # ------------------------------------------------------------------ #$
 # Each hidden channel (PREFILL_1, PREFI
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:25:06</sup>


---

## Assistant <sup>2026/8/6 11:25:08</sup>

现在的情况更清晰了：目标分支与源仓库的 c19ac 已经产生了差异——导入顺序发生了变化，且目标分支缺少 `ScheduledDraftTensorMeta`/`build_scheduled_draft_tensor_meta` 代码块（c19ac 的第 155-233 行）。因此，9772 补丁中的部分代码块将无法应用。第一个代码块在字节上是完全一致的，但 `git apply` 仍然拒绝了它——让我找出原因（空白字符），并绘制出目标文件中实际存在的调用点。


---

## Assistant <sup>2026/8/6 11:25:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== try --ignore-whitespace check ===\" && git apply --check --ignore-whitespace /tmp/9772_sync.patch 2>&1 | head -20; echo \"exit: $?\"; echo \"\"; echo \"=== blank line 39 raw ===\" && sed -n '39p' vllm_ascend/distributed/parallel_state.py | cat -A",
  "description": "Try ignore-whitespace and check blank line"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:25:12</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== all _hidden_channel_stream_ctx( call sites + defs ===\" && grep -nE \"_hidden_channel_stream_ctx\\(|_get_hidden_channel_stream\\(|def edge_cloud_isend_tensor_dict|def edge_cloud_irecv_tensor_dict|def edge_cloud_send_tensor_dict_scheduled_draft|def edge_cloud_broadcast_recv_scheduled_draft|ScheduledDraftTensorMeta\" vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Map call sites and scheduled_draft presence in target"
}
```

</details>


---

## User <sup>2026/8/6 11:25:14</sup>

<details>
<summary>Tool Result</summary>

```
=== try --ignore-whitespace check ===
error: patch failed: vllm_ascend/distributed/parallel_state.py:1357
error: vllm_ascend/distributed/parallel_state.py: patch does not apply
exit: 0

=== blank line 39 raw ===
$
```

</details>


---

## User <sup>2026/8/6 11:25:14</sup>

<details>
<summary>Tool Result</summary>

```
=== all _hidden_channel_stream_ctx( call sites + defs ===
60:def _get_hidden_channel_stream(channel: Any) -> Any:
79:def _hidden_channel_stream_ctx(
94:    stream = _get_hidden_channel_stream(channel)
969:def edge_cloud_isend_tensor_dict(
1115:        with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1148:        with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1237:def edge_cloud_irecv_tensor_dict(
1300:        with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1357:            with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1389:def edge_cloud_isend_tensor_dict_on_hidden_channel(
1406:def edge_cloud_irecv_tensor_dict_on_hidden_channel(
1441:def edge_cloud_send_tensor_dict_scheduled_draft(
1815:def edge_cloud_broadcast_recv_scheduled_draft(
```

</details>


---

## Assistant <sup>2026/8/6 11:27:25</sup>


---

## Assistant <sup>2026/8/6 11:27:30</sup>

现在我已经了解了整体情况。关键发现如下：

1. **Hunks 1–4 可以通过 `--ignore-whitespace` 顺利应用**（核心的 stream-split 重写 + 2 个 isend 站点）。在 hunk 1 处的普通失败仅仅是因为空格问题。
2. **Hunks 5–6 (irecv 站点) 失败**，因为目标分支的分支已将 `wait_for_default=False` 改为了 `True` —— 这是实质性的差异，而非空格问题。9772 并未改动 `wait_for_default`，它只是添加了 `direction` 参数，所以我将保留 `True` 并手动添加 `_HC_STREAM_RECV`。
3. **目标分支中存在 scheduled_draft 函数**，但 grep 显示它们并未直接调用 `_hidden_channel_stream_ctx` —— 需要验证 hunk 7–8 是否适用。

我先使用 `--reject --ignore-whitespace` 来应用兼容的部分，然后再手动处理被拒绝的 hunks。


---

## Assistant <sup>2026/8/6 11:27:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "git apply --reject --ignore-whitespace /tmp/9772_sync.patch 2>&1; echo \"=== exit: $? ===\"; echo \"\"; echo \"=== .rej files created ===\"; ls -la vllm_ascend/distributed/*.rej 2>&1; echo \"\"; echo \"=== post-apply: call sites now ===\"; grep -nE \"_hidden_channel_stream_ctx\\(|_HC_STREAM_SEND|_HC_STREAM_RECV|_get_hidden_channel_stream\\(|_hidden_channel_streams: dict\" vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Apply with reject and inspect results"
}
```

</details>


---

## User <sup>2026/8/6 11:27:43</sup>

<details>
<summary>Tool Result</summary>

```
Checking patch vllm_ascend/distributed/parallel_state.py...
Hunk #4 succeeded at 1147 (offset -81 lines).
Hunk #5 succeeded at 1180 (offset -77 lines).
error: while searching for:
        # the leading num_tokens rows (mirrors the non-merge SP path).  When
        # SP is off this view is the whole buffer, a no-op.
        recv_view = merged[:num_tokens]
        with _hidden_channel_stream_ctx(channel, wait_for_default=False):
            handle = torch.distributed.irecv(
                recv_view, src=pp_group.ranks[src], group=group
            )

error: patch failed: vllm_ascend/distributed/parallel_state.py:1357
error: while searching for:

            if key in send_keys:
                recv_view = full_tensor[:num_tokens]
                with _hidden_channel_stream_ctx(channel, wait_for_default=False):
                    handle = torch.distributed.irecv(
                        recv_view, src=pp_group.ranks[src], group=group
                    )

error: patch failed: vllm_asce
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:28:20</sup>


---

## Assistant <sup>2026/8/6 11:28:22</sup>

进展顺利——核心更改（字典类型、`_HC_STREAM_SEND/RECV` 常量、重写的 `_get_hidden_channel_stream`/`_hidden_channel_stream_ctx`）以及 2 个 isend 站点均已顺利应用。4 处拒绝的情况如下：2 个 irecv 站点（目标已将 `wait_for_default` 修改为 `True`）以及 2 个 scheduled_draft 站点。我来读取拒绝的 hunks，并验证目标分支中 scheduled_draft 函数的实际内容。


---

## Assistant <sup>2026/8/6 11:28:23</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py.rej"
}
```

</details>


---

## User <sup>2026/8/6 11:28:23</sup>

<details>
<summary>Tool Result</summary>

```
1	diff a/vllm_ascend/distributed/parallel_state.py b/vllm_ascend/distributed/parallel_state.py	(rejected hunks)
2	@@ -1357,7 +1392,7 @@ def edge_cloud_irecv_tensor_dict(
3	         # the leading num_tokens rows (mirrors the non-merge SP path).  When
4	         # SP is off this view is the whole buffer, a no-op.
5	         recv_view = merged[:num_tokens]
6	-        with _hidden_channel_stream_ctx(channel, wait_for_default=False):
7	+        with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=False):
8	             handle = torch.distributed.irecv(
9	                 recv_view, src=pp_group.ranks[src], group=group
10	             )
11	@@ -1413,7 +1448,7 @@ def edge_cloud_irecv_tensor_dict(
12	 
13	             if key in send_keys:
14	                 recv_view = full_tensor[:num_tokens]
15	-                with _hidden_channel_stream_ctx(channel, wait_for_default=False):
16	+                with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:28:24</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== scheduled_draft function defs + any _hidden_channel_stream usage in them ===\" && grep -nE \"def edge_cloud_send_tensor_dict_scheduled_draft|def edge_cloud_broadcast_recv_scheduled_draft|_hidden_channel_stream\" vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Find scheduled_draft fns and stream usage"
}
```

</details>


---

## User <sup>2026/8/6 11:28:25</sup>

<details>
<summary>Tool Result</summary>

```
=== scheduled_draft function defs + any _hidden_channel_stream usage in them ===
67:_hidden_channel_streams: dict[tuple[Any, str], Any] = {}
68:_hidden_channel_stream_lock = threading.Lock()
70:# Direction tags for _get_hidden_channel_stream. Send = isend path
76:def _get_hidden_channel_stream(channel: Any, direction: str) -> Any:
86:            f"_get_hidden_channel_stream: direction must be "
91:    stream = _hidden_channel_streams.get(key)
94:    with _hidden_channel_stream_lock:
95:        stream = _hidden_channel_streams.get(key)
98:            _hidden_channel_streams[key] = stream
107:def _hidden_channel_stream_ctx(
129:    stream = _get_hidden_channel_stream(channel, direction)
1150:        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):
1183:        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):
1335:        with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1392:            with _hidden_channel_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:29:01</sup>


---

## Assistant <sup>2026/8/6 11:29:04</sup>

现在情况明确了：

- **拒绝了 2 个 irecv hunks**（第 1335、1392 行）：需要添加 `_HC_STREAM_RECV`，但保留目标分支现有的 `wait_for_default=True`（9772 从未更改此值——它仅添加了 `direction` 参数）。
- **拒绝了 2 个 scheduled_draft hunks**：目标分支的 `edge_cloud_send_tensor_dict_scheduled_draft` (1476) 和 `edge_cloud_broadcast_recv_scheduled_draft` (1850) **完全没有使用 `_hidden_channel_stream_ctx`** —— grep 显示 1392 之后没有出现该函数。该分支已将它们重构为不同的通信路径，因此 9772 对这些函数的更改不适用（无需操作）。

我来读取具体的 irecv 站点上下文以进行精确编辑，并确认 scheduled_draft 函数的通信机制。


---

## Assistant <sup>2026/8/6 11:29:05</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 12,
  "offset": 1330
}
```

</details>


---

## User <sup>2026/8/6 11:29:05</sup>

<details>
<summary>Tool Result</summary>

```
1330	        # When SP is on, `merged` is padded up to a TP multiple; the sender
1331	        # only transmits the actual num_tokens rows, so irecv into a view of
1332	        # the leading num_tokens rows (mirrors the non-merge SP path).  When
1333	        # SP is off this view is the whole buffer, a no-op.
1334	        recv_view = merged[:num_tokens]
1335	        with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1336	            handle = torch.distributed.irecv(
1337	                recv_view, src=pp_group.ranks[src], group=group
1338	            )
1339	            if recv_view.device.type == "npu":
1340	                recv_view.record_stream(torch.npu.current_stream(recv_view.device))
1341	        handles.append(handle)
```

</details>


---

## Assistant <sup>2026/8/6 11:29:05</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 12,
  "offset": 1387
}
```

</details>


---

## User <sup>2026/8/6 11:29:05</sup>

<details>
<summary>Tool Result</summary>

```
1387	            tensor_dict[key] = full_tensor
1388	            continue
1389	
1390	        if key in send_keys:
1391	            recv_view = full_tensor[:num_tokens]
1392	            with _hidden_channel_stream_ctx(channel, wait_for_default=True):
1393	                handle = torch.distributed.irecv(
1394	                    recv_view, src=pp_group.ranks[src], group=group
1395	                )
1396	                if recv_view.device.type == "npu":
1397	                    recv_view.record_stream(
1398	                        torch.npu.current_stream(recv_view.device))
```

</details>


---

## Assistant <sup>2026/8/6 11:29:06</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 55,
  "offset": 1476
}
```

</details>


---

## User <sup>2026/8/6 11:29:06</sup>

<details>
<summary>Tool Result</summary>

```
1476	def edge_cloud_send_tensor_dict_scheduled_draft(
1477	    tensor_dict: dict[str, torch.Tensor | Any],
1478	    channel: HiddenChannelType = HiddenChannelType.DECODE,
1479	) -> list[Handle]:
1480	    """Send a dynamically-shaped scheduled draft payload."""
1481	    pp_group = get_pp_group()
1482	    if hasattr(pp_group, "isend_tensor_dict_on_hidden_channel"):
1483	        return pp_group.isend_tensor_dict_on_hidden_channel(
1484	            tensor_dict,
1485	            dst=None,
1486	            channel=channel,
1487	        )
1488	    return pp_group.isend_tensor_dict(tensor_dict)
1489	
1490	
1491	def _apply_sp_chunk_inplace(tensor_dict: dict[str, Any]) -> None:
1492	    """Sequence-parallel chunk each tensor in ``tensor_dict`` along dim 0.
1493	
1494	    This runs as the final communication postprocess for both merged and
1495	    non-merged payloads. It must happen after the inter-node receive and
1496	    intra-node TP broadcast complete; ``sequence_parallel_chunk`` may clone 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:29:25</sup>


---

## Assistant <sup>2026/8/6 11:29:28</sup>

现在一切都很清楚了。确认如下：

- **Irecv 位置 (1335, 1392)**：目标特意使用了 `wait_for_default=True`（上游 9772 上下文中为 `False`）。9772 仅添加了 `direction` 参数，所以我保留了 `True` 并添加了 `_HC_STREAM_RECV`。注意：目标还添加了 `recv_view.record_stream(...)` 调用——这与我们之前讨论过的精度安全机制相同。
- **Scheduled_draft 函数 (1476, 1850)**：它们委托给 `pp_group.isend_tensor_dict_on_hidden_channel(...)`，且不包含任何 `_hidden_channel_stream_ctx` 调用——因此 9772 对这些函数的修改不适用 (N/A)。

让我手动应用这两个 irecv 编辑。


---

## Assistant <sup>2026/8/6 11:29:29</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "        recv_view = merged[:num_tokens]\n        with _hidden_channel_stream_ctx(channel, wait_for_default=True):",
  "new_string": "        recv_view = merged[:num_tokens]\n        with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):"
}
```

</details>


---

## Assistant <sup>2026/8/6 11:29:30</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "            recv_view = full_tensor[:num_tokens]\n            with _hidden_channel_stream_ctx(channel, wait_for_default=True):",
  "new_string": "            recv_view = full_tensor[:num_tokens]\n            with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):"
}
```

</details>


---

## User <sup>2026/8/6 11:29:30</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## User <sup>2026/8/6 11:29:31</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 11:29:40</sup>


---

## Assistant <sup>2026/8/6 11:29:41</sup>

两个 irecv 修改已应用。现在让我检查一下是否还有未转换的调用点，运行语法检查，并清理被拒绝的文件。


---

## Assistant <sup>2026/8/6 11:29:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== any _hidden_channel_stream_ctx calls still WITHOUT direction? (should be none) ===\" && grep -nE \"_hidden_channel_stream_ctx\\(channel, wait_for_default=\" vllm_ascend/distributed/parallel_state.py 2>&1; echo \"(empty above = all converted)\"; echo \"\"; echo \"=== all call sites now ===\" && grep -nE \"_hidden_channel_stream_ctx\\(channel, _HC_STREAM\" vllm_ascend/distributed/parallel_state.py 2>&1",
  "description": "Verify all call sites converted"
}
```

</details>


---

## User <sup>2026/8/6 11:29:44</sup>

<details>
<summary>Tool Result</summary>

```
=== any _hidden_channel_stream_ctx calls still WITHOUT direction? (should be none) ===
(empty above = all converted)

=== all call sites now ===
1150:        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):
1183:        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):
1335:        with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
1392:            with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
```

</details>


---

## Assistant <sup>2026/8/6 11:29:44</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== python syntax check ===\" && python -m py_compile vllm_ascend/distributed/parallel_state.py 2>&1 && echo \"OK: compiles cleanly\" || echo \"FAILED\"; echo \"\"; echo \"=== cleanup .rej ===\" && rm -f vllm_ascend/distributed/parallel_state.py.rej && echo \"removed .rej\"",
  "description": "Syntax check and cleanup rej file"
}
```

</details>


---

## User <sup>2026/8/6 11:30:40</sup>

<details>
<summary>Tool Result</summary>

```
=== python syntax check ===
OK: compiles cleanly

=== cleanup .rej ===
removed .rej
```

</details>


---

## Assistant <sup>2026/8/6 11:31:02</sup>


---

## Assistant <sup>2026/8/6 11:31:04</sup>

所有验证均已通过：语法编译正常，所有 4 处调用点均已转换（2×SEND, 2×RECV），无遗漏。让我为你生成一份最终总结差异（diff）供查阅。


---

## Assistant <sup>2026/8/6 11:31:06</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "git diff --stat vllm_ascend/distributed/parallel_state.py 2>&1; echo \"\"; echo \"=== core region (60-135) post-sync ===\"; sed -n '60,135p' vllm_ascend/distributed/parallel_state.py",
  "description": "Show diff stat and core region"
}
```

</details>


---

## User <sup>2026/8/6 11:31:07</sup>

<details>
<summary>Tool Result</summary>

```
vllm_ascend/distributed/parallel_state.py | 73 +++++++++++++++++++++++--------
 1 file changed, 54 insertions(+), 19 deletions(-)

=== core region (60-135) post-sync ===
# pair, atb_llm/.../edge_cloud_data_comm.py).
#
# TP-broadcast (intra-node collective) stays on the default stream --
# it runs inside execute_model's wait_for_comm() on all TP ranks
# synchronized; only the cross-node P2P (isend/irecv) uses the
# per-(channel, direction) stream, and (when wait=True) handle.wait()
# syncs back to the default stream before the broadcast.
_hidden_channel_streams: dict[tuple[Any, str], Any] = {}
_hidden_channel_stream_lock = threading.Lock()

# Direction tags for _get_hidden_channel_stream. Send = isend path
# (cloud->edge P尾 / edge->cloud P首); Recv = irecv path (the reverse).
_HC_STREAM_SEND = "send"
_HC_STREAM_RECV = "recv"


def _get_hidden_channel_stream(channel: Any, direction: str) -> Any:
    """Return the dedicated NPU stream for (channel, direction), creating
    it lazily. Thre
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 11:32:03</sup>


---

## Assistant <sup>2026/8/6 11:32:05</sup>

同步完成并经过验证。核心区域与 9772 的意图完全一致。在结束之前，让我检查一件重要的事情——9772 在源仓库中建立在 c19ac (worker.py `wait=False`) 的基础之上，因此让我确认一下目标分支是否具备该配套更改，否则 9772 的流拆分（stream-split）将是一个不完整的修复。


---

## Assistant <sup>2026/8/6 11:32:07</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== does target worker.py have c19ac's wait param in _wait_pp_send_work? ===\" && grep -nE \"def _wait_pp_send_work|wait: bool|wait=False|_HC_STREAM|handle\\.wait\\(\\)\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/worker.py 2>&1 | head -20",
  "description": "Check if target has c19ac wait param"
}
```

</details>


---

## User <sup>2026/8/6 11:32:08</sup>

<details>
<summary>Tool Result</summary>

```
=== does target worker.py have c19ac's wait param in _wait_pp_send_work? ===
787:    def _wait_pp_send_work(self, channel: HiddenChannelType | None = None) -> None:
790:                handle.wait()
794:                    handle.wait()
800:            handle.wait()
1360:            handle.wait()
```

</details>


---

## Assistant <sup>2026/8/6 11:32:33</sup>


---

## Assistant <sup>2026/8/6 11:32:53</sup>

同步完成。下面是完整结论。

## 同步结果

已将源仓 (`theroadtofree_github\vllm-ascend`) 的提交 `9772b349`(**拆分边缘云P2P的发送和接收流**) 同步到本分支 `v0.23.0_lwd_acc_test_br_wtt`，目标文件 [parallel_state.py](vllm-ascend/vllm_ascend/distributed/parallel_state.py)，`+54/-19`，**未提交**（留在工作区）。

由于两仓已分叉，`git apply` 不能整块套用，采用「自动 + 手工」方式：
- `git apply --reject --ignore-whitespace` 自动落地了核心改动 + isend 调用点；
- 2 处 irecv 调用点因本分支语义已变，手工补齐。

### 已应用的 9772 改动
| 改动 | 位置 | 状态 |
|---|---|---|
| 流字典按 `(channel, direction)` 键化 + `_HC_STREAM_SEND/RECV` 常量 | `_hidden_channel_streams` / 常量 | ✅ |
| `_get_hidden_channel_stream(channel, direction)`（含 direction 校验） | 函数重写 | ✅ |
| `_hidden_channel_stream_ctx(channel, direction, *, wait_for_default)` | 签名+函数体 | ✅ |
| isend 调用点 ×2 → `_HC_STREAM_SEND` | L1150, L1183 | ✅ |
| irecv 调用点 ×2 → `_HC_STREAM_RECV` | L1335, L1392 | ✅ 手工 |

校验：`python -m py_compile` 通过；无遗漏的未带 direction 调用点；`.rej` 已清理。

### 处理/保留的本分支差异（重要）
1. **irecv 的 `wait_for_default`**：本分支为 `True`，上游 9772 上下文为 `False`。9772 本身不改这个参数，**已保留本分支的 `True`**。
2. **`recv_view.record_stream(...)`**：本分支在 irecv 后加了 record_stream（精度保活），未触碰。
3. **scheduled_draft 函数（L1476/L1850）**：上游 9772 还改了 `edge_cloud_send_tensor_dict_scheduled_draft` / `edge_cloud_broadcast_recv_scheduled_draft` 里的 `_hidden_channel_stream_ctx` 调用；但**本分支这两个函数已重构为委托 `pp_group.isend_tensor_dict_on_hidden_channel(...)`，不再直接调用 `_hidden_channel_stream_ctx`**，故这两处 hunk **不适用（N/A），未改**。

### ⚠️ 需要你注意的两个点

**1. 缺少配套的 c19ac（`wait=False`）——9772 是「半套」修复。**
我核查了本分支 worker.py：`_wait_pp_send_work(self, channel=None)` **没有** c19ac 的 `wait` 参数，仍在调用 `handle.wait()`（L790/794/800/1360）。如前一轮分析，9772（流拆分）与 c19ac（不 wait）是同一死锁修复的互补两半：
- 仅 9772：send/recv 不再在同通道串行，但 `handle.wait()` 仍会把 isend 完成钉回计算流 → 计算流仍会等对端 irecv → **2P1D / DP 调度失配下死锁可能仍未解除**。
- 要完整复刻源仓的修复效果，**还需要同步 c19ac5b1**（worker.py 的 `wait=False`）。

**2. scheduled_draft 路径未受 9772 覆盖。**
本分支该路径走 `pp_group.isend_tensor_dict_on_hidden_channel`，流管理在 pp_group 实现里（不在 parallel_state.py）。若 9772 的流拆分语义对该路径同样需要，需另行检查 pp_group 侧实现——这超出「同步 9772 的 parallel_state.py 改动」范围。

---

需要我继续：① 把 c19ac5b1（worker.py `wait=False`）也同步过来凑齐整套死锁修复？② 将当前改动提交到本分支？


---

## User <sup>2026/8/6 12:20:36</sup>

同步后边云场景gsm8k测试还是存在精度问题（200个请求，得分70），C:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py的141行到147放开后，精度可以达标（得分98），帮分析一下原因


---

## Assistant <sup>2026/8/6 12:20:51</sup>


---

## Assistant <sup>2026/8/6 12:20:51</sup>

我将分析为什么在 `gpu_worker.py` 中放开第 141-147 行可以修复边云场景的精度问题。让我来读取该文件及其上下文。


---

## Assistant <sup>2026/8/6 12:20:51</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 90,
  "offset": 100
}
```

</details>


---

## User <sup>2026/8/6 12:20:52</sup>

<details>
<summary>Tool Result</summary>

```
100	class AsyncIntermediateTensors(IntermediateTensors):
101	    """IntermediateTensors with lazy comm synchronization"""
102	
103	    def __init__(
104	        self,
105	        tensors: dict[str, torch.Tensor],
106	        comm_handles: list[Handle] | None = None,
107	        comm_postprocess: list[Callable[[], None]] | None = None,
108	        batch_type: Any = None,
109	        req_ids: list[str] | None = None,
110	    ) -> None:
111	        super().__init__(tensors)
112	        self._comm_handles = comm_handles
113	        self._comm_postprocess = comm_postprocess
114	        self._comm_waited = False
115	        self._batch_type = batch_type
116	        self._req_ids = req_ids
117	
118	    def wait_for_comm(self) -> None:
119	        if self._comm_waited:
120	            return
121	        if self._comm_handles:
122	            for handle in self._comm_handles:
123	                handle.wait()
124	        if self._comm_postprocess:
125	            for fn in self._comm_postproces
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:21:41</sup>


---

## Assistant <sup>2026/8/6 12:21:42</sup>

这是一个经典的“取消注释调试打印修复了该 bug”的症状，这指向了流同步缺失所导致的竞态条件。让我来精确追踪一下边缘云的接收路径，以找出同步是在哪里丢失的。


---

## Assistant <sup>2026/8/6 12:21:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== AsyncIntermediateTensors construction + comm_handles/postprocess wiring in parallel_state.py ===\" && grep -nE \"AsyncIntermediateTensors|comm_handles|comm_postprocess|wait_for_comm|\\.wait\\(\\)|record_stream|broadcast_postprocess|def edge_cloud_broadcast_recv\\b|def edge_cloud_irecv_tensor_dict\" vllm_ascend/distributed/parallel_state.py 2>&1 | head -60",
  "description": "Map recv path and AsyncIntermediateTensors wiring"
}
```

</details>


---

## User <sup>2026/8/6 12:21:44</sup>

<details>
<summary>Tool Result</summary>

```
=== AsyncIntermediateTensors construction + comm_handles/postprocess wiring in parallel_state.py ===
63:# it runs inside execute_model's wait_for_comm() on all TP ranks
65:# per-(channel, direction) stream, and (when wait=True) handle.wait()
996:                handle.wait()
1155:                merged.record_stream(torch.cuda.current_stream(merged.device))
1157:                merged.record_stream(torch.npu.current_stream(merged.device))
1188:                value.record_stream(torch.cuda.current_stream(value.device))
1190:                value.record_stream(torch.npu.current_stream(value.device))
1272:def edge_cloud_irecv_tensor_dict(
1327:        # split is appended to comm_postprocess so it runs after the irecv
1328:        # handle is waited on by AsyncIntermediateTensors.wait_for_comm().
1340:                recv_view.record_stream(torch.npu.current_stream(recv_view.device))
1397:                    recv_view.record_stream(
1441:def edge_cloud_irecv_tensor_dict_on_hidden_channel(
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:22:01</sup>


---

## Assistant <sup>2026/8/6 12:22:02</sup>

接收路径返回 `(tensor_dict, comm_handles, comm_postprocess)`。我注意到第 1847/1936 行返回 `[]` 作为 `comm_handles`——因此，在某些路径中，irecv 句柄可能并未包含在 `wait_for_comm` 所等待的句柄中。让我读取实际的接收实现，以追踪流和句柄的连接情况。


---

## Assistant <sup>2026/8/6 12:22:02</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 145,
  "offset": 1272
}
```

</details>


---

## User <sup>2026/8/6 12:22:02</sup>

<details>
<summary>Tool Result</summary>

```
1272	def edge_cloud_irecv_tensor_dict(
1273	    num_tokens: int,
1274	    src: int | None = None,
1275	    use_alt_group: bool = False,
1276	    channel: HiddenChannelType | None = None,
1277	    include_mrope: bool = True,
1278	) -> tuple[dict[str, torch.Tensor | Any], list[Handle], list[Callable[[], None]]]:
1279	    """Receive tensor dict without metadata sync (edge-cloud optimized).
1280	
1281	    Computes metadata locally from num_tokens + the pre-computed
1282	    EdgeCloudTensorMeta, pre-allocates tensors, then issues irecv
1283	    for each. This eliminates the inter-node pickle+Gloo metadata
1284	    exchange that the standard GroupCoordinator.irecv_tensor_dict
1285	    performs.
1286	
1287	    When SP is enabled, the receive buffer is padded up to the nearest
1288	    multiple of the local TP size.  The sender still transmits only the
1289	    actual ``num_tokens`` rows, so we issue ``irecv`` into a view of the
1290	    first ``num_tokens`` rows of the larger buffer.  This ke
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:22:34</sup>


---

## Assistant <sup>2026/8/6 12:22:35</sup>

接收处理流程对 `_HC_STREAM_RECV` 执行 `irecv`，将句柄附加到 `handles` 中，并将拆分作为后处理附加。让我读取一下 `edge_cloud_broadcast_recv` 以及广播后处理逻辑，看看是否有流切换或缺失依赖的情况。


---

## Assistant <sup>2026/8/6 12:22:35</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 135,
  "offset": 1538
}
```

</details>


---

## User <sup>2026/8/6 12:22:35</sup>

<details>
<summary>Tool Result</summary>

```
1538	def edge_cloud_broadcast_recv(
1539	    num_tokens: int,
1540	    channel: HiddenChannelType = HiddenChannelType.PREFILL_1,
1541	    sp_chunk: bool = False,
1542	    src: int | None = None,
1543	    include_mrope: bool = True,
1544	) -> tuple[
1545	    dict[str, torch.Tensor | Any] | None,
1546	    list[Handle],
1547	    list[Callable[[], None]],
1548	]:
1549	    """Receive PP tensors on the selected Phase6 channel and broadcast them
1550	    within the local edge/cloud TP group.
1551	
1552	    Uses locally computed metadata instead of receiving it from the sender.
1553	    This eliminates the inter-node pickle+Gloo metadata exchange, while
1554	    still broadcasting metadata within the local TP group (intra-node)
1555	    so that non-NPU0 TP ranks can allocate tensors.
1556	    Args:
1557	        sp_chunk: Whether to split the fully received tensors across the local
1558	            TP/SP ranks. The split is deferred until after receive and TP
1559	            broadcast completi
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:22:53</sup>


---

## Assistant <sup>2026/8/6 12:22:53</sup>

`edge_cloud_broadcast_recv` 会调用 `edge_cloud_irecv_tensor_dict_on_hidden_channel` (第 1585 行)，而不是直接调用我读取的那个函数。我来读取一下该函数，看看它实际上是如何执行 `irecv` 并返回 `handles` 的。


---

## Assistant <sup>2026/8/6 12:22:54</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 97,
  "offset": 1441
}
```

</details>


---

## User <sup>2026/8/6 12:22:54</sup>

<details>
<summary>Tool Result</summary>

```
1441	def edge_cloud_irecv_tensor_dict_on_hidden_channel(
1442	    channel: HiddenChannelType,
1443	    src: int | None = None,
1444	    num_tokens: int | None = None,
1445	    include_mrope: bool = True,
1446	) -> tuple[dict[str, torch.Tensor | Any], list[Handle], list[Callable[[], None]]]:
1447	    """Receive edge-cloud tensors on a hidden channel without metadata sync."""
1448	    assert num_tokens is not None, (
1449	        "num_tokens must be provided for edge-cloud hidden-channel receive"
1450	    )
1451	    return edge_cloud_irecv_tensor_dict(
1452	        num_tokens=num_tokens,
1453	        src=src,
1454	        channel=channel,
1455	        include_mrope=include_mrope,
1456	    )
1457	
1458	
1459	def edge_cloud_send_tensor_dict(
1460	    tensor_dict: dict[str, torch.Tensor | Any],
1461	    channel: HiddenChannelType,
1462	    num_tokens: int,
1463	    dst: int | None = None,
1464	    include_mrope: bool = True,
1465	) -> list[Handle]:
1466	    """Send edge-cloud hidden tensors
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:24:30</sup>


---

## Assistant <sup>2026/8/6 12:24:31</sup>

我来检查一下同步原语，并将边云（edge-cloud）接收路径与常规 PP 路径进行比较，以确定具体差异在哪里。我还要确认一下 `.item()` 在 NPU 上的同步行为。


---

## Assistant <sup>2026/8/6 12:24:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== synchronize / current_stream usage in recv path (vllm-ascend) ===\" && grep -rnE \"synchronize|current_stream\\(\\)\\.wait|wait_stream|record_event|Event\\(\\)\" vllm_ascend/distributed/parallel_state.py 2>&1 | head -30; echo \"\"; echo \"=== base IntermediateTensors.wait_for_comm in vllm core ===\" && grep -rnE \"def wait_for_comm|class IntermediateTensors|synchronize\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm/distributed/parallel_state.py 2>&1 | head -20",
  "description": "Find sync primitives and base class wait_for_comm"
}
```

</details>


---

## Assistant <sup>2026/8/6 12:24:33</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== how is the recv result consumed? AsyncIntermediateTensors usage in vllm-ascend worker ===\" && grep -rnE \"AsyncIntermediateTensors|wait_for_comm|\\.tensors\" vllm_ascend/worker/worker.py 2>&1 | head -20; echo \"\"; echo \"=== torch_npu item/sync behavior: look for aclrtSynchronize in torch_npu if present ===\" && python -c \"import torch_npu, os; print(os.path.dirname(torch_npu.__file__))\" 2>&1 | head -3",
  "description": "Find AsyncIntermediateTensors consumers and torch_npu path"
}
```

</details>


---

## User <sup>2026/8/6 12:24:34</sup>

<details>
<summary>Tool Result</summary>

```
=== synchronize / current_stream usage in recv path (vllm-ascend) ===
64:# synchronized; only the cross-node P2P (isend/irecv) uses the
131:        stream.wait_stream(torch.npu.current_stream())

=== base IntermediateTensors.wait_for_comm in vllm core ===
```

</details>


---

## User <sup>2026/8/6 12:51:39</sup>

<details>
<summary>Tool Result</summary>

```
=== how is the recv result consumed? AsyncIntermediateTensors usage in vllm-ascend worker ===
68:from vllm.v1.worker.gpu_worker import AsyncIntermediateTensors
231:        # AsyncIntermediateTensors and runs wait_for_comm() (which both
236:        self._early_recv_handles: dict[str, AsyncIntermediateTensors] = {}
814:    ) -> AsyncIntermediateTensors:
830:        entry = AsyncIntermediateTensors(
900:    ) -> AsyncIntermediateTensors | None:
1068:            _gathered = self._all_gather_tensor_dict(output.tensors)
1070:            _gathered = output.tensors
1122:        intermediate_tensors = AsyncIntermediateTensors(
1172:            # done by execute_model's wait_for_comm() on the busy_loop thread.
1205:                # wait_for_comm() runs implicitly on first .tensors access
1206:                # inside execute_model (AsyncIntermediateTensors.__getattr__),
1240:                intermediate_tensors = AsyncIntermediateTensors(
1266:            _gathered = self._all_gather_tensor_dic
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:51:59</sup>


---

## Assistant <sup>2026/8/6 12:52:00</sup>

关键发现：接收路径中**没有 `synchronize()` 或基于事件的同步**——唯一的接收→计算同步机制是 `wait_for_comm` 中的 `handle.wait()`。并且 `wait_for_comm` 是在 `execute_model` 期间“在 busy_loop 线程上”运行的。我来查看一下 worker 的消耗流程，以确定线程/流的上下文。


---

## Assistant <sup>2026/8/6 12:52:00</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 60,
  "offset": 1160
}
```

</details>


---

## User <sup>2026/8/6 12:52:00</sup>

<details>
<summary>Tool Result</summary>

```
1160	        forward_pass = scheduler_output.total_num_scheduled_tokens > 0
1161	        if forward_pass and is_first_slice:
1162	            # [CHER] Atomically reuse the guard thread's early-recv entry, or
1163	            # post the irecv ourselves.  get_or_post_early_recv guarantees at
1164	            # most one irecv per head_token even when the guard thread's hint
1165	            # dequeue races this dequeue.  Applies to PREFILL_FIRST only:
1166	            # DECODE_FIRST must NOT use early-recv because DECODE is a single
1167	            # channel/stream -- a guard-thread irecv post on the DECODE stream
1168	            # races busy_loop's isend on that same stream (cross-thread FIFO
1169	            # ordering is non-deterministic -> deadlock).  PREFILL has two
1170	            # channels (PREFILL_1/2) so irecv and isend land on different
1171	            # streams.  The guard thread ONLY posts (never wait()s); wait is
1172	            # done by execute_model's wait_for_comm(
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:52:15</sup>


---

## Assistant <sup>2026/8/6 12:52:16</sup>

这揭示了 CHER (Cloud Hidden Early-Receive) 架构：一个 **guard thread** 会提前发布 `irecv`，而 `wait_for_comm` 稍后会在 `busy_loop` 线程上运行。关键问题是，early-recv 条目是否将 `irecv` 句柄存储在 `_comm_handles` 中。让我检查一下。


---

## Assistant <sup>2026/8/6 12:52:16</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 45,
  "offset": 808
}
```

</details>


---

## User <sup>2026/8/6 12:52:16</sup>

<details>
<summary>Tool Result</summary>

```
808	    # agnostic: the hidden_channel + num_tokens fully determine the recv, so
809	    # the same
810	    # primitives serve CHER (cloud, edge->cloud) and EHER (edge, cloud->edge).
811	    def _post_early_irecv_locked(
812	        self, ht: str, channel: "HiddenChannelType", num_tokens: int,
813	        include_mrope: bool = True,
814	    ) -> AsyncIntermediateTensors:
815	        """Post an irecv and return the entry.  Caller MUST hold
816	        ``_early_recv_lock``.  Does NOT cache in ``_early_recv_handles`` --
817	        the caller decides whether to cache (guard thread) or consume
818	        immediately (busy_loop).  This prevents the memory leak where
819	        busy_loop's self-posted entries were left in the dict forever.
820	        """
821	        do_sp_chunk = enable_sp() and (
822	            self.model_runner.edge_cloud_cfg.mode != "embedding_only"
823	            or not self.model_runner.supports_mm_inputs)
824	        tensor_dict, comm_handles, comm_postprocess = e
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:52:16</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -nE \"def get_or_post_early_recv|_early_recv_handles|comm_handles|_comm_handles|def _post_early_recv|early_recv\" vllm_ascend/worker/worker.py 2>&1 | head -30",
  "description": "Find early recv handle storage"
}
```

</details>


---

## User <sup>2026/8/6 12:52:17</sup>

<details>
<summary>Tool Result</summary>

```
236:        self._early_recv_handles: dict[str, AsyncIntermediateTensors] = {}
237:        self._early_recv_lock = threading.Lock()
238:        # head_tokens already consumed by busy_loop (get_or_post_early_recv).
241:        self._early_recv_consumed: set[str] = set()
247:        self._cloud_hidden_early_recv_enabled: bool = False
639:            # early-recv cache via get_or_post_early_recv.  Stays False on the
654:            self._cloud_hidden_early_recv_enabled = bool(
668:            if self._cloud_hidden_early_recv_enabled:
678:                self._early_recv_max_inflight = 1
680:                self._early_recv_max_inflight = 0
681:            if self._cloud_hidden_early_recv_enabled:
807:    # get_or_post_early_recv() to consume/reuse it.  These are direction-
816:        ``_early_recv_lock``.  Does NOT cache in ``_early_recv_handles`` --
824:        tensor_dict, comm_handles, comm_postprocess = edge_cloud_broadcast_recv(
832:            comm_handles=comm_handles,
840:       
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:53:06</sup>


---

## Assistant <sup>2026/8/6 12:53:06</sup>

我现在已经掌握了完整的情况。让我最后确认一个细节——即 `.item()` 在 NPU 上是否确实执行了 device-wide 同步（这是该机制的核心）。


---

## Assistant <sup>2026/8/6 12:53:08</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== find torch_npu installs ===\" && find /c -maxdepth 6 -type d -name \"torch_npu\" 2>/dev/null | head -5; echo \"\"; echo \"=== search torch_npu for item/synchronizeDevice semantics ===\" && for d in $(find /c -maxdepth 6 -type d -name \"torch_npu\" 2>/dev/null | head -3); do echo \"--- $d ---\"; grep -rnE \"aclrtSynchronizeDevice|SynchronizeDevice|def item|syncDevice|aclrtSynchronizeStream\" \"$d\" 2>/dev/null | grep -iE \"item|sync\" | head -8; done",
  "description": "Locate torch_npu and item sync semantics"
}
```

</details>


---

## User <sup>2026/8/6 12:53:59</sup>

<details>
<summary>Tool Result</summary>

```
=== find torch_npu installs ===
/c/cann/torch_npu
/c/cann/torch_npu/pytorch/torch_npu
/c/theroadtofree_vllm_ds/pytorch/torch_npu
/c/torch/torch_npu
/c/torch/torch_npu/pytorch/torch_npu

=== search torch_npu for item/synchronizeDevice semantics ===
--- /c/cann/torch_npu ---
/c/cann/torch_npu/pytorch/third_party/acl/libs/acl.cpp:16:aclError aclrtSynchronizeDevice(void){return 0;}
/c/cann/torch_npu/pytorch/third_party/acl/libs/acl.cpp:38:aclError aclrtSynchronizeStream(aclrtStream stream){return 0;}
/c/cann/torch_npu/pytorch/third_party/acl/libs/acl.cpp:39:aclError aclrtSynchronizeStreamWithTimeout(aclrtStream stream, int32_t timeout){return 0;}
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/TensorFactories.cpp:82:        c10_npu::npuSynchronizeDevice();
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/TensorFactories.cpp:92:            c10_npu::npuSynchronizeDevice();
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/TensorFactories.cpp:107:            c10_npu::npuSynchroniz
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:54:05</sup>


---

## Assistant <sup>2026/8/6 12:54:06</sup>

NPU 代码中大量使用了 `npuSynchronizeDevice()`。我来确认一下 `.item()` 具体触发了什么同步——即 NPU 上的 item/local-scalar 路径。


---

## Assistant <sup>2026/8/6 12:54:08</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch; echo \"=== item / local_scalar_dense sync in torch_npu + pytorch ===\" && grep -rnE \"local_scalar_dense|item_from_memory|npuSynchronizeDevice|aclrtSynchronizeStream|SynchronizeDevice\" \"$TN/torch_npu/csrc/aten/ops\" 2>/dev/null | grep -iE \"item|local_scalar|scalar\" | head -15; echo \"\"; echo \"=== pytorch core: Tensor.item -> _local_scalar_dense sync ===\" && grep -rnE \"local_scalar_dense|synchronize|Synchronize\" \"$TN/aten/src/ATen/native/cuda/TensorFactories.cu\" \"$TN/aten/src/ATen/native/ResizeCommon.h\" 2>/dev/null | grep -iE \"item|local_scalar|synchronize\" | head; echo \"\"; echo \"=== search broadly for the local_scalar impl ===\" && grep -rln \"local_scalar_dense\" \"$TN/aten/src/ATen/native\" 2>/dev/null | head; grep -rnE \"synchronize|Synchronize\" \"$TN/aten/src/ATen/native/SharedReduceOps.h\" \"$TN/aten/src/ATen/native/cuda/Copy.cu\" 2>/dev/null | grep -i synchronize | head",
  "description": "Find item/local_scalar sync on NPU"
}
```

</details>


---

## User <sup>2026/8/6 12:54:17</sup>

<details>
<summary>Tool Result</summary>

```
=== item / local_scalar_dense sync in torch_npu + pytorch ===

=== pytorch core: Tensor.item -> _local_scalar_dense sync ===

=== search broadly for the local_scalar impl ===
```

</details>


---

## Assistant <sup>2026/8/6 12:54:21</sup>


---

## Assistant <sup>2026/8/6 12:54:22</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch; echo \"=== _local_scalar_dense definition ===\" && grep -rln \"local_scalar_dense\" \"$TN\" 2>/dev/null | head; echo \"\"; echo \"=== NPU custom item/local_scalar op registration ===\" && grep -rnE \"local_scalar_dense|npu_item|\\\"item\\\"\" \"$TN/torch_npu/csrc\" 2>/dev/null | head -15; echo \"\"; echo \"=== what sync does the cuda local_scalar_dense use (reference) ===\" && f=$(grep -rln \"local_scalar_dense\" \"$TN/aten/src/ATen/native/cuda\" 2>/dev/null | head -1); echo \"file: $f\"; grep -nE \"synchronize|Synchronize|stream|Stream\" \"$f\" 2>/dev/null | head",
  "description": "Find local_scalar_dense and its sync"
}
```

</details>


---

## User <sup>2026/8/6 12:54:26</sup>

<details>
<summary>Tool Result</summary>

```
=== _local_scalar_dense definition ===
/c/cann/torch_npu/pytorch/test/dynamo/test_repros.py
/c/cann/torch_npu/pytorch/test/test_ops.py
/c/cann/torch_npu/pytorch/test/test_torch.py
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/npu_native_functions.yaml
/c/cann/torch_npu/pytorch/torch_npu/_inductor/ascend_npu_ir/ascend_npu_ir/npu/inductor_patch/lowering.py
/c/cann/torch_npu/pytorch/torch_npu/_inductor/utils.py

=== NPU custom item/local_scalar op registration ===
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp:14:c10::Scalar NPUNativeFunctions::_local_scalar_dense(const at::Tensor& self)
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp:17:    TORCH_CHECK(self.numel() > 0, "_local_scalar_dense(): Empty tensor not supported");
/c/cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp:19:        self.scalar_type(), "_local_scalar_dense_npu"
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:54:31</sup>


---

## Assistant <sup>2026/8/6 12:54:31</sup>

找到了 `.item()` 的 NPU 实现 (`LocalScalarDenseNpu.cpp`)。我来查看一下它具体执行了什么同步操作。


---

## Assistant <sup>2026/8/6 12:54:31</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\cann\\torch_npu\\pytorch\\torch_npu\\csrc\\aten\\common\\LocalScalarDenseNpu.cpp"
}
```

</details>


---

## User <sup>2026/8/6 12:54:31</sup>

<details>
<summary>Tool Result</summary>

```
1	#include <ATen/ATen.h>
2	#include <ATen/NativeFunctions.h>
3	#include <ATen/Dispatch_v2.h>
4	
5	#include "third_party/acl/inc/acl/acl_base.h"
6	#include "third_party/acl/inc/acl/acl_rt.h"
7	#include "torch_npu/csrc/core/npu/NPUStream.h"
8	#include "torch_npu/csrc/framework/utils/CalcuOpUtil.h"
9	#include "torch_npu/csrc/aten/NPUNativeFunctions.h"
10	
11	namespace at_npu {
12	namespace native {
13	
14	c10::Scalar NPUNativeFunctions::_local_scalar_dense(const at::Tensor& self)
15	{
16	    c10::Scalar r;
17	    TORCH_CHECK(self.numel() > 0, "_local_scalar_dense(): Empty tensor not supported");
18	    AT_DISPATCH_V2(
19	        self.scalar_type(), "_local_scalar_dense_npu", AT_WRAP([&] {
20	            scalar_t value = 0;
21	            c10_npu::NPUStream copy_stream = c10_npu::getCurrentNPUStream();
22	            // Synchronous copy after stream synchronization
23	            NPU_CHECK_ERROR(c10_npu::acl::AclrtSynchronizeStreamWithTimeout(copy_stream));
24	
25	            NPU_CHECK_ERR
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:54:47</sup>


---

## Assistant <sup>2026/8/6 12:54:48</sup>

决定性发现：NPU 的 `.item()` ([LocalScalarDenseNpu.cpp:21-23](cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp#L21-L23)) **仅同步 *当前* 流** (`getCurrentNPUStream()` → `AclrtSynchronizeStreamWithTimeout`)，而非整个设备。这推翻了“设备级同步”的假设。因此，修复必须来自计算流同步。关键问题在于 `handle.wait()` 同步的是哪个流——让我找一下 HCCL `Work::synchronize` 的实现（c19ac 注释引用了 `ProcessGroupHCCL.cpp:1001`）。


---

## Assistant <sup>2026/8/6 12:54:50</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch; echo \"=== locate ProcessGroupHCCL ===\" && find \"$TN\" -name \"ProcessGroupHCCL.cpp\" 2>/dev/null | head; echo \"\"; echo \"=== synchronizeInternal / hcclEndEvent / block logic ===\" && f=$(find \"$TN\" -name \"ProcessGroupHCCL.cpp\" 2>/dev/null | head -1); echo \"file: $f\"; grep -nE \"synchronizeInternal|synchronize\\(\\)|hcclEndEvent|->block\\(|\\.block\\(|wait\\(|getCurrentNPUStream|currentStream|ACLRT_MEMCPY|synchronize_event|npuSynchronize\" \"$f\" 2>/dev/null | head -40",
  "description": "Find HCCL Work synchronize implementation"
}
```

</details>


---

## User <sup>2026/8/6 12:58:18</sup>

<details>
<summary>Tool Result</summary>

```
=== locate ProcessGroupHCCL ===
/c/cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp

=== synchronizeInternal / hcclEndEvent / block logic ===
file: /c/cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp
106:    auto current_Stream = c10_npu::getCurrentNPUStream(device);
266:        hcclEvent.record(c10_npu::getCurrentNPUStream(devices[i].index()));
267:        hcclEvent.block(hcclStream);
704:    hcclEndEvents_ = std::make_shared<std::vector<c10_npu::NPUEvent>>(devices.size());
715:    hcclEndEvents_(w.hcclEndEvents_),
837:            if (!(*hcclEndEvents_)[i].query()) {
953:void ProcessGroupHCCL::WorkHCCL::synchronize()
957:    synchronizeInternal(kNoTimeout);
996:void ProcessGroupHCCL::WorkHCCL::synchronizeInternal(std::chrono::milliseconds timeout)
999:        auto currentStream = c10_npu::getCurrentNPUStream(devices_[i].index());
1001:        (*hcclEndEvents_)[i].block(currentStream);
1002:        TORCH_NPU_HCCL_LOGI("Event: block hccl work 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 12:59:19</sup>


---

## Assistant <sup>2026/8/6 12:59:20</sup>

`.item()` 仅同步**当前流**（第 21-23 行）。而 `handle.wait()` 会阻塞**调用时所在流**的 hccl 完成事件（第 999-1001 行）——如果这与模型读取所在的流不一致，数据将保持不同步。我来查看一下完整的 `synchronizeInternal`，包括第 1006 行的 `npuSynchronizeDevice` 分支。


---

## Assistant <sup>2026/8/6 12:59:20</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\cann\\torch_npu\\pytorch\\torch_npu\\csrc\\distributed\\ProcessGroupHCCL.cpp",
  "limit": 62,
  "offset": 953
}
```

</details>


---

## User <sup>2026/8/6 12:59:20</sup>

<details>
<summary>Tool Result</summary>

```
953	void ProcessGroupHCCL::WorkHCCL::synchronize()
954	{
955	    // Call Synchronize without a timeout. We use this method to avoid adding a
956	    // timeout argument to the public synchronize API.
957	    synchronizeInternal(kNoTimeout);
958	    if (c10d::allow_inflight_collective_as_graph_input()) {
959	        c10d::unregister_work(
960	            c10::intrusive_ptr<
961	                ProcessGroupHCCL::WorkHCCL>::unsafe_reclaim_from_nonowning(this));
962	    }
963	}
964	
965	void ProcessGroupHCCL::WorkHCCL::handleException(ErrorHandlingMode errorHandling)
966	{
967	    if (exception_) {
968	        auto exceptionMsg = c10::str(
969	            "Some HCCL operations have failed or timed out. Due to the ",
970	            "asynchronous nature of ASCEND kernels, subsequent NPU operations ",
971	            "might run on corrupted/incomplete data.");
972	        LOG(ERROR) << exceptionMsg;
973	        C10_LOG_API_USAGE_ONCE("ProcessGroupHCCL.WorkHCCL.handleException");
974	
975	   
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 13:00:06</sup>


---

## Assistant <sup>2026/8/6 13:00:25</sup>

我现在已经从源码中得到了确切的答案。分析如下。

## 直接结论

这是**流同步竞态（race），不是数值/逻辑 bug**。把 [gpu_worker.py:141-147](vllm/vllm/v1/worker/gpu_worker.py#L141-L147) 放开之所以能修精度，是因为那些 `.item()` 调用偷偷插入了一个**阻塞宿主的流同步**，而生产路径里恰好缺这个同步。典型的「打开 debug 打印 → bug 消失」= 时序竞态的铁证。

## 证据链（全部来自源码）

**1. NPU 上 `.item()` 到底做了什么** — [LocalScalarDenseNpu.cpp:21-23](cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp#L21-L23)：
```cpp
c10_npu::NPUStream copy_stream = c10_npu::getCurrentNPUStream();
NPU_CHECK_ERROR(c10_npu::acl::AclrtSynchronizeStreamWithTimeout(copy_stream));  // 阻塞宿主，直到该流排空
```
`.item()` = 取**当前流**并 `aclrtSynchronizeStream` 阻塞宿主。注释行里的 `t.mean().item()` / `t.min().item()` / `...tolist()` 每一个都触发一次。所以放开 141-147 = 在 `wait_for_comm` 末尾对**计算流**做了一次宿主阻塞同步。

**2. `handle.wait()` 到底做了什么** — [ProcessGroupHCCL.cpp:996-1007](cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp#L996-L1007)：
```cpp
auto currentStream = c10_npu::getCurrentNPUStream(devices_[i].index());
(*hcclEndEvents_)[i].block(currentStream);   // 让“当前流”等 hccl 完成事件
if (!barrierTensors_.empty()) { npuSynchronizeDevice(); }  // 仅 barrier 才整机同步
```
`handle.wait()` 只是**入队一个流侧依赖**（`currentStream.wait(hcclEndEvent)`），**不阻塞宿主**，且只作用于“调用 wait 时所在的当前流”。普通 irecv 不会走 `npuSynchronizeDevice`。

**3. 整条边云 recv 路径没有其它同步** — `parallel_state.py` 里 irecv 跑在专用 `_HC_STREAM_RECV` 流上（[L1335](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1335)/[L1392](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1392)），唯一的 recv→compute 同步就是 `wait_for_comm` 里的 `handle.wait()`。没有 `synchronize()`、没有 event。`record_stream(...)`（[L1340](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1340)）只管**缓存分配器的生命周期**，不建立任何“读可见性”依赖。

**4. CHER 把这事跨线程化了** — [worker.py:1171-1172](vllm-ascend/vllm_ascend/worker/worker.py#L1171-L1172)：irecv 由**guard 线程提前 post**（`start_early_irecv`），`wait_for_comm` 在 **busy_loop 线程**通过 `__getattribute__` 懒触发（[worker.py:1205-1206](vllm-ascend/vllm_ascend/worker/worker.py#L1205-L1206)）。`getCurrentNPUStream()` 是**线程局部**的——post 的线程和 wait/consume 的线程不是同一个。

## 为什么 `.item()` 能修

生产路径：`handle.wait()`（非阻塞、仅入队当前流依赖）→ postprocess → 立即返回，宿主继续往下跑模型 forward。recv→compute 的可见性**完全押在“`handle.wait()` 入队的那个 `currentStream` 恰好等于模型 forward 实际读取的流”**上。

放开 141-147 后：在 `wait_for_comm` 末尾对计算流 `aclrtSynchronizeStream` **阻塞宿主**，把“异步 recv”强制变成“宿主可见的已完成 recv”再让模型消费。它把竞态窗口关上了。

得 70 分而不是 0 分，正好符合**时序竞态**：多数请求 recv 抢赢，少数被消费方抢先读到未完成/被覆写的 hidden → 个别 token 错乱 → GSM8K 推理链断 → 掉分。

## 根因定位（高置信度类别，精确点需运行时确认）

`handle.wait()` 这个**非阻塞、相对于“当前流”**的同步，在 CHER 跨线程提前收 + 专用 recv 流的架构下，**不能可靠覆盖模型消费点**。最可能的两个具体缺口：

- **(A) 流错配**：`wait_for_comm` 经 `__getattribute__` 懒触发，其 `handle.wait()` 阻塞的是“触发时所在线程的当前流”。若该流 ≠ 模型 forward 实际读取的流（per-thread 默认流分叉，或 `cloud_prepare_early`/早访问在别的流上先触发过一次、`_comm_waited` 短路），模型所在流从未被钉在 irecv 完成上 → 读到旧数据。
- **(B) 缓冲复用竞态**：`handle.wait()` 不阻塞宿主，busy_loop 立即往下走；guard 线程见 head_token 被消费便 post **下一步 irecv**。若分配器把上一步 recv 缓冲复用给下一步（`record_stream` 未在正确流上保活，或 `AsyncIntermediateTensors` 已释放），新 irecv 会在模型排队读旧缓冲之前覆写它 → 错乱。`.item()` 阻塞宿主，把整条流水线节拍拖慢，恰好让旧读先完成。

两者都符合“加一次宿主阻塞同步即消失”。区分 (A)/(B) 需要一次 nsys/aclrt 事件追踪，或加临时日志确认 `wait_for_comm` 的触发线程与模型 forward 线程是否一致。

## 与 9772 的关系

精度问题是**预先存在**的（你说“同步后**还是**存在”）。9772 没有制造它，也没修它。但 9772 把 recv 拆到独立 `_HC_STREAM_RECV` 流 + CHER 跨线程 post，正是让“仅靠 `handle.wait()` 的非阻塞同步”变得脆弱的那种结构——拆流后 recv 与 compute 之间不再有任何隐式顺序，竞态窗口可能更宽，但根因是缺一个**显式的 compute←recv 依赖**。

## 正确修法（不要把 debug `.item()` 当修复）

`.item()` 块每次 recv 都整机/流阻塞，正好抵消 CHER 想要的 overlap（[worker.py:1208-1211](vllm-ascend/vllm_ascend/worker/worker.py#L1208-L1211) 明说不能在这里阻塞）。正确做法是补一个**真正的、不阻塞宿主的流依赖**：

1. **诊断确认**：先在 `wait_for_comm` 末尾加一次 `torch.npu.synchronize()` 跑 GSM8K，若→98，坐实“同步竞态”。（这等价于 `.item()`，但是显式的。）
2. **针对性修复（推荐）**：irecv 在 `_HC_STREAM_RECV` 上 post 完后，立即在该流上 `record` 一个完成事件；在 `wait_for_comm` 里、读 `self.tensors` 之前 `torch.npu.current_stream().wait_event(evt)`。这是真流依赖，不阻塞宿主，保住 overlap。
3. **若是 (B) 缓冲复用**：核实 `record_stream` 记录在 `_HC_STREAM_RECV`（而非被 `with` 改变了语义），并确保 `AsyncIntermediateTensors` 的生命周期覆盖到模型 forward 真正消费完。
4. **若是 (A) 流错配**：确保 `wait_for_comm` 与模型 forward 在同一线程/同一当前流触发，或把依赖显式 plumb 到 forward 实际用的流（含 graph replay 场景）。

需要我直接帮你实现第 2 步（event 方案）或第 1 步（诊断同步）并改 `gpu_worker.py` / `parallel_state.py` 吗？


---

## User <sup>2026/8/6 14:14:56</sup>

想确认根因，可以增加error级别日志确认根因，但不要引入同步操作避免问题消失


---

## Assistant <sup>2026/8/6 14:16:50</sup>


---

## Assistant <sup>2026/8/6 14:16:51</sup>

好计划——添加仅观测的 `error` 级别日志，不进行同步，这样 `race` 仍然会复现（分数 70），我们就能读取到线索了。让我先检查一下我需要用到的 `imports`/`helpers` 以及 buffer 的分配方式，以确保日志是非同步的，且能够确定是 `hypothesis` A 还是 B。


---

## Assistant <sup>2026/8/6 14:16:55</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== gpu_worker.py imports + logger ===\" && grep -nE \"^import|^from|logger\\s*=|import logging|import threading|import torch\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/worker/gpu_worker.py 2>&1 | head -30; echo \"\"; echo \"=== parallel_state.py: logger / threading / npu imports ===\" && grep -nE \"^import threading|^import logging|logger\\s*=|^import torch|getCurrentNPUStream|current_stream\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 | head -15; echo \"\"; echo \"=== guard thread creation/name in worker.py ===\" && grep -nE \"Thread\\(|threading\\.Thread|\\.name\\s*=|guard|busy_loop|daemon\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/worker.py 2>&1 | head -20",
  "description": "Check imports, logger, threading, thread names"
}
```

</details>


---

## Assistant <sup>2026/8/6 14:16:56</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== _allocate_merged_recv_buffer: cached or fresh? ===\" && grep -nE \"def _allocate_merged_recv_buffer\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1; sed -n \"/def _allocate_merged_recv_buffer/,/^def /p\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 | head -55",
  "description": "Inspect merged recv buffer allocation"
}
```

</details>


---

## User <sup>2026/8/6 14:16:57</sup>

<details>
<summary>Tool Result</summary>

```
=== gpu_worker.py imports + logger ===
5:import gc
6:import os
7:from collections.abc import Callable
8:from contextlib import AbstractContextManager, contextmanager, nullcontext
9:from datetime import timedelta
10:from types import NoneType
11:from typing import TYPE_CHECKING, Any
13:import numpy as np
14:import regex as re
15:import torch
16:import torch.nn as nn
18:import vllm.envs as envs
19:from vllm.config import CUDAGraphMode, VllmConfig, set_current_vllm_config
20:from vllm.config.compilation import CompilationMode
21:from vllm.device_allocator import get_mem_allocator_instance
22:from vllm.distributed import (
27:from vllm.distributed.ec_transfer import (
31:from vllm.distributed.eplb.eplb_utils import override_envs_for_eplb
32:from vllm.distributed.kv_transfer import (
38:from vllm.distributed.kv_transfer.kv_connector.v1.base import (
41:from vllm.distributed.parallel_state import (
47:from vllm.distributed.weight_transfer import (
51:from vllm.logger import init_logger
52:fr
...(truncated)
```

</details>


---

## User <sup>2026/8/6 14:17:00</sup>

<details>
<summary>Tool Result</summary>

```
=== _allocate_merged_recv_buffer: cached or fresh? ===
1196:def _allocate_merged_recv_buffer(
def _allocate_merged_recv_buffer(
    ec_meta: "EdgeCloudTensorMeta",
    num_tokens: int,
) -> torch.Tensor:
    """Allocate the merged P2P recv buffer that matches the sender's cat layout.

    The buffer's remaining dims come from ec_meta.merged_shape_tail (which
    already encodes hc_mult for 3D models and the total last-dim concatenation
    for either 2D or 3D).

    The leading dim is padded up to the local TP size when SP is enabled, so
    the per-key views handed to downstream SP ops satisfy the divisibility
    requirement — mirroring the non-merge path's ``recv_num_tokens``.  The
    sender still transmits only the actual ``num_tokens`` rows; the receiver
    irecvs into the leading ``num_tokens`` rows of this larger buffer (see
    edge_cloud_irecv_tensor_dict), leaving the padding tail unfilled.
    """
    assert ec_meta.merge_payload
    assert ec_meta.merged_dtype is not None
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 14:17:42</sup>


---

## Assistant <sup>2026/8/6 14:17:43</sup>

`_allocate_merged_recv_buffer` 每次调用都使用 `torch.empty`（新分配，非环形缓冲区），因此 B 需要分配器回收——`record_stream` 的流很重要。`gpu_worker.py` 中有 `init_logger` 但没有 `threading`；`parallel_state.py` 两者都有。让我确认一下 `logger` 的设置，并找到一种非同步的方式来标识当前的 NPU 流（原始指针）。


---

## Assistant <sup>2026/8/6 14:17:45</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== gpu_worker logger init ===\" && grep -nE \"logger\\s*=\\s*init_logger|^logger\" /c/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/worker/gpu_worker.py 2>&1 | head; echo \"\"; echo \"=== torch_npu Stream raw-pointer property ===\" && f=$(find /c/cann/torch_npu/pytorch/torch_npu -name \"Stream.py\" 2>/dev/null | head -1); echo \"file: $f\"; grep -nE \"def |cuda_stream|npu_stream|_stream|stream_id|property\" \"$f\" 2>/dev/null | head -30",
  "description": "Confirm logger init and NPU stream pointer attr"
}
```

</details>


---

## User <sup>2026/8/6 14:20:19</sup>

<details>
<summary>Tool Result</summary>

```
=== gpu_worker logger init ===
79:logger = init_logger(__name__)

=== torch_npu Stream raw-pointer property ===
file:
```

</details>


---

## Assistant <sup>2026/8/6 14:20:24</sup>


---

## Assistant <sup>2026/8/6 14:20:27</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== find torch.npu Stream class ===\" && grep -rlnE \"class Stream\\b\" /c/cann/torch_npu/pytorch/torch_npu 2>/dev/null | head; echo \"\"; echo \"=== Stream property for raw ptr ===\" && grep -rnE \"cuda_stream|npu_stream|def _stream|stream_id|_c10_stream\" /c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/Stream*.cpp /c/cann/torch_npu/pytorch/torch_npu/_C/__init__.py 2>/dev/null | head; echo \"\"; echo \"=== python-level: does torch.npu.current_stream() expose cuda_stream? (torch.Stream base) ===\"; grep -rnE \"cuda_stream|def stream_id|_c10_stream\" /c/torch/torch_npu/pytorch/torch/__init__.py 2>/dev/null | head; python - <<'EOF' 2>&1 | head\nimport torch\nprint(\"Stream attrs:\", [a for a in dir(torch.Stream) if not a.startswith(\"__\")][:20])\nEOF",
  "description": "Locate Stream raw pointer attribute"
}
```

</details>


---

## User <sup>2026/8/6 14:20:32</sup>

<details>
<summary>Tool Result</summary>

```
=== find torch.npu Stream class ===
/c/cann/torch_npu/pytorch/torch_npu/npu/streams.py

=== Stream property for raw ptr ===

=== python-level: does torch.npu.current_stream() expose cuda_stream? (torch.Stream base) ===
Traceback (most recent call last):
  File "<stdin>", line 1, in <module>
ModuleNotFoundError: No module named 'torch'
```

</details>


---

## Assistant <sup>2026/8/6 14:20:37</sup>


---

## Assistant <sup>2026/8/6 14:20:38</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== torch_npu Stream class properties ===\" && grep -nE \"class Stream|@property|def |cuda_stream|npu_stream|_stream|stream_id\" /c/cann/torch_npu/pytorch/torch_npu/npu/streams.py 2>&1 | head -40",
  "description": "Inspect NPU Stream properties"
}
```

</details>


---

## User <sup>2026/8/6 14:20:39</sup>

<details>
<summary>Tool Result</summary>

```
=== torch_npu Stream class properties ===
9:class Stream(torch_npu._C._NPUStreamBase):
24:    def __new__(cls, device=None, priority=0, **kwargs):
28:    def wait_event(self, event):
42:    def wait_stream(self, stream):
56:    def record_event(self, event=None):
71:    def query(self):
79:    def synchronize(self):
87:    def set_data_preprocess_stream(self, is_data_preprocess_stream=False):
91:            is_data_preprocess_stream(bool): determine
94:        super(Stream, self).set_data_preprocess_stream(is_data_preprocess_stream)
96:    @property
97:    def _as_parameter_(self):
98:        return ctypes.c_void_p(self.npu_stream)
100:    def __eq__(self, other):
105:    def __hash__(self):
106:        return hash((self.npu_stream, self.device))
108:    def __repr__(self):
109:        return ('<torch_npu.npu.Stream device={0} npu_stream={1:#x}>'
110:                .format(self.device, self.npu_stream))
134:    def __new__(cls, enable_timing=False, blocking=False, interprocess=False):
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 14:24:48</sup>


---

## Assistant <sup>2026/8/6 14:24:53</sup>

确认：`logger = init_logger(__name__)` 位于 [gpu_worker.py:79](vllm/vllm/v1/worker/gpu_worker.py#L79)，并且 `torch.npu.Stream` 暴露了 `.npu_stream`（原始指针，非同步）以及正确的 `__eq__` 方法。合并后的 recv buffer 是通过 `torch.empty` 进行新分配的，因此 B 需要 allocator recycling——此时 `record_stream` 指向的流非常重要。

我的计划：添加仅用于观测的 `logger.error` 日志（无需 `.item()`/同步），以区分以下三种假设：**(A)** `handle.wait()` 在与模型使用不同的流上运行；**(B)** recv buffer 在被消费前被回收；**(C)** irecv 句柄从未到达 `wait_for_comm` (`nhandles=0`)。让我重新读取我将要编辑的具体区域，以确保修改准确无误。


---

## Assistant <sup>2026/8/6 14:24:53</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 8,
  "offset": 4
}
```

</details>


---

## User <sup>2026/8/6 14:24:53</sup>

<details>
<summary>Tool Result</summary>

```
4	
5	import gc
6	import os
7	from collections.abc import Callable
8	from contextlib import AbstractContextManager, contextmanager, nullcontext
9	from datetime import timedelta
10	from types import NoneType
11	from typing import TYPE_CHECKING, Any
```

</details>


---

## Assistant <sup>2026/8/6 14:24:53</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 4,
  "offset": 78
}
```

</details>


---

## User <sup>2026/8/6 14:24:53</sup>

<details>
<summary>Tool Result</summary>

```
78	
79	logger = init_logger(__name__)
80	
81	# Debug: edge-cloud hidden-recv info is appended to this file (same file
```

</details>


---

## Assistant <sup>2026/8/6 14:24:53</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 60,
  "offset": 100
}
```

</details>


---

## User <sup>2026/8/6 14:24:53</sup>

<details>
<summary>Tool Result</summary>

```
100	class AsyncIntermediateTensors(IntermediateTensors):
101	    """IntermediateTensors with lazy comm synchronization"""
102	
103	    def __init__(
104	        self,
105	        tensors: dict[str, torch.Tensor],
106	        comm_handles: list[Handle] | None = None,
107	        comm_postprocess: list[Callable[[], None]] | None = None,
108	        batch_type: Any = None,
109	        req_ids: list[str] | None = None,
110	    ) -> None:
111	        super().__init__(tensors)
112	        self._comm_handles = comm_handles
113	        self._comm_postprocess = comm_postprocess
114	        self._comm_waited = False
115	        self._batch_type = batch_type
116	        self._req_ids = req_ids
117	
118	    def wait_for_comm(self) -> None:
119	        if self._comm_waited:
120	            return
121	        if self._comm_handles:
122	            for handle in self._comm_handles:
123	                handle.wait()
124	        if self._comm_postprocess:
125	            for fn in self._comm_postproces
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 14:24:57</sup>


---

## Assistant <sup>2026/8/6 14:24:58</sup>

已确认当前状态。现在应用 `gpu_worker.py` 的插桩 —— 添加 `threading` 导入、一个非同步流 ID 辅助函数，以及三个日志点（`[EC-WAIT]`、`[EC-WAIT-END]`、`[EC-ACCESS]`）。


---

## Assistant <sup>2026/8/6 14:24:59</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "import gc\nimport os\nfrom collections.abc import Callable",
  "new_string": "import gc\nimport os\nimport threading\nfrom collections.abc import Callable"
}
```

</details>


---

## User <sup>2026/8/6 14:25:00</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:00</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "logger = init_logger(__name__)",
  "new_string": "logger = init_logger(__name__)\n\n\ndef _ec_stream_id() -> str:\n    \"\"\"Current NPU stream raw pointer (hex) for edge-cloud recv diagnostics.\n\n    NON-syncing: only reads the thread-local stream handle, never calls\n    synchronize/item, so it cannot perturb the race under investigation.\n    \"\"\"\n    try:\n        if hasattr(torch, \"npu\"):\n            return f\"0x{torch.npu.current_stream().npu_stream:x}\"\n    except Exception:\n        pass\n    return \"n/a\""
}
```

</details>


---

## User <sup>2026/8/6 14:25:01</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:02</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        self._comm_waited = False\n        self._batch_type = batch_type\n        self._req_ids = req_ids",
  "new_string": "        self._comm_waited = False\n        self._batch_type = batch_type\n        self._req_ids = req_ids\n        # Stream on which wait_for_comm()->handle.wait() ran; compared against\n        # the stream of later .tensors accesses to detect stream-affinity races.\n        self._wait_stream_id: str | None = None"
}
```

</details>


---

## User <sup>2026/8/6 14:25:03</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:06</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "    def wait_for_comm(self) -> None:\n        if self._comm_waited:\n            return\n        if self._comm_handles:\n            for handle in self._comm_handles:\n                handle.wait()\n        if self._comm_postprocess:\n            for fn in self._comm_postprocess:\n                fn()\n        self._comm_waited = True",
  "new_string": "    def wait_for_comm(self) -> None:\n        if self._comm_waited:\n            return\n        # [EC-WAIT] NON-syncing diagnostic: capture the thread/stream on which\n        # handle.wait() runs, and how many HCCL handles are actually waited.\n        # nhandles==0  -> irecv handles never reach wait_for_comm (root cause C).\n        # this stream != a later .tensors consumption stream (see [EC-ACCESS]\n        #   MISMATCH) -> recv->compute sync missed the consumer's stream (A).\n        self._wait_stream_id = _ec_stream_id()\n        _nhandles = len(self._comm_handles) if self._comm_handles else 0\n        logger.error(\n            \"[EC-WAIT] entry=%#x thread=%s(%s) stream=%s nhandles=%d \"\n            \"batch=%s reqs=%s\",\n            id(self), threading.get_ident(), threading.current_thread().name,\n            self._wait_stream_id, _nhandles, self._batch_type, self._req_ids,\n        )\n        if self._comm_handles:\n            for handle in self._comm_handles:\n                handle.wait()\n        if self._comm_postprocess:\n            for fn in self._comm_postprocess:\n                fn()\n        self._comm_waited = True\n        # [EC-WAIT-END] storage ptrs of the consumed tensors; correlate with\n        # [EC-POST] storage_ptr to detect recv-buffer reuse before consumption.\n        try:\n            _buf_ptrs = [\n                t.storage().data_ptr() for t in self.tensors.values()\n                if isinstance(t, torch.Tensor)\n            ]\n        except Excepti
...(truncated)
```

</details>


---

## User <sup>2026/8/6 14:25:07</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:09</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "    def __getattribute__(self, name: str):\n        # ensure `.tensors` is ready before use\n        if name == \"tensors\" and not object.__getattribute__(self, \"_comm_waited\"):\n            object.__getattribute__(self, \"wait_for_comm\")()\n        return object.__getattribute__(self, name)",
  "new_string": "    def __getattribute__(self, name: str):\n        # ensure `.tensors` is ready before use\n        if name == \"tensors\":\n            # [EC-ACCESS] NON-syncing diagnostic on every .tensors consumption.\n            # will_trigger=True => this access runs wait_for_comm() (same\n            #   thread/stream as handle.wait()).\n            # MISMATCH=True => consuming on a stream different from where\n            #   handle.wait() ran -> recv->compute sync missed this stream (A).\n            _waited = object.__getattribute__(self, \"_comm_waited\")\n            _cur = _ec_stream_id()\n            _wstream = object.__getattribute__(self, \"_wait_stream_id\")\n            _trigger = not _waited\n            _mismatch = bool(\n                _waited and _wstream is not None and _cur != _wstream)\n            if _trigger or _mismatch:\n                logger.error(\n                    \"[EC-ACCESS] entry=%#x thread=%s(%s) cur_stream=%s \"\n                    \"wait_stream=%s already_waited=%s will_trigger=%s \"\n                    \"MISMATCH=%s\",\n                    id(self), threading.get_ident(),\n                    threading.current_thread().name, _cur, _wstream, _waited,\n                    _trigger, _mismatch,\n                )\n            if _trigger:\n                object.__getattribute__(self, \"wait_for_comm\")()\n        return object.__getattribute__(self, name)"
}
```

</details>


---

## User <sup>2026/8/6 14:25:10</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:33</sup>


---

## Assistant <sup>2026/8/6 14:25:33</sup>

`gpu_worker.py` 的修改已全部完成。现在开始 `parallel_state.py` 的修改：添加 stream-id 辅助函数，并在两个 `irecv` 位置添加 `[EC-POST]` 日志。


---

## Assistant <sup>2026/8/6 14:25:35</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "def edge_cloud_irecv_tensor_dict(\n    num_tokens: int,",
  "new_string": "def _ec_stream_id() -> str:\n    \"\"\"Current NPU stream raw pointer (hex) for edge-cloud recv diagnostics.\n\n    NON-syncing: only reads the thread-local stream handle.\n    \"\"\"\n    try:\n        if hasattr(torch, \"npu\"):\n            return f\"0x{torch.npu.current_stream().npu_stream:x}\"\n    except Exception:\n        pass\n    return \"n/a\"\n\n\ndef edge_cloud_irecv_tensor_dict(\n    num_tokens: int,"
}
```

</details>


---

## User <sup>2026/8/6 14:25:36</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:37</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "        handles.append(handle)\n\n        # Zero-fill the SP padding tail (see the non-merge path for why).",
  "new_string": "        handles.append(handle)\n        # [EC-POST] NON-syncing diagnostic: who posts the irecv (guard thread\n        # vs busy_loop), on which stream, and the recv buffer's storage ptr\n        # (correlate with [EC-WAIT-END] buf_ptrs to detect reuse before\n        # consumption -> root cause B).\n        logger.error(\n            \"[EC-POST] merge channel=%s num_tokens=%d thread=%s(%s) \"\n            \"stream=%s recv_view_ptr=0x%x storage_ptr=0x%x storage_size=%s\",\n            channel, num_tokens, threading.get_ident(),\n            threading.current_thread().name, _ec_stream_id(),\n            recv_view.data_ptr(), recv_view.storage().data_ptr(),\n            recv_view.storage().size(),\n        )\n\n        # Zero-fill the SP padding tail (see the non-merge path for why)."
}
```

</details>


---

## User <sup>2026/8/6 14:25:38</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:25:39</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "            handles.append(handle)\n            # Zero-fill the SP padding tail.  The sender only transmits",
  "new_string": "            handles.append(handle)\n            logger.error(\n                \"[EC-POST] key=%s channel=%s num_tokens=%d thread=%s(%s) \"\n                \"stream=%s recv_view_ptr=0x%x storage_ptr=0x%x storage_size=%s\",\n                key, channel, num_tokens, threading.get_ident(),\n                threading.current_thread().name, _ec_stream_id(),\n                recv_view.data_ptr(), recv_view.storage().data_ptr(),\n                recv_view.storage().size(),\n            )\n            # Zero-fill the SP padding tail.  The sender only transmits"
}
```

</details>


---

## User <sup>2026/8/6 14:25:40</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 14:26:06</sup>


---

## Assistant <sup>2026/8/6 14:26:07</sup>

所有修改已应用。让我验证语法并审查日志代码是否未引入同步操作（不能有 `.item`/`.tolist`/`.cpu`/`.numpy`/`synchronize`/reductions）。


---

## Assistant <sup>2026/8/6 14:26:08</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== syntax check ===\" && python -m py_compile vllm/vllm/v1/worker/gpu_worker.py 2>&1 && echo \"gpu_worker OK\" || echo \"gpu_worker FAIL\"; python -m py_compile vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 && echo \"parallel_state OK\" || echo \"parallel_state FAIL\"",
  "description": "Syntax check both files"
}
```

</details>


---

## Assistant <sup>2026/8/6 14:26:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== audit: any sync-inducing call inside EC-* diagnostic lines? (must be empty) ===\" && grep -nE \"\\.item\\(|\\.tolist\\(|\\.cpu\\(|\\.numpy\\(|synchronize\\(|\\.mean\\(|\\.std\\(|\\.min\\(|\\.max\\(|\\.sum\\(|\\.float\\(|record_stream\" vllm/vllm/v1/worker/gpu_worker.py | grep -E \"EC-WAIT|EC-ACCESS|EC-POST|_ec_stream_id\" ; echo \"--- (above empty = clean) ---\"; echo \"\"; echo \"=== confirm record_stream is the ONLY stream op, and it pre-existed (not added by us) ===\"; grep -nE \"record_stream\" vllm-ascend/vllm_ascend/distributed/parallel_state.py | head",
  "description": "Audit diagnostic lines for hidden syncs"
}
```

</details>


---

## User <sup>2026/8/6 14:27:02</sup>

<details>
<summary>Tool Result</summary>

```
=== syntax check ===
gpu_worker OK
parallel_state OK
```

</details>


---

## User <sup>2026/8/6 14:27:06</sup>

<details>
<summary>Tool Result</summary>

```
=== audit: any sync-inducing call inside EC-* diagnostic lines? (must be empty) ===
--- (above empty = clean) ---

=== confirm record_stream is the ONLY stream op, and it pre-existed (not added by us) ===
1155:                merged.record_stream(torch.cuda.current_stream(merged.device))
1157:                merged.record_stream(torch.npu.current_stream(merged.device))
1188:                value.record_stream(torch.cuda.current_stream(value.device))
1190:                value.record_stream(torch.npu.current_stream(value.device))
1353:                recv_view.record_stream(torch.npu.current_stream(recv_view.device))
1422:                    recv_view.record_stream(
```

</details>


---

## Assistant <sup>2026/8/6 14:27:10</sup>


---

## Assistant <sup>2026/8/6 14:27:11</sup>

两个文件均编译通过；审计确认在诊断日志中**没有同步调用**（`record_stream` 是预先存在的，并非由我添加）。让我对插桩后的类进行最后检查。


---

## Assistant <sup>2026/8/6 14:27:11</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 95,
  "offset": 112
}
```

</details>


---

## User <sup>2026/8/6 14:27:11</sup>

<details>
<summary>Tool Result</summary>

```
112	    from vllm.v1.worker.gpu_model_runner import GPUModelRunner
113	
114	
115	class AsyncIntermediateTensors(IntermediateTensors):
116	    """IntermediateTensors with lazy comm synchronization"""
117	
118	    def __init__(
119	        self,
120	        tensors: dict[str, torch.Tensor],
121	        comm_handles: list[Handle] | None = None,
122	        comm_postprocess: list[Callable[[], None]] | None = None,
123	        batch_type: Any = None,
124	        req_ids: list[str] | None = None,
125	    ) -> None:
126	        super().__init__(tensors)
127	        self._comm_handles = comm_handles
128	        self._comm_postprocess = comm_postprocess
129	        self._comm_waited = False
130	        self._batch_type = batch_type
131	        self._req_ids = req_ids
132	        # Stream on which wait_for_comm()->handle.wait() ran; compared against
133	        # the stream of later .tensors accesses to detect stream-affinity races.
134	        self._wait_stream_id: str | None = None
135	
136	  
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 14:28:35</sup>


---

## Assistant <sup>2026/8/6 14:28:48</sup>

插桩完成且简洁。以下是如何使用它来确认根因。

## 加了什么（全部 error 级、全部非同步）

三个日志标签，只记录**指针/形状/线程/流句柄**等元数据，**没有任何 `.item()/.tolist()/.cpu()/synchronize()`**（已用 grep 审计确认），所以竞态不会被掩盖、精度应仍为 ~70：

| 标签 | 位置 | 作用 |
|---|---|---|
| `[EC-POST]` | [parallel_state.py](vllm-ascend/vllm_ascend/distributed/parallel_state.py) 两处 irecv（merge/非merge） | 谁（线程）在哪条流 post 了 irecv + recv 缓冲的 `storage_ptr` |
| `[EC-WAIT]` | [gpu_worker.py wait_for_comm](vllm/vllm/v1/worker/gpu_worker.py#L136) 入口 | `handle.wait()` 实际跑在哪个线程/哪条流 + `nhandles` |
| `[EC-WAIT-END]` | 同上末尾 | 消费时各 tensor 的 `storage_ptr`（与 POST 对照查缓冲复用） |
| `[EC-ACCESS]` | [gpu_worker.py __getattribute__](vllm/vllm/v1/worker/gpu_worker.py#L196) 每次 `.tensors` 访问 | 消费所在的流；若 `MISMATCH=True` = 消费流 ≠ handle.wait 阻塞的流 |

## 怎么跑

建议先用**小批量（如 50 个请求）**复现，既够触发精度掉分又控制日志量；把 vllm 日志重定向到文件：
```bash
# 跑完后，确认得分仍 ~70（没被日志掩盖），再分析
grep -E "EC-(POST|WAIT|ACCESS)" vllm.log > ec.log
```
> ⚠️ Heisenberg 提醒：`logger.error` 有宿主 I/O 开销。若开日志后得分跳到 ~98，说明宿主延迟掩盖了竞态——届时把 `[EC-ACCESS]` 里 `will_trigger` 那条注释掉再跑。但设备侧竞态是毫秒级（跨节点 irecv），微秒级日志一般掩不住，预计仍复现。

## 怎么读（决策树）

```bash
# —— 根因 C：irecv handle 根本没进 wait_for_comm ——
grep "EC-WAIT" ec.log | grep "nhandles=0"
# 有命中 => C 成立：handle.wait() 什么都没等，recv 从未同步

# —— 根因 A：消费流 ≠ handle.wait 阻塞的流 ——
grep "EC-ACCESS" ec.log | grep "MISMATCH=True"
# 有命中 => A 成立：模型在 handle.wait 没阻塞的流上读，recv->compute 依赖打空
# 也可看 [EC-WAIT] 的 thread 是否就是 [EC-POST] 的 guard 线程（wait 跑在 guard 线程=可疑）
```

**根因 B（缓冲复用覆写）** 需要按时间序关联 `storage_ptr`：若某个 `storage_ptr` 在被 `[EC-WAIT-END]` 消费之前，就再次出现在 `[EC-POST]` 里，说明分配器把这块内存在模型读之前回收给了下一个 irecv → B 成立。用下面脚本扫日志：


---

## Assistant <sup>2026/8/6 14:28:56</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cat > /c/v0.23.0_lwd_acc_test_br/ec_rootcause.py <<'PYEOF'\n#!/usr/bin/env python3\n\"\"\"Parse vllm logs and classify the edge-cloud recv precision race.\nRoot causes: A=stream/thread mismatch, B=recv buffer reused before consumption,\nC=irecv handles never waited. NON-syncing logs only -> race still reproduces.\"\"\"\nimport re, sys\n\nPOST = re.compile(r\"\\[EC-POST\\].*?storage_ptr=0x([0-9a-f]+)\")\nWAITN = re.compile(r\"\\[EC-WAIT\\].*?nhandles=(\\d+)\")\nACC = re.compile(r\"\\[EC-ACCESS\\].*?MISMATCH=(True|False)\")\nEND = re.compile(r\"\\[EC-WAIT-END\\].*?buf_ptrs=\\[([0-9a-fx, ]*)\\]\")\n\nfound_A = found_C = found_B = 0\nin_flight = set()  # storage_ptrs posted but not yet consumed\n\nfor line in sys.stdin:\n    if \"[EC-WAIT]\" in line and \"EC-WAIT-END\" not in line:\n        m = WAITN.search(line)\n        if m and int(m.group(1)) == 0:\n            found_C += 1\n            print(\"[C] nhandles=0 in:\", line.strip())\n    elif \"[EC-ACCESS]\" in line:\n        m = ACC.search(line)\n        if m and m.group(1) == \"True\":\n            found_A += 1\n            print(\"[A] MISMATCH in:\", line.strip())\n    elif \"[EC-POST]\" in line:\n        m = POST.search(line)\n        if m:\n            ptr = m.group(1)\n            if ptr in in_flight:\n                found_B += 1\n                print(f\"[B] storage_ptr 0x{ptr} REPOSTED before consumption:\", line.strip())\n            in_flight.add(ptr)\n    elif \"[EC-WAIT-END]\" in line:\n        m = END.search(line)\n        if m:\n            for p in m.group(1).replace(\"0x\", \"\").split(\",\"):\n                p = p.strip()\n                if p:\n                    in_flight.discard(p)\n\nprint(\"\\n=== SUMMARY ===\")\nprint(f\"A (stream/thread mismatch): {found_A}\")\nprint(f\"B (buffer reused before consumption): {found_B}\")\nprint(f\"C (handles never waited, nhandles=0): {found_C}\")\nprint(\"=> highest non-zero is the root cause.\")\nPYEOF\necho \"parser written: /c/v0.23.0_lwd_a
...(truncated)
```

</details>


---

## User <sup>2026/8/6 14:28:57</sup>

<details>
<summary>Tool Result</summary>

```
parser written: /c/v0.23.0_lwd_acc_test_br/ec_rootcause.py
用法: grep -E 'EC-(POST|WAIT|ACCESS)' vllm.log | python ec_rootcause.py
```

</details>


---

## Assistant <sup>2026/8/6 14:29:16</sup>


---

## Assistant <sup>2026/8/6 14:29:17</sup>

我在解析器中发现了一个 base-mismatch bug：`[EC-POST]` 将 `storage_ptr` 记录为十六进制（`0x...`），而 `[EC-WAIT-END]` 将 `buf_ptrs` 记录为十进制整数列表。在比较之前，我需要将两者都标准化为 `int`。我来修复一下。


---

## Assistant <sup>2026/8/6 14:29:24</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cat > /c/v0.23.0_lwd_acc_test_br/ec_rootcause.py <<'PYEOF'\n#!/usr/bin/env python3\n\"\"\"Parse vllm logs and classify the edge-cloud recv precision race.\nRoot causes: A=stream/thread mismatch, B=recv buffer reused before consumption,\nC=irecv handles never waited. NON-syncing logs only -> race still reproduces.\n\nUsage: grep -E 'EC-(POST|WAIT|ACCESS)' vllm.log | python ec_rootcause.py\n\"\"\"\nimport re, sys\n\nPOST  = re.compile(r\"\\[EC-POST\\].*?storage_ptr=0x([0-9a-f]+)\")\nWAITN = re.compile(r\"\\[EC-WAIT\\].*?nhandles=(\\d+)\")\nACC   = re.compile(r\"\\[EC-ACCESS\\].*?MISMATCH=(True|False)\")\n# buf_ptrs is a Python list of ints, e.g. buf_ptrs=[1234, 5678]  (decimal)\nEND   = re.compile(r\"\\[EC-WAIT-END\\].*?buf_ptrs=\\[([0-9, ]*)\\]\")\n\nfound_A = found_C = found_B = 0\nin_flight = set()  # storage ptrs (as int) posted but not yet consumed\n\nfor line in sys.stdin:\n    if \"[EC-WAIT-END]\" in line:\n        m = END.search(line)\n        if m:\n            for p in m.group(1).split(\",\"):\n                p = p.strip()\n                if p:\n                    in_flight.discard(int(p))\n    elif \"[EC-WAIT]\" in line:\n        m = WAITN.search(line)\n        if m and int(m.group(1)) == 0:\n            found_C += 1\n            print(\"[C] nhandles=0 (handles never waited):\", line.strip())\n    elif \"[EC-ACCESS]\" in line:\n        m = ACC.search(line)\n        if m and m.group(1) == \"True\":\n            found_A += 1\n            print(\"[A] MISMATCH (consumer stream != handle.wait stream):\",\n                  line.strip())\n    elif \"[EC-POST]\" in line:\n        m = POST.search(line)\n        if m:\n            ptr = int(m.group(1), 16)\n            if ptr in in_flight:\n                found_B += 1\n                print(f\"[B] storage_ptr 0x{ptr:x} REPOSTED before consumption:\",\n                      line.strip())\n            in_flight.add(ptr)\n\nprint(\"\\n=== SUMMARY ===\")\nprint(f\"A (stream/thread mismatch)          
...(truncated)
```

</details>


---

## User <sup>2026/8/6 14:34:15</sup>

<details>
<summary>Tool Result</summary>

```
parser OK
```

</details>


---

## Assistant <sup>2026/8/6 14:34:34</sup>


---

## Assistant <sup>2026/8/6 14:34:48</sup>

解析器已修复并完成验证。这是完整的诊断方案。

## 跑测与分析

```bash
# 1) 小批量复现（50 请求够触发掉分又控日志量），日志重定向到文件
#    确认得分仍 ~70（没被日志掩盖）

# 2) 抽出诊断行
grep -E "EC-(POST|WAIT|ACCESS)" vllm.log | python /c/v0.23.0_lwd_acc_test_br/ec_rootcause.py
```

解析器会逐行按时间序判别并打印 SUMMARY：

```
A (stream/thread mismatch)            : N
B (buffer reused before consumption)  : N
C (handles never waited, nhandles=0)  : N
```

非零的那项就是根因。也可手动复核：
- **C**：`grep "EC-WAIT" vllm.log | grep "nhandles=0"`
- **A**：`grep "EC-ACCESS" vllm.log | grep "MISMATCH=True"`

## 各根因对应的修法

| 根因 | 含义 | 正确修法（不要用 `.item()` 当修复） |
|---|---|---|
| **C** | irecv handle 没进 `_comm_handles`，`handle.wait()` 啥也没等 | 确认边云 recv 路径把 irecv handle 透传进 `AsyncIntermediateTensors(comm_handles=...)`（[worker.py:832](vllm-ascend/vllm_ascend/worker/worker.py#L832) 已传，排查是否有分支返回 `[]`） |
| **A** | 模型消费所在的 NPU 流 ≠ `handle.wait()` 阻塞的流（CHER 跨线程 post + 懒触发 `__getattribute__`） | 在 `_HC_STREAM_RECV` 上 irecv 后 `record` 一个完成事件，`wait_for_comm` 里 `current_stream().wait_event(evt)` 建立真正的流依赖；或确保 `wait_for_comm` 与模型 forward 同线程/同流 |
| **B** | recv 缓冲被分配器回收、在模型读取前被下一个 irecv 覆写 | `record_stream` 改记在**消费流（compute）**而非 recv 流（见下）；或延长 `AsyncIntermediateTensors` 生命周期到模型真正读完 |

## 我的预判与一个关键旁证

得分 **70（偶发、多数正确）** 更像 **B**，而非 A/C：若 `handle.wait()` 完全失效（A 流错配 / C 不等待），计算流几乎总是抢在跨节点 irecv 前读到旧数据 -> 得分应接近 0，而不是 70。偶发掉分符合“分配器偶尔回收缓冲、下一轮 irecv 偶尔覆写”。

旁证正好指向 B 的机制：`record_stream` 是在 `_hidden_channel_stream_ctx(...)` 的 `with` 块**内部**调的（[parallel_state.py:1353](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1353)/[1422](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1422)），此时 `torch.npu.current_stream()` = **recv 流**。于是分配器在 **irecv 完成时**就认为该缓冲可回收--而模型在 **compute 流**上还没读完。下一个 `torch.empty`（[_allocate_merged_recv_buffer](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1196) 是每次现分配）就可能拿到同一块内存，被下一个 irecv 覆写。`.item()` 之所以能修，是因为它对 compute 流做了宿主阻塞，把模型读取“提前确定完成”，抢在下一轮覆写之前。

跑完把 SUMMARY 结果贴回来，我据此给确定性的修复补丁（B 的话就是把 `record_stream` 记到 compute 流 / 或加 event 依赖；A 的话加 `wait_event`）。


---

## User <sup>2026/8/6 14:56:59</sup>

部署是边侧1卡的embedding only，边侧  "EC-WAIT" 的nhandles都是1，云侧TP0"EC-WAIT" 的nhandles都是1， 云侧非TP0的nhandles都是0；边云 "EC-ACCESS"都没有 "MISMATCH=True"


---

## Assistant <sup>2026/8/6 15:06:28</sup>


---

## Assistant <sup>2026/8/6 15:06:41</sup>

这是一组非常关键的发现。我先解读一下，然后再确定剩下的 suspect。

## 解读：A 和 C 都已排除

- **C 排除**：边侧、云侧 TP0 的 `nhandles=1` → irecv handle **确实进了** `wait_for_comm` 并被 `handle.wait()`。云侧非 TP0 的 `nhandles=0` 是**正常的**，不是 bug——它们不跨节点 irecv，靠 TP broadcast 拿数据（[parallel_state.py](vllm-ascend/vllm_ascend/distributed/parallel_state.py) 的非 PP-NPU0 分支返回 `[]` handles，由 `broadcast_postprocess` 同步）。
- **A 排除**：边云都没有 `MISMATCH=True` → `handle.wait()` 跑在的流 == 模型 `.tensors` 消费所在的流。recv→compute 的流依赖**打对了**。

所以：handle 在正确的流上、确实被 wait 了，`.item()`（= `aclrtSynchronizeStream(compute)`，宿主阻塞计算流）却仍然必需。结合**得分 70（偶发、多数正确）**，可逻辑推出剩余唯一根因是 **B**：

> `handle.wait()` 只让计算流等到“irecv[N] 完成”，**不等“irecv[N+1] 不会覆写这块缓冲”**。`_allocate_merged_recv_buffer` 每次 `torch.empty`（[L1196](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1196)），CHER 守护线程会提前 post 下一个 irecv；而 `record_stream` 现在记在 **recv 流（生产者流）**上（[L1353](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1353)/[L1422](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1422)），分配器在 irecv 完成时就认为可回收——**早于模型在 compute 流上读完**。下一个 irecv 复用同一块内存覆写 → 计算流偶发读到错数据 → 掉分。
> `.item()` 之所以能修：它把计算流排空（宿主阻塞），让模型对 buffer[N] 的读**抢在** buffer 被回收/覆写之前完成。

（若是 `handle.wait()` 完全不提供可见性，postprocess 的 broadcast/split/sp_chunk 读到的就总是旧数据 → 得分应≈0 而非 70。偶发 70 正好符合“覆写竞态”。）

## 日志为何到此为止

B 的关键时序是“模型在 compute 流上读完 buffer vs 下一个 irecv 在 recv 流上覆写同一块内存”。这条竞态**无法用非同步日志可靠观测**：模型真正读完的时刻不在 `wait_for_comm` 里（它在之后），而 `__del__` 受 GC 时机影响、`stream.query()` 不可靠。所以下一步用**非同步实验**来一锤定音——它不引入任何同步，若 bug 消失即证明 B（消失的原因是“延长了缓冲寿命”而非“加了同步”）。

## 确认实验（非同步）：把 recv buffer 也记到 compute（消费）流

`record_stream` 是**纯分配器元数据，不是同步**。现在只记了 recv/生产者流；补记一条 compute/消费流，让分配器在模型读完前不回收。若精度→98，B 坐实且这就是修复；若仍 70，则退回，改用 event 建 compute←recv 依赖。

我先确认两处 irecv 的当前文本再改：


---

## Assistant <sup>2026/8/6 15:06:42</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && grep -nE \"record_stream|handles\\.append\\(handle\\)|with _hidden_channel_stream_ctx\\(channel, _HC_STREAM_RECV\" vllm_ascend/distributed/parallel_state.py | sed -n '1,20p'",
  "description": "Locate current irecv record_stream lines"
}
```

</details>


---

## User <sup>2026/8/6 15:06:44</sup>

<details>
<summary>Tool Result</summary>

```
1155:                merged.record_stream(torch.cuda.current_stream(merged.device))
1157:                merged.record_stream(torch.npu.current_stream(merged.device))
1158:        handles.append(handle)
1188:                value.record_stream(torch.cuda.current_stream(value.device))
1190:                value.record_stream(torch.npu.current_stream(value.device))
1191:        handles.append(handle)
1348:        with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
1353:                recv_view.record_stream(torch.npu.current_stream(recv_view.device))
1354:        handles.append(handle)
1417:            with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
1422:                    recv_view.record_stream(
1424:            handles.append(handle)
```

</details>


---

## Assistant <sup>2026/8/6 15:06:50</sup>


---

## Assistant <sup>2026/8/6 15:06:51</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 8,
  "offset": 1348
}
```

</details>


---

## User <sup>2026/8/6 15:06:51</sup>

<details>
<summary>Tool Result</summary>

```
1348	        with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
1349	            handle = torch.distributed.irecv(
1350	                recv_view, src=pp_group.ranks[src], group=group
1351	            )
1352	            if recv_view.device.type == "npu":
1353	                recv_view.record_stream(torch.npu.current_stream(recv_view.device))
1354	        handles.append(handle)
1355	        # [EC-POST] NON-syncing diagnostic: who posts the irecv (guard thread
```

</details>


---

## Assistant <sup>2026/8/6 15:06:51</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 9,
  "offset": 1417
}
```

</details>


---

## User <sup>2026/8/6 15:06:51</sup>

<details>
<summary>Tool Result</summary>

```
1417	            with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
1418	                handle = torch.distributed.irecv(
1419	                    recv_view, src=pp_group.ranks[src], group=group
1420	                )
1421	                if recv_view.device.type == "npu":
1422	                    recv_view.record_stream(
1423	                        torch.npu.current_stream(recv_view.device))
1424	            handles.append(handle)
1425	            logger.error(
```

</details>


---

## Assistant <sup>2026/8/6 15:07:56</sup>


---

## Assistant <sup>2026/8/6 15:07:56</sup>

让我重新读取这两个 `irecv` 区域，以获取准确的当前文本（缩进很重要），然后再进行编辑。


---

## Assistant <sup>2026/8/6 15:07:56</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 10,
  "offset": 1414
}
```

</details>


---

## User <sup>2026/8/6 15:07:56</sup>

<details>
<summary>Tool Result</summary>

```
1414	
1415	        if key in send_keys:
1416	            recv_view = full_tensor[:num_tokens]
1417	            with _hidden_channel_stream_ctx(channel, _HC_STREAM_RECV, wait_for_default=True):
1418	                handle = torch.distributed.irecv(
1419	                    recv_view, src=pp_group.ranks[src], group=group
1420	                )
1421	                if recv_view.device.type == "npu":
1422	                    recv_view.record_stream(
1423	                        torch.npu.current_stream(recv_view.device))
```

</details>


---

## Assistant <sup>2026/8/6 15:09:06</sup>


---

## Assistant <sup>2026/8/6 15:09:10</sup>

好的——已确认：`if/record_stream` 在 `with` 代码块内部（分别在第 16/20 空格处），因此它们记录的是 **recv 流（生产者流）**。在 `with` 代码块退出后，`current_stream()` 会恢复为外部流。

与其在 `irecv` 位置（该位置在 **guard thread** 上运行，因此其外部流可能不是模型的读取流）进行探测，不如采用更简洁的实验方案：在 `wait_for_comm`（在 **busy_loop 线程** = 模型的计算/读取流上运行）中记录消费张量。此处使用 `torch.npu.current_stream()` 即为模型的读取流。`record_stream` **不是同步操作**——它只是分配器的元数据，因此如果 bug 消失，说明是由于生命周期原因，从而确认是 B 导致的。


---

## Assistant <sup>2026/8/6 15:09:13</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        logger.error(\"[EC-WAIT-END] entry=%#x buf_ptrs=%s\",\n                     id(self), _buf_ptrs)\n\n        # Edge-cloud debug: comm finished, the hidden tensors received",
  "new_string": "        logger.error(\"[EC-WAIT-END] entry=%#x buf_ptrs=%s\",\n                     id(self), _buf_ptrs)\n        # [EC-B-PROBE] record the consumed tensors' storage on the COMPUTE\n        # (consume) stream == the model's read stream (wait_for_comm runs on\n        # the busy_loop thread). NON-syncing (allocator lifetime only). The\n        # record_stream in edge_cloud_irecv_tensor_dict is on the recv/producer\n        # stream, so the allocator may recycle the buffer once the irecv\n        # finishes -- before the model reads it on compute. If adding this\n        # makes the precision bug disappear, root cause = B. Revert if no effect.\n        try:\n            if hasattr(torch, \"npu\"):\n                _cs = torch.npu.current_stream()\n                for _t in self.tensors.values():\n                    if isinstance(_t, torch.Tensor) and _t.device.type == \"npu\":\n                        _t.record_stream(_cs)\n        except Exception:\n            pass\n\n        # Edge-cloud debug: comm finished, the hidden tensors received"
}
```

</details>


---

## User <sup>2026/8/6 15:09:14</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 15:09:25</sup>


---

## Assistant <sup>2026/8/6 15:09:27</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br && python -m py_compile vllm/vllm/v1/worker/gpu_worker.py 2>&1 && echo \"gpu_worker OK\" || echo \"FAIL\"; echo \"\"; echo \"=== audit EC-B-PROBE: no sync calls (record_stream only) ===\"; grep -nE \"EC-B-PROBE|record_stream\\(_cs\\)|aclrtSynchronize|\\.item\\(|synchronize\\(\" vllm/vllm/v1/worker/gpu_worker.py | head",
  "description": "Verify syntax and probe is non-sync"
}
```

</details>


---

## User <sup>2026/8/6 15:09:28</sup>

<details>
<summary>Tool Result</summary>

```
gpu_worker OK

=== audit EC-B-PROBE: no sync calls (record_stream only) ===
170:        # [EC-B-PROBE] record the consumed tensors' storage on the COMPUTE
182:                        _t.record_stream(_cs)
198:                # f"mean={t.mean().item():.6f} "
199:                # f"std={t.std(unbiased=False).item():.6f} "
200:                # f"min={t.min().item():.6f} max={t.max().item():.6f} "
201:                # f"abs_max={t.abs().max().item():.6f} "
202:                # f"has_nan={torch.isnan(t).any().item()} "
1258:            torch.accelerator.synchronize()
```

</details>


---

## Assistant <sup>2026/8/6 15:10:41</sup>


---

## Assistant <sup>2026/8/6 15:10:54</sup>

探针已加装并校验：仅 `record_stream`（分配器元数据），**无任何同步**；`.item()` 行仍是注释状态，1258 行的 `synchronize` 是文件里别处既有的、与本次无关。

## 结论先行：A、C 已排除，剩下 B

你的日志把另外两条都否掉了：
- **C 否决**：边侧、云侧 TP0 `nhandles=1`（handle 确实被 wait）；云侧非 TP0 `nhandles=0` 是**正常**的（它们走 TP broadcast，不跨节点 irecv）。
- **A 否决**：边云都没有 `MISMATCH=True`（`handle.wait()` 跑的流 == 模型消费的流）。

而 `.item()`（= `aclrtSynchronizeStream(compute)`，宿主阻塞计算流）仍必需 + 得分 70（偶发），逻辑上只剩 **B**：`handle.wait()` 只保证计算流等到“irecv[N] 完成”，**不阻止 irecv[N+1] 复用并覆写同一块缓冲**；现有 `record_stream` 记在 **recv/生产者流**（irecv 一完成分配器就认为可回收），早于模型在 compute 流上读完 → 偶发读到被覆写的数据。`.item()` 把计算流排空，让模型读抢在覆写前完成，所以能修。

## 已加的非同步确认探针 `[EC-B-PROBE]`

在 [gpu_worker.py wait_for_comm](vllm/vllm/v1/worker/gpu_worker.py#L169) 末尾（`_comm_waited=True` 之后，busy_loop 线程 = 模型读流）补了一行：把消费 tensor 的 storage 也 `record_stream` 到 **compute（消费）流**。`record_stream` 是纯分配器元数据、**不是同步**，所以如果 bug 消失，原因是“缓冲寿命被延长到模型读完之后”，而非“加了同步把竞态掩盖”→ 干净地坐实 B。

## 怎么跑、怎么判读

1. 确保 `gpu_worker.py` 的 **141–147 行 `.item()` 仍注释着**（让 bug 处于可复现状态，探针成为唯一变量）。`[EC-*]` 日志可留着（非同步，不影响判读）。
2. 跑 GSM8K：
   - **得分 → 98**：**B 确认**。根因 = recv 缓冲在模型读取前被分配器回收覆写（`record_stream` 只记了 recv/生产者流，没记 compute/消费流）。这个探针就是修复，保留即可（建议再把 [EC-*] 日志清掉）。
   - **得分仍 ~70**：B 否决 → 那就是 HCCL 的 `handle.wait()` 的 `hcclEndEvent.block(compute)` 在该版本上**不能可靠建立 recv→compute 的数据可见性**，必须真同步。届时把探针 revert，改用：irecv 后在 recv 流 `record` 一个 event，`wait_for_comm` 里 `current_stream().wait_event(evt)` 建真依赖（非宿主阻塞，保 overlap）；若该机制也不够，则只能上针对性的 `current_stream().synchronize()`。

把跑分结果告诉我，我据此给最终修复补丁（B 的话基本就是这个探针清理版；HCCL 可见性问题的话给 event 方案）。


---

## User <sup>2026/8/6 15:33:11</sup>

得分仍 ~70，改用：irecv 后在 recv 流 record 一个 event，wait_for_comm 里 current_stream().wait_event(evt) 建真依赖


---

## Assistant <sup>2026/8/6 15:35:31</sup>


---

## Assistant <sup>2026/8/6 15:35:33</sup>

探测结果排除了 B（计算流上的 `record_stream` 没有改变任何东西 -> 不是缓冲区生命周期/覆盖问题）。因此，根本原因在于 `handle.wait()` 的流侧 `hcclEndEvent.block(compute)` 无法可靠地使 irecv 数据对计算流可见；只有真正的同步（`.item()` = `aclrtSynchronizeStream`）才能做到。

在我实现基于事件的方法之前，我必须确认一个关键细节：**irecv 实际上是在 `_HC_STREAM_RECV` 上运行，还是在 HCCL 内部的专用流上运行？** 这决定了在 recv 流上记录的事件是否能真正捕获 irecv 的完成状态。让我检查一下 HCCL 代码。


---

## Assistant <sup>2026/8/6 15:35:35</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp; echo \"=== hcclStream: dedicated or user current stream? ===\" && grep -nE \"hcclStream\\s*=|getHCCLStream|GetHcclStream|NPUStream.*hccl|usedStream_|auto.*[Ss]tream\\s*=|getCurrentNPUStream|c10_npu::getCurrentNPUStream\" \"$TN\" 2>/dev/null | head -30",
  "description": "Determine if HCCL uses dedicated or user stream"
}
```

</details>


---

## User <sup>2026/8/6 15:35:46</sup>

<details>
<summary>Tool Result</summary>

```
=== hcclStream: dedicated or user current stream? ===
106:    auto current_Stream = c10_npu::getCurrentNPUStream(device);
261:    std::vector<c10_npu::NPUStream>& hcclStreams)
264:        c10_npu::NPUStream& hcclStream = hcclStreams[i];
266:        hcclEvent.record(c10_npu::getCurrentNPUStream(devices[i].index()));
999:        auto currentStream = c10_npu::getCurrentNPUStream(devices_[i].index());
1393:    std::vector<c10_npu::NPUStream> hcclStreamsToSync;
2661:    auto stream = getHcclStreamByBufferName(bufferName, device.index());
2667:    auto newStream = getNPUStreamByCurrentType(device.index());
3055:    auto hcclStream = hcclStreams_[key][0];
3991:        auto npu_stream = c10_npu::getCurrentNPUStream();
4004:            c10_npu::NPUStream& hcclStream = hcclStreams[i];
4016:            c10_npu::NPUStreamGuard guard(hcclStreams[i]);
4075:        c10_npu::NPUStream& hcclStream = hcclStreams[i];
4119:            c10_npu::NPUStream& hcclStream = hcclStreams[i];
4144:        c10_npu::
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 15:39:43</sup>


---

## Assistant <sup>2026/8/6 15:39:46</sup>

有一个关键的流细节需要解决。HCCL 使用一个 **专用的 `hcclStreams_`** 来执行实际的 irecv（第 4016/4144 行：op + end-event 在 `hcclStream` 上，而不是用户的 `recv_stream` 上）；用户的 `recv_stream` 仅通过 `hcclEvent.record(currentStream); hcclEvent.block(hcclStream)`（第 266-267 行）进行桥接，从而使 hcclStream 等待用户流。因此，`recv_stream` 上的事件可能无法捕获 irecv 的完成——我需要检查是否存在反向桥接（hcclStream → 用户流）。让我查看一下启动/结束事件的相关代码。


---

## Assistant <sup>2026/8/6 15:39:46</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\cann\\torch_npu\\pytorch\\torch_npu\\csrc\\distributed\\ProcessGroupHCCL.cpp",
  "limit": 60,
  "offset": 4100
}
```

</details>


---

## User <sup>2026/8/6 15:39:46</sup>

<details>
<summary>Tool Result</summary>

```
4100	        } else {
4101	            c10_npu::NPUCachingAllocator::recordStream(inputs[i].storage().data_ptr(), hcclStream);
4102	            if (multi_stream_memory_reuse_mode == c10_npu::option::ERASE_RECORD_STREAM ||
4103	                multi_stream_memory_reuse_mode == c10_npu::option::ERASE_RECORD_STREAM_WITH_OPTIMIZE) {
4104	                work->recorded_inputs_.push_back(std::make_pair(inputs[i].storage().getWeakStorageImpl(), hcclStream));
4105	                if (multi_stream_memory_reuse_mode == c10_npu::option::ERASE_RECORD_STREAM_WITH_OPTIMIZE) {
4106	                    auto block_ptr = c10_npu::NPUCachingAllocator::getBlockPtr(inputs[i].storage().data_ptr());
4107	                    work->recorded_block_ptr_for_inputs_.push_back(block_ptr);
4108	                    c10_npu::NPUCachingAllocator::recordHcclWorkForBlock(block_ptr, static_cast<void*>(work.get()));
4109	                }
4110	            }
4111	        }
4112	    }
4113	
4114	    {
4115	        for (const
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 15:41:01</sup>


---

## Assistant <sup>2026/8/6 15:41:03</sup>

启动确认：irecv 操作及其结束事件在 **专用 `hcclStream`** 上运行（第 4125、4145 行），并且 **没有自动的结束桥接回用户流** —— `handle.wait()` 是*唯一*连接计算流与 hcclStream 的东西（通过 `hcclEndEvent.block(compute)`）。因此，在 `recv_stream` 上记录的事件**无法**捕获 irecv 的完成状态。让我验证一下 `NPUEvent::block`（`handle.wait` 的实现）与 `NPUStream::wait_event` 是否使用了相同的底层原语——这决定了手动事件是否可能与 `handle.wait` 有所不同。


---

## Assistant <sup>2026/8/6 15:41:05</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch; echo \"=== NPUEvent::block impl ===\" && grep -rnE \"::block\\(|void block|wait_event|aclrtStreamWaitEvent|WaitEvent\" \"$TN/torch_npu/csrc/core/npu/\" 2>/dev/null | grep -iE \"block|wait_event|aclrtStreamWaitEvent\" | head -20",
  "description": "Compare NPUEvent::block vs wait_event primitives"
}
```

</details>


---

## User <sup>2026/8/6 15:41:06</sup>

<details>
<summary>Tool Result</summary>

```
=== NPUEvent::block impl ===
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/CachingHostAllocator.cpp:675:    void block_free(ExpandableBlock *block)
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/impl/NPUGuardImpl.cpp:169:void NPUGuardImpl::block(void *event, const c10::Stream &stream) const
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/impl/NPUGuardImpl.cpp:184:    ASCEND_LOGI("Event: aclrtStreamWaitEvent is successfully executed, stream=%p, event=%p",
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/impl/NPUGuardImpl.h:53:    void block(void *event, const c10::Stream &stream) const override;
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/interface/AsyncTaskQueueInterface.cpp:25:    { WAIT_EVENT, "wait_event" },
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/interface/AsyncTaskQueueInterface.cpp:28:    { WAIT_VALUE, "wait_event" },
/c/cann/torch_npu/pytorch/torch_npu/csrc/core/npu/interface/AsyncTaskQueueInterface.cpp:269:            NPU_CHECK_ERROR(aclrtStreamWaitEve
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 15:46:12</sup>


---

## Assistant <sup>2026/8/6 15:46:20</sup>

在实现之前，我需要指出 HCCL 源码中的一个关键发现，这改变了目前的计划。

## 关键发现：event 方案与 `handle.wait()` 是同一原语，且 irecv 不在 recv 流上

1. **irecv 跑在 HCCL 专用的 `hcclStream` 上，不是 `_HC_STREAM_RECV`**（[ProcessGroupHCCL.cpp:4125](cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp#L4125) `fn(..., hcclStream, ...)`，结束事件 [L4145](cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp#L4145) 也 record 在 `hcclStream`）。用户的 `recv_stream` 只做**起始**桥接（[L266-267](cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp#L266) `hcclStream` 等 `recv_stream`），**没有结束方向的桥接**。所以在 `recv_stream` 上 record 的 event **根本捕获不到 irecv 的完成**（它在 hcclStream 上）。

2. **`handle.wait()` 本身就是“compute ← hcclStream 的 event 依赖”**：[L1001](cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp#L1001) `hcclEndEvents_[i].block(currentStream)` → `NPUGuardImpl::block` → `aclrtStreamWaitEvent(compute, hcclEndEvent)`（[NPUGuardImpl.cpp:169-184](cann/torch_npu/pytorch/torch_npu/csrc/core/npu/impl/NPUGuardImpl.cpp#L169)）。而手动 `current_stream().wait_event(evt)` 用的也是 `aclrtStreamWaitEvent`（[AsyncTaskQueueInterface.cpp:269](cann/torch_npu/pytorch/torch_npu/csrc/core/npu/interface/AsyncTaskQueueInterface.cpp#L269)）。

**结论**：`handle.wait()` 已经在做“compute 等 hcclStream 上的 irecv 完成事件”，用的是 `aclrtStreamWaitEvent`；手动 event 用的是**同一个原语**。既然 `handle.wait()` 不够、只有 `aclrtSynchronizeStream`（即 `.item()`）才管用，那么 event 方案（同为 `aclrtStreamWaitEvent`）大概率**仍然 ~70**——而且 recv 流上的 event 还捕获不到 irecv，更没用。

这是 CANN/HCCL 的 `aclrtStreamWaitEvent` 在该版本上**不能可靠建立跨流数据可见性**的症结，只有真正的流同步能绕过。

鉴于此，我想确认一下怎么推进：


---

## Assistant <sup>2026/8/6 15:46:24</sup>

<details>
<summary>Tool: <code>AskUserQuestion</code></summary>

```json
{
  "questions": [
    {
      "header": "修复路线",
      "multiSelect": false,
      "options": [
        {
          "description": "在 wait_for_comm 里 current_stream().synchronize()。与你已验证的 .item() 等价(都是 aclrtSynchronizeStream(compute))，得分应 98。代价：busy_loop 在此阻塞到计算流排空(与 .item() 相同的 overlap 损失)。可靠。",
          "label": "真同步(current_stream().synchronize())"
        },
        {
          "description": "按你说的在 recv 流 record event + wait_for_comm 里 wait_event。据上面分析我预期仍 ~70(同原语、且 recv 流捕获不到 irecv)，但可 empirically 验证我的判断。",
          "label": "仍按 event 方案实现"
        },
        {
          "description": "先实现 event 方案测一次;若仍 70,我再换成真同步。两次测试。",
          "label": "两者都试(先 event 再 sync)"
        }
      ],
      "question": "鉴于 event 方案用的是与 handle.wait() 相同的 aclrtStreamWaitEvent 原语(且 recv 流捕获不到 irecv),预期仍 ~70。如何推进修复?"
    }
  ]
}
```

</details>


---

## User <sup>2026/8/6 15:48:35</sup>

<details>
<summary>Tool Result</summary>

```
The user answered: "鉴于 event 方案用的是与 handle.wait() 相同的 aclrtStreamWaitEvent 原语(且 recv 流捕获不到 irecv),预期仍 ~70。如何推进修复?"="Other". Read the answers carefully — they may request clarification, changes, or that you not proceed — and follow what they actually say.
```

</details>


---

## User <sup>2026/8/6 15:48:37</sup>

[Request interrupted by user]


---

## User <sup>2026/8/6 15:49:16</sup>

参考C:\MindIE-LLM_master\MindIE-LLM\examples\atb_models\atb_llm\utils\layerwise_disaggregated\edge_cloud_data_comm.py的471和476行分析一下


---

## Assistant <sup>2026/8/6 15:49:31</sup>


---

## Assistant <sup>2026/8/6 15:49:32</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\MindIE-LLM_master\\MindIE-LLM\\examples\\atb_models\\atb_llm\\utils\\layerwise_disaggregated\\edge_cloud_data_comm.py",
  "limit": 70,
  "offset": 430
}
```

</details>


---

## User <sup>2026/8/6 15:49:32</sup>

<details>
<summary>Tool Result</summary>

```
430	            return
431	            
432	        if self.rank == src_rank: # 对应的卡才进行收发
433	            if mode == 'p':
434	                if self.role == CLOUD and not self.set_prefill_device_done:
435	                    torch.npu.set_device(torch.device(f"npu:{self.npu_device_id}"))
436	                    self.set_prefill_device_done = True
437	                end_pos = start_position + shape[recv_index]
438	                self.target_p[recv_index] = self.out_hidden_p[recv_index][start_position: end_pos, :]
439	                with torch.npu.stream(self.streams[P_INDEX][recv_index][RECV_INDEX]):
440	                    ret = torch.distributed.irecv(
441	                        self.target_p[recv_index], 
442	                        src=self.maps_inter_send_recv[self.comm_group][P_INDEX][recv_index][peer_index], 
443	                        group=self.groups_inter_send_recv[self.comm_group][P_INDEX][recv_index])
444	                self.prefill_recv_ret_queue[recv_index].put(ret
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 15:52:05</sup>


---

## Assistant <sup>2026/8/6 15:52:08</sup>

这是关键参考。MindIE 的 `data_wait_after_recv` 执行了 **两个**步骤，而 vLLM 的 `wait_for_comm` 只执行了其中一个：

- 第 470/475 行：`handle.wait()`（HCCL 工作等待）
- **第 471/476 行：`torch.npu.default_stream().wait_stream(self.streams[...][RECV_INDEX])`** —— 使 **默认/计算流等待 recv 流**。

vLLM 的 `wait_for_comm` 执行了 `handle.wait()`，但 **缺少了 `wait_stream(recv_stream)`**。这就是与 MindIE 设计的差距。但在实现之前，我必须确认在 NPU 上 `wait_stream(recv_stream)` 是否真的能捕获 irecv（即 p2p irecv 是在用户的 recv 流上完成，还是在专用的 hcclStream 上完成，且没有反向桥接）。让我检查一下 HCCL 中的 p2p recv 路径。


---

## Assistant <sup>2026/8/6 15:52:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch/torch_npu/csrc/distributed/ProcessGroupHCCL.cpp; echo \"=== recv/send/PointToPoint methods ===\" && grep -nE \"::recv\\(|::send\\(|PointToSend|PointToRecv|pointToPoint|point_to_point|SendRecv|::sendrecv\" \"$TN\" 2>/dev/null | head -20; echo \"\"; echo \"=== context around 4585 (pointToPoint recordStream) ===\"; sed -n '4560,4600p' \"$TN\" 2>/dev/null | grep -nE \"stream|Stream|recordStream|fn\\(|hccl|getCurrent|guard\" | head -25",
  "description": "Locate p2p recv path and stream usage"
}
```

</details>


---

## User <sup>2026/8/6 15:53:47</sup>

<details>
<summary>Tool Result</summary>

```
=== recv/send/PointToPoint methods ===
237:std::string getKeySendRecv(int myRank, int peer)
1453:        p2pSendRecvKeys_.clear();
1487:    p2pSendRecvKeys_.clear();
1536:        p2pSendRecvKeys_.clear();
3013:        auto iter = p2pSendRecvKeys_.find(rank_);
3014:        if (iter == p2pSendRecvKeys_.end()) {
3015:            p2pSendRecvKeys_.emplace(rank_, std::vector<std::string>{devicesKey});
3037:        key = getKeySendRecv(rank_, peer);
3069:        key = getKeySendRecv(rank_, peer);
3479:        if (p2pSendRecvKeys_.find(rank_) != p2pSendRecvKeys_.end()) {
3480:            auto p2pKeys = p2pSendRecvKeys_[rank_];
3512:        bool isSendRecvSelf = rank_ == p2pPeer;
3513:        uint32_t p2pTargetRank = isSendRecvSelf ? 0 : 1 - p2pRank;
4385:c10::intrusive_ptr<c10d::Work> ProcessGroupHCCL::pointToPoint(
4407:    bool isSendRecvSelf = false;
4413:        key = getKeySendRecv(rank_, peer);
4415:        isSendRecvSelf = rank_ == peer;
4416:        p2pTargetRank = isSendRecvSelf ? 0 :
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 15:54:32</sup>


---

## Assistant <sup>2026/8/6 15:54:34</sup>

p2p `irecv` 也在专用的 `hcclStream` 上运行（第 4585 行，注释 4561-4564："在 worker 流上创建 tensor，在不同的 `hcclStreams` 上使用"）。所以现在关键问题是：NPU 的 `Stream.wait_stream()` 到底是怎么做的——它是和 `handle.wait` 一样的 `aclrtStreamWaitEvent`，还是更强的操作？这决定了复制 MindIE 的第 471/476 行代码是否能解决问题。


---

## Assistant <sup>2026/8/6 15:54:36</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TN=/c/cann/torch_npu/pytorch; echo \"=== NPUStream::wait_stream impl ===\" && grep -rnE \"wait_stream|WaitStream|aclrtStreamWaitEvent|aclrtSynchronizeStream\" \"$TN/torch_npu/csrc/core/npu/NPUStream.cpp\" \"$TN/torch_npu/csrc/core/npu/NPUStream.h\" 2>/dev/null | head -20; echo \"\"; echo \"=== NPUStream.cpp wait_stream body ===\"; f=\"$TN/torch_npu/csrc/core/npu/NPUStream.cpp\"; n=$(grep -n \"wait_stream\" \"$f\" 2>/dev/null | head -1 | cut -d: -f1); echo \"line $n:\"; sed -n \"$((n-1)),$((n+12))p\" \"$f\" 2>/dev/null",
  "description": "Inspect NPUStream::wait_stream implementation"
}
```

</details>


---

## User <sup>2026/8/6 15:54:43</sup>

<details>
<summary>Tool Result</summary>

```
Exit code 1
=== NPUStream::wait_stream impl ===

=== NPUStream.cpp wait_stream body ===
line :
```

</details>


---

## Assistant <sup>2026/8/6 15:54:49</sup>


---

## Assistant <sup>2026/8/6 15:54:49</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\cann\\torch_npu\\pytorch\\torch_npu\\npu\\streams.py",
  "limit": 30,
  "offset": 28
}
```

</details>


---

## User <sup>2026/8/6 15:54:49</sup>

<details>
<summary>Tool Result</summary>

```
28	    def wait_event(self, event):
29	        r"""Makes all future work submitted to the stream wait for an event.
30	
31	        Arguments:
32	            event (Event): an event to wait for.
33	
34	        .. note:: This is a wrapper around ``npuStreamWaitEvent()``
35	
36	           This function returns without waiting for :attr:`event`: only future
37	           operations are affected.
38	
39	        """
40	        event.wait(self)
41	
42	    def wait_stream(self, stream):
43	        r"""Synchronizes with another stream.
44	
45	        All future work submitted to this stream will wait until all kernels
46	        submitted to a given stream at the time of call complete.
47	
48	        Arguments:
49	            stream (Stream): a stream to synchronize.
50	
51	        .. note:: This function returns without waiting for currently enqueued
52	           kernels in :attr:`stream`: only future operations are affected.
53	        """
54	        self.wait_event(stream.record_event())
55
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 15:59:09</sup>


---

## Assistant <sup>2026/8/6 15:59:14</sup>

`wait_stream(s)` = `self.wait_event(s.record_event())` ([streams.py:54](cann/torch_npu/pytorch/torch_npu/npu/streams.py#L54)) = record an event on `s` + `aclrtStreamWaitEvent`. So MindIE 471/476 establishes **compute ← recv_stream** on top of `handle.wait()`'s compute ← hcclStream.

This is the gap: vLLM's `wait_for_comm` does only `handle.wait()`. The c19ac comment claimed to "mirror MindIE's [recv_stream, send_stream] pair" but vLLM implemented only the **stream split** (9772) + `handle.wait`—it **omitted MindIE's `wait_stream(recv_stream)`**. On CANN, irecv data visibility is tied to the recv (owner) stream; `handle.wait()`'s event lives on the internal hccl stream and apparently doesn't confer visibility to compute, whereas `wait_stream(recv_stream)` does. That fits: event-based, non-blocking, preserves overlap (unlike `synchronize`).

Let me find the return point of `edge_cloud_irecv_tensor_dict` to insert the `wait_stream` callback at the front of `postprocess` (so it runs right after `handle.wait`, before the buffer-reading TP-broadcast/split).


---

## Assistant <sup>2026/8/6 15:59:15</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== edge_cloud_irecv_tensor_dict return + postprocess refs ===\" && grep -nE \"return tensor_dict, handles, postprocess|return \\{|postprocess\\.append|postprocess\\.insert|^\\s*return \" vllm_ascend/distributed/parallel_state.py | awk -F: '$1>=1280 && $1<=1620' | head -20",
  "description": "Find return and postprocess appends in irecv fn"
}
```

</details>


---

## User <sup>2026/8/6 16:01:57</sup>

<details>
<summary>Tool Result</summary>

```
=== edge_cloud_irecv_tensor_dict return + postprocess refs ===
1282:    return "n/a"
1315:        return {}, [], []
1380:        postprocess.append(_split_into_dict)
1454:    return tensor_dict, handles, postprocess
1465:    return edge_cloud_isend_tensor_dict(
1484:    return edge_cloud_irecv_tensor_dict(
1500:    return edge_cloud_isend_tensor_dict_on_hidden_channel(
1516:        return pp_group.isend_tensor_dict_on_hidden_channel(
1521:    return pp_group.isend_tensor_dict(tensor_dict)
```

</details>


---

## Assistant <sup>2026/8/6 16:02:02</sup>


---

## Assistant <sup>2026/8/6 16:02:03</sup>

`edge_cloud_irecv_tensor_dict` 返回位于第 1454 行。我来读取其前面的区域，以便精确地插入 `wait_stream` 回调。


---

## Assistant <sup>2026/8/6 16:02:03</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 22,
  "offset": 1434
}
```

</details>


---

## User <sup>2026/8/6 16:02:03</sup>

<details>
<summary>Tool Result</summary>

```
1434	            # the real num_tokens rows; the remaining
1435	            # (recv_num_tokens - num_tokens) rows are padding to satisfy
1436	            # SP's TP-divisibility and must be zero, not torch.empty's
1437	            # uninitialized memory.  Garbage here is read by downstream
1438	            # ops that iterate over the full TP-padded buffer (SP
1439	            # all-gather inside attention, DSA compression, hc_head/norm)
1440	            # and probabilistically corrupts batched requests on 3D
1441	            # (DeepSeek V4) models.  Runs on the compute stream
1442	            # concurrent with the HCCL irecv (disjoint regions); the
1443	            # irecv handle wait plus the next HCCL op's compute->HCCL
1444	            # sync make it visible before any read.
1445	            if recv_num_tokens > num_tokens:
1446	                full_tensor[num_tokens:].zero_()
1447	        else:
1448	            # The sender skipped this tensor (e.g. the zero residual in
1449	       
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 16:02:49</sup>


---

## Assistant <sup>2026/8/6 16:02:50</sup>

现在我将在 `edge_cloud_irecv_tensor_dict` 中实现 MindIE 的 `wait_stream(recv_stream)`，并将其插入到 `postprocess` 的最前面，使其在 `handle.wait()` 之后、任何读取缓冲区的后处理（TP broadcast/split）之前运行。并回退失败的 `EC-B-PROBE` 以便隔离此更改。


---

## Assistant <sup>2026/8/6 16:02:53</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "        tensor_dict[key] = full_tensor\n\n    return tensor_dict, handles, postprocess",
  "new_string": "        tensor_dict[key] = full_tensor\n\n    if channel is not None:\n        # Mirror MindIE edge_cloud_data_comm.py:471/476: in addition to the\n        # HCCL handle.wait() that AsyncIntermediateTensors.wait_for_comm()\n        # runs (compute <- internal hccl stream), also make the compute\n        # (current) stream wait for the dedicated recv stream. On CANN the\n        # irecv data visibility is owned by the recv stream; handle.wait()\n        # alone (event on the internal hccl stream) does not make the received\n        # hidden states visible to compute -> intermittent stale reads.\n        # Inserted at index 0 so it runs right after handle.wait(), before any\n        # buffer-reading postprocess (TP broadcast / split). Non-blocking\n        # stream-side wait -> preserves CHER overlap.\n        _recv_stream = _get_hidden_channel_stream(channel, _HC_STREAM_RECV)\n\n        def _wait_recv_stream(_rs=_recv_stream) -> None:\n            torch.npu.current_stream().wait_stream(_rs)\n\n        postprocess.insert(0, _wait_recv_stream)\n\n    return tensor_dict, handles, postprocess"
}
```

</details>


---

## User <sup>2026/8/6 16:02:54</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 16:02:55</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        logger.error(\"[EC-WAIT-END] entry=%#x buf_ptrs=%s\",\n                     id(self), _buf_ptrs)\n        # [EC-B-PROBE] record the consumed tensors' storage on the COMPUTE\n        # (consume) stream == the model's read stream (wait_for_comm runs on\n        # the busy_loop thread). NON-syncing (allocator lifetime only). The\n        # record_stream in edge_cloud_irecv_tensor_dict is on the recv/producer\n        # stream, so the allocator may recycle the buffer once the irecv\n        # finishes -- before the model reads it on compute. If adding this\n        # makes the precision bug disappear, root cause = B. Revert if no effect.\n        try:\n            if hasattr(torch, \"npu\"):\n                _cs = torch.npu.current_stream()\n                for _t in self.tensors.values():\n                    if isinstance(_t, torch.Tensor) and _t.device.type == \"npu\":\n                        _t.record_stream(_cs)\n        except Exception:\n            pass\n\n        # Edge-cloud debug: comm finished, the hidden tensors received",
  "new_string": "        logger.error(\"[EC-WAIT-END] entry=%#x buf_ptrs=%s\",\n                     id(self), _buf_ptrs)\n\n        # Edge-cloud debug: comm finished, the hidden tensors received"
}
```

</details>


---

## User <sup>2026/8/6 16:02:56</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 16:03:02</sup>


---

## Assistant <sup>2026/8/6 16:03:02</sup>

两个修改已应用。让我验证一下语法，并确认 `wait_stream` 是否为非同步/非阻塞的。


---

## Assistant <sup>2026/8/6 16:03:04</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br && python -m py_compile vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 && echo \"parallel_state OK\" || echo \"FAIL\"; python -m py_compile vllm/vllm/v1/worker/gpu_worker.py 2>&1 && echo \"gpu_worker OK\" || echo \"FAIL\"; echo \"\"; echo \"=== wait_stream insertion (non-blocking, no sync) ===\"; grep -nE \"_wait_recv_stream|wait_stream\\(_rs\\)|postprocess.insert\\(0\" vllm-ascend/vllm_ascend/distributed/parallel_state.py; echo \"\"; echo \"=== confirm EC-B-PROBE removed from gpu_worker ===\"; grep -c \"EC-B-PROBE\" vllm/vllm/v1/worker/gpu_worker.py",
  "description": "Syntax check and audit wait_stream"
}
```

</details>


---

## User <sup>2026/8/6 16:03:06</sup>

<details>
<summary>Tool Result</summary>

```
parallel_state OK
gpu_worker OK

=== wait_stream insertion (non-blocking, no sync) ===
1467:        def _wait_recv_stream(_rs=_recv_stream) -> None:
1468:            torch.npu.current_stream().wait_stream(_rs)
1470:        postprocess.insert(0, _wait_recv_stream)

=== confirm EC-B-PROBE removed from gpu_worker ===
0
```

</details>


---

## Assistant <sup>2026/8/6 16:04:59</sup>


---

## Assistant <sup>2026/8/6 16:05:11</sup>

完成。语法已校验；`wait_stream` 是非阻塞的流侧等待（无 `synchronize`/`.item`），已移除失败的 `EC-B-PROBE`。

## MindIE 471/476 分析结论

MindIE 的 `data_wait_after_recv` 在 `handle.wait()` 之后多做了一步：
```python
torch.npu.default_stream().wait_stream(self.streams[...][RECV_INDEX])   # 471 / 476
```
而 `wait_stream(s)` = `self.wait_event(s.record_event())`（[streams.py:54](cann/torch_npu/pytorch/torch_npu/npu/streams.py#L54)）= 在 recv 流上 record 事件 + `aclrtStreamWaitEvent`，即建立 **compute ← recv_stream** 依赖。

vLLM 的 `wait_for_comm` 只做了 `handle.wait()`（compute ← 内部 hccl 流），**漏掉了 MindIE 这步 `wait_stream(recv_stream)`**。c19ac 注释说“mirror MindIE's [recv_stream, send_stream] pair”，但实际只实现了流拆分（9772）+ `handle.wait`，把 MindIE 的 `wait_stream` 同步步漏了。

机制：在 CANN 上，irecv 数据的可见性归属于 **recv（owner）流**；`handle.wait()` 的事件在内部 hccl 流上，不能把数据可见性传递给 compute -> 偶发读到旧 hidden -> 掉分。`wait_stream(recv_stream)` 让 compute 等 recv 流，才把可见性建立起来。这正好是事件依赖、非阻塞、保住 CHER overlap（不像 `synchronize` 会阻塞宿主）。

## 已实现的修复

在 [edge_cloud_irecv_tensor_dict](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1454) 返回前，`postprocess.insert(0, _wait_recv_stream)`：
```python
_recv_stream = _get_hidden_channel_stream(channel, _HC_STREAM_RECV)
def _wait_recv_stream(_rs=_recv_stream):
    torch.npu.current_stream().wait_stream(_rs)
postprocess.insert(0, _wait_recv_stream)
```
- 它在 `wait_for_comm` 里、`handle.wait()` **之后**、TP broadcast/split（读缓冲）**之前**执行（insert 到 index 0）。
- `current_stream()` 此时是 busy_loop 的 compute 流 -> `compute.wait_stream(recv_stream)`，等价于 MindIE 471/476。
- `channel is None` 的 legacy 路径不加；非 TP0 走 broadcast、无 recv 流，也不加。
- 已 revert 掉无效的 `EC-B-PROBE`（compute 流 record_stream），让本次只有 `wait_stream` 一个变量。

## 怎么验证

1. 确保 `gpu_worker.py` 的 **141–147 `.item()` 仍注释**（保持 bug 可复现，`wait_stream` 为唯一变量）。`[EC-*]` 日志留着（非同步，与之前 70 的基线同条件）。
2. 跑 GSM8K（200 请求）：
   - **得分 -> 98**：根因确认 = 漏了 MindIE 的 `wait_stream(recv_stream)`（CANN 上 recv 流才持有 irecv 数据可见性）。这就是正解，保留；之后可清掉 `[EC-*]` 日志。
   - **仍 ~70**：说明连 `wait_stream`（同为 `aclrtStreamWaitEvent`）也不够，即 CANN 的 `aclrtStreamWaitEvent` 本身在该版本不可靠，只有 `aclrtSynchronizeStream` 管用 -> 那时再上 `current_stream().synchronize()`（或升级 CANN）。

把跑分结果给我；若到 98，我把 `[EC-*]` 诊断日志清理掉收尾。


---

## User <sup>2026/8/6 16:32:54</sup>

精度依然存在问题，在_wait_recv_stream增加stream的error级日志打印


---

## Assistant <sup>2026/8/6 16:33:59</sup>


---

## Assistant <sup>2026/8/6 16:34:01</sup>

`wait_stream`（同样基于 `aclrtStreamWaitEvent`）也未能解决问题——这证实了 `aclrtStreamWaitEvent` 在此 CANN 上是不可靠的。但首先，让我添加你要求的流日志：它将准确显示 `wait_stream` 是否真的被执行了，以及 `recv stream` 是否与 `compute stream` 不同（如果它们相同，`wait_stream` 就是空操作）。这仅用于观测——不涉及同步。


---

## Assistant <sup>2026/8/6 16:34:02</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "        def _wait_recv_stream(_rs=_recv_stream) -> None:\n            torch.npu.current_stream().wait_stream(_rs)",
  "new_string": "        def _wait_recv_stream(_rs=_recv_stream, _ch=channel) -> None:\n            _cur = torch.npu.current_stream()\n            logger.error(\n                \"[EC-WAITSTREAM] channel=%s recv_stream=0x%x cur_stream=0x%x \"\n                \"same=%s thread=%s(%s)\",\n                _ch, _rs.npu_stream, _cur.npu_stream,\n                _rs.npu_stream == _cur.npu_stream, threading.get_ident(),\n                threading.current_thread().name,\n            )\n            _cur.wait_stream(_rs)"
}
```

</details>


---

## User <sup>2026/8/6 16:34:03</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 16:34:55</sup>


---

## Assistant <sup>2026/8/6 16:34:55</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "python -m py_compile vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 && echo \"parallel_state OK\" || echo \"FAIL\"; echo \"\"; echo \"=== EC-WAITSTREAM log (non-sync: only npu_stream ptr + == + thread) ===\"; grep -nE \"EC-WAITSTREAM|npu_stream|wait_stream\\(_rs\\)\" vllm-ascend/vllm_ascend/distributed/parallel_state.py | head",
  "description": "Verify syntax and non-sync log"
}
```

</details>


---

## User <sup>2026/8/6 16:34:57</sup>

<details>
<summary>Tool Result</summary>

```
parallel_state OK

=== EC-WAITSTREAM log (non-sync: only npu_stream ptr + == + thread) ===
1437:                "[EC-WAITSTREAM] channel=%s recv_stream=0x%x cur_stream=0x%x "
1439:                _ch, _rs.npu_stream, _cur.npu_stream,
1440:                _rs.npu_stream == _cur.npu_stream, threading.get_ident(),
1443:            _cur.wait_stream(_rs)
```

</details>


---

## Assistant <sup>2026/8/6 16:35:15</sup>


---

## Assistant <sup>2026/8/6 16:35:23</sup>

已加好，语法通过，日志**非同步**（只读 `npu_stream` 指针 + `==` 比较 + 线程号，不碰 `.item()`/`synchronize`），bug 仍会复现。

## 这个日志能判定什么

`[EC-WAITSTREAM]` 在 `wait_for_comm` 的 postprocess 里（`handle.wait()` 之后、broadcast/split 之前）触发，busy_loop 线程。字段含义：
- `recv_stream` = 专用 `_HC_STREAM_RECV`（irecv 提交流）；
- `cur_stream` = 当前 compute 流；
- `same` = 两者是否相等；
- `thread` = 触发线程。

跑完（保持 141–147 注释），对照三种结果：

1. **完全没有 `[EC-WAITSTREAM]`** → `_wait_recv_stream` 根本没执行（postprocess 没跑到），说明 `wait_stream` 这步压根没发生。
2. **`same=True`**（recv_stream == cur_stream）→ `wait_stream` 是空操作（等自己），即“专用 recv 流”其实和 compute 流是同一条流，流没真正分开。
3. **`same=False` 且仍 ~70**（最可能）→ `wait_stream` 确实在跑、流也确实不同，但 `aclrtStreamWaitEvent` 在该 CANN 上**不能建立跨流数据可见性**。

注意：`handle.wait()` 和 `wait_stream` 用的都是 `aclrtStreamWaitEvent` 这个原语，两者都没修好，已经强烈指向**第 3 种**--即该 CANN 版本的 `aclrtStreamWaitEvent` 不可靠，只有 `aclrtSynchronizeStream`（`.item()` 验证过）才管用。

把 `[EC-WAITSTREAM]` 的几行样例（特别是 `same=` 值）贴回来。若确认是第 3 种，下一步就是把 `_wait_recv_stream` 里的 `_cur.wait_stream(_rs)` 换成 `_cur.synchronize()`（等价于你已验证的 `.item()`，但显式、不依赖 debug 日志）；若 `same=True`，那要先查为什么 recv 流没和 compute 流分开。


---

## User <sup>2026/8/6 17:02:20</sup>

不能建立跨流数据可见性 如何确认呢


---

## Assistant <sup>2026/8/6 17:08:41</sup>


---

## Assistant <sup>2026/8/6 17:08:46</sup>

问得好——由于 `handle.wait()` 和 `wait_stream` 使用了相同的 `aclrtStreamWaitEvent` 原语，且都失败了，而 `.item()` (`aclrtSynchronizeStream`) 却成功了，确认工作需要 **直接探测计算流（compute stream）实际看到的内容**，即在流侧等待（stream-side waits）之后立即查看，还是在真正的同步（true sync）之后查看。让我添加一个 A/B 可见性探针。

设计（非掩码诊断）：在流侧等待（`handle.wait` + `wait_stream`）之后，在计算流上对收到的张量（received tensor）进行校验和（`ck_wait`）——这捕获了计算流在没有真正同步的情况下看到的内容。然后进行一次设备同步（device sync）并对同一个张量进行校验和（`ck_sync` = 保证有效）。比较两者。校验和在同步之前排队，因此它捕获的是同步前的可见性；同步仅用于读取该值并获取有效的参考值。


---

## Assistant <sup>2026/8/6 17:08:47</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "    try:\n        if hasattr(torch, \"npu\"):\n            return f\"0x{torch.npu.current_stream().npu_stream:x}\"\n    except Exception:\n        pass\n    return \"n/a\"",
  "new_string": "    try:\n        if hasattr(torch, \"npu\"):\n            return f\"0x{torch.npu.current_stream().npu_stream:x}\"\n    except Exception:\n        pass\n    return \"n/a\"\n\n\n# Diagnostic counter for [EC-VISPROBE] -- caps how many wait_for_comm calls are\n# probed (each probe adds a device sync, which masks the model read).\n_EC_VISPROBE_N = [0]"
}
```

</details>


---

## User <sup>2026/8/6 17:08:47</sup>

<details>
<summary>Tool Result</summary>

```
<tool_use_error>String to replace not found in file.
String:     try:
        if hasattr(torch, "npu"):
            return f"0x{torch.npu.current_stream().npu_stream:x}"
    except Exception:
        pass
    return "n/a"</tool_use_error>
```

</details>


---

## Assistant <sup>2026/8/6 17:08:52</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        logger.error(\"[EC-WAIT-END] entry=%#x buf_ptrs=%s\",\n                     id(self), _buf_ptrs)\n\n        # Edge-cloud debug: comm finished, the hidden tensors received",
  "new_string": "        logger.error(\"[EC-WAIT-END] entry=%#x buf_ptrs=%s\",\n                     id(self), _buf_ptrs)\n        # [EC-VISPROBE] Confirm whether the stream-side waits (handle.wait +\n        # wait_stream, both aclrtStreamWaitEvent) make the irecv data visible to\n        # the compute stream, or whether a true sync is required. Compares\n        # compute's view right after the stream-side waits (ck_wait) vs after a\n        # full device sync (ck_sync, guaranteed valid). WARNING: this probe\n        # ADDS syncs -> it masks the model read (score will look ~98 on probed\n        # iters); read the `match=` field, NOT the score.\n        #   match=False => stream-side waits do NOT establish cross-stream\n        #                  visibility (confirms the CANN aclrtStreamWaitEvent\n        #                  quirk; fix = true sync / event on the right stream).\n        #   match=True  => visibility is fine; the bug is a host-side race, not\n        #                  a stream-visibility problem.\n        _n = _EC_VISPROBE_N[0]\n        _EC_VISPROBE_N[0] += 1\n        if _n < 200:\n            try:\n                _t = None\n                for _v in self.tensors.values():\n                    if isinstance(_v, torch.Tensor) and _v.numel() > 0:\n                        _t = _v\n                        break\n                if _t is not None:\n                    _ck_wait = _t.float().sum()\n                    torch.npu.synchronize()\n                    _ck_sync = _t.float().sum()\n                    _w = _ck_wait.item()\n                    _s = _ck_sync.item()\n                    logger.error(\n                        \"[EC-VISPROBE] n=%d 
...(truncated)
```

</details>


---

## User <sup>2026/8/6 17:08:52</sup>

<details>
<summary>Tool Result</summary>

```
<tool_use_error>String to replace not found in file.
String:         logger.error("[EC-WAIT-END] entry=%#x buf_ptrs=%s",
                     id(self), _buf_ptrs)

        # Edge-cloud debug: comm finished, the hidden tensors received</tool_use_error>
```

</details>


---

## Assistant <sup>2026/8/6 17:08:58</sup>


---

## Assistant <sup>2026/8/6 17:08:59</sup>

让我重新阅读一下 `gpu_worker.py` 中的当前确切文本——文件状态与我预想的不符。


---

## Assistant <sup>2026/8/6 17:09:00</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -nE \"_ec_stream_id|return \\\"n/a\\\"|EC-WAIT-END|Edge-cloud debug: comm finished|_buf_ptrs\" vllm/vllm/v1/worker/gpu_worker.py | head -20",
  "description": "Locate helper and wait_for_comm regions"
}
```

</details>


---

## User <sup>2026/8/6 17:09:05</sup>

<details>
<summary>Tool Result</summary>

```
129:        # Edge-cloud debug: comm finished, the hidden tensors received
```

</details>


---

## Assistant <sup>2026/8/6 17:09:13</sup>


---

## Assistant <sup>2026/8/6 17:09:14</sup>

只匹配到了第 129 行 —— 看起来 `gpu_worker.py` 已经被还原了（我的 `[EC-*]` 诊断编辑不见了）。在添加探针之前，让我先确认一下当前的状态。


---

## Assistant <sup>2026/8/6 17:09:14</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 60,
  "offset": 95
}
```

</details>


---

## User <sup>2026/8/6 17:09:15</sup>

<details>
<summary>Tool Result</summary>

```
95	if TYPE_CHECKING:
96	    from vllm.model_executor.model_loader.tensorizer import TensorizerConfig
97	    from vllm.v1.worker.gpu_model_runner import GPUModelRunner
98	
99	
100	class AsyncIntermediateTensors(IntermediateTensors):
101	    """IntermediateTensors with lazy comm synchronization"""
102	
103	    def __init__(
104	        self,
105	        tensors: dict[str, torch.Tensor],
106	        comm_handles: list[Handle] | None = None,
107	        comm_postprocess: list[Callable[[], None]] | None = None,
108	        batch_type: Any = None,
109	        req_ids: list[str] | None = None,
110	    ) -> None:
111	        super().__init__(tensors)
112	        self._comm_handles = comm_handles
113	        self._comm_postprocess = comm_postprocess
114	        self._comm_waited = False
115	        self._batch_type = batch_type
116	        self._req_ids = req_ids
117	
118	    def wait_for_comm(self) -> None:
119	        if self._comm_waited:
120	            return
121	        if self._comm_hand
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 17:09:44</sup>


---

## Assistant <sup>2026/8/6 17:09:45</sup>

`gpu_worker.py` 已恢复到原始状态（我的 EC 诊断信息已被移除）。`parallel_state.py` 中仍然包含 `_wait_recv_stream` (wait_stream) 的修复。我将在（原始的）`wait_for_comm` 中添加 A/B 可见性探针。让我确认一下确切的计数器插入点。


---

## Assistant <sup>2026/8/6 17:09:45</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 5,
  "offset": 78
}
```

</details>


---

## User <sup>2026/8/6 17:09:45</sup>

<details>
<summary>Tool Result</summary>

```
78	
79	logger = init_logger(__name__)
80	
81	# Debug: edge-cloud hidden-recv info is appended to this file (same file
82	# used by gpu_model_runner's per-request sample prints).
```

</details>


---

## Assistant <sup>2026/8/6 17:09:53</sup>


---

## Assistant <sup>2026/8/6 17:09:53</sup>

现在我将把 A/B probe 添加到原始的 `wait_for_comm` 中。


---

## Assistant <sup>2026/8/6 17:09:55</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "logger = init_logger(__name__)\n\n# Debug: edge-cloud hidden-recv info is appended to this file (same file",
  "new_string": "logger = init_logger(__name__)\n\n\n# Diagnostic counter for [EC-VISPROBE] -- caps how many wait_for_comm calls are\n# probed (each probe adds a device sync, which masks the model read).\n_EC_VISPROBE_N = [0]\n\n# Debug: edge-cloud hidden-recv info is appended to this file (same file"
}
```

</details>


---

## User <sup>2026/8/6 17:09:56</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 17:09:59</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        self._comm_waited = True\n\n        # Edge-cloud debug: comm finished, the hidden tensors received",
  "new_string": "        self._comm_waited = True\n        # [EC-VISPROBE] Confirm whether the stream-side waits (handle.wait +\n        # wait_stream, both aclrtStreamWaitEvent) make the irecv data visible to\n        # the compute stream, or whether a true sync is required. Compares\n        # compute's view right after the stream-side waits (ck_wait) vs after a\n        # full device sync (ck_sync, guaranteed valid). WARNING: this probe\n        # ADDS syncs -> it masks the model read (score ~98 on probed iters);\n        # read `match=`, NOT the score.\n        #   match=False => stream-side waits do NOT establish cross-stream\n        #                  visibility (CANN aclrtStreamWaitEvent quirk).\n        #   match=True  => visibility is fine; bug is a host-side race.\n        _n = _EC_VISPROBE_N[0]\n        _EC_VISPROBE_N[0] += 1\n        if _n < 200:\n            try:\n                _t = None\n                for _v in self.tensors.values():\n                    if isinstance(_v, torch.Tensor) and _v.numel() > 0:\n                        _t = _v\n                        break\n                if _t is not None:\n                    _ck_wait = _t.float().sum()\n                    torch.npu.synchronize()\n                    _ck_sync = _t.float().sum()\n                    _w = _ck_wait.item()\n                    _s = _ck_sync.item()\n                    logger.error(\n                        \"[EC-VISPROBE] n=%d ck_wait=%s ck_sync=%s match=%s\",\n                        _n, _w, _s, bool(_w == _s))\n            except Exception as e:  # noqa: BLE001\n                logger.error(\"[EC-VISPROBE] n=%d err=%s\", _n, e)\n\n        # Edge-cloud debug: comm finished, the hidden tensors received"
}
```

</details>


---

## User <sup>2026/8/6 17:10:00</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 17:11:17</sup>


---

## Assistant <sup>2026/8/6 17:11:19</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "python -m py_compile vllm/vllm/v1/worker/gpu_worker.py 2>&1 && echo \"gpu_worker OK\" || echo \"FAIL\"; echo \"\"; echo \"=== EC-VISPROBE present ===\"; grep -nE \"EC-VISPROBE|_EC_VISPROBE_N\" vllm/vllm/v1/worker/gpu_worker.py | head",
  "description": "Verify syntax and probe presence"
}
```

</details>


---

## User <sup>2026/8/6 17:11:20</sup>

<details>
<summary>Tool Result</summary>

```
gpu_worker OK

=== EC-VISPROBE present ===
82:# Diagnostic counter for [EC-VISPROBE] -- caps how many wait_for_comm calls are
84:_EC_VISPROBE_N = [0]
133:        # [EC-VISPROBE] Confirm whether the stream-side waits (handle.wait +
143:        _n = _EC_VISPROBE_N[0]
144:        _EC_VISPROBE_N[0] += 1
159:                        "[EC-VISPROBE] n=%d ck_wait=%s ck_sync=%s match=%s",
162:                logger.error("[EC-VISPROBE] n=%d err=%s", _n, e)
```

</details>


---

## Assistant <sup>2026/8/6 17:11:56</sup>


---

## Assistant <sup>2026/8/6 17:12:07</sup>

语法通过，探针已就位。

## 这个探针如何确认“跨流可见性是否建立”

`[EC-VISPROBE]` 在 `wait_for_comm` 里、**流侧等待（`handle.wait` + `wait_stream`）都跑完之后**做一次 A/B：

```python
_ck_wait = _t.float().sum()      # 计算流在“仅靠流侧等待”下看到的值（此时还没任何真同步）
torch.npu.synchronize()           # 整机同步：irecv 必定完成 + 可见
_ck_sync = _t.float().sum()       # 真同步后计算流看到的值（保真基准）
# 比较 ck_wait vs ck_sync
```

关键点：`ck_wait` 是**在真同步之前**就排到计算流上的，它捕获的是“流侧等待能不能让计算流看到 irecv 数据”。后面的 `synchronize`/`.item()` 只是为了把这个值读回宿主、并拿到保真基准，**不会改变 `ck_wait` 已经算出的结果**。所以它不会把结论“修没”。

## 判读（看 `match=`，不要看分数）

- **`match=False`（ck_wait ≠ ck_sync）**：计算流在仅靠 `aclrtStreamWaitEvent`（`handle.wait`/`wait_stream`）时读到了与真同步后不同的（旧/未完成）数据 -> **确认“流侧等待不能建立跨流可见性”**，即 CANN 的 `aclrtStreamWaitEvent` 在该版本不可靠，只有 `synchronize` 管用。
- **`match=True`（全部相等）**：流侧等待其实已经让数据可见了 -> 可见性没问题，bug 是**宿主侧竞态**（`.item()` 是靠阻塞宿主修好的，不是靠可见性）。方向就要转去查宿主竞态（如下一轮 irecv/entry 生命周期时序）。

## 注意

- 探针**带了同步**（`synchronize`+`.item`），会**掩盖模型读取** -> 跑分这次会偏 ~98（或前 200 个 recv 被掩盖）。**只看 `[EC-VISPROBE] match=`，不要用分数判断**。已限前 200 个 recv。
- 保持 `gpu_worker.py` 的 141–147 `.item()` 注释状态（探针自己会同步，不需要那段）。
- 边云两侧都会打（各自进程 n=0..199），都看。

跑完把几行 `[EC-VISPROBE]`（尤其有没有 `match=False`）贴回来：
- 有 `match=False` -> 坐实可见性问题，下一步把 `_wait_recv_stream` 里的 `wait_stream` 换成 `current_stream().synchronize()`（等价你已验证的 `.item()`）作为正式修复；
- 全 `match=True` -> 转查宿主竞态，我再给对应的确认探针。

确认完记得把这个 `[EC-VISPROBE]` 探针删掉。


---

## User <sup>2026/8/6 17:59:16</sup>

这一步修改会导致挂死，日志和挂死信息C:\v0.23.0_lwd_acc_test_br\0806_1.txt


---

## Assistant <sup>2026/8/6 17:59:38</sup>


---

## Assistant <sup>2026/8/6 17:59:38</sup>

我来读取一下挂死日志，以了解发生了什么。


---

## Assistant <sup>2026/8/6 17:59:38</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\0806_1.txt"
}
```

</details>


---

## User <sup>2026/8/6 17:59:38</sup>

<details>
<summary>Tool Result</summary>

```
1	1、边侧日志
2	(Worker_PP0 pid=89129) ERROR 08-06 09:28:26 [parallel_state.py:1436] [EC-WAITSTREAM] channel=HiddenChannelType.PREFILL_1 recv_stream=0xfffe9d22e000 cur_stream=0xfffe9bcef000 same=False thread=281473001472032(MainThread)
3	(Worker_PP0 pid=89129) ERROR 08-06 09:28:26 [gpu_worker.py:158] [EC-VISPROBE] n=0 ck_wait=134812.984375 ck_sync=134812.984375 match=True
4	(Worker_PP0 pid=89129) ERROR 08-06 09:28:26 [parallel_state.py:1436] [EC-WAITSTREAM] channel=HiddenChannelType.DECODE recv_stream=0xfffe9d233000 cur_stream=0xfffe9bcef000 same=False thread=281473001472032(MainThread)
5	(Worker_PP0 pid=89129) ERROR 08-06 09:28:26 [gpu_worker.py:158] [EC-VISPROBE] n=1 ck_wait=-22.52099609375 ck_sync=-22.52099609375 match=True
6	(Worker_PP0 pid=89129) ERROR 08-06 09:28:26 [parallel_state.py:1436] [EC-WAITSTREAM] channel=HiddenChannelType.DECODE recv_stream=0xfffe9d233000 cur_stream=0xfffe9bcef000 same=False thread=281473001472032(MainThread)
7	(Worker_PP0 pid=89129) ERROR 08-06 09:28:26 [gp
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 18:04:29</sup>


---

## Assistant <sup>2026/8/6 18:04:37</sup>

这份日志信息量很大。有两个关键发现：

## 1. `match=True`（n=0..7）→ 可见性假设被推翻

每次 `[EC-VISPROBE]` 都显示 `ck_wait == ck_sync`（`match=True`）。`ck_wait` 是在 `handle.wait`+`wait_stream` 之后、真同步之前算的；它和真同步后的 `ck_sync` 完全一致。这说明 **流侧等待已经让 irecv 数据对计算流可见**——即“`aclrtStreamWaitEvent` 不能建立跨流可见性”的假设**被证伪**。recv 侧的可见性没问题。

（注意：`match=True` 只证明“计算流看到的数据稳定一致”，不证明数据“正确”——若数据在源头就被污染，`ck_wait` 和 `ck_sync` 会同为一个错误值，仍 `match=True`。所以这排除的是“recv 可见性竞态”，不是“数据正确性”。）

## 2. 挂死原因：探针用了整机同步

挂死栈：`wait_for_comm → synchronize → c10_npu::npuSynchronizeDevice → AclrtSynchronizeDeviceWithTimeout`（错误码 507011）。探针里的 `torch.npu.synchronize()` 是**整机同步**（`aclrtSynchronizeDevice`），它会等设备上**所有流**，包括还在飞的跨节点 HCCL `irecv`/`isend`——这些 op 依赖对端，而对端自己也卡在整机同步里（没 post 对应的 send/recv）→ 循环等待 → 超时挂死。

关键对比：你验证过能修精度的 `.item()`，其底层是 `aclrtSynchronizeStream`（[LocalScalarDenseNpu.cpp:23](cann/torch_npu/pytorch/torch_npu/csrc/aten/common/LocalScalarDenseNpu.cpp#L23)），**只同步计算流、不等整机**，所以不会挂死。探针错在用了整机同步。

## 结论与下一步

- recv 可见性是好的（`match=True`），`wait_stream`/`record_stream` 都没用、只有 `.item()`（计算流宿主阻塞）管用 → bug 是**宿主侧/流水线时序竞态**，不是流可见性问题。`.item()` 靠阻塞宿主（让计算流排空、串行化流水线）修好，不是靠可见性。
- 探针既已得出结论（`match=True`）又会挂死，应移除；正式修复用**计算流同步** `torch.npu.current_stream().synchronize()`（= `.item()` 的机制，非整机、不挂死）。

让我先移除会挂死的探针，并把修复改成计算流同步。先确认当前文本：


---

## Assistant <sup>2026/8/6 18:04:37</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 40,
  "offset": 127
}
```

</details>


---

## User <sup>2026/8/6 18:04:37</sup>

<details>
<summary>Tool Result</summary>

```
127	            for handle in self._comm_handles:
128	                handle.wait()
129	        if self._comm_postprocess:
130	            for fn in self._comm_postprocess:
131	                fn()
132	        self._comm_waited = True
133	        # [EC-VISPROBE] Confirm whether the stream-side waits (handle.wait +
134	        # wait_stream, both aclrtStreamWaitEvent) make the irecv data visible to
135	        # the compute stream, or whether a true sync is required. Compares
136	        # compute's view right after the stream-side waits (ck_wait) vs after a
137	        # full device sync (ck_sync, guaranteed valid). WARNING: this probe
138	        # ADDS syncs -> it masks the model read (score ~98 on probed iters);
139	        # read `match=`, NOT the score.
140	        #   match=False => stream-side waits do NOT establish cross-stream
141	        #                  visibility (CANN aclrtStreamWaitEvent quirk).
142	        #   match=True  => visibility is fine; bug is a host-side race.
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 18:05:09</sup>


---

## Assistant <sup>2026/8/6 18:05:09</sup>

现在我将把导致挂起的探针替换为非挂起、经过验证的修复方案（计算流同步 = `.item()` 的机制），并移除该探针的计数器。


---

## Assistant <sup>2026/8/6 18:05:14</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        self._comm_waited = True\n        # [EC-VISPROBE] Confirm whether the stream-side waits (handle.wait +\n        # wait_stream, both aclrtStreamWaitEvent) make the irecv data visible to\n        # the compute stream, or whether a true sync is required. Compares\n        # compute's view right after the stream-side waits (ck_wait) vs after a\n        # full device sync (ck_sync, guaranteed valid). WARNING: this probe\n        # ADDS syncs -> it masks the model read (score ~98 on probed iters);\n        # read `match=`, NOT the score.\n        #   match=False => stream-side waits do NOT establish cross-stream\n        #                  visibility (CANN aclrtStreamWaitEvent quirk).\n        #   match=True  => visibility is fine; bug is a host-side race.\n        _n = _EC_VISPROBE_N[0]\n        _EC_VISPROBE_N[0] += 1\n        if _n < 200:\n            try:\n                _t = None\n                for _v in self.tensors.values():\n                    if isinstance(_v, torch.Tensor) and _v.numel() > 0:\n                        _t = _v\n                        break\n                if _t is not None:\n                    _ck_wait = _t.float().sum()\n                    torch.npu.synchronize()\n                    _ck_sync = _t.float().sum()\n                    _w = _ck_wait.item()\n                    _s = _ck_sync.item()\n                    logger.error(\n                        \"[EC-VISPROBE] n=%d ck_wait=%s ck_sync=%s match=%s\",\n                        _n, _w, _s, bool(_w == _s))\n            except Exception as e:  # noqa: BLE001\n                logger.error(\"[EC-VISPROBE] n=%d err=%s\", _n, e)\n\n        # Edge-cloud debug: comm finished, the hidden tensors received",
  "new_string": "        self._comm_waited = True\n        # [EC-FIX] Compute-stream host block. Stream-side waits (handle.wait +\n        # wait_stream) alre
...(truncated)
```

</details>


---

## User <sup>2026/8/6 18:05:15</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 18:05:15</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "logger = init_logger(__name__)\n\n\n# Diagnostic counter for [EC-VISPROBE] -- caps how many wait_for_comm calls are\n# probed (each probe adds a device sync, which masks the model read).\n_EC_VISPROBE_N = [0]\n\n# Debug: edge-cloud hidden-recv info is appended to this file (same file",
  "new_string": "logger = init_logger(__name__)\n\n# Debug: edge-cloud hidden-recv info is appended to this file (same file"
}
```

</details>


---

## User <sup>2026/8/6 18:05:16</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 18:05:21</sup>


---

## Assistant <sup>2026/8/6 18:05:22</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "python -m py_compile vllm/vllm/v1/worker/gpu_worker.py 2>&1 && echo \"gpu_worker OK\" || echo \"FAIL\"; echo \"\"; echo \"=== probe removed, compute-stream fix in place ===\"; grep -nE \"EC-VISPROBE|_EC_VISPROBE_N|current_stream\\(\\).synchronize|torch.npu.synchronize\" vllm/vllm/v1/worker/gpu_worker.py",
  "description": "Verify probe removed and fix in place"
}
```

</details>


---

## User <sup>2026/8/6 18:05:23</sup>

<details>
<summary>Tool Result</summary>

```
gpu_worker OK

=== probe removed, compute-stream fix in place ===
134:        # HCCL (unlike torch.npu.synchronize(), which hung with error 507011).
135:        torch.npu.current_stream().synchronize()
```

</details>


---

## Assistant <sup>2026/8/6 18:06:17</sup>


---

## Assistant <sup>2026/8/6 18:06:27</sup>

完成。探针已移除（不再挂死），换成计算流同步修复。语法通过。

## 当前状态

[gpu_worker.py wait_for_comm](vllm/vllm/v1/worker/gpu_worker.py#L132) 里，`handle.wait` + postprocess（含 `wait_stream`）之后加了一行：
```python
torch.npu.current_stream().synchronize()
```

- **不挂死**：这是 `aclrtSynchronizeStream`（只等计算流），不像 `torch.npu.synchronize()`（整机 `aclrtSynchronizeDevice`，会等在飞的跨节点 HCCL -> 循环等待 -> 507011）。`.item()` 之所以不挂死也是因为它是 `aclrtSynchronizeStream`。
- **= 你验证过的 `.item()` 机制**：计算流宿主阻塞。预期精度 98、无挂死。

## 结论回顾

- `match=True`（n=0..7）证伪了“跨流可见性建立不了”--`handle.wait`+`wait_stream` 已经让 irecv 数据对计算流可见。
- 所以精度问题不是流可见性，而是**宿主侧/流水线时序竞态**：数据在 `wait_for_comm` 时是对的，但宿主不阻塞就会推进流水线（post 下一个 irecv / 下一轮），抢在模型读取前把数据搞坏。`.item()`/计算流同步靠**阻塞宿主**修好，不是靠可见性。
- 这也解释了为什么 `wait_stream`、`record_stream(compute)` 都没用--它们都不阻塞宿主。

## 取舍

- 这个修复有和 `.item()` 一样的代价：busy_loop 在 `wait_for_comm` 阻塞到计算流排空（等 irecv 完成），损失这部分宿主 overlap。CHER 的 `cloud_prepare_early`（在 `wait_for_comm` 之前）不受影响。
- `parallel_state.py` 里的 `wait_stream` 现在是“匹配 MindIE 但非必需”的非阻塞依赖，可留可删（不影响正确性，真正起作用的是这行计算流同步）。

## 如果想找非同步修复

既然可见性没问题、缺的只是“宿主阻塞”，非同步方向得**定位宿主竞态源头**：到底是谁在模型读取前改写了 recv 缓冲（下一轮 irecv 复用？还是 `sync_and_slice` 后模型读的 tensor 没被 `record_stream(compute)` 覆盖到？）。`record_stream(compute)` 之前没修好，多半是记错了 tensor（模型实际读的是 slice/sp_chunk 之后的，不是 `self.tensors` 里那个）。要的话我可以加一个**非同步**探针：在模型真正消费点（`sync_and_slice_intermediate_tensors`）前后打 recv 缓冲的 `data_ptr`，看是否被下一轮 irecv 复用。

先跑这版确认 98 + 不挂死；之后再决定要不要追非同步修复。


---

## User <sup>2026/8/6 20:16:04</sup>

这版确认 98 + 不挂死； 要追非同步修复


---

## Assistant <sup>2026/8/6 20:17:09</sup>


---

## Assistant <sup>2026/8/6 20:17:11</sup>

太好了 —— 已确认 98 且无挂死。现在让我们寻找一种非同步修复方案，以恢复重叠。主机块（`current_stream().synchronize()`）在 `wait_for_comm` 处序列化了主机；为了在不阻塞的情况下替换它，我需要确切了解它防止了什么竞争条件。`match=True` 证明可见性没问题，且 `record_stream(compute)` 未能解决问题 —— 因此该竞争条件出现在 `wait_for_comm` *之后*，在模型实际消费路径中（`sync_and_slice` / `sync_and_gather`）。我来读取一下该路径。


---

## Assistant <sup>2026/8/6 20:17:12</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 70,
  "offset": 7270
}
```

</details>


---

## User <sup>2026/8/6 20:17:12</sup>

<details>
<summary>Tool Result</summary>

```
7270	                    recv_len = min(v.shape[0], copy_len)
7271	                    if recv_len:
7272	                        dst[:recv_len].copy_(v[:recv_len], non_blocking=True)
7273	                    if recv_len < copy_len:
7274	                        dst[recv_len:].zero_()
7275	                return IntermediateTensors(
7276	                    {
7277	                        k: v[:num_tokens]
7278	                        for k, v in self.intermediate_tensors.items()
7279	                    }
7280	                )
7281	            else:
7282	                for k, v in intermediate_tensors.items():
7283	                    # mrope_positions is an edge-cloud side-channel tensor that
7284	                    # lives outside the model's layer-to-layer intermediate
7285	                    # buffer (self.intermediate_tensors, declared by
7286	                    # make_empty_intermediate_tensors as hidden/residual only).
7287	                    # It is materialized into self.m
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:21:51</sup>


---

## Assistant <sup>2026/8/6 20:22:03</sup>

确认 98 + 不挂死，好。追非同步修复前，先把“host-block 到底挡住了什么”想清楚--这决定了非同步替代有没有可能。

## 已经排除的

- **可见性**：`match=True` 证明 `handle.wait`+`wait_stream` 已让 irecv 数据对计算流可见。✗
- **缓冲复用覆写（B）**：`record_stream(compute)` 没修好；而且 CHER 的 `_early_recv_max_inflight` 基本为 1（下一个 irecv 在当前被消费前不会 post），所以 recv 缓冲在模型读之前不会被下一个 irecv 复用。✗
- **recv→copy→dst 链路**：消费路径是 [sync_and_slice](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7297) 里 `dst.copy_(v, non_blocking=True)`，`v` 和 `dst` 都在计算流上、FIFO 有序，`v` 在 `wait_for_comm` 时已有效。✗

也就是说：数据在 `wait_for_comm` 时是对的、copy 也在计算流上有序读它、缓冲不会被复用--静态分析里找不到该被 host-block 挡住的竞态。host-block 真正起作用的是**阻塞宿主**这件事本身，说明竞态在“宿主推进流水线”层面（很可能是某个我没插桩的路径/流，或跨步骤的集合通信时序），不是数据可见性。

## 两个现实选项

**A. 先量化 host-block 的代价，再决定要不要追**
host-block 只在 `wait_for_comm`（`_preprocess` 里第一次访问 `.tensors` 时）阻塞宿主，等计算流排空（等 irecv 完成）。CHER 的 `cloud_prepare_early`（在 `wait_for_comm` 之前）不受影响。所以代价只是“busy_loop 在等 irecv 完成这段时间不能做别的宿主活”。如果 decode 期间 busy_loop 这段时间本就没有有用活干，host-block ≈ 免费。**建议先测 TPOT：有/无这行 `synchronize()` 的差值**。如果差很小，直接保留这行即可，不必追非同步。

**B. 确实要追，下一步得用运行时追踪，非同步日志已到极限**
非同步日志能看指针/线程/流，但看不出“数据在哪一步发散”（那需要 checksum，而 checksum 要同步）。已经把能非同步看的都看过了。要定位“host-block 挡住的具体竞态”，正路是 **nsys/aclrt 事件时间线**：抓一次有 host-block（98）和一次去掉 host-block（70）的 trace，对比 irecv/copy/broadcast/forward 的时间线，看 70 那次哪个 op 抢前了。这超出静态分析+日志能给的结论。

## 我能立刻帮你做的

如果你不想上 nsys，我可以加一个**延迟 checksum 探针**（仍非破坏性）来缩小范围：在 `wait_for_comm` 对 `v` 排一个 `sum()`（非同步，记在 entry 上），在模型 forward 真正消费 `dst` 时再排一个 `sum()`，下一轮用计算流同步把它们读回来比对--这样能在不挡住当前轮关键路径的前提下，判断数据是“在 recv→forward 之间发散”还是“根本没发散（问题在别处，比如 send 侧或集合通信）”。

你要哪个：先测 TPOT 代价（A），还是我直接加延迟 checksum 探针（B 的轻量版）？或者直接上 nsys 我帮你列抓取命令？


---

## User <sup>2026/8/6 20:35:30</sup>

边云场景边调度prefill_first，prefill_last，decode_first，decode_last，如果prefill_first，prefill_last不插入decode也不会有精度问题，所以想确认当前实现是否必须要加synchronize，以及为什么


---

## Assistant <sup>2026/8/6 20:37:15</sup>


---

## Assistant <sup>2026/8/6 20:37:17</sup>

这是一个关键线索——精度问题仅出现在 decode 嵌入到 prefill_first 和 prefill_last 之间时。这把问题从“通用的可见性竞态”收窄到了“跨 batch 类型交错时的资源复用竞态”。要回答“是否必须加 synchronize、为什么”，我得看清当前实现里 prefill_first / decode / prefill_last 三者如何复用 send/recv 缓冲与流。让我读相关代码。


---

## Assistant <sup>2026/8/6 20:37:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== _wait_pp_send_work call sites + batch-type dispatch ===\" && grep -nE \"_wait_pp_send_work|_pp_send_work|PREFILL_FIRST|PREFILL_LAST|DECODE_FIRST|DECODE_LAST|_execute_model_edge_tail|_execute_model_cloud|def execute_model|edge_cloud_send|edge_cloud_broadcast_recv|_hidden_channel_for\" vllm_ascend/worker/worker.py 2>&1 | head -50",
  "description": "Find batch-type dispatch and send/recv call sites"
}
```

</details>


---

## User <sup>2026/8/6 20:37:19</sup>

<details>
<summary>Tool Result</summary>

```
=== _wait_pp_send_work call sites + batch-type dispatch ===
79:    edge_cloud_broadcast_recv,
80:    edge_cloud_broadcast_recv_scheduled_draft,
81:    edge_cloud_send_tensor_dict,
82:    edge_cloud_send_tensor_dict_scheduled_draft,
225:        self._pp_send_work: list[Handle] = []
226:        self._pp_send_work_by_channel: dict[str, list[Handle]] = {}
638:            # worker (local_rank==0), so _execute_model_cloud consults the
779:    def _record_pp_send_work(
783:            self._pp_send_work = handles
785:            self._pp_send_work_by_channel[channel.value] = handles
787:    def _wait_pp_send_work(self, channel: HiddenChannelType | None = None) -> None:
789:            for handle in self._pp_send_work:
791:            self._pp_send_work = []
792:            for handles in self._pp_send_work_by_channel.values():
795:            self._pp_send_work_by_channel.clear()
798:        handles = self._pp_send_work_by_channel.pop(channel.value, [])
824:        tensor_dict, comm_handles, 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:37:26</sup>


---

## Assistant <sup>2026/8/6 20:37:27</sup>

让我读取一下 `dispatch` 和 `channel mapping`，看看 `prefill` 和 `decode` 是如何映射到 `channels`/`streams` 的。


---

## Assistant <sup>2026/8/6 20:37:27</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 75,
  "offset": 974
}
```

</details>


---

## User <sup>2026/8/6 20:37:27</sup>

<details>
<summary>Tool Result</summary>

```
974	    def execute_model(
975	        self,
976	        scheduler_output: "SchedulerOutput",
977	        layer_slice_info: Any = None,
978	    ) -> ModelRunnerOutput | AsyncModelRunnerOutput | None:
979	        batch_type = scheduler_output.batch_type
980	        use_alt_group = (batch_type == SchedulerBatchType.ALL_DECODE)
981	
982	        if envs_ascend.MSMONITOR_USE_DAEMON:
983	            dp.step()
984	
985	        # Edge-cloud PD separation can keep one outstanding send per hidden
986	        # channel.  Only wait on the channel about to be reused; legacy PP waits
987	        # for all outstanding sends to preserve the original behavior.
988	        if self.model_runner._edge_cloud_enabled:
989	            bt = scheduler_output.batch_type
990	            if bt in (
991	                BatchType.PREFILL_FIRST,
992	                BatchType.DECODE_FIRST,
993	                BatchType.DRAFT_FIRST,
994	                BatchType.PREFILL_LAST,
995	                BatchType.DECODE_LAST,
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:37:57</sup>


---

## Assistant <sup>2026/8/6 20:37:58</sup>

通道映射确认了：PREFILL_FIRST/LAST → PREFILL_1/2，DECODE_FIRST/LAST → DECODE，每个都有各自的流。并且在每次 `execute_model` 开始时，`_wait_pp_send_work` 只会等待**即将被重用的通道**。让我读取一下云端发送路径——即 P2 hidden 是如何生成和发送的——因为交错竞争很可能存在于发送端。


---

## Assistant <sup>2026/8/6 20:37:58</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 60,
  "offset": 1255
}
```

</details>


---

## User <sup>2026/8/6 20:37:58</sup>

<details>
<summary>Tool Result</summary>

```
1255	        )
1256	        if not is_last_slice:
1257	            return None
1258	
1259	        if isinstance(output, (ModelRunnerOutput, AsyncModelRunnerOutput, NoneType)):
1260	            return output
1261	
1262	        assert isinstance(output, IntermediateTensors)
1263	        # Edge-cloud with heterogeneous SP: aggregate SP shards to full
1264	        # sequence before cross-PP send so edge can re-chunk by its SP.
1265	        if enable_sp():
1266	            _gathered = self._all_gather_tensor_dict(output.tensors)
1267	        else:
1268	            _gathered = output.tensors
1269	
1270	        # In the shared-model edge-cloud topology the cloud
1271	        # first-worker of each dp_rank is in the shared PP group
1272	        # with the edge and must send its middle-layer output
1273	        # back to the edge (in-group rank 0). Other cloud
1274	        # workers (TP non-first) are in singleton PP groups
1275	        # Send intermediate tensors to edge.  In the shared-model 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:38:56</sup>


---

## Assistant <sup>2026/8/6 20:38:58</sup>

这很可能就是问题的根源。云端通过 `edge_cloud_send_tensor_dict(_gathered, ...)` 发送 P2，其中 `_gathered = output.tensors` —— 即**模型自身的中间输出缓冲区** —— 并且 `_record_pp_send_work` 会*延迟*等待句柄，直到下一个*相同通道*的 `execute_model`。让我来验证一下发送操作是直接读取模型缓冲区（存在竞态条件），还是将其复制/合并（无竞态条件）。


---

## Assistant <sup>2026/8/6 20:38:58</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 60,
  "offset": 1000
}
```

</details>


---

## User <sup>2026/8/6 20:38:58</sup>

<details>
<summary>Tool Result</summary>

```
1000	    )
1001	
1002	
1003	
1004	def edge_cloud_isend_tensor_dict(
1005	    tensor_dict: dict[str, torch.Tensor | Any],
1006	    dst: int | None = None,
1007	    num_tokens: int | None = None,
1008	    use_alt_group: bool = False,
1009	    channel: HiddenChannelType | None = None,
1010	    include_mrope: bool = True,
1011	) -> list[Handle]:
1012	    """Send tensor dict without metadata sync (edge-cloud optimized).
1013	
1014	    Skips send_object(metadata_list) the receiver already knows the
1015	    tensor structure from init_edge_cloud_tensor_meta() and computes
1016	    shapes locally from SchedulerOutput.total_num_scheduled_tokens.
1017	
1018	    This eliminates the inter-node pickle+Gloo metadata exchange that
1019	    the standard GroupCoordinator.isend_tensor_dict performs.
1020	
1021	    Args:
1022	        tensor_dict: tensors to send. Non-tensor / zero-numel entries are
1023	            skipped, matching the receiver's allocation logic.
1024	        dst: destination rank in P
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:39:03</sup>


---

## Assistant <sup>2026/8/6 20:39:03</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 75,
  "offset": 1060
}
```

</details>


---

## User <sup>2026/8/6 20:39:03</sup>

<details>
<summary>Tool Result</summary>

```
1060	    # crash. Fail fast here with a precise message instead.
1061	    ec_meta = _select_edge_cloud_meta_for_send()
1062	    # Dynamic send key set: drop mrope_positions when the caller signals a
1063	    # text-only batch (include_mrope=False). Both sides derive include_mrope
1064	    # from the same step_has_multimodal_req(scheduler_output), so sender and
1065	    # receiver agree on whether mrope is on the wire.
1066	    meta_send_keys = ec_meta.send_tensor_keys or ec_meta.tensor_keys
1067	    send_keys = [
1068	        k for k in meta_send_keys
1069	        if not (k == "mrope_positions" and not include_mrope)
1070	    ]
1071	    sender_tensor_keys = [
1072	        k for k in send_keys
1073	        if k in tensor_dict and isinstance(tensor_dict[k], torch.Tensor)
1074	    ]
1075	    assert sender_tensor_keys == send_keys, (
1076	        "edge_cloud_isend_tensor_dict: tensor key set/order does not match "
1077	        f"the pre-computed EdgeCloudTensorMeta send keys. sender={sende
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:39:44</sup>


---

## Assistant <sup>2026/8/6 20:39:46</sup>

在第 1131-1132 行发现关键点：合并路径执行了 `merged = torch.cat(pieces, dim=-1)` ——但是 `pieces` 是 `value[:num_tokens]`（模型输出缓冲区的视图），并且 `torch.cat` 在 **发送流 (SEND stream)** 内运行（在 `_hidden_channel_stream_ctx(..., _HC_STREAM_SEND, ...)` 内部）。因此，发送操作在发送流上读取模型输出缓冲区，而该缓冲区在 **计算流 (COMPUTE stream)** 上被每一次前向传播（forward）原地重用。让我确认一下每个 key 的路径是否也直接读取模型缓冲区。


---

## Assistant <sup>2026/8/6 20:39:47</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 55,
  "offset": 1148
}
```

</details>


---

## User <sup>2026/8/6 20:39:47</sup>

<details>
<summary>Tool Result</summary>

```
1148	            "it or unset VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD."
1149	        )
1150	        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):
1151	            handle = torch.distributed.isend(
1152	                merged, dst=pp_group.ranks[dst], group=group
1153	            )
1154	            if merged.is_cuda:
1155	                merged.record_stream(torch.cuda.current_stream(merged.device))
1156	            elif merged.device.type == "npu":
1157	                merged.record_stream(torch.npu.current_stream(merged.device))
1158	        handles.append(handle)
1159	        # Do NOT return: keys not in merge_keys (e.g. mrope_positions) still
1160	        # need to be sent as individual isends by the per-key loop below.
1161	
1162	    merged_key_set = set(ec_meta.merge_keys) if ec_meta.merge_payload else set()
1163	    for key in send_keys:
1164	        if key in merged_key_set:
1165	            continue  # already sent inside the merged buffer above
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:42:21</sup>


---

## Assistant <sup>2026/8/6 20:42:35</sup>

找到根因了。这回答了你的问题：**synchronize 不是必须的，它是个时序掩盖**。

## 根因：发送侧 buffer 原地复用竞态（per-key 路径）

云侧发 P2 走 [edge_cloud_isend_tensor_dict](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1004)。两条路径：

- **merge 路径**（[L1131](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1131)）：`merged = torch.cat(pieces)` 在**计算流**上（在 send ctx 之外）把模型输出 buffer 拷成一块新内存，再 isend 新内存。**安全**——cat 在计算流上、FIFO 排在 forward 之后、下一 forward 之前。
- **per-key 路径**（[L1183-1185](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1183-L1185)）：`value` 是模型输出 buffer 的 view（contiguous 时不拷贝），直接 `isend(value)`，而 isend 跑在 **SEND 流**上。

问题在 per-key 路径：**isend 在 SEND 流上读模型输出 buffer，而模型输出 buffer 被每次 forward 在 COMPUTE 流上原地复用**。两条流之间没有顺序约束。而 isend handle 是**懒等待**的——`_wait_pp_send_work` 只等“即将复用的那个 channel”（[worker.py:988-998](vllm-ascend/vllm_ascend/worker/worker.py#L988)）。

## 为什么“decode 插在 prefill_first/prefill_last 之间”才出问题

- **不交错**：prefill_first 发完 P2（PREFILL_2）后，紧接着下一个 prefill_first 在 execute_model 开头 `_wait_pp_send_work(PREFILL_2)` **先等 P2 isend 完成**，再 forward 复用 buffer。先读完再覆写，无竞态。
- **交错**：prefill_first 发 P2（PREFILL_2，handle 挂起未等）→ decode 执行：decode 在 execute_model 开头只 `_wait_pp_send_work(DECODE)`，**不等 PREFILL_2 的 P2 isend**；decode 的 forward 在 COMPUTE 流上覆写模型输出 buffer，而 P2 isend 还在 SEND 流上没读完这块 buffer → P2 被发成错数据 → 边侧收到错的 hidden → 掉分。

`record_stream` 没用，因为模型输出 buffer 是**持久 buffer 原地复用**，不是分配器回收——record_stream 只管分配器回收，挡不住模型自己原地覆写。`wait_stream` 没用，因为这是发送侧 buffer 读写竞态，不是接收侧可见性。

## 为什么 synchronize 能“修”但是假修

`current_stream().synchronize()`（计算流宿主阻塞）挡在 `wait_for_comm`，把 busy_loop 卡住，**延迟了 decode 的 forward**，给 P2 isend 留出墙钟时间读完 buffer。是**时序掩盖**，不是建立了真正的依赖。这也解释了之前所有现象：match=True（接收侧可见性没问题）、record_stream/wait_stream 无效、只有宿主阻塞管用。

## 非同步正解

让 isend 发的是**发送专属副本**（在计算流上先拷贝，和 merge 路径的 cat 一样），把发送 buffer 与模型输出 buffer 解耦——模型 buffer 随便原地复用，isend 读的是副本。无死锁、非宿主阻塞、恢复 overlap：

per-key 路径里，进 send ctx 前把 `value` clone 一份（在计算流上）：
```python
# 原: if not value.is_contiguous(): value = value.contiguous()
# 改: 始终在计算流上物化一份发送专属副本
if not value.is_contiguous():
    value = value.contiguous()
value = value.clone()   # 解耦：模型输出 buffer 可被下一轮 forward（任意 channel）原地复用
```
然后 `isend(value)`（副本）、`value.record_stream(send_stream)` 保活副本。merge 路径已是此模式（cat），无需改。

代价：per-key 的 key 每次发送多一次拷贝。若 `merge_payload=True`，per-key 只剩 mrope 等小 tensor，代价很小；若 `merge_payload=False`，主 hidden 走 per-key，拷贝较大（可考虑改用 merge 路径避免）。

改完后即可**移除** `wait_for_comm` 里的 `current_stream().synchronize()`（以及之前的 `wait_stream`，它对这个问题无效）。

---

确认两点后我就动手：① 你的 `VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD` 是开还是关（决定 per-key 是否含主 hidden、拷贝代价）？② 要我直接按“per-key clone + 移除 host-block”改，还是你想先只改 per-key clone、暂时保留 host-block 验证一轮再摘？


---

## User <sup>2026/8/6 20:53:20</sup>

VLLM_ASCEND_EDGE_CLOUD_MERGE_PAYLOAD 默认是开吧；直接按“per-key clone + 移除 host-block”改


---

## Assistant <sup>2026/8/6 20:54:43</sup>


---

## Assistant <sup>2026/8/6 20:54:44</sup>

确认：`merge_payload` 默认开启 → 主隐藏状态通过合并路径（cat，安全）传输；每个键仅涉及 mrope 等小张量。因此，每个键的克隆成本很低。我来应用“每个键克隆 + 移除 host-block + 移除无效的 wait_stream”这一方案。先读取一下目前的确切文本。


---

## Assistant <sup>2026/8/6 20:54:44</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 16,
  "offset": 131
}
```

</details>


---

## User <sup>2026/8/6 20:54:44</sup>

<details>
<summary>Tool Result</summary>

```
131	        # corrupts the model read unless the host blocks here. This mirrors
132	        # `.item()`: aclrtSynchronizeStream on the current/compute stream --
133	        # NOT device-wide -- so it does NOT deadlock on in-flight cross-node
134	        # HCCL (unlike torch.npu.synchronize(), which hung with error 507011).
135	        torch.npu.current_stream().synchronize()
136	
137	        # Edge-cloud debug: comm finished, the hidden tensors received
138	        # from the previous PP stage (cloud side) are now valid.
139	        # Write numeric stats of each received hidden tensor to file,
140	        # one line per tensor.
141	        log_lines = []
142	        for name, tensor in self.tensors.items():
143	            t = tensor.float()
144	            log_lines.append(
145	                f"[EDGE-CLOUD-RECV] is_edge={is_edge_device()} "
146	                f"batch_type={self._batch_type} req_ids={self._req_ids} "
```

</details>


---

## Assistant <sup>2026/8/6 20:54:45</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 12,
  "offset": 1176
}
```

</details>


---

## User <sup>2026/8/6 20:54:45</sup>

<details>
<summary>Tool Result</summary>

```
1176	        if num_tokens is not None and value.shape[0] > num_tokens:
1177	            value = value[:num_tokens]
1178	        if not value.is_contiguous():
1179	            # isend requires contiguous storage; a non-contiguous slice
1180	            # only happens when upstream code returned a non-standard
1181	            # layout, in which case we materialize once.
1182	            value = value.contiguous()
1183	        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):
1184	            handle = torch.distributed.isend(
1185	                value, dst=pp_group.ranks[dst], group=group
1186	            )
1187	            if value.is_cuda:
```

</details>


---

## Assistant <sup>2026/8/6 20:54:45</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 30,
  "offset": 1452
}
```

</details>


---

## User <sup>2026/8/6 20:54:45</sup>

<details>
<summary>Tool Result</summary>

```
1452	    channel: HiddenChannelType,
1453	    dst: int | None = None,
1454	    num_tokens: int | None = None,
1455	    include_mrope: bool = True,
1456	) -> list[Handle]:
1457	    """Send edge-cloud tensors on a hidden channel without metadata sync."""
1458	    return edge_cloud_isend_tensor_dict(
1459	        tensor_dict,
1460	        dst=dst,
1461	        num_tokens=num_tokens,
1462	        channel=channel,
1463	        include_mrope=include_mrope,
1464	    )
1465	
1466	
1467	def edge_cloud_irecv_tensor_dict_on_hidden_channel(
1468	    channel: HiddenChannelType,
1469	    src: int | None = None,
1470	    num_tokens: int | None = None,
1471	    include_mrope: bool = True,
1472	) -> tuple[dict[str, torch.Tensor | Any], list[Handle], list[Callable[[], None]]]:
1473	    """Receive edge-cloud tensors on a hidden channel without metadata sync."""
1474	    assert num_tokens is not None, (
1475	        "num_tokens must be provided for edge-cloud hidden-channel receive"
1476	    )
1477	    re
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:54:51</sup>


---

## Assistant <sup>2026/8/6 20:54:51</sup>

第三次读取定位到了不同的函数。让我找到 `_wait_recv_stream` 代码块和 `edge_cloud_irecv_tensor_dict` 的返回值。


---

## Assistant <sup>2026/8/6 20:54:52</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && grep -nE \"_wait_recv_stream|_recv_stream = _get_hidden_channel|Mirror MindIE edge_cloud_data_comm|return tensor_dict, handles, postprocess\" vllm_ascend/distributed/parallel_state.py | head",
  "description": "Locate _wait_recv_stream block"
}
```

</details>


---

## User <sup>2026/8/6 20:54:53</sup>

<details>
<summary>Tool Result</summary>

```
1422:        # Mirror MindIE edge_cloud_data_comm.py:471/476: in addition to the
1432:        _recv_stream = _get_hidden_channel_stream(channel, _HC_STREAM_RECV)
1434:        def _wait_recv_stream(_rs=_recv_stream, _ch=channel) -> None:
1445:        postprocess.insert(0, _wait_recv_stream)
1447:    return tensor_dict, handles, postprocess
```

</details>


---

## Assistant <sup>2026/8/6 20:54:59</sup>


---

## Assistant <sup>2026/8/6 20:54:59</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 30,
  "offset": 1420
}
```

</details>


---

## User <sup>2026/8/6 20:54:59</sup>

<details>
<summary>Tool Result</summary>

```
1420	
1421	    if channel is not None:
1422	        # Mirror MindIE edge_cloud_data_comm.py:471/476: in addition to the
1423	        # HCCL handle.wait() that AsyncIntermediateTensors.wait_for_comm()
1424	        # runs (compute <- internal hccl stream), also make the compute
1425	        # (current) stream wait for the dedicated recv stream. On CANN the
1426	        # irecv data visibility is owned by the recv stream; handle.wait()
1427	        # alone (event on the internal hccl stream) does not make the received
1428	        # hidden states visible to compute -> intermittent stale reads.
1429	        # Inserted at index 0 so it runs right after handle.wait(), before any
1430	        # buffer-reading postprocess (TP broadcast / split). Non-blocking
1431	        # stream-side wait -> preserves CHER overlap.
1432	        _recv_stream = _get_hidden_channel_stream(channel, _HC_STREAM_RECV)
1433	
1434	        def _wait_recv_stream(_rs=_recv_stream, _ch=channel) -> None:
1435	            _
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 20:55:10</sup>


---

## Assistant <sup>2026/8/6 20:55:11</sup>

让我获取 gpu_worker.py 中完整的 `[EC-FIX]` 代码块以进行精确移除。


---

## Assistant <sup>2026/8/6 20:55:11</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "limit": 12,
  "offset": 126
}
```

</details>


---

## User <sup>2026/8/6 20:55:11</sup>

<details>
<summary>Tool Result</summary>

```
126	                fn()
127	        self._comm_waited = True
128	        # [EC-FIX] Compute-stream host block. Stream-side waits (handle.wait +
129	        # wait_stream) already make the irecv data visible to compute (probe
130	        # confirmed ck_wait==ck_sync), but a host-side/pipeline race still
131	        # corrupts the model read unless the host blocks here. This mirrors
132	        # `.item()`: aclrtSynchronizeStream on the current/compute stream --
133	        # NOT device-wide -- so it does NOT deadlock on in-flight cross-node
134	        # HCCL (unlike torch.npu.synchronize(), which hung with error 507011).
135	        torch.npu.current_stream().synchronize()
136	
137	        # Edge-cloud debug: comm finished, the hidden tensors received
```

</details>


---

## Assistant <sup>2026/8/6 20:55:34</sup>


---

## Assistant <sup>2026/8/6 20:55:34</sup>

现在应用这三个变更：per-key clone (修复)，移除 host-block，移除无效的 wait_stream。


---

## Assistant <sup>2026/8/6 20:55:36</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "        if not value.is_contiguous():\n            # isend requires contiguous storage; a non-contiguous slice\n            # only happens when upstream code returned a non-standard\n            # layout, in which case we materialize once.\n            value = value.contiguous()\n        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):",
  "new_string": "        if not value.is_contiguous():\n            # isend requires contiguous storage; a non-contiguous slice\n            # only happens when upstream code returned a non-standard\n            # layout, in which case we materialize once.\n            value = value.contiguous()\n        # Materialize a send-owned copy on the compute stream (before entering\n        # the send stream). The model's intermediate output buffer is reused\n        # in-place by every forward (any channel); without a copy, an\n        # interleaved decode's forward (compute stream) overwrites this buffer\n        # while the isend still reads it on the send stream, and the lazy\n        # channel-specific _wait_pp_send_work does not cover the interleaving\n        # -> corrupted payload. The merge path already decouples via torch.cat;\n        # mirror it here. (merge_payload is on by default, so per-key is only\n        # small tensors like mrope_positions -- clone cost is negligible.)\n        value = value.clone()\n        with _hidden_channel_stream_ctx(channel, _HC_STREAM_SEND, wait_for_default=True):"
}
```

</details>


---

## User <sup>2026/8/6 20:55:37</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 20:55:39</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "old_string": "    if channel is not None:\n        # Mirror MindIE edge_cloud_data_comm.py:471/476: in addition to the\n        # HCCL handle.wait() that AsyncIntermediateTensors.wait_for_comm()\n        # runs (compute <- internal hccl stream), also make the compute\n        # (current) stream wait for the dedicated recv stream. On CANN the\n        # irecv data visibility is owned by the recv stream; handle.wait()\n        # alone (event on the internal hccl stream) does not make the received\n        # hidden states visible to compute -> intermittent stale reads.\n        # Inserted at index 0 so it runs right after handle.wait(), before any\n        # buffer-reading postprocess (TP broadcast / split). Non-blocking\n        # stream-side wait -> preserves CHER overlap.\n        _recv_stream = _get_hidden_channel_stream(channel, _HC_STREAM_RECV)\n\n        def _wait_recv_stream(_rs=_recv_stream, _ch=channel) -> None:\n            _cur = torch.npu.current_stream()\n            logger.error(\n                \"[EC-WAITSTREAM] channel=%s recv_stream=0x%x cur_stream=0x%x \"\n                \"same=%s thread=%s(%s)\",\n                _ch, _rs.npu_stream, _cur.npu_stream,\n                _rs.npu_stream == _cur.npu_stream, threading.get_ident(),\n                threading.current_thread().name,\n            )\n            _cur.wait_stream(_rs)\n\n        postprocess.insert(0, _wait_recv_stream)\n\n    return tensor_dict, handles, postprocess",
  "new_string": "    return tensor_dict, handles, postprocess"
}
```

</details>


---

## User <sup>2026/8/6 20:55:40</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\distributed\parallel_state.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 20:55:40</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_worker.py",
  "old_string": "        self._comm_waited = True\n        # [EC-FIX] Compute-stream host block. Stream-side waits (handle.wait +\n        # wait_stream) already make the irecv data visible to compute (probe\n        # confirmed ck_wait==ck_sync), but a host-side/pipeline race still\n        # corrupts the model read unless the host blocks here. This mirrors\n        # `.item()`: aclrtSynchronizeStream on the current/compute stream --\n        # NOT device-wide -- so it does NOT deadlock on in-flight cross-node\n        # HCCL (unlike torch.npu.synchronize(), which hung with error 507011).\n        torch.npu.current_stream().synchronize()\n\n        # Edge-cloud debug: comm finished, the hidden tensors received",
  "new_string": "        self._comm_waited = True\n\n        # Edge-cloud debug: comm finished, the hidden tensors received"
}
```

</details>


---

## User <sup>2026/8/6 20:55:42</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm\vllm\v1\worker\gpu_worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 20:55:47</sup>


---

## Assistant <sup>2026/8/6 20:55:48</sup>

让我验证一下语法并确认这三处修改。


---

## Assistant <sup>2026/8/6 20:55:49</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br && python -m py_compile vllm-ascend/vllm_ascend/distributed/parallel_state.py 2>&1 && echo \"parallel_state OK\" || echo \"FAIL\"; python -m py_compile vllm/vllm/v1/worker/gpu_worker.py 2>&1 && echo \"gpu_worker OK\" || echo \"FAIL\"; echo \"\"; echo \"=== 1. per-key clone present ===\"; grep -nE \"value = value.clone\\(\\)\" vllm-ascend/vllm_ascend/distributed/parallel_state.py; echo \"\"; echo \"=== 2. wait_stream removed (should be empty) ===\"; grep -nE \"_wait_recv_stream|EC-WAITSTREAM|wait_stream\\(_rs\\)\" vllm-ascend/vllm_ascend/distributed/parallel_state.py; echo \"\"; echo \"=== 3. host-block removed from wait_for_comm (should be empty) ===\"; grep -nE \"current_stream\\(\\).synchronize|EC-FIX\" vllm/vllm/v1/worker/gpu_worker.py",
  "description": "Verify all three changes"
}
```

</details>


---

## User <sup>2026/8/6 20:55:52</sup>

<details>
<summary>Tool Result</summary>

```
parallel_state OK
gpu_worker OK

=== 1. per-key clone present ===
1192:        value = value.clone()

=== 2. wait_stream removed (should be empty) ===

=== 3. host-block removed from wait_for_comm (should be empty) ===
```

</details>


---

## Assistant <sup>2026/8/6 20:56:07</sup>


---

## Assistant <sup>2026/8/6 20:56:14</sup>

三处改动完成，语法通过：

## 改动总结

**1. 根因修复 — per-key 发送解耦**（[parallel_state.py:1192](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1192)）
per-key 路径进 send ctx 前 `value = value.clone()`，在**计算流**上物化一份发送专属副本。isend 读副本（send 流），模型输出 buffer 可被任意 channel 的 forward 原地复用，互不干扰。与 merge 路径的 `torch.cat`（本就分配新 buffer）一致。merge_payload 默认开，per-key 只剩 mrope 等小 tensor，clone 代价可忽略。

**2. 移除 host-block**（gpu_worker.py `wait_for_comm`）
删掉 `torch.npu.current_stream().synchronize()`（那个时序掩盖）。`wait_for_comm` 回到 `handle.wait` + postprocess，不再阻塞宿主，overlap 恢复。

**3. 移除无效的 wait_stream**（parallel_state.py `edge_cloud_irecv_tensor_dict`）
删掉 `_wait_recv_stream` 回调（含 `[EC-WAITSTREAM]` 日志）。它作用在接收侧、对发送侧 buffer 竞态无效，已不需要。

## 修复逻辑

之前：per-key isend 在 SEND 流读模型输出 buffer（view）→ 交错的 decode forward 在 COMPUTE 流原地覆写同一 buffer → 无跨流顺序 + 懒等待只等本 channel → P2 被发成错数据。
现在：per-key isend 读的是 clone 出的副本（计算流上、FIFO 排在 forward 之后、下一 forward 之前完成拷贝），模型 buffer 怎么复用都不影响发送。根因消除，无需任何同步。

## 验证建议

- GSM8K 200 请求，**带 prefill/decode 交错**：预期 98、无挂死、无死锁。
- 不交错的场景应仍 98（回归）。
- 可顺带对比 TPOT：host-block 已移除，`wait_for_comm` 不再阻塞宿主，overlap 应比上一版（带 synchronize）更好。

## 残留清理（可选）

`parallel_state.py` 的接收侧还留着之前排查用的 `[EC-POST]` error 日志和 `_ec_stream_id` 辅助函数（非同步、但会刷 error 日志）。确认精度达标后可以一并删掉，要的话我来清理。

跑完把结果（得分 + 是否还挂）告诉我。


---

## User <sup>2026/8/6 21:27:42</sup>

得分82，配置是跑的1p1d


---

## Assistant <sup>2026/8/6 21:29:23</sup>


---

## Assistant <sup>2026/8/6 21:29:25</sup>

82 -- per-key clone 确实修了一部分（70→82），但还有残留竞态。说明 send 侧还有另一处“读模型输出 buffer”的路径没解耦。最可能是 SP 开启时的 `_all_gather_tensor_dict(output.tensors)`（cloud TP=8，SP 很可能开）--它在 send 之前读模型输出 buffer，若在 hccl 流上就又和下一轮 forward（compute）竞态。让我确认。


---

## Assistant <sup>2026/8/6 21:29:26</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== _all_gather_tensor_dict def + body ===\" && grep -nE \"def _all_gather_tensor_dict|_all_gather_tensor_dict\\(\" vllm_ascend/worker/worker.py | head; echo \"\"; echo \"=== enable_sp / SP status ===\" && grep -nE \"def enable_sp|VLLM_ASCEND_ENABLE_SP|enable_sp\\(\\)\" vllm_ascend/envs.py 2>/dev/null | head; grep -rnE \"def enable_sp\" vllm_ascend/ 2>/dev/null | head -3",
  "description": "Find _all_gather_tensor_dict and SP config"
}
```

</details>


---

## User <sup>2026/8/6 21:29:29</sup>

<details>
<summary>Tool Result</summary>

```
=== _all_gather_tensor_dict def + body ===
942:    def _all_gather_tensor_dict(
1068:            _gathered = self._all_gather_tensor_dict(output.tensors)
1266:            _gathered = self._all_gather_tensor_dict(output.tensors)

=== enable_sp / SP status ===
vllm_ascend/utils.py:899:def enable_sp_by_pass():
vllm_ascend/utils.py:903:def enable_sp(vllm_config=None, enable_shared_expert_dp: bool = False) -> bool:
```

</details>


---

## Assistant <sup>2026/8/6 21:29:34</sup>


---

## Assistant <sup>2026/8/6 21:29:34</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 40,
  "offset": 942
}
```

</details>


---

## User <sup>2026/8/6 21:29:34</sup>

<details>
<summary>Tool Result</summary>

```
942	    def _all_gather_tensor_dict(
943	        self,
944	        tensor_dict: dict[str, torch.Tensor],
945	    ) -> dict[str, torch.Tensor]:
946	        """All-gather tensors across the local TP group along sequence dim.
947	
948	        Used in edge-cloud mode when edge and cloud have different SP sizes.
949	        Before cross-PP send, each side must aggregate its SP shards back to
950	        the full sequence so the remote side can re-chunk with its own SP size.
951	
952	        Only the all-gather happens here; the gathered tensor is *not* padded
953	        to the remote TP size.  The sender transmits only the real
954	        ``num_tokens`` rows (sliced in edge_cloud_isend_tensor_dict via the
955	        ``num_tokens`` argument), and the receiver zero-pads its buffer up to
956	        its own local TP size (see ``_pad_num_tokens_to_tp_multiple``).  So a
957	        send-side pad to the remote TP size is redundant — its dim-0 rows are
958	        sliced off before send — and f
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 21:31:35</sup>


---

## Assistant <sup>2026/8/6 21:31:38</sup>

82 —— per-key clone 修复了一个竞态（70→82），因此 send 侧现在大部分已经解耦了。残留的问题必定是第二个竞态。send 侧的 merge path 是安全的（`torch.cat` 在 compute 上运行，FIFO），并且 SP all-gather 是同步的（在 compute 上）。所以残留的问题很可能在 **recv 侧**：在 `sync_and_slice` 中的非阻塞拷贝 `dst.copy_(v, non_blocking=True)` 异步读取了 recv tensor `v`；entry 可能会在拷贝执行前被 drop，导致 recv buffer 被回收。让我阅读完整的 `sync_and_slice` 以便放置 `record_stream` 修复。


---

## Assistant <sup>2026/8/6 21:31:38</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -nE \"def sync_and_slice_intermediate_tensors\" vllm_ascend/worker/model_runner_v1.py",
  "description": "Find sync_and_slice def line"
}
```

</details>


---

## User <sup>2026/8/6 21:31:41</sup>

<details>
<summary>Tool Result</summary>

```
7224:    def sync_and_slice_intermediate_tensors(
```

</details>


---

## Assistant <sup>2026/8/6 21:31:46</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 90,
  "offset": 7224
}
```

</details>


---

## User <sup>2026/8/6 21:31:46</sup>

<details>
<summary>Tool Result</summary>

```
7224	    def sync_and_slice_intermediate_tensors(
7225	        self,
7226	        num_tokens: int,
7227	        intermediate_tensors: IntermediateTensors | None,
7228	        sync_self: bool,
7229	    ) -> IntermediateTensors:
7230	        assert self.intermediate_tensors is not None
7231	        tp = self.vllm_config.parallel_config.tensor_parallel_size
7232	
7233	        if sync_self:
7234	            assert intermediate_tensors is not None, (
7235	                "sync_and_slice_intermediate_tensors received None; "
7236	                "check PP/TP tensor delivery."
7237	            )
7238	            if (self._edge_cloud_enabled
7239	                    and self.edge_cloud_cfg.role == "cloud"
7240	                    and self.edge_cloud_cfg.mode == "embedding_only"
7241	                    and self.supports_mm_inputs):
7242	                # In edge-cloud embedding-only multimodal mode the edge sends
7243	                # the full sequence (it does not SP-chunk, see worker.py).
7
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 21:33:18</sup>


---

## Assistant <sup>2026/8/6 21:33:20</sup>

`sync_and_slice` 在两个分支中均执行了 `dst.copy_(v, non_blocking=True)` (L7272, L7297) —— 这是对接收张量 `v` 的异步复制。由于该条目在 `sync_and_slice` 返回后即被丢弃（返回值使用的是本地 `self.intermediate_tensors`，而非接收条目），因此在计算繁忙时，异步复制执行前，`v` 的接收缓冲区可能会被回收。这就是残留的竞态问题。修复方法：在计算流上对 `v` 执行 `record_stream`，以便在复制完成前保持其处于活跃状态。我来确认一下 `torch.npu` 在此文件中是否可用。


---

## Assistant <sup>2026/8/6 21:33:21</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -nE \"torch\\.npu|import torch\\b|current_stream\" vllm_ascend/worker/model_runner_v1.py | head -8; echo \"---count of the copy pattern---\"; grep -cE \"dst\\[:recv_len\\]\\.copy_\\(v\\[:recv_len\\], non_blocking=True\\)\" vllm_ascend/worker/model_runner_v1.py",
  "description": "Check torch.npu usage and copy pattern count"
}
```

</details>


---

## User <sup>2026/8/6 21:33:23</sup>

<details>
<summary>Tool Result</summary>

```
36:import torch
37:import torch.distributed as dist
38:import torch.nn as nn
239:torch.npu.config.allow_internal_format = True
254:    stream: torch.npu.Stream
271:    graph_capture_context = GraphCaptureContext(torch.npu.Stream(device=device))
279:    curr_stream = torch.npu.current_stream()
283:    with torch.npu.stream(stream), maybe_ca_context:
---count of the copy pattern---
2
```

</details>


---

## Assistant <sup>2026/8/6 21:33:37</sup>


---

## Assistant <sup>2026/8/6 21:33:38</sup>

`torch.npu` 可用，且复制模式出现了 2 次（两个分支）。我将使用 `replace_all` 应用 `record_stream(compute)` 修复方案，以在异步复制完成前保持接收张量（recv tensor）处于活跃状态。


---

## Assistant <sup>2026/8/6 21:33:39</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": true,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "old_string": "                    if recv_len:\n                        dst[:recv_len].copy_(v[:recv_len], non_blocking=True)",
  "new_string": "                    if recv_len:\n                        # Keep the recv tensor's storage alive on the compute\n                        # stream for the async copy below. The recv entry is\n                        # dropped after sync_and_slice returns (the result uses\n                        # the local buffer, not the recv entry), so without this\n                        # the next irecv can recycle v's buffer before this\n                        # non-blocking copy executes -> corrupted local buffer.\n                        v[:recv_len].record_stream(torch.npu.current_stream())\n                        dst[:recv_len].copy_(v[:recv_len], non_blocking=True)"
}
```

</details>


---

## User <sup>2026/8/6 21:33:40</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py has been updated. All occurrences were successfully replaced. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/6 21:33:46</sup>


---

## Assistant <sup>2026/8/6 21:33:47</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "python -m py_compile vllm_ascend/worker/model_runner_v1.py 2>&1 && echo \"model_runner_v1 OK\" || echo \"FAIL\"; echo \"\"; echo \"=== record_stream added at both copy sites ===\"; grep -nE \"record_stream\\(torch.npu.current_stream|dst\\[:recv_len\\]\\.copy_\" vllm_ascend/worker/model_runner_v1.py",
  "description": "Verify syntax and record_stream placement"
}
```

</details>


---

## User <sup>2026/8/6 22:20:25</sup>

<details>
<summary>Tool Result</summary>

```
model_runner_v1 OK

=== record_stream added at both copy sites ===
1909:                dst[:recv_len].copy_(value[:recv_len])
7278:                        v[:recv_len].record_stream(torch.npu.current_stream())
7279:                        dst[:recv_len].copy_(v[:recv_len], non_blocking=True)
7310:                        v[:recv_len].record_stream(torch.npu.current_stream())
7311:                        dst[:recv_len].copy_(v[:recv_len], non_blocking=True)
```

</details>


---

## Assistant <sup>2026/8/6 22:20:57</sup>


---

## Assistant <sup>2026/8/6 22:21:04</sup>

两处都改完，语法通过。现在 send 侧和 recv 侧的 buffer 生命周期竞态都解耦了，且都是非同步操作（clone / record_stream 是分配器生命周期管理，无设备同步、无宿主阻塞），overlap 保留。

## 本轮两处修复

**1. send 侧 - per-key clone**（[parallel_state.py:1192](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L1192)）
per-key isend 进 send ctx 前在计算流上 `value.clone()`，isend 读副本、不再读模型输出 buffer。已修掉 send 侧竞态（70->82）。

**2. recv 侧 - 异步 copy 保活**（[model_runner_v1.py:7278/7310](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7278)）
`sync_and_slice` 里 `dst.copy_(v, non_blocking=True)` 异步读 recv tensor `v`。问题：`sync_and_slice` 返回值用的是本地 buffer（`self.intermediate_tensors`），不引用 recv entry，所以 entry 可在异步 copy 执行前被释放 -> 下一个 irecv 回收 `v` 的 buffer -> copy 读到错数据。修法：copy 前 `v[:recv_len].record_stream(torch.npu.current_stream())`，把 recv buffer 钉在计算流上直到 copy 完成。两个分支（L7278、L7310）都加了。

## 为什么这是残留竞态

send 侧已经全解耦（per-key clone + merge 路径 `torch.cat` 本就分配新 buffer + SP all_gather 同步在计算流上），所以 82->98 的残留不在 send 侧。recv 侧的 `non_blocking` copy + entry 提前释放是剩下的 buffer 生命周期漏洞，正好是“偶发、小幅度”的类型（82 接近 98，符合）。`record_stream` 是标准修法，非同步。

## 验证

跑 GSM8K 1P1D（带 prefill/decode 交错）：预期 98、无挂死、无死锁。两处都是非同步，TPOT 应和基线持平（没有 host-block 了）。

如果还差一点（比如 90+），那大概率是某个 merge 路径在“单 merge_key”时 `torch.cat` 不一定拷贝（注释里“cat with multiple inputs always allocates”暗示单输入可能不分配）--到时我再核查 merge_keys 数量、必要时给 merge 路径也加保活。先把这版跑出来看分数。


---

## User <sup>2026/8/6 22:42:05</sup>

prepare_inputs_event的功能是什么


---

## Assistant <sup>2026/8/6 22:42:18</sup>


---

## Assistant <sup>2026/8/6 22:42:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== prepare_inputs_event occurrences (vllm-ascend) ===\"; grep -rnE \"prepare_inputs_event\" vllm_ascend/ 2>/dev/null | head -30; echo \"\"; echo \"=== prepare_inputs_event occurrences (vllm) ===\"; grep -rnE \"prepare_inputs_event\" vllm/ 2>/dev/null | head -30",
  "description": "Find all prepare_inputs_event references"
}
```

</details>


---

## User <sup>2026/8/6 22:42:20</sup>

<details>
<summary>Tool Result</summary>

```
=== prepare_inputs_event occurrences (vllm-ascend) ===

=== prepare_inputs_event occurrences (vllm) ===
vllm/vllm/v1/worker/gpu_model_runner.py:751:        self.prepare_inputs_event: torch.Event | None = None
vllm/vllm/v1/worker/gpu_model_runner.py:754:            self.prepare_inputs_event = torch.Event()
vllm/vllm/v1/worker/gpu_model_runner.py:3809:        if self.prepare_inputs_event is None:
vllm/vllm/v1/worker/gpu_model_runner.py:3816:        self.prepare_inputs_event.synchronize()
vllm/vllm/v1/worker/gpu_model_runner.py:3820:            self.prepare_inputs_event.record()
```

</details>


---

## Assistant <sup>2026/8/6 22:42:25</sup>


---

## Assistant <sup>2026/8/6 22:42:26</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_model_runner.py",
  "limit": 18,
  "offset": 745
}
```

</details>


---

## User <sup>2026/8/6 22:42:26</sup>

<details>
<summary>Tool Result</summary>

```
745	
746	        # Separate cuda stream for overlapping transfer of sampled token ids from
747	        # GPU to CPU when async scheduling is enabled.
748	        self.async_output_copy_stream: torch.cuda.Stream | None = None
749	        # cuda event to synchronize use of reused CPU tensors between steps
750	        # when async scheduling is enabled.
751	        self.prepare_inputs_event: torch.Event | None = None
752	        if self.use_async_scheduling:
753	            self.async_output_copy_stream = torch.cuda.Stream()
754	            self.prepare_inputs_event = torch.Event()
755	
756	        # self.cudagraph_batch_sizes sorts in ascending order.
757	        if (
758	            self.compilation_config.cudagraph_capture_sizes
759	            and self.compilation_config.cudagraph_mode != CUDAGraphMode.NONE
760	        ):
761	            self.cudagraph_batch_sizes = sorted(
762	                self.compilation_config.cudagraph_capture_sizes
```

</details>


---

## Assistant <sup>2026/8/6 22:42:26</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_model_runner.py",
  "limit": 35,
  "offset": 3798
}
```

</details>


---

## User <sup>2026/8/6 22:42:26</sup>

<details>
<summary>Tool Result</summary>

```
3798	            num_nans_in_logits,
3799	            logprobs_lists,
3800	            valid_sampled_token_ids,
3801	            prompt_logprobs_dict,
3802	            req_ids_output_copy,
3803	            req_id_to_index_output_copy,
3804	            invalid_req_indices,
3805	        )
3806	
3807	    @contextmanager
3808	    def synchronize_input_prep(self):
3809	        if self.prepare_inputs_event is None:
3810	            yield
3811	            return
3812	
3813	        # Ensure prior step has finished with reused CPU tensors.
3814	        # This is required in the async scheduling case because
3815	        # the CPU->GPU transfer happens async.
3816	        self.prepare_inputs_event.synchronize()
3817	        try:
3818	            yield
3819	        finally:
3820	            self.prepare_inputs_event.record()
3821	
3822	    def _model_forward(
3823	        self,
3824	        input_ids: torch.Tensor | None = None,
3825	        positions: torch.Tensor | None = None,
3826	        int
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:42:31</sup>


---

## Assistant <sup>2026/8/6 22:42:31</sup>

我来查找一下 `synchronize_input_prep`（使用该 event 的上下文管理器）是在哪里调用的，以便了解完整的流程。


---

## Assistant <sup>2026/8/6 22:42:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rnE \"synchronize_input_prep|use_async_scheduling\" vllm/vllm/v1/worker/gpu_model_runner.py | head -15",
  "description": "Find synchronize_input_prep callers"
}
```

</details>


---

## User <sup>2026/8/6 22:42:33</sup>

<details>
<summary>Tool Result</summary>

```
561:        self.use_async_scheduling = self.scheduler_config.async_scheduling
689:            self.use_async_scheduling and self.num_spec_tokens > 0
752:        if self.use_async_scheduling:
938:            if self.use_async_scheduling:
1347:            if req_state.prev_num_draft_len and self.use_async_scheduling:
1443:                if self.use_async_scheduling and num_output_tokens > 0:
2128:            if self.use_async_scheduling and prev_req_id_to_index:
3653:        if self.use_async_scheduling and self._draft_token_req_ids is not None:
3705:        if not self.use_async_scheduling:
3765:            if self.use_async_scheduling:
3808:    def synchronize_input_prep(self):
4148:            self.synchronize_input_prep(),
4498:            if self.use_async_scheduling and not get_pp_group().is_last_rank:
4532:        if self.use_async_scheduling:
4693:        if not self.use_async_scheduling:
```

</details>


---

## Assistant <sup>2026/8/6 22:42:39</sup>


---

## Assistant <sup>2026/8/6 22:42:40</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_model_runner.py",
  "limit": 25,
  "offset": 4140
}
```

</details>


---

## User <sup>2026/8/6 22:42:40</sup>

<details>
<summary>Tool Result</summary>

```
4140	        if has_kv_transfer_group():
4141	            kv_connector_metadata = scheduler_output.kv_connector_metadata
4142	            assert kv_connector_metadata is not None
4143	            get_kv_transfer_group().handle_preemptions(kv_connector_metadata)
4144	
4145	        num_scheduled_tokens = scheduler_output.total_num_scheduled_tokens
4146	        with (
4147	            record_function_or_nullcontext("gpu_model_runner: preprocess"),
4148	            self.synchronize_input_prep(),
4149	        ):
4150	            # Update persistent batch states.
4151	            deferred_state_corrections_fn = self._update_states(scheduler_output)
4152	
4153	            if has_ec_transfer() and not get_ec_transfer().is_consumer:
4154	                with self.maybe_get_ec_connector_output(
4155	                    scheduler_output,
4156	                    encoder_cache=self.encoder_cache,
4157	                ) as ec_connector_output:
4158	                    self._execute_mm_encoder(sched
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:43:04</sup>


---

## Assistant <sup>2026/8/6 22:43:15</sup>

`prepare_inputs_event` 是 vLLM v1 在**异步调度（async scheduling）**下用的一个 `torch.Event`，作用是**在跨步骤复用 CPU 输入张量时做同步**，防止上一步的异步 CPU→GPU 拷贝还没读完、下一步就把这些 CPU buffer 覆写掉。

## 定义与创建

[gpu_model_runner.py:751-754](vllm/vllm/v1/worker/gpu_model_runner.py#L751-L754)：
```python
self.prepare_inputs_event: torch.Event | None = None
if self.use_async_scheduling:
    self.async_output_copy_stream = torch.cuda.Stream()
    self.prepare_inputs_event = torch.Event()
```
只在 `use_async_scheduling=True` 时创建（同步调度下是 None，走空路径）。

## 用法：`synchronize_input_prep` 上下文管理器

[gpu_model_runner.py:3807-3820](vllm/vllm/v1/worker/gpu_model_runner.py#L3807-L3820)：
```python
@contextmanager
def synchronize_input_prep(self):
    if self.prepare_inputs_event is None:
        yield
        return
    # Ensure prior step has finished with reused CPU tensors.
    # This is required in the async scheduling case because
    # the CPU->GPU transfer happens async.
    self.prepare_inputs_event.synchronize()   # 进：等上一步 record
    try:
        yield                                  # 跑本步 input prep
    finally:
        self.prepare_inputs_event.record()     # 出：在本步 prep 末尾 record
```
它在 `_preprocess` 里包住输入准备阶段（[L4146-4149](vllm/vllm/v1/worker/gpu_model_runner.py#L4146-L4149)），即 `_update_states` + 构造 `input_ids`/`positions` 等。

## 工作机理

异步调度的核心是**把第 N 步的 GPU 执行 和 第 N+1 步的 CPU 输入准备重叠起来**。输入准备在 CPU 上用**固定复用的 pinned CPU buffer**（input_ids、positions 等）拼好，再**异步**拷到 GPU。

- **进 prep（第 N+1 步）**：`event.synchronize()` 阻塞宿主，等到第 N 步在计算流上 `record` 的那个点--也就是第 N 步 input prep（含它发起的异步 CPU→GPU 拷贝）已经提交/完成。这样第 N+1 步才能安全复用同一批 CPU buffer，不会把第 N 步还没传完的数据覆写掉。
- **出 prep（第 N+1 步）**：`event.record()` 在计算流当前点记录事件，供第 N+2 步进来时 `synchronize` 等待。

所以它本质是一个**“每步 input-prep 阶段的成对屏障”**：`synchronize(上一步) → 本步 prep → record(本步)`，专门保护被跨步复用的 CPU 输入张量。

## 与你正在查的精度问题的关系

它管的是 **CPU 侧输入张量**（input_ids/positions 等）的跨步复用，**不是**边云 P2P hidden（P2/P1）的收发 buffer--我们之前定位的精度问题是 send/recv 侧的设备 buffer 复用竞态，和这个 event 不是一回事。

但有一点值得留意：如果你的边云跑开了 `async_scheduling`，那么“第 N+1 步 input prep 与第 N 步 GPU 执行（含边云 send/recv）重叠”会让跨步时序更紧凑，**可能放大**我们修的那种“下一轮 irecv/forward 抢在上一轮 send/copy 完成前覆写 buffer”的竞态。`prepare_inputs_event` 只覆盖 CPU 输入 buffer 这一段，不覆盖 hidden 收发 buffer--所以它不能替代我们加的 per-key clone / recv record_stream。

要不要我顺便确认下你这次 1P1D 跑测里 `async_scheduling` 是开还是关？开着的话，这类跨步重叠竞态确实更可能冒头。


---

## User <sup>2026/8/6 22:52:57</sup>

async_scheduling 是开的


---

## Assistant <sup>2026/8/6 22:53:50</sup>


---

## Assistant <sup>2026/8/6 22:53:58</sup>

`async_scheduling` 开着，这点很关键--它和我们的精度问题直接相关，但不是我之前加的 host-block 能替代的。

## async_scheduling 在这里的含义

异步调度把**第 N 步的 GPU 执行（含边云 send/recv）**和**第 N+1 步的 CPU 输入准备**重叠起来。这会**放大**我们定位的那类跨步 buffer 生命周期竞态：

- 第 N 步的 isend 还在读模型输出 buffer（SEND 流），第 N+1 步的 forward 已经在 COMPUTE 流上原地覆写它；
- 第 N 步的异步 `copy_(v)` 还在读 recv buffer，第 N+1 步的 irecv（guard 线程提前 post）已经把这块 buffer 回收复用。

这正是“偶发掉分”的温床--重叠越紧、竞态窗口越大。`prepare_inputs_event` 只保护 **CPU 侧输入张量**（input_ids/positions 等 pinned buffer）的跨步复用，**不管**边云 hidden 的收发 buffer，所以它挡不住这两条设备 buffer 竞态。

## 和已加修复的关系

我加的两处都是**分配器生命周期保护**，和调度重叠与否无关，在 async 下同样成立：

1. **per-key clone**（send 侧）：isend 读副本，模型输出 buffer 怎么被下步覆写都不影响发送。
2. **recv record_stream**（recv 侧 copy 前）：把 recv buffer 钉在计算流上直到异步 copy 完成，下个 irecv 抢不走。

这两个把“跨步设备 buffer 复用”这条根因直接堵死，不需要靠 host-block 去串行化。所以即便 async 开着，理论上应该能到 98，而且**不必关 async_scheduling**（关了是吞吐回退，治标）。

## 下一步

当前版本（per-key clone + recv record_stream，host-block 已移除）还没在你那边跑过--你报的 82 是只有 per-key clone、还没加 recv record_stream 时的分数。**建议先跑这版**（带 prefill/decode 交错的 1P1D）：

- 到 98：确认两条设备 buffer 竞态都堵住，async 下也稳，收工。
- 还差一点（比如 90+）：那说明 async 重叠下还有第三条竞态，最可能在 **guard 线程提前 post 下一轮 irecv 的时序** 或 **send handle 的懒等待（`_wait_pp_send_work` channel-specific）在 async 下覆盖不全**。到时我加一个非同步探针在 guard 线程 post 点和 send handle wait 点打 `data_ptr`/线程/流，定位第三条。

先跑这版看分数。


---

## User <sup>2026/8/6 22:56:00</sup>

分析一下_fast_path流程


---

## Assistant <sup>2026/8/6 22:56:05</sup>


---

## Assistant <sup>2026/8/6 22:56:06</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== _fast_path in vllm-ascend ===\"; grep -rnE \"_fast_path|def fast_path|fast_path\\b\" vllm_ascend/ 2>/dev/null | head -30; echo \"\"; echo \"=== _fast_path in vllm ===\"; grep -rnE \"_fast_path|def fast_path|fast_path\\b\" vllm/ 2>/dev/null | head -30",
  "description": "Find _fast_path references"
}
```

</details>


---

## User <sup>2026/8/6 22:56:08</sup>

<details>
<summary>Tool Result</summary>

```
=== _fast_path in vllm-ascend ===

=== _fast_path in vllm ===
vllm/csrc/cpu/cpu_attn_impl.hpp:421:    const bool use_gqa_fast_path = supports_gqa && decode_only_batch;
vllm/csrc/cpu/cpu_attn_impl.hpp:693:            (use_gqa_fast_path ? input.num_heads_kv : input.num_heads_q);
vllm/csrc/cpu/cpu_attn_impl.hpp:1434:      const bool use_gqa_fast_path = supports_gqa && decode_only_batch;
vllm/csrc/cpu/cpu_attn_impl.hpp:1436:          use_gqa_fast_path ? kv_head_num : q_head_num;
vllm/csrc/cpu/cpu_attn_impl.hpp:1438:          use_gqa_fast_path ? q_heads_per_kv : 1;
vllm/csrc/cpu/cpu_attn_impl.hpp:1543:                use_gqa_fast_path || (supports_gqa && q_token_num == 1);
vllm/csrc/cpu/cpu_attn_impl.hpp:1544:            if (!use_gqa_fast_path && curr_use_gqa &&
vllm/csrc/cpu/cpu_attn_impl.hpp:1555:                use_gqa_fast_path ? (kv_head_idx * q_heads_per_kv)
vllm/csrc/cpu/cpu_attn_impl.hpp:1620:                  use_gqa_fast_path ? kv_head_idx
vllm/csrc/cpu/cpu_attn_impl.hpp:1851:    
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:56:15</sup>


---

## Assistant <sup>2026/8/6 22:56:17</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== fast_path / fast-path in vllm-ascend (worker, model_runner, engine) ===\"; grep -rniE \"fast[_-]path\" vllm_ascend/worker/ vllm_ascend/ 2>/dev/null | grep -viE \"test\" | head -30; echo \"\"; echo \"=== broader: _fast_path as method/attr ===\"; grep -rnE \"_fast_path|fast_path\" vllm_ascend/ vllm/vllm/v1/ 2>/dev/null | grep -viE \"cpu_attn|test_\" | head -30",
  "description": "Search fast_path broadly in worker/v1"
}
```

</details>


---

## User <sup>2026/8/6 22:56:19</sup>

<details>
<summary>Tool Result</summary>

```
=== fast_path / fast-path in vllm-ascend (worker, model_runner, engine) ===

=== broader: _fast_path as method/attr ===
```

</details>


---

## Assistant <sup>2026/8/6 22:56:29</sup>


---

## Assistant <sup>2026/8/6 22:56:30</sup>

让我更广泛地搜索一下——之前有一个关于 "fast-path" 的提交 (`6fbd8606`)。


---

## Assistant <sup>2026/8/6 22:56:31</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== all fast_path in vllm tree (py) ===\"; grep -rniE \"fast_path\" vllm/vllm/ 2>/dev/null | grep -viE \"cpu_attn|test\" | head -20; echo \"\"; echo \"=== git show 6fbd8606 (fast-path commit) in source repo ===\"; git -C /c/theroadtofree_github/vllm-ascend show --stat 6fbd8606 2>&1 | head -25",
  "description": "Search vllm tree and the fast-path commit"
}
```

</details>


---

## User <sup>2026/8/6 22:57:25</sup>

<details>
<summary>Tool Result</summary>

```
=== all fast_path in vllm tree (py) ===

=== git show 6fbd8606 (fast-path commit) in source repo ===
commit 6fbd860620945ba108916f064d8df29f4de0a10d
Author: aolin123 <zhangaolin5@huawei.com>
Date:   Fri Jul 31 20:39:01 2026 +0800

    临时修复qwen s1w1多模态精度，fast—path修好后需要去掉

 vllm_ascend/worker/model_runner_v1.py | 30 +++++++++++++++++++++++++-----
 1 file changed, 25 insertions(+), 5 deletions(-)
```

</details>


---

## Assistant <sup>2026/8/6 22:57:31</sup>


---

## Assistant <sup>2026/8/6 22:57:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== diff of 6fbd8606 ===\"; git -C /c/theroadtofree_github/vllm-ascend show 6fbd8606 2>&1 | head -70; echo \"\"; echo \"=== 'fast' in current model_runner_v1.py ===\"; grep -niE \"fast\" vllm_ascend/worker/model_runner_v1.py | head -20",
  "description": "Show fast-path commit diff and current fast refs"
}
```

</details>


---

## User <sup>2026/8/6 22:57:36</sup>

<details>
<summary>Tool Result</summary>

```
=== diff of 6fbd8606 ===
commit 6fbd860620945ba108916f064d8df29f4de0a10d
Author: aolin123 <zhangaolin5@huawei.com>
Date:   Fri Jul 31 20:39:01 2026 +0800

    临时修复qwen s1w1多模态精度，fast—path修好后需要去掉

diff --git a/vllm_ascend/worker/model_runner_v1.py b/vllm_ascend/worker/model_runner_v1.py
index 66cbf555..4d414f75 100644
--- a/vllm_ascend/worker/model_runner_v1.py
+++ b/vllm_ascend/worker/model_runner_v1.py
@@ -2348,11 +2348,31 @@ class NPUModelRunner(GPUModelRunner):
         # CPU values are optimistic (all drafts accepted). The kernel
         # corrects on GPU using the previous step's
         # valid_sampled_token_count_gpu. Otherwise, just copy from CPU.
-        # In edge-cloud mode, the tail segment reuses the
-        # num_computed_tokens already corrected by the head segment, so skip
-        # both the kernel and the CPU fallback copy to avoid re-introducing
-        # the scheduler's optimistic value.
-        if not self._is_edge_cloud_tail_segment:
+        # Edge-cloud tai
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:57:45</sup>


---

## Assistant <sup>2026/8/6 22:57:45</sup>

grep 因目录变更而失败。让我妥善搜索一下当前的工作区。


---

## Assistant <sup>2026/8/6 22:57:46</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== _fast_path / fast_path / _skip_tail_sync / slow path in current tree ===\"; grep -rniE \"_fast_path|fast_path|_skip_tail_sync|slow path|fast path|fast-path\" vllm_ascend/ 2>/dev/null | grep -viE \"test\" | head -30",
  "description": "Search current tree for fast_path related code"
}
```

</details>


---

## User <sup>2026/8/6 22:57:48</sup>

<details>
<summary>Tool Result</summary>

```
=== _fast_path / fast_path / _skip_tail_sync / slow path in current tree ===
vllm_ascend/attention/attention_v1.py:1653:        BF16 BNSD antiquant tensors for FIA V1 decode fast path.
vllm_ascend/core/single_type_kv_cache_manager.py:85:            # Fast-path: a running request won't have any new prefix-cache hits.
vllm_ascend/distributed/kv_transfer/kv_pool/ascend_store/kv_transfer.py:1038:                # Fast path: reuse cached (start, end, key_all) tuples
vllm_ascend/distributed/parallel_state.py:1108:        # Fast path: concatenate the homogeneous subset (merge_keys, e.g.
vllm_ascend/distributed/parallel_state.py:1335:        # Fast path for the homogeneous subset (merge_keys): single irecv of
vllm_ascend/distributed/parallel_state.py:1684:        # Non-PP-rank-0 path on the merged fast path: allocate a single
vllm_ascend/distributed/parallel_state.py:1795:    so it cannot use the locally-computed fast path.  Keep this old
Binary file vllm_ascend/distributed/__pycache__/paralle
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:57:55</sup>


---

## Assistant <sup>2026/8/6 22:57:55</sup>

Found it. `_fast_path` is in [model_runner_v1.py:3997](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L3997) -- the "segment_e fast path" that reuses segment_a's cached prepare results. Let me read the flow.


---

## Assistant <sup>2026/8/6 22:57:56</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 115,
  "offset": 3980
}
```

</details>


---

## User <sup>2026/8/6 22:57:56</sup>

<details>
<summary>Tool Result</summary>

```
3980	            if new_token_ids and all(not token_ids for token_ids in new_token_ids):
3981	                scheduler_output = deepcopy(scheduler_output)
3982	                scheduler_output.scheduled_cached_reqs.new_token_ids = []
3983	
3984	        if has_kv_transfer_group():
3985	            kv_connector_metadata = scheduler_output.kv_connector_metadata
3986	            assert kv_connector_metadata is not None
3987	            # Preemption stores must run before _update_states() zeroes newly
3988	            # allocated blocks that may reuse the same physical KV cache IDs.
3989	            get_kv_transfer_group().handle_preemptions(kv_connector_metadata)
3990	
3991	        num_scheduled_tokens = scheduler_output.total_num_scheduled_tokens
3992	
3993	        # ---- segment_e fast path: reuse segment_a's cached prepare results ----
3994	        # NOTE: if an intervening EMPTY batch cleared input_batch, we must
3995	        # fall through to the normal path so _update_states can re-
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:58:02</sup>


---

## Assistant <sup>2026/8/6 22:58:02</sup>

让我看看缓存是在哪里被填充的 (segment_a)，以及在 L4327 处的后续使用情况。


---

## Assistant <sup>2026/8/6 22:58:03</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== _edge_prepare_cache_by_token populate + use ===\"; grep -nE \"_edge_prepare_cache_by_token|_cloud_prepare_cache|segment_a|segment_e\" vllm_ascend/worker/model_runner_v1.py | head -30",
  "description": "Find cache populate and segment_a/e refs"
}
```

</details>


---

## User <sup>2026/8/6 22:58:04</sup>

<details>
<summary>Tool Result</summary>

```
=== _edge_prepare_cache_by_token populate + use ===
815:            self.segment_a: Any = None
816:            self.segment_e: Any = None
819:            self.segment_a_wrapper: Any = None
820:            self.segment_e_wrapper: Any = None
822:            # Cache segment_a prepare results for segment_e reuse.  Entries
825:            self._edge_prepare_cache_by_token: dict[str, dict[str, Any]] = {}
827:            # Cache cloud-side prepare results to overlap with edge segment_a
828:            self._cloud_prepare_cache: dict | None = None
1180:            self.segment_a: Any = None
1181:            self.segment_e: Any = None
1184:            self.segment_a_wrapper: Any = None
1185:            self.segment_e_wrapper: Any = None
1187:            # Cache segment_a prepare results for segment_e reuse (edge-cloud
1190:            # an earlier chunk's cache before its segment_e consumes it: each
1191:            # segment_a stores under its own head_token, and the matching
1192:            
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:58:09</sup>


---

## Assistant <sup>2026/8/6 22:58:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== where segment_a stores into the cache ===\"; grep -nE \"_edge_prepare_cache_by_token\\[|_edge_prepare_cache_by_token\\.update|_edge_prepare_cache_by_token\\.setdefault|_store_segment_a|segment_a.*cache|cache\\[\\\"total\" vllm_ascend/worker/model_runner_v1.py | head; echo \"\"; echo \"=== L4320-4340 (_fast_path use at end) ===\"; sed -n '4320,4345p' vllm_ascend/worker/model_runner_v1.py",
  "description": "Find cache store and end usage"
}
```

</details>


---

## User <sup>2026/8/6 22:58:12</sup>

<details>
<summary>Tool Result</summary>

```
=== where segment_a stores into the cache ===
1193:            # segment_a would clobber chunk-0's cache while chunk-0's segment_e
3909:                    # The segment_a prepare cache was built for the FULL
3993:        # ---- segment_e fast path: reuse segment_a's cached prepare results ----
4035:            total_num_scheduled_tokens = cache["total_num_scheduled_tokens"]
4061:            total_num_scheduled_tokens = cache["total_num_scheduled_tokens"]
4256:                    total_num_scheduled_tokens = cache["total_num_scheduled_tokens"]
4376:                #     "Edge segment_a cache exceeded bound (%d); evicting oldest "
4397:            self._edge_prepare_cache_by_token[scheduler_output.head_token] = (
6298:        if cache["total_num_scheduled_tokens"] == 0:

=== L4320-4340 (_fast_path use at end) ===
                model_kwargs,
                ec_connector_output,
            ) = self._preprocess(
                scheduler_output,
                num_tokens_padded,
      
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:58:34</sup>


---

## Assistant <sup>2026/8/6 22:58:34</sup>

让我查看一下 segment_a 的 cache-store 端，以便全面了解情况。


---

## Assistant <sup>2026/8/6 22:58:35</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 35,
  "offset": 4370
}
```

</details>


---

## User <sup>2026/8/6 22:58:35</sup>

<details>
<summary>Tool Result</summary>

```
4370	            if (
4371	                len(self._edge_prepare_cache_by_token)
4372	                >= self._edge_prepare_cache_max
4373	            ):
4374	                stale_token = next(iter(self._edge_prepare_cache_by_token))
4375	                # logger.warning(
4376	                #     "Edge segment_a cache exceeded bound (%d); evicting oldest "
4377	                #     "head_token=%s (its segment_e likely never arrived, e.g. "
4378	                #     "request abort).",
4379	                #     self._edge_prepare_cache_max,
4380	                #     stale_token,
4381	                # )
4382	                self._edge_prepare_cache_by_token.pop(stale_token, None)
4383	
4384	            cache_entry = {
4385	                "num_tokens_padded": num_tokens_padded,
4386	                "num_tokens_across_dp": num_tokens_across_dp,
4387	                "attn_metadata": attn_metadata,
4388	                "logits_indices": logits_indices,
4389	                "spec_dec
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 22:59:01</sup>


---

## Assistant <sup>2026/8/6 22:59:22</sup>

## `_fast_path` 流程分析

`_fast_path` 是边云 PD 分离里**边侧尾段（segment_e / PREFILL_LAST）的预处理快速路径**，位于 [model_runner_v1.py:3997](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L3997)。核心思想：**边侧把一个 prefill 拆成 segment_a（头）和 segment_e（尾），中间夹着云侧计算；segment_e 直接复用 segment_a 缓存的预处理结果，不重算。**

### 为什么需要它

边云 prefill 的拆分：
- **segment_a**（边头，PREFILL_FIRST）：算 embedding + 前若干层，把 hidden 发给云。
- **云侧**（中间）：算中间层，把 hidden 发回边。
- **segment_e**（边尾，PREFILL_LAST）：收 hidden，算最后几层 + lm_head，采样第一个 token。

segment_a 和 segment_e 是**同一个 prefill 请求**的两半，但跑在**两次独立的 execute_model**里，中间还会插别的 batch（decode、别的 prefill）-> `input_batch` 被搅动。segment_e 需要的和 segment_a 一样的 `attn_metadata / positions / logits_indices / batch_desc / cudagraph_mode` 等，如果在 segment_e 里重算 `_prepareInputs`，既贵又会因为 `input_batch` 已被搅动而算错。所以 segment_a 把这些结果**缓存**起来，segment_e **直接取用**。

### 存入侧（segment_a，[L4370-4399](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L4370-L4399)）

segment_a 的 `_preprocess` 末尾，把算好的 `attn_metadata / positions / logits_indices / batch_desc / cudagraph_mode / cudagraph_stats / spec_decode_metadata / num_tokens_padded / total_num_scheduled_tokens` 等打包，用 `_freeze_scheduled_state` 冻结后存入：
```python
self._edge_prepare_cache_by_token[scheduler_output.head_token] = cache_entry
```
按 **head_token** 做 key（这样 chunk-prefill 时 chunk-1 的 segment_a 不会覆盖 chunk-0 还没被 segment_e 消费的缓存）；有上限 `_edge_prepare_cache_max`，超了淘汰最老的（防止 segment_e 永不到来——比如请求 abort——导致泄漏）。

### 取用侧（segment_e 快速路径，[L3993-4057](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L3993-L4057)）

进入条件：
```python
_fast_path = (
    self._edge_cloud_enabled
    and self.edge_cloud_cfg.role == "edge"
    and intermediate_tensors is not None                       # 已收到云侧 hidden
    and scheduler_output.head_token in self._edge_prepare_cache_by_token  # segment_a 缓存还在
    and self.input_batch.num_reqs > 0                          # 没被 EMPTY batch 清空
)
```
命中后：
1. **pop** 该 head_token 的缓存（避免后续别的 segment_a 错配给本 PL）。
2. **修正被搅动的 input_batch**：如果中间插的 decode 把 req_ids 改得和本尾段调度的 reqs 不一致，调 `_update_states` 把 prefill 请求重新加回，让尾段能采样/记录首 token；但**布局元数据（attn_metadata 等）仍用缓存的、不重算**。req_ids 已匹配则跳过（避免重复计数）。
3. **复用缓存**的全部预处理结果（attn_metadata / logits_indices / batch_desc / cudagraph_mode / …）。
4. **重同步 num_computed_tokens**：从 CPU 拷回 GPU（除非 `use_async_spec_decode`——此时 segment_a 已用实际接受 token 数纠正过 GPU buffer，不能再被调度器的乐观 CPU 镜像覆盖）。
5. **跳过**正常 `_prepareInputs`（`if not _fast_path and not _cloud_fast_path:` 分支，L4086）。

### 退出 `_preprocess` 后的补救（[L4324-4328](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L4324-L4328)）

```python
if _fast_path:
    # _preprocess reads the runner's reusable positions buffer, which may have
    # been rewritten by an interleaved batch even though the metadata cache
    # itself is keyed by head_token.
    positions = cache["positions"]
```
即：缓存的元数据本身按 head_token 隔离没问题，但 `_preprocess` 内部读的是 runner 的**可复用 positions buffer**，这个 buffer 可能被中间交错的 batch 改写了，所以出来后要**用缓存里的 positions 覆盖回去**。

### 相邻的 `_cloud_fast_path`（[L4005-4082](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L4005-L4082)）

云侧对称的快速路径：云侧把预处理结果存进 `_cloud_prepare_cache`，下次取用，用于把云侧预处理和边侧 segment_a 重叠。命中后复用缓存 + 在与慢路径相同的 post-launch 点应用遗留的 deferred 状态修正。

### 与精度问题 / 交错的关系

`_fast_path` 正是处理“prefill_first / prefill_last 之间插 decode”的核心机制：它要正确应对 `input_batch` 被中间 decode 搅动的情况（步骤 2 重新加请求、步骤 5 覆盖 positions）。历史上这里出过精度 bug：

- **`6fbd8606`（临时修复 qwen s1w1 多模态精度）** 改的是尾段 `num_computed_tokens` 同步（`_skip_tail_sync`，[L2376-2383](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L2376-L2383)）：尾段复用头段已纠正的 GPU `num_computed_tokens`、跳过同步，只在 `embedding_only` 或 `async_spec_decode` 下安全；**head_tail + 非_spec_decode 的尾段必须走慢路径同步**，否则 PD 交错搅动 input_batch 时，尾段 `_update_states` 只刷新 CPU 的 `num_computed_tokens`、GPU buffer 还是头段批次的旧值 -> positions/seq_lens/slot_mapping 错位 -> KV cache 写错槽 -> 整批腐败。

### 和我们之前查的 send/recv buffer 竞态的区别

- `_fast_path` 管的是**预处理元数据的跨段复用**（attn_metadata / positions / num_computed_tokens），是**逻辑层面**的“尾段拿头段算好的布局”。
- 我们修的（per-key clone / recv record_stream）是**设备 buffer 的跨步生命周期**（模型输出 buffer 被 isend 读、recv buffer 被异步 copy 读），是**物理层面**的“发送/接收缓冲不要被下一轮覆写”。

两者都只在“交错”场景下暴露，但是不同层面的竞态。`_fast_path` 本身有针对交错的修正（重新加请求、覆盖 positions、`_skip_tail_sync` 门控）；如果当前还残留精度问题，值得核查 `_fast_path` 的这些交错修正在你的 1P1D 配置下是否都被正确触发（尤其 `num_computed_tokens` 走的是快路径还是慢路径、positions 覆盖是否生效）。

要不要我顺着 `_fast_path` 把这几处交错修正（req_ids 不匹配时的 `_update_states`、positions 覆盖、`_skip_tail_sync` 门控）在你 1P1D + async_scheduling 下的实际命中情况核一遍？


---

## User <sup>2026/8/6 23:15:29</sup>

需要


---

## Assistant <sup>2026/8/6 23:16:08</sup>


---

## Assistant <sup>2026/8/6 23:16:09</sup>

让我根据您的配置（edge 1-card embedding_only, 1P1D, async_scheduling）来验证这三个 `_fast_path` 交错修正。首先，读取 `_skip_tail_sync` 逻辑，并找出 `_is_edge_cloud_tail_segment` 和 `use_async_spec_decode` 是如何设置的。


---

## Assistant <sup>2026/8/6 23:16:10</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 45,
  "offset": 2355
}
```

</details>


---

## User <sup>2026/8/6 23:16:10</sup>

<details>
<summary>Tool Result</summary>

```
2355	        # Update num_computed_tokens on GPU. In async spec decode,
2356	        # CPU values are optimistic (all drafts accepted). The kernel
2357	        # corrects on GPU using the previous step's
2358	        # valid_sampled_token_count_gpu. Otherwise, just copy from CPU.
2359	        # Edge-cloud tail segments reuse the GPU num_computed_tokens
2360	        # corrected by their head segment, so the sync below is normally
2361	        # skipped. That reuse is only safe when a re-sync would be wrong or
2362	        # unneeded:
2363	        #   * embedding_only: the edge has no attention layers, so stale
2364	        #     positions / seq_lens / slot_mapping cannot corrupt attention.
2365	        #   * async spec decode (MTP/eagle3): the head already wrote THIS
2366	        #     step's corrected values into the GPU buffer; re-running the
2367	        #     correction kernel on the tail reads those already-corrected
2368	        #     values (buffer indices overlap) and double-cou
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 23:16:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== _is_edge_cloud_tail_segment setting ===\"; grep -nE \"_is_edge_cloud_tail_segment\" vllm_ascend/worker/model_runner_v1.py | head; echo \"\"; echo \"=== use_async_spec_decode setting ===\"; grep -nE \"use_async_spec_decode\\s*=|self.use_async_spec_decode\" vllm_ascend/worker/model_runner_v1.py | head; echo \"\"; echo \"=== num_spec_tokens / spec decode config ===\"; grep -nE \"num_spec_tokens|speculative_config|async_scheduling\\s*=\" vllm_ascend/worker/model_runner_v1.py | head",
  "description": "Find tail segment flag and spec decode config"
}
```

</details>


---

## User <sup>2026/8/6 23:16:13</sup>

<details>
<summary>Tool Result</summary>

```
=== _is_edge_cloud_tail_segment setting ===
grep: vllm_ascend/worker/model_runner_v1.py: No such file or directory

=== use_async_spec_decode setting ===
grep: vllm_ascend/worker/model_runner_v1.py: No such file or directory

=== num_spec_tokens / spec decode config ===
grep: vllm_ascend/worker/model_runner_v1.py: No such file or directory
```

</details>


---

## Assistant <sup>2026/8/6 23:16:19</sup>


---

## Assistant <sup>2026/8/6 23:16:20</sup>

`grep` 操作因为 `cwd` 重置又失败了。让我重新运行一下。


---

## Assistant <sup>2026/8/6 23:16:21</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd /c/v0.23.0_lwd_acc_test_br/vllm-ascend && echo \"=== _is_edge_cloud_tail_segment ===\"; grep -nE \"_is_edge_cloud_tail_segment\" vllm_ascend/worker/model_runner_v1.py | head; echo \"\"; echo \"=== use_async_spec_decode = ===\"; grep -nE \"self\\.use_async_spec_decode\\s*=|use_async_scheduling\\s*=\" vllm_ascend/worker/model_runner_v1.py | head; echo \"\"; echo \"=== num_spec_tokens (spec decode on?) ===\"; grep -nE \"num_spec_tokens|self\\.num_spec_tokens\" vllm_ascend/worker/model_runner_v1.py | head -5",
  "description": "Find tail flag and spec decode config"
}
```

</details>


---

## User <sup>2026/8/6 23:16:23</sup>

<details>
<summary>Tool Result</summary>

```
=== _is_edge_cloud_tail_segment ===
780:        self._is_edge_cloud_tail_segment = False
2377:            self._is_edge_cloud_tail_segment
3933:        self._is_edge_cloud_tail_segment = (

=== use_async_spec_decode = ===

=== num_spec_tokens (spec decode on?) ===
915:        if self.use_async_scheduling and self.num_spec_tokens:
1759:            num_spec_tokens = int(self.num_spec_tokens or 0)
1760:            if num_spec_tokens <= 0:
1773:                num_spec_tokens,
2148:                self.num_spec_tokens,
```

</details>


---

## Assistant <sup>2026/8/6 23:16:29</sup>


---

## Assistant <sup>2026/8/6 23:16:29</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 22,
  "offset": 3925
}
```

</details>


---

## User <sup>2026/8/6 23:16:29</sup>

<details>
<summary>Tool Result</summary>

```
3925	        self._last_scheduler_output = scheduler_output
3926	
3927	        # In edge-cloud mode, execute_model is called twice for the
3928	        # same scheduler_output: head segment (intermediate_tensors is None) and
3929	        # tail segment (intermediate_tensors is not None). The tail segment should
3930	        # reuse the num_computed_tokens corrected by the head segment, instead of
3931	        # re-running update_num_computed_tokens_for_batch_change or copying the
3932	        # potentially optimistic CPU value back to GPU.
3933	        self._is_edge_cloud_tail_segment = (
3934	            self._edge_cloud_enabled
3935	            and self.edge_cloud_cfg.role == "edge"
3936	            and intermediate_tensors is not None
3937	        )
3938	
3939	        # If ngram_gpu is used, we need to copy the scheduler_output to avoid
3940	        # the modification has influence on the scheduler_output in engine core process.
3941	        # The replace is much faster than deepcop
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/6 23:16:30</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== use_async_spec_decode definition (parent GPUModelRunner) ===\"; grep -rnE \"def use_async_spec_decode|use_async_spec_decode\" vllm/vllm/v1/worker/gpu_model_runner.py 2>/dev/null | head; echo \"\"; echo \"=== num_spec_tokens source ===\"; grep -rnE \"self\\.num_spec_tokens\\s*=|num_spec_tokens\\s*=\" vllm/vllm/v1/worker/gpu_model_runner.py 2>/dev/null | head",
  "description": "Find use_async_spec_decode and num_spec_tokens def"
}
```

</details>


---

## User <sup>2026/8/6 23:16:32</sup>

<details>
<summary>Tool Result</summary>

```
=== use_async_spec_decode definition (parent GPUModelRunner) ===

=== num_spec_tokens source ===
```

</details>


---

## Assistant <sup>2026/8/6 23:16:39</sup>


---

## Assistant <sup>2026/8/6 23:16:40</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rnE \"def use_async_spec_decode|use_async_spec_decode\\s*=|self\\.use_async_spec_decode\" vllm/vllm/ 2>/dev/null | grep -viE \"test\" | head; echo \"\"; echo \"=== where num_spec_tokens is set ===\"; grep -rnE \"num_spec_tokens\\s*=\" vllm/vllm/v1/worker/gpu_model_runner.py 2>/dev/null | head",
  "description": "Find use_async_spec_decode property"
}
```

</details>


---

## User <sup>2026/8/6 23:16:42</sup>

<details>
<summary>Tool Result</summary>

```
=== where num_spec_tokens is set ===
```

</details>


---

## Assistant <sup>2026/8/6 23:16:48</sup>


---

## Assistant <sup>2026/8/6 23:16:48</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rnE \"use_async_spec_decode\" vllm/vllm/ 2>/dev/null | grep -viE \"test\" | head -10; echo \"---\"; grep -rnE \"num_spec_tokens\" vllm/vllm/v1/worker/gpu_model_runner.py 2>/dev/null | head -5",
  "description": "Search whole vllm tree for use_async_spec_decode"
}
```

</details>


---

## User <sup>2026/8/6 23:16:50</sup>

<details>
<summary>Tool Result</summary>

```
---
```

</details>


---

## Assistant <sup>2026/8/6 23:17:00</sup>


---

## Assistant <sup>2026/8/6 23:17:02</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rnE \"async_spec_decode|spec_decode\" vllm/vllm/v1/worker/gpu_model_runner.py 2>/dev/null | head -8; echo \"=== maybe a property ===\"; grep -rnE \"def use_async_spec_decode|@property\" vllm/vllm/v1/worker/gpu_model_runner.py 2>/dev/null | head; echo \"=== vllm-ascend override? ===\"; grep -rnE \"use_async_spec_decode\" /c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ 2>/dev/null | grep -iE \"def |=|property\" | head",
  "description": "Locate use_async_spec_decode definition"
}
```

</details>


---

## User <sup>2026/8/6 23:17:04</sup>

<details>
<summary>Tool Result</summary>

```
=== maybe a property ===
=== vllm-ascend override? ===
/c/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:2423:                use_async_spec_decode=self.use_async_spec_decode,
```

</details>


---

## Assistant <sup>2026/8/6 23:17:57</sup>


---

## Assistant <sup>2026/8/6 23:18:15</sup>

核完了。先说结论：**在你这套配置（边侧 1 卡 embedding_only、1P1D、async_scheduling）下，`_fast_path` 的三处交错修正都会被触发，且对 embedding_only 是正确的--`_fast_path` 不是精度问题来源；精度问题仍是 send/recv 的设备 buffer 竞态（已由 per-key clone + recv record_stream 修）。** 下面逐条核对。

## 配置前提（请确认）

- 边侧 `role == "edge"`、`mode == "embedding_only"`：是（你说的）。
- `use_async_spec_decode`：你没开 spec decode（MTP/eagle3）的话为 False。**但对本结论不影响**--`_skip_tail_sync` 的第一个条件 `mode == "embedding_only"` 已经成立，与 spec decode 无关。
- segment_e = 边侧 PREFILL_LAST（收云侧 hidden、跑 lm_head+采样首 token）。

## 1. `_fast_path` 是否命中：是

[_is_edge_cloud_tail_segment](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L3933)（L3933-3937）= edge + role=edge + `intermediate_tensors is not None`。对 PREFILL_LAST（收到云侧 hidden）= True。

`_fast_path`（[L3997-4003](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L3997-L4003)）四个条件全满足：edge 云开启、role=edge、`intermediate_tensors` 非空、`head_token` 在 segment_a 缓存里、`input_batch.num_reqs>0`。**命中**，走复用缓存、跳过正常 `_prepareInputs`。

## 2. 交错 decode 搅动 input_batch -> 重新加请求：会触发

[L4027-4031](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L4027-L4031)：`tuple(input_batch.req_ids) != tuple(scheduler_output.num_scheduled_tokens)` 时调 `_update_states` 把 prefill 请求加回。中间插了 decode 就会把 input_batch 的 req_ids 改掉 -> 不匹配 -> 触发重新加请求。**交错时正确触发**；不交错时 req_ids 已匹配 -> 跳过（避免重复计数）。

⚠️ 一个潜在逻辑风险（不是 buffer 竞态）：缓存的 `logits_indices / attn_metadata` 是 segment_a 时刻按当时 input_batch 的**请求下标**算的。`_update_states` 重新加请求后，若该 prefill 请求在 input_batch 里的**下标变了**，缓存的 indices/attn_metadata 仍按旧下标 -> 可能错位。代码注释（L4018-4026）假设“缓存布局仍正确”，这依赖重新加请求后下标不变。**如果 per-key clone + recv record_stream 跑完仍不到 98，这是下一个要查的逻辑点**（加日志看 re-add 后 req 的 index 是否和缓存里一致）。

## 3. positions 覆盖：会应用

[L4326-4328](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L4326-L4328)：`_preprocess` 返回后，若 `_fast_path`，`positions = cache["positions"]`。因为 `_preprocess` 内部读的是 runner 的**可复用 positions buffer**（被中间 decode 改写过），所以用缓存里的 prefill positions 覆盖回去。**交错时正确应用**。

## 4. `_skip_tail_sync`（num_computed_tokens 同步跳过）：True，且对 embedding_only 安全

[L2376-2383](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L2376-L2383)：
```python
_skip_tail_sync = (
    self._is_edge_cloud_tail_segment          # True（边尾段）
    and (self.edge_cloud_cfg.mode == "embedding_only"  # True
         or self.use_async_spec_decode)       # 与你无关
)
```
= True -> **跳过** num_computed_tokens 的 CPU->GPU 同步/纠正 kernel，复用头段已纠正的 GPU 值。

对 embedding_only 这是**安全的**（注释 L2363-2364）：边侧没有 attention 层，stale 的 positions/seq_lens/slot_mapping 不会污染 attention（没有 attention 可污染）。这正是 `6fbd8606` 临时修复显式允许 embedding_only 跳过的原因。**所以这条对你不会引入精度问题。**

> 对比：如果是 `head_tail`（非 embedding_only）+ 非 spec decode 的尾段，`_skip_tail_sync=False`，强制走慢路径同步--因为那种尾段有 attention，PD 交错搅动 input_batch 时 GPU buffer 会留头段批次的旧值 -> positions/seq_lens/slot_mapping 错位 -> KV 写错槽 -> 整批腐败（注释 L2370-2375 说的就是这个）。你不在这种情况。

## 总结

| 修正 | 你的配置下 | 正确性 |
|---|---|---|
| `_fast_path` 命中 | 是 | -- |
| req_ids 不匹配 -> `_update_states` 重加请求 | 交错时触发 | 正确（但见下标风险） |
| positions 覆盖 | 应用 | 正确 |
| `_skip_tail_sync` | True（embedding_only） | 安全（边侧无 attention） |

`_fast_path` 这条线在你的 embedding_only 配置下是自洽的，**不是 82->98 那段残留的来源**。残留仍是设备 buffer 竞态，应由已加的 per-key clone + recv record_stream 修掉。

**建议**：先把当前这版（per-key clone + recv record_stream）跑出来看分数。
- 到 98：`_fast_path` 无需再动，收工。
- 还差：优先查上面第 2 条的**下标一致性**（re-add 请求后 req index 是否与缓存里的 logits_indices/attn_metadata 对得上）--那是个逻辑错位，和 buffer 竞态不同，得加非同步日志看 index。

要我现在就把“re-add 后 req index 一致性”的非同步探针准备好（先不插，等分数出来再决定插不插）吗？


---
