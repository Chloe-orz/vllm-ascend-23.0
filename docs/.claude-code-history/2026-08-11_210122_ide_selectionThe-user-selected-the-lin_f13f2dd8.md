# Claude Code Session

> **Resume in CLI:** `claude --resume f13f2dd8-1b8a-4bb8-86e0-6dd49e41955f`

| Field | Value |
|---|---|
| **Project** | `c:\v0\23\0-lwd-acc-test-br` |
| **Session ID** | `f13f2dd8-1b8a-4bb8-86e0-6dd49e41955f` |
| **Working Dir** | `c:\v0.23.0_lwd_acc_test_br` |
| **Started** | 2026/8/10 12:48:50 |
| **Last Updated** | 2026/8/11 21:05:34 |
| **Messages** | 686 |

---

## User <sup>2026/8/10 12:48:50</sup>

<ide_selection>The user selected the lines 40 to 40 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\patch\platform\patch_dp_device_ids.py:
get_physical_gpu_ids_for_local_dp_rank

This may or may not be related to the current task.</ide_selection>

File "/vllm-workspace/vllm-ascend/vllm_ascend/init.py", line 51, in register_connector
_ensure_global_patch()
File "/vllm-workspace/vllm-ascend/vllm_ascend/init.py", line 34, in _ensure_global_patch
adapt_patch(is_global_patch=True)
File "/vllm-workspace/vllm-ascend/vllm_ascend/utils.py", line 565, in adapt_patch
from vllm_ascend.patch import platform # noqa: F401
File "/vllm-workspace/vllm-ascend/vllm_ascend/patch/platform/init.py", line 70, in
import vllm_ascend.patch.platform.patch_dp_device_ids # noqa
File "/vllm-workspace/vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py", line 40, in
_original_get_physical_gpu_ids = _engine_utils.get_physical_gpu_ids_for_local_dp_rank
AttributeError: module 'vllm.v1.engine.utils' has no attribute 'get_physical_gpu_ids_for_local_dp_rank'


---

## Assistant <sup>2026/8/10 12:48:55</sup>


---

## Assistant <sup>2026/8/10 12:48:55</sup>

I'll investigate this error. The patch is trying to monkey-patch a function that doesn't exist in the installed vllm version. Let me look at both the patch file and the actual vllm module.


---

## Assistant <sup>2026/8/10 12:48:55</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\patch\\platform\\patch_dp_device_ids.py"
}
```

</details>


---

## User <sup>2026/8/10 12:48:55</sup>

<details>
<summary>Tool Result</summary>

```
1	#
2	# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
3	# This file is a part of the vllm-ascend project.
4	#
5	# Licensed under the Apache License, Version 2.0 (the "License");
6	# you may not use this file except in compliance with the License.
7	# You may obtain a copy of the License at
8	#
9	#     http://www.apache.org/licenses/LICENSE-2.0
10	#
11	# Unless required by applicable law or agreed to in writing, software
12	# distributed under the License is distributed on an "AS IS" BASIS,
13	# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
14	# See the License for the specific language governing permissions and
15	# limitations under the License.
16	#
17	# Patch vLLM v0.24.0+ ``get_physical_gpu_ids_for_local_dp_rank`` so that it
18	# tolerates a pre-sharded ASCEND_RT_VISIBLE_DEVICES env var (one slice per
19	# DP rank), instead of unconditionally applying ``local_dp_rank * world_size``
20	# as an offset into it.
21	#
22	# Background:
2
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:48:55</sup>

<details>
<summary>Tool: <code>Glob</code></summary>

```json
{
  "pattern": "**/v1/engine/utils.py"
}
```

</details>


---

## User <sup>2026/8/10 12:48:56</sup>

<details>
<summary>Tool Result</summary>

```
vllm\tests\v1\engine\utils.py
vllm\vllm\v1\engine\utils.py
```

</details>


---

## Assistant <sup>2026/8/10 12:48:58</sup>


---

## Assistant <sup>2026/8/10 12:48:58</sup>

Let me look at the actual vllm `v1/engine/utils.py` to see what functions exist there.


---

## Assistant <sup>2026/8/10 12:48:58</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\engine\\utils.py"
}
```

</details>


---

## User <sup>2026/8/10 12:48:58</sup>

<details>
<summary>Tool Result</summary>

```
1	# SPDX-License-Identifier: Apache-2.0
2	# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
3	
4	import contextlib
5	import os
6	import threading
7	import weakref
8	from collections.abc import Callable, Iterator
9	from dataclasses import dataclass
10	from enum import Enum, auto
11	from multiprocessing import Process, connection
12	from multiprocessing.process import BaseProcess
13	from multiprocessing.queues import Queue
14	from typing import TYPE_CHECKING, cast
15	from unittest.mock import patch
16	
17	import msgspec
18	import zmq
19	
20	from vllm import envs
21	from vllm.config import CacheConfig, ParallelConfig, VllmConfig
22	from vllm.logger import init_logger
23	from vllm.platforms import current_platform
24	from vllm.ray.ray_env import get_env_vars_to_copy
25	from vllm.utils import numa_utils
26	from vllm.utils.network_utils import (
27	    get_open_port,
28	    get_open_zmq_ipc_path,
29	    get_tcp_uri,
30	    zmq_socket_ctx,
31	)
32	from vllm.utils.system_uti
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:48:59</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"get_physical_gpu_ids_for_local_dp_rank\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/\" 2>/dev/null | head -50",
  "description": "Find references to get_physical_gpu_ids_for_local_dp_rank in vllm"
}
```

</details>


---

## User <sup>2026/8/10 12:49:09</sup>

<details>
<summary>Tool Result</summary>

```
(Bash completed with no output)
```

</details>


---

## Assistant <sup>2026/8/10 12:49:15</sup>


---

## Assistant <sup>2026/8/10 12:49:16</sup>

Now I understand the core issue. Let me check the `vllm_version_is` utility and the installed vllm version to understand the version guard logic.


---

## Assistant <sup>2026/8/10 12:49:16</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"vllm_version_is\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/utils.py\" | head -20",
  "description": "Find vllm_version_is definition"
}
```

</details>


---

## Assistant <sup>2026/8/10 12:49:17</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm\" && git log --oneline -5 2>/dev/null; echo \"---VERSION---\"; cat vllm/version.py 2>/dev/null | grep -i version; echo \"---SETUP---\"; grep -i \"version\" setup.py 2>/dev/null | head -5",
  "description": "Check vllm git log and version"
}
```

</details>


---

## User <sup>2026/8/10 12:49:17</sup>

<details>
<summary>Tool Result</summary>

```
610:def vllm_version_is(target_vllm_version: str):
763:    if vllm_version_is("0.23.0"):
812:        if vllm_version_is("0.23.0"):
```

</details>


---

## User <sup>2026/8/10 12:50:00</sup>

<details>
<summary>Tool Result</summary>

```
88c9c117d Merge pull request #9 from theroadtofree/v0.20.2_lwd_update_dpds_0730_mtp
424025204 !3 merge v0.23.0_0807 into v0.23.0_lwd
fdb27dc0c 迁移dpds修改
78e4d2896 !2 merge v0.23.0_0803 into v0.23.0_lwd
03475406f !1 merge qwen_accuracy_fix_0806 into v0.23.0_lwd
---VERSION---
    from ._version import __version__, __version_tuple__
    __version__ = "dev"
    __version_tuple__ = (0, 0, __version__)
def _prev_minor_version_was(version_str):
    """Check whether a given version matches the previous minor version.
    Return True if version_str matches the previous minor version.
    For example - return True if the current version if 0.7.4 and the
    supplied version_str is '0.6'.
    Used for --show-hidden-metrics-for-version.
    if __version_tuple__[0:2] == (0, 0):
    assert __version_tuple__[0] == 0
    assert isinstance(__version_tuple__[1], int)
    return version_str == f"{__version_tuple__[0]}.{__version_tuple__[1] - 1}"
def _prev_minor_version():
    """For the purpose of testing
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:50:02</sup>


---

## Assistant <sup>2026/8/10 12:50:03</sup>

Let me read the `vllm_version_is` function and check how version detection works for a "dev" checkout.


---

## Assistant <sup>2026/8/10 12:50:03</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\utils.py",
  "limit": 60,
  "offset": 605
}
```

</details>


---

## User <sup>2026/8/10 12:50:03</sup>

<details>
<summary>Tool Result</summary>

```
605	
606	    os.environ["ASCEND_LOCAL_COMM_RES"] = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
607	
608	
609	@functools.cache
610	def vllm_version_is(target_vllm_version: str):
611	    if envs_ascend.VLLM_VERSION is not None:
612	        vllm_version = envs_ascend.VLLM_VERSION
613	    else:
614	        import vllm
615	
616	        vllm_version = vllm.__version__
617	    try:
618	        return Version(vllm_version) == Version(target_vllm_version)
619	    except InvalidVersion:
620	        raise ValueError(
621	            f"Invalid vllm version {vllm_version} found. A dev version of vllm "
622	            "is installed probably. Set the environment variable VLLM_VERSION "
623	            "to control it by hand. And please make sure the value follows the "
624	            "format of x.y.z."
625	        )
626	
627	
628	def get_max_hidden_layers(hf_config) -> int:
629	    cfg_dict = hf_config.to_dict()
630	    layer_counts = []
631	
632	    def _rec_find(d):
633	        if
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:50:04</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm\" && python -c \"from vllm.version import __version__, __version_tuple__; print('version:', repr(__version__)); print('tuple:', repr(__version_tuple__))\" 2>&1 | head -20",
  "description": "Check actual vllm version at runtime"
}
```

</details>


---

## User <sup>2026/8/10 12:50:07</sup>

<details>
<summary>Tool Result</summary>

```
C:\v0.23.0_lwd_acc_test_br\vllm\vllm\__init__.py:7: RuntimeWarning: Failed to read commit hash:
No module named 'vllm._version'
  from .version import __version__, __version_tuple__  # isort:skip
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    from vllm.version import __version__, __version_tuple__; print('version:', repr(__version__)); print('tuple:', repr(__version_tuple__))
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\v0.23.0_lwd_acc_test_br\vllm\vllm\__init__.py", line 14, in <module>
    import vllm.env_override  # noqa: F401
    ^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\v0.23.0_lwd_acc_test_br\vllm\vllm\env_override.py", line 87, in <module>
    import torch
ModuleNotFoundError: No module named 'torch'
```

</details>


---

## Assistant <sup>2026/8/10 12:50:21</sup>


---

## Assistant <sup>2026/8/10 12:50:21</sup>

Let me check how `VLLM_VERSION` env var is determined in vllm_ascend's envs, since that takes precedence in version detection.


---

## Assistant <sup>2026/8/10 12:50:22</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"VLLM_VERSION\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/envs.py\" 2>/dev/null",
  "description": "Find VLLM_VERSION definition in envs.py"
}
```

</details>


---

## Assistant <sup>2026/8/10 12:50:22</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"get_physical_gpu_ids_for_local_dp_rank\\|get_device_indices\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null",
  "description": "Find all references to these function names in vllm-ascend"
}
```

</details>


---

## User <sup>2026/8/10 12:50:23</sup>

<details>
<summary>Tool Result</summary>

```
68:    "VLLM_VERSION": lambda: os.getenv("VLLM_VERSION", None),
```

</details>


---

## User <sup>2026/8/10 12:50:23</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py:17:# Patch vLLM v0.24.0+ ``get_physical_gpu_ids_for_local_dp_rank`` so that it
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py:40:    _original_get_physical_gpu_ids = _engine_utils.get_physical_gpu_ids_for_local_dp_rank
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py:42:    def _patched_get_physical_gpu_ids_for_local_dp_rank(
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py:72:    _engine_utils.get_physical_gpu_ids_for_local_dp_rank = _patched_get_physical_gpu_ids_for_local_dp_rank
```

</details>


---

## Assistant <sup>2026/8/10 12:50:37</sup>


---

## Assistant <sup>2026/8/10 12:50:37</sup>

Let me look at how the platform patch module loads these patches and how sibling patches handle version guards, to match the existing style.


---

## Assistant <sup>2026/8/10 12:50:38</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\patch\\platform\\__init__.py"
}
```

</details>


---

## User <sup>2026/8/10 12:50:38</sup>

<details>
<summary>Tool Result</summary>

```
1	#
2	# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
3	# This file is a part of the vllm-ascend project.
4	#
5	# Licensed under the Apache License, Version 2.0 (the "License");
6	# you may not use this file except in compliance with the License.
7	# You may obtain a copy of the License at
8	#
9	#     http://www.apache.org/licenses/LICENSE-2.0
10	#
11	# Unless required by applicable law or agreed to in writing, software
12	# distributed under the License is distributed on an "AS IS" BASIS,
13	# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
14	# See the License for the specific language governing permissions and
15	# limitations under the License.
16	
17	import vllm_ascend.patch.platform.patch_camem_allocator  # noqa
18	import vllm_ascend.patch.platform.patch_distributed  # noqa
19	import vllm_ascend.patch.platform.patch_kv_cache_utils  # noqa
20	import vllm_ascend.patch.platform.patch_mla_prefill_backend  # noqa
21	import vllm_ascend.p
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:50:41</sup>


---

## Assistant <sup>2026/8/10 12:50:41</sup>

Let me check the sibling patch `patch_fused_moe.py` (also gated on `if not vllm_version_is("0.23.0")`) to see how it handles attribute presence, and look at the git history of this patch file.


---

## Assistant <sup>2026/8/10 12:50:42</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "head -60 \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_fused_moe.py\" 2>/dev/null",
  "description": "Read top of patch_fused_moe.py"
}
```

</details>


---

## User <sup>2026/8/10 12:50:43</sup>

<details>
<summary>Tool Result</summary>

```
#
# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
# This file is a part of the vllm-ascend project.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# Patch vllm's FusedMoE factory to use AscendMoERunner by default.
#
# vllm's FusedMoE is a factory function (not a class). deepseek_v2 and other
# models do `from vllm.model_executor.layers.fused_moe import FusedMoE` and
# call it directly, so we must patch the binding in the package __init__ as
# well as the layer module be
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:50:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && git log --oneline -8 -- vllm_ascend/patch/platform/patch_dp_device_ids.py 2>/dev/null; echo \"---SHOW FILE CREATE COMMIT---\"; git log --oneline --diff-filter=A -- vllm_ascend/patch/platform/patch_dp_device_ids.py 2>/dev/null",
  "description": "Git history of the patch file"
}
```

</details>


---

## User <sup>2026/8/10 12:50:46</sup>

<details>
<summary>Tool Result</summary>

```
05e095a20 [CI] main2mian v0.24.0 (#11227)
---SHOW FILE CREATE COMMIT---
05e095a20 [CI] main2mian v0.24.0 (#11227)
```

</details>


---

## Assistant <sup>2026/8/10 12:51:13</sup>


---

## Assistant <sup>2026/8/10 12:51:13</sup>

I now have a clear picture. Let me verify the version-detection hypothesis by checking the git tags and setuptools_scm configuration in the vllm checkout.


---

## Assistant <sup>2026/8/10 12:51:15</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm\" && echo \"=== TAGS (nearest) ===\"; git tag --sort=-creatordate 2>/dev/null | head -10; echo \"=== describe ===\"; git describe --tags --dirty 2>/dev/null; echo \"=== commits since v0.23.0 tag ===\"; git rev-list --count v0.23.0..HEAD 2>/dev/null || echo \"(no v0.23.0 tag found)\"",
  "description": "Check git tags and describe for version inference"
}
```

</details>


---

## Assistant <sup>2026/8/10 12:51:16</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"version_file\\|version_file_template\\|write_to\\|tag_regex\" \"c:/v0.23.0_lwd_acc_test_br/vllm/pyproject.toml\" 2>/dev/null | head; echo \"=== _version.py exists? ===\"; ls -la \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/_version.py\" 2>/dev/null || echo \"NO _version.py (will fall back to setuptools_scm dynamic / 'dev')\"",
  "description": "Check setuptools_scm version config"
}
```

</details>


---

## User <sup>2026/8/10 12:51:35</sup>

<details>
<summary>Tool Result</summary>

```
=== TAGS (nearest) ===
=== describe ===
=== commits since v0.23.0 tag ===
(no v0.23.0 tag found)
```

</details>


---

## User <sup>2026/8/10 12:51:36</sup>

<details>
<summary>Tool Result</summary>

```
=== _version.py exists? ===
NO _version.py (will fall back to setuptools_scm dynamic / 'dev')
```

</details>


---

## Assistant <sup>2026/8/10 12:51:46</sup>


---

## Assistant <sup>2026/8/10 12:51:46</sup>

Let me confirm whether `VLLM_VERSION` is set anywhere in launch scripts or docs, and check the full envs context.


---

## Assistant <sup>2026/8/10 12:51:47</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"VLLM_VERSION\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20",
  "description": "Find all VLLM_VERSION usages in vllm-ascend"
}
```

</details>


---

## Assistant <sup>2026/8/10 12:51:47</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\envs.py",
  "limit": 20,
  "offset": 60
}
```

</details>


---

## User <sup>2026/8/10 12:51:47</sup>

<details>
<summary>Tool Result</summary>

```
60	    # not set, the default value is libhccl.so.
61	    "HCCL_SO_PATH": lambda: os.getenv("HCCL_SO_PATH", None),
62	    # The version of vllm is installed. This value is used for developers who
63	    # installed vllm from source locally. In this case, the version of vllm is
64	    # usually changed. For example, if the version of vllm is "0.9.0", but when
65	    # it's installed from source, the version of vllm is usually set to "0.9.1".
66	    # In this case, developers need to set this value to "0.9.0" to make sure
67	    # that the correct package is installed.
68	    "VLLM_VERSION": lambda: os.getenv("VLLM_VERSION", None),
69	    # Whether to enable MatmulAllReduce fusion kernel when tensor parallel is enabled.
70	    # this feature is supported in A2, and eager mode will get better performance.
71	    "VLLM_ASCEND_ENABLE_MATMUL_ALLREDUCE": lambda: bool(int(os.getenv("VLLM_ASCEND_ENABLE_MATMUL_ALLREDUCE", "0"))),
72	    # Whether to enable FlashComm optimization when tensor para
...(truncated)
```

</details>


---

## User <sup>2026/8/10 12:51:48</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/.agents/skills/vllm-ascend-release/references/version-files.yaml:69:      - variable: VLLM_VERSION
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/.agents/skills/vllm-ascend-release/references/version-files.yaml:75:      - variable: VLLM_VERSION
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/.agents/skills/vllm-ascend-release/references/version-files.yaml:96:  - "grep 'VLLM_VERSION' .github/workflows/*.yml  # Check CI workflow versions"
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/.agents/skills/vllm-ascend-release/scripts/update_version_references.py:104:            # Handle variable-based updates (e.g., VLLM_VERSION in workflow files)
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/.agents/skills/vllm-ascend-release/scripts/update_version_references.py:109:                # YAML: VLLM_VERSION: "0.15.0"
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/.agents/skills/vllm-ascend-release/scripts/update_version_references.py:114:                # Shell: VLLM_VERSION=0.15.0
c:/v0.23.0_lwd_ac
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 12:52:17</sup>


---

## Assistant <sup>2026/8/10 12:52:27</sup>

## Root cause

The crash is a **version-detection failure**, not a bug in the patch logic itself.

[patch_dp_device_ids.py](vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py) is a **v0.24.0-only** patch. It monkey-patches `get_physical_gpu_ids_for_local_dp_rank`, a function that was *renamed* in vLLM v0.24.0+ (per the comment, PR #45026). In your vLLM 0.23.0 codebase that same function is still called `get_device_indices` — see [vllm/v1/engine/utils.py:310](vllm/vllm/v1/engine/utils.py#L310). So the attribute doesn't exist, and line 40 raises `AttributeError`.

The guard that's *supposed* to skip this patch on 0.23.0 is at [patch_dp_device_ids.py:34](vllm-ascend/vllm_ascend/patch/platform/patch_dp_device_ids.py#L34):

```python
if not vllm_version_is("0.23.0"):
```

It let the patch through, which means `vllm_version_is("0.23.0")` returned **False** even though your vLLM *is* 0.23.0. That function ([utils.py:610](vllm-ascend/vllm_ascend/utils.py#L610)) does an **exact** PEP 440 equality check: `Version(vllm.__version__) == Version("0.23.0")`. You're running a dev/editable vLLM build (the checkout has no `_version.py` and no git tags, so setuptools_scm reports something like `0.23.0.devN+g…`), which parses fine but is **not equal** to `0.23.0` — so the guard fails.

This is the exact scenario documented in the repo: [docs/source/faqs.md:136](vllm-ascend/docs/source/faqs.md#L136) and [patch.md:76](vllm-ascend/docs/source/developer_guide/Design_Documents/patch.md#L76).

## Fix

Set the environment variable before launching vLLM:

```bash
export VLLM_VERSION=0.23.0
# then run your workload as usual
```

`vllm_version_is` checks `VLLM_VERSION` first ([envs.py:68](vllm-ascend/vllm_ascend/envs.py#L68)), so this forces it to identify the install as 0.23.0. The `if not vllm_version_is("0.23.0")` guard at [platform/__init__.py:68-70](vllm-ascend/vllm_ascend/patch/platform/__init__.py#L68-L70) then correctly **skips** `patch_dp_device_ids`, and the crash goes away.

This is the right root-cause fix for another reason: the *same* failed detection is silently mis-selecting **every other** version-gated patch too — e.g. the `if vllm_version_is("0.23.0")` block at [platform/__init__.py:39-42](vllm-ascend/vllm_ascend/patch/platform/__init__.py#L39-L42) (glm47/minimax tool-call parsers, minimax usage accounting) is being **skipped** on your 0.23.0 build. Those don't crash only because their target symbols happen to still exist; they just run the wrong variant — exactly the kind of silent drift you don't want on an accuracy-test branch. Setting `VLLM_VERSION=0.23.0` corrects all of them at once.

## Confirm the diagnosis

On the container, before setting anything:

```bash
python -c "import vllm; print(repr(vllm.__version__))"
echo "VLLM_VERSION=${VLLM_VERSION:-<unset>}"
```

You'll see a version string that isn't exactly `0.23.0` (and/or `VLLM_VERSION` unset/wrong). After `export VLLM_VERSION=0.23.0`, the import succeeds.

---

One optional hardening note (not needed to unblock you): the patch could guard on `hasattr(_engine_utils, "get_physical_gpu_ids_for_local_dp_rank")` instead of relying solely on the version string, so a dev-version mismatch degrades to a no-op rather than a crash. I'd only make that change if you want defense-in-depth; on its own it would mask this symptom while leaving the broader mis-selection above uncorrected, so `VLLM_VERSION=0.23.0` is the fix that actually matters. Want me to apply the `hasattr` hardening as well?


---

## User <sup>2026/8/10 15:43:25</sup>

<ide_selection>The user selected the lines 1956 to 1956 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py:
uniform_decode

This may or may not be related to the current task.</ide_selection>

C:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py的1956行uniform_decode表示什么意思


---

## Assistant <sup>2026/8/10 15:43:37</sup>


---

## Assistant <sup>2026/8/10 15:43:37</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 120,
  "offset": 1900
}
```

</details>


---

## User <sup>2026/8/10 15:43:37</sup>

<details>
<summary>Tool Result</summary>

```
1900	            if (
1901	                kv_cache_config.needs_kv_cache_zeroing
1902	                and hasattr(self.model_runner, "_init_kv_zero_meta")
1903	                and self.vllm_config is not None
1904	                and self.vllm_config.speculative_config is not None
1905	                and self.vllm_config.speculative_config.method == "eagle3"
1906	                and self.vllm_config.speculative_config.num_speculative_tokens > 1
1907	            ):
1908	                self.model_runner._init_kv_zero_meta()
1909	
1910	    def profile(self, is_start: bool = True, profile_prefix: str | None = None):
1911	        # Check if profiling is enabled (RFC #6954 - align with upstream vLLM)
1912	        if self.profiler_config is None or self.profiler_config.profiler is None:
1913	            raise RuntimeError(
1914	                "Profiling is not enabled. Please set --profiler-config to enable "
1915	                "profiling. Example: "
1916	                "'--profiler-co
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:43:41</sup>


---

## Assistant <sup>2026/8/10 15:43:41</sup>

`uniform_decode` 是传递给 `_dummy_run` 的参数。让我查一下 `_dummy_run` 中是如何使用 `uniform_decode` 的。


---

## Assistant <sup>2026/8/10 15:43:42</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"uniform_decode\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -40",
  "description": "Find all uniform_decode references"
}
```

</details>


---

## User <sup>2026/8/10 15:43:44</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1331:        uniform_decode_query_len: int = 1,
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1402:            and uniform_decode_query_len > 1
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1432:        # Adjust cudagraph sizes to be a multiple of uniform_decode_query_len
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1439:            and uniform_decode_query_len > 1
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1442:                uniform_decode_query_len,
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1474:        self, uniform_decode_query_len: int, tensor_parallel_size: int
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1476:        multiple_of = uniform_decode_query_len
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/config/compilation.py:1478:            multiple_of = max(uniform_decode_query_len, tensor_parallel_size)
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/co
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:43:48</sup>


---

## Assistant <sup>2026/8/10 15:43:49</sup>

我来查看一下关键的定义，以便准确解释该参数的含义。


---

## Assistant <sup>2026/8/10 15:43:49</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu_model_runner.py",
  "limit": 60,
  "offset": 3805
}
```

</details>


---

## User <sup>2026/8/10 15:43:49</sup>

<details>
<summary>Tool Result</summary>

```
3805	            **model_kwargs,
3806	        )
3807	
3808	    @staticmethod
3809	    def _is_uniform_decode(
3810	        max_num_scheduled_tokens: int,
3811	        uniform_decode_query_len: int,
3812	        num_tokens: int,
3813	        num_reqs: int,
3814	        force_uniform_decode: bool | None = None,
3815	    ) -> bool:
3816	        """
3817	        Checks if it's a decode batch with same amount scheduled tokens
3818	        across all requests.
3819	        """
3820	        return (
3821	            (
3822	                (max_num_scheduled_tokens == uniform_decode_query_len)
3823	                and (num_tokens == max_num_scheduled_tokens * num_reqs)
3824	            )
3825	            if force_uniform_decode is None
3826	            else force_uniform_decode
3827	        )
3828	
3829	    def _determine_batch_execution_and_padding(
3830	        self,
3831	        num_tokens: int,
3832	        num_reqs: int,
3833	        num_scheduled_tokens_np: np.ndarray,
3834	        max_n
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:43:50</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\worker\\gpu\\model_runner.py",
  "limit": 45,
  "offset": 490
}
```

</details>


---

## User <sup>2026/8/10 15:43:50</sup>

<details>
<summary>Tool Result</summary>

```
490	
491	    @torch.inference_mode()
492	    @step_eplb_after(is_dummy=True)
493	    def _dummy_run(
494	        self,
495	        num_tokens: int,
496	        *args,
497	        skip_attn: bool = False,
498	        uniform_decode: bool = False,
499	        skip_eplb: bool = False,
500	        is_profile: bool = False,
501	        **kwargs,
502	    ) -> tuple[torch.Tensor | None, torch.Tensor | None]:
503	        if skip_attn and not is_profile:
504	            raise ValueError(
505	                "skip_attn must only be True for initial memory profiling."
506	            )
507	
508	        # Create a dummy scheduler output.
509	        num_reqs = min(num_tokens, self.max_num_reqs)
510	        if uniform_decode:
511	            # HACK(lucas): for now since the worker is shared between MRV1 and MRV2,
512	            # and for spec-decode with MTP we want to make sure the dummy runs use
513	            # 1+num_speculative_tokens we use max here, this will likely be eventually
514	      
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:43:54</sup>


---

## Assistant <sup>2026/8/10 15:43:54</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\cudagraph_dispatcher.py",
  "limit": 45,
  "offset": 135
}
```

</details>


---

## User <sup>2026/8/10 15:43:55</sup>

<details>
<summary>Tool Result</summary>

```
135	
136	    def _create_padded_batch_descriptor(
137	        self,
138	        num_tokens: int,
139	        uniform_decode: bool,
140	        has_lora: bool,
141	        num_active_loras: int = 0,
142	    ) -> BatchDescriptor:
143	        max_num_seqs = self.vllm_config.scheduler_config.max_num_seqs
144	        uniform_decode_query_len = self.uniform_decode_query_len
145	        num_tokens_padded = self._bs_to_padded_graph_size[num_tokens]
146	
147	        if uniform_decode and self.cudagraph_mode.has_mode(CUDAGraphMode.FULL):
148	            num_reqs = min(num_tokens_padded // uniform_decode_query_len, max_num_seqs)
149	            assert num_tokens_padded % uniform_decode_query_len == 0
150	        else:
151	            uniform_decode = False
152	            num_reqs = min(num_tokens_padded, max_num_seqs)
153	
154	        return BatchDescriptor(
155	            num_tokens=num_tokens_padded,
156	            num_reqs=num_reqs,
157	            uniform=uniform_decode,
158	            ha
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:43:55</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\cudagraph_dispatcher.py",
  "limit": 70,
  "offset": 240
}
```

</details>


---

## User <sup>2026/8/10 15:43:55</sup>

<details>
<summary>Tool Result</summary>

```
240	        self,
241	        num_tokens: int,
242	        uniform_decode: bool = False,
243	        has_lora: bool = False,
244	        num_active_loras: int = 0,
245	        valid_modes: AbstractSet[CUDAGraphMode] | None = None,
246	        invalid_modes: AbstractSet[CUDAGraphMode] | None = None,
247	    ) -> tuple[CUDAGraphMode, BatchDescriptor]:
248	        """
249	        Given conditions(e.g.,batch descriptor and if using piecewise only),
250	        dispatch to a cudagraph runtime mode and the valid batch descriptor.
251	        A new batch descriptor is returned as we might dispatch a uniform batch
252	        to a graph that supports a more general batch (uniform to non-uniform).
253	
254	        Args:
255	            num_tokens: Number of tokens in the batch.
256	            uniform_decode: Whether the batch is uniform decode (i.e. uniform and query
257	                length is uniform_decode_query_len).
258	            has_lora: Whether LoRA is active.
259	            num_a
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:44:00</sup>


---

## Assistant <sup>2026/8/10 15:44:00</sup>

我来检查一下 Ascend 特有的 `decode_token_per_req` 和 `decode_query_len`，以完善对 `execute_dummy_batch` 的说明。


---

## Assistant <sup>2026/8/10 15:44:01</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"decode_token_per_req\\|decode_query_len\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20",
  "description": "Find decode_token_per_req definition in ascend"
}
```

</details>


---

## User <sup>2026/8/10 15:44:02</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py:202:def set_mc2_tokens_capacity(vllm_config, max_num_reqs, uniform_decode_query_len):
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py:211:        max_num_tokens = max_num_reqs * uniform_decode_query_len
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/sfa_cp.py:79:        decode_query_lens: torch.Tensor,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/sfa_cp.py:82:        decode_query_lens_cpu = decode_query_lens.to(device="cpu", dtype=torch.int64, non_blocking=True)
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/sfa_cp.py:83:        total_valid_tokens = int(decode_query_lens_cpu.sum().item())
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/sfa_cp.py:86:        decode_query_lens = decode_query_lens_cpu.to(device=device, dtype=torch.int64, non_blocking=True)
c:/v0.
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:44:08</sup>


---

## Assistant <sup>2026/8/10 15:44:09</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\attention\\utils.py",
  "limit": 55,
  "offset": 225
}
```

</details>


---

## User <sup>2026/8/10 15:44:09</sup>

<details>
<summary>Tool Result</summary>

```
225	    # E.g., tensor([128, 256, 64]) for 3 requests with different seq lengths.
226	    seq_lens_cpu: torch.Tensor = None
227	
228	    # CPU tensor of already computed tokens count per request.
229	    # E.g., tensor([100, 200, 50]) means req0 has 100 tokens already computed.
230	    num_computed_tokens_cpu: torch.Tensor = None
231	
232	    # Number of decode tokens per request, used for speculative decoding.
233	    # E.g., 1 for normal decoding, >1 for speculative decoding.
234	    decode_token_per_req: int = 1
235	
236	    # Actual query sequence lengths for each token in the batch (CPU list).
237	    # E.g., [1, 1, 1, 128] for 3 decode tokens and 1 prefill with 128 tokens.
238	    actual_seq_lengths_q: list[int] = field(default_factory=list)
239	
240	    # NPU tensor of position indices for rotary embeddings computation.
241	    # E.g., tensor([0, 1, 2, ...]) indicating token positions in sequence.
242	    positions: torch.Tensor = None
243	    positions_cpu: torch.Tensor = None

...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:44:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"decode_token_per_req\\s*=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | grep -v \"decode_token_per_req: int\" | head -20",
  "description": "Find where decode_token_per_req is assigned"
}
```

</details>


---

## User <sup>2026/8/10 15:44:11</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/utils.py:274:            decode_token_per_req=self.decode_token_per_req,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/spec_decode/dflash_proposer.py:140:            cad.decode_token_per_req = num_query_per_req
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/spec_decode/llm_base_proposer.py:656:                decode_token_per_req=self.runner.decode_token_per_req,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/spec_decode/llm_base_proposer.py:1689:            common_attn_metadata.decode_token_per_req = 1
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/spec_decode/llm_base_proposer.py:2011:            decode_token_per_req=self.runner.decode_token_per_req,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/spec_decode/llm_base_proposer.py:2120:            decode_token_per_req=self.runner.decode_token_per_req,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/spec_decode/step3p5.py:276:                decode_toke
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:44:14</sup>


---

## Assistant <sup>2026/8/10 15:44:15</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 12,
  "offset": 1284
}
```

</details>


---

## User <sup>2026/8/10 15:44:15</sup>

<details>
<summary>Tool Result</summary>

```
1284	            | None
1285	        ) = None
1286	        self.actual_seq_lengths_q: list[int] = []
1287	        self.decode_token_per_req = 1
1288	        if self.speculative_config:
1289	            spec_token_num = self.speculative_config.num_speculative_tokens
1290	            assert spec_token_num > 0
1291	            self.decode_token_per_req = 1 + spec_token_num
1292	            if get_pp_group().is_last_rank or (
1293	                self._edge_cloud_enabled
1294	                and self.speculative_config.method in ("mtp", "eagle3")
1295	            ):
```

</details>


---

## Assistant <sup>2026/8/10 15:44:41</sup>


---

## Assistant <sup>2026/8/10 15:44:42</sup>

让我确认一下 Ascend 的 model runner 是如何处理带有 `uniform_decode` 的 `_dummy_run` 的，以便我准确地归因于该行为。


---

## Assistant <sup>2026/8/10 15:44:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"def _dummy_run\\|uniform_decode\\|decode_query_len\\b\\|decode_token_per_req\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head -30",
  "description": "Check ascend model_runner_v1 _dummy_run and uniform_decode handling"
}
```

</details>


---

## User <sup>2026/8/10 15:44:44</sup>

<details>
<summary>Tool Result</summary>

```
1039:        set_cos_and_sin(vllm_config, self.max_num_reqs, self.uniform_decode_query_len, self.dtype, self.device)
1040:        set_mc2_tokens_capacity(vllm_config, self.max_num_reqs, self.uniform_decode_query_len)
1072:            self.eplb_pd_thresholds = self.max_num_reqs * self.uniform_decode_query_len
1287:        self.decode_token_per_req = 1
1291:            self.decode_token_per_req = 1 + spec_token_num
2114:            num_tokens_padded == num_reqs_padded * self.uniform_decode_query_len
2122:                self.arange_np[1 : num_reqs_padded + 1 - num_reqs] * self.uniform_decode_query_len + last_loc
2680:            max_num_reqs_across_dp = self.max_num_reqs * self.uniform_decode_query_len
4298:                            num_tokens=self.decode_token_per_req,
4299:                            uniform_decode=False,
5887:            common_attn_metadata.decode_token_per_req = 1
7881:        force_uniform_decode: bool | None = None,
7891:        uniform_decode = (
7894:         
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:44:48</sup>


---

## Assistant <sup>2026/8/10 15:44:49</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 100,
  "offset": 8342
}
```

</details>


---

## User <sup>2026/8/10 15:44:49</sup>

<details>
<summary>Tool Result</summary>

```
8342	    def _dummy_run(
8343	        self,
8344	        num_tokens: int,
8345	        with_prefill: bool = False,
8346	        cudagraph_runtime_mode: CUDAGraphMode | None = None,
8347	        force_attention: bool = False,
8348	        uniform_decode: bool = False,
8349	        is_profile: bool = False,
8350	        create_mixed_batch: bool = False,
8351	        allow_microbatching: bool = True,
8352	        skip_eplb: bool = False,
8353	        remove_lora: bool = True,
8354	        is_graph_capturing: bool = False,
8355	        num_active_loras: int = 0,
8356	        profile_seq_lens: int | None = None,
8357	        profile_cpp: bool = False,
8358	        layer_slice_info: Any = None,
8359	    ) -> tuple[torch.Tensor, torch.Tensor]:
8360	        # only support eager mode and piecewise graph now
8361	        assert cudagraph_runtime_mode is None or cudagraph_runtime_mode.valid_runtime_modes()
8362	
8363	        # [SLICE-DIAG] Log whether _dummy_run receives layer_slice_info.
8364	  
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:44:49</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 45,
  "offset": 7878
}
```

</details>


---

## User <sup>2026/8/10 15:44:49</sup>

<details>
<summary>Tool Result</summary>

```
7878	        force_eager: bool = False,
7879	        # For cudagraph capture TODO(lucas): Refactor how we capture cudagraphs (will
7880	        # be improved in model runner v2)
7881	        force_uniform_decode: bool | None = None,
7882	        force_has_lora: bool | None = None,
7883	        force_num_active_loras: int | None = None,
7884	        num_encoder_reqs: int = 0,
7885	        for_cudagraph_capture: bool = False,
7886	    ) -> tuple[CUDAGraphMode, BatchDescriptor, bool, torch.Tensor | None, CUDAGraphStat | None]:
7887	        num_tokens_padded = self._pad_for_sequence_parallelism(
7888	            num_tokens, for_cudagraph_capture=for_cudagraph_capture
7889	        )
7890	        is_all_decode = np.all(self.input_batch.num_computed_tokens_cpu[:num_reqs] > 0)
7891	        uniform_decode = (
7892	            (
7893	                (is_all_decode if self.speculative_config else True)
7894	                and (max_num_scheduled_tokens == self.uniform_decode_query_len)
7895	     
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:45:04</sup>


---

## Assistant <sup>2026/8/10 15:45:18</sup>

`uniform_decode` 是传给 `_dummy_run` 的一个布尔参数,表示**「均匀解码批次」(uniform decode batch)**。下面分定义、为什么重要、在这行具体做什么三部分说明。

## 1. 定义:什么叫「均匀解码批次」

它指批次里**每个 request 调度的 token 数完全相同**,且恰好等于 `uniform_decode_query_len`:

- 普通解码:`uniform_decode_query_len = 1`
- 投机解码(MTP / EAGLE):`uniform_decode_query_len = 1 + num_speculative_tokens`

判定条件见 [model_runner_v1.py:7891-7898](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7891-L7898)(与上游 `_is_uniform_decode` 等价):

```python
uniform_decode = (
    (max_num_scheduled_tokens == self.uniform_decode_query_len)
    and (num_tokens == max_num_scheduled_tokens * num_reqs)
)
```

即「每个 request 都是 `uniform_decode_query_len` 个 token,总数 = `uniform_decode_query_len × num_reqs`」,是一个形状完全规整的纯解码批次。Ascend 侧在 [model_runner_v1.py:1287-1291](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L1287-L1291) 把它存为 `decode_token_per_req`(`= 1` 或 `1 + spec_token_num`),正是 worker.py 第 1956 行传给 `_dummy_run` 的 `num_tokens`。

## 2. 为什么这是个值得单独标记的概念

因为形状规整,均匀解码批次可以走一条**专门的、更优化的 cudagraph / attention 路径**(FULL 模式 + `separate_routine()`)。Ascend 的 `_dummy_run` 注释说得很清楚,见 [model_runner_v1.py:8378-8390](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8378-L8390):

> A uniform decode batch means that all requests have identical query length… Uniform decode batch could either be common pure decode, where max_query_len == 1, or speculative decode, where max_query_len == 1 + num_spec_decode_tokens. When setting max_query_len = 1, we switch to and capture the optimized routine of FA2 for pure decode, i.e., Flashdecode + an optimization for GQA/MQA.

对应到 cudagraph dispatcher,`uniform_decode=True` 会让 `BatchDescriptor` 标记为 `uniform=True`,从而按「每 request = `uniform_decode_query_len` 个 token」的方式选图(见 [cudagraph_dispatcher.py:147-157](vllm/vllm/v1/cudagraph_dispatcher.py#L147-L157))。

## 3. 在第 1956 行具体做了什么

```python
def execute_dummy_batch(self) -> None:
    self.model_runner._dummy_run(
        num_tokens=self.model_runner.decode_token_per_req,
        uniform_decode=True,
    )
```

`uniform_decode=True` 会让 `_dummy_run` 按「均匀解码」来构造这个 dummy 批次(见 [model_runner_v1.py:8391-8403](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8391-L8403)):

- `max_query_len = self.uniform_decode_query_len`(否则会取 `num_tokens`)
- `num_scheduled_tokens_list = [max_query_len] * num_reqs`,即每个 request 都分到相同的 token 数
- 把 `force_uniform_decode=uniform_decode` 传给 `_determine_batch_execution_and_padding`,强制 cudagraph 走均匀解码的捕获/分发路径([model_runner_v1.py:8435](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8435))

因为 `num_tokens = decode_token_per_req`(一个 request 的解码 token 数),所以这是在跑一个**最小的均匀解码 dummy forward**(1 个 request、`decode_token_per_req` 个 token),目的是**预热 / 预捕获均匀解码执行路径及其 cudagraph**,让真实解码步走到这条优化路径时已经是「热」的,避免首次命中时的捕获/编译开销。

一句话总结:**`uniform_decode=True` 告诉 `_dummy_run`「按均匀解码批次(每 request query length = 1+投机token数)来构造并走优化的解码专用图路径」,而不是按一般的混合 prefill-decode 批次处理。**


---

## User <sup>2026/8/10 15:49:06</sup>

<ide_selection>The user selected the lines 1956 to 1956 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py:
PD-separation

This may or may not be related to the current task.</ide_selection>

C:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py的execute_dummy_batch实现已经被修改了，原因是边云PD-separation场景，dp


---

## User <sup>2026/8/10 15:49:08</sup>

[Request interrupted by user]


---

## User <sup>2026/8/10 15:49:59</sup>

<ide_selection>The user selected the lines 1975 to 1975 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py:
uniform_decode

This may or may not be related to the current task.</ide_selection>

C:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py的execute_dummy_batch实现已经被修改了，边云PD-separation场景，dp并行场景将uniform_decode从True修改成False，分析一下原因


---

## Assistant <sup>2026/8/10 15:50:16</sup>


---

## Assistant <sup>2026/8/10 15:50:17</sup>

让我读取一下 `execute_dummy_batch` 的当前状态，并查看 `git` 历史记录以了解具体的修改内容。


---

## Assistant <sup>2026/8/10 15:50:17</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"execute_dummy_batch\\|uniform_decode\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/worker.py\" 2>/dev/null | head -20",
  "description": "Find execute_dummy_batch and uniform_decode in worker.py"
}
```

</details>


---

## User <sup>2026/8/10 15:50:18</sup>

<details>
<summary>Tool Result</summary>

```
1204:            uniform_decode=False,
1258:                uniform_decode=False,
1955:    def execute_dummy_batch(self, layer_slice_info: Any = None) -> None:
1956:        # PD-separation: use uniform_decode=False (prefill-style attention)
1964:            "[SLICE-DIAG] execute_dummy_batch entry: layer_slice_info=%s "
1975:            uniform_decode=False,
```

</details>


---

## Assistant <sup>2026/8/10 15:50:19</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && git log --oneline -10 -- vllm_ascend/worker/worker.py 2>/dev/null; echo \"=== blame on execute_dummy_batch ===\"; git log -p -S \"execute_dummy_batch\" --oneline -- vllm_ascend/worker/worker.py 2>/dev/null | head -60",
  "description": "Git history and blame for execute_dummy_batch"
}
```

</details>


---

## User <sup>2026/8/10 15:53:52</sup>

<details>
<summary>Tool Result</summary>

```
02e1dc2a5 Merge pull request #21 from theroadtofree/v0.20.2_lwd_update_dpds_0730_mtp
b9bcbd34c 修正迁移
2e862b002 迁移dpds修改
459a0b8d7 feat(edge-cloud): scale PD channels across DP ranks
76cb1584c 修复多模态流量结束后纯文本请求卡死（cloud include_mrope决策改用盖戳）
a8eecf42b qwen多模态适配+qwen emonly精度修复
bd9ecf15e fix kimi s1w1 accuracy
dfd4230cb 扩展模型适配范围
73ef9424a 增加残差传输
ee3be21fc feat:边云修改 - 第三部分
=== blame on execute_dummy_batch ===
b69b04d3a implement model runner v2 basic framework (#5051)
diff --git a/vllm_ascend/worker/worker.py b/vllm_ascend/worker/worker.py
new file mode 100644
index 000000000..de23efa7e
--- /dev/null
+++ b/vllm_ascend/worker/worker.py
@@ -0,0 +1,501 @@
+#
+# Copyright (c) 2025 Huawei Technologies Co., Ltd. All Rights Reserved.
+# Copyright 2023 The vLLM team.
+#
+# Licensed under the Apache License, Version 2.0 (the "License");
+# you may not use this file except in compliance with the License.
+# You may obtain a copy of the License at
+#
+#     http://www.apache.org/licenses/LICENSE-2.0
+#
+
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:53:56</sup>


---

## Assistant <sup>2026/8/10 15:53:57</sup>

我来阅读一下当前完整的 `execute_dummy_batch` 实现。


---

## Assistant <sup>2026/8/10 15:53:57</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 45,
  "offset": 1955
}
```

</details>


---

## User <sup>2026/8/10 15:53:57</sup>

<details>
<summary>Tool Result</summary>

```
1955	    def execute_dummy_batch(self, layer_slice_info: Any = None) -> None:
1956	        # PD-separation: use uniform_decode=False (prefill-style attention)
1957	        # instead of True (decode-style). Decode attention reads from the KV
1958	        # cache which has real data from previous forwards, causing softmax
1959	        # overflow -> NaN when the dummy's query (from zero input) interacts
1960	        # with large real KV values. Prefill-style attention is causal (only
1961	        # writes KV, doesn't read), avoiding the NaN.
1962	        _lsi = layer_slice_info
1963	        logger.info(
1964	            "[SLICE-DIAG] execute_dummy_batch entry: layer_slice_info=%s "
1965	            "is_first=%s is_last=%s start=%s end=%s total=%s",
1966	            type(_lsi).__name__ if _lsi is not None else "None",
1967	            getattr(_lsi, "is_first_slice", None) if _lsi is not None else None,
1968	            getattr(_lsi, "is_last_slice", None) if _lsi is not None else None,
196
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:54:07</sup>


---

## Assistant <sup>2026/8/10 15:54:08</sup>

代码注释解释了机制。让我深入研究一下*为什么*这会出现在 PD-separation + DP 场景中：谁调用了 `execute_dummy_batch`，以及它是在何时被调用的。我来找一下调用者和相关的 git 提交记录。


---

## Assistant <sup>2026/8/10 15:54:09</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"execute_dummy_batch\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/\" 2>/dev/null | grep -v \"\\.pyc\" | grep -v \"def execute_dummy_batch\"",
  "description": "Find callers of execute_dummy_batch"
}
```

</details>


---

## Assistant <sup>2026/8/10 15:54:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && git log -p -S \"PD-separation: use uniform_decode=False\" --oneline -- vllm_ascend/worker/worker.py 2>/dev/null | head -80",
  "description": "Find commit that introduced the False change"
}
```

</details>


---

## User <sup>2026/8/10 15:54:10</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/core/passive_scheduler.py:297:            # (from _patched_execute_dummy_batch / _publish_pd_dummy_zmq) is
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_balance_schedule.py:636:                self.execute_dummy_batch()
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py:352:    ``_patched_execute_dummy_batch`` / ``_publish_pd_dummy_zmq``) bypass
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py:1394:# EngineCore.execute_dummy_batch - 方案③: route dummy per-DP via zmq.       #
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py:1396:def _patched_execute_dummy_batch(self):
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py:1402:    Cloud workers skip the cross-node ``execute_dummy_batch`` (see
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_engine_c
...(truncated)
```

</details>


---

## User <sup>2026/8/10 15:54:11</sup>

<details>
<summary>Tool Result</summary>

```
(Bash completed with no output)
```

</details>


---

## Assistant <sup>2026/8/10 15:54:16</sup>


---

## Assistant <sup>2026/8/10 15:54:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && git status --short vllm_ascend/worker/worker.py 2>/dev/null; echo \"=== diff vs HEAD for execute_dummy_batch ===\"; git diff HEAD -- vllm_ascend/worker/worker.py 2>/dev/null | head -80",
  "description": "Check if change is committed or working-tree"
}
```

</details>


---

## User <sup>2026/8/10 15:54:19</sup>

<details>
<summary>Tool Result</summary>

```
M vllm_ascend/worker/worker.py
=== diff vs HEAD for execute_dummy_batch ===
diff --git a/vllm_ascend/worker/worker.py b/vllm_ascend/worker/worker.py
index 1116ebb05..3271846a0 100644
--- a/vllm_ascend/worker/worker.py
+++ b/vllm_ascend/worker/worker.py
@@ -1952,8 +1952,30 @@ class NPUWorker(WorkerBase):
     def reset_encoder_cache(self) -> None:
         self.model_runner.reset_encoder_cache()
 
-    def execute_dummy_batch(self) -> None:
-        self.model_runner._dummy_run(num_tokens=self.model_runner.decode_token_per_req, uniform_decode=True)
+    def execute_dummy_batch(self, layer_slice_info: Any = None) -> None:
+        # PD-separation: use uniform_decode=False (prefill-style attention)
+        # instead of True (decode-style). Decode attention reads from the KV
+        # cache which has real data from previous forwards, causing softmax
+        # overflow -> NaN when the dummy's query (from zero input) interacts
+        # with large real KV values. Prefill-style attention
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:54:27</sup>


---

## Assistant <sup>2026/8/10 15:54:28</sup>

这是工作区中未提交的更改。注释解释了 NaN 的机制。现在我需要分析*为什么这会特别在 PD-separation + DP 中出现*。让我来查看一下 PD-separation 的 dummy-batch 流程以及调用者。


---

## Assistant <sup>2026/8/10 15:54:28</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\patch\\platform\\patch_engine_core.py",
  "limit": 130,
  "offset": 1380
}
```

</details>


---

## User <sup>2026/8/10 15:54:28</sup>

<details>
<summary>Tool Result</summary>

```
1380	            break
1381	        if not block:
1382	            break
1383	
1384	    if waited:
1385	        logger.debug("EngineCore loop active.")
1386	
1387	    # Handle any more client requests.
1388	    while not self.input_queue.empty():
1389	        req = self.input_queue.get_nowait()
1390	        self._handle_client_request(*req)
1391	
1392	
1393	# =======================================================================#
1394	# EngineCore.execute_dummy_batch - 方案③: route dummy per-DP via zmq.       #
1395	# =======================================================================#
1396	def _patched_execute_dummy_batch(self):
1397	    """PD-separation edge: mirror execute_model's per-DP zmq path so the
1398	    idle DP's dummy does NOT reach the cloud via the cross-node
1399	    rpc_broadcast_mq broadcast (which would deliver it to the DP running
1400	    real work and break cross-DP all_reduce pairing -> deadlock).
1401	
1402	    Cloud workers skip the cross-node ``execute_dumm
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:55:02</sup>


---

## Assistant <sup>2026/8/10 15:55:03</sup>

现在让我来确认一下关键的不对称性：在常规（非 PD）流程与 PD-separation 流程中，`execute_dummy_batch` 分别是在*什么时候*触发的，以及 DP 是如何产生空闲秩（idle-rank）场景的。


---

## Assistant <sup>2026/8/10 15:55:03</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\engine\\core.py",
  "limit": 25,
  "offset": 1935
}
```

</details>


---

## User <sup>2026/8/10 15:55:03</sup>

<details>
<summary>Tool Result</summary>

```
1935	
1936	                if self._is_coordinated_dp():
1937	                    # Cross-DP coordination already produces dummy
1938	                    # SchedulerOutputs (via _schedule_target) when pairing is
1939	                    # needed; reaching here with not-executed means both DPs
1940	                    # are waiting for cloud (winner=EMPTY). Do NOT self-drive
1941	                    # a dummy - that reintroduces the count-drift deadlock.
1942	                    # Yield briefly and wait for cloud to return work.
1943	                    time.sleep(0.001)
1944	                else:
1945	                    # We are in a running state and so must execute a dummy pass
1946	                    # if the model didn't execute any ready requests.
1947	                    with self.log_iteration_details(None):
1948	                        self.execute_dummy_batch()
1949	
1950	            # 3) All-reduce operation to determine global unfinished reqs.
1951	            self.engines
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:55:04</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\engine\\llm_engine.py",
  "limit": 30,
  "offset": 180
}
```

</details>


---

## User <sup>2026/8/10 15:55:04</sup>

<details>
<summary>Tool Result</summary>

```
180	        return self.output_processor.get_num_unfinished_requests()
181	
182	    def has_unfinished_requests(self) -> bool:
183	        has_unfinished = self.output_processor.has_unfinished_requests()
184	        if self.dp_group is None:
185	            return has_unfinished or self.engine_core.dp_engines_running()
186	        return self.has_unfinished_requests_dp(has_unfinished)
187	
188	    def has_unfinished_requests_dp(self, has_unfinished: bool) -> bool:
189	        aggregated_has_unfinished = ParallelConfig.has_unfinished_dp(
190	            self.dp_group, has_unfinished
191	        )
192	        if not has_unfinished and aggregated_has_unfinished:
193	            self.should_execute_dummy_batch = True
194	        return aggregated_has_unfinished
195	
196	    def get_supported_tasks(self) -> tuple[SupportedTask, ...]:
197	        if not hasattr(self, "_supported_tasks"):
198	            # Cache the result
199	            self._supported_tasks = self.engine_core.get_supported
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:55:33</sup>


---

## Assistant <sup>2026/8/10 15:55:34</sup>

让我检查一下 ascend 特有的 `balance_schedule` 调用者，以及 PD-separation 流程是如何触发 dummy 的，另外看看关于 KV-cache 读取与写入的关注机制是如何实现的。


---

## Assistant <sup>2026/8/10 15:55:34</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\patch\\platform\\patch_balance_schedule.py",
  "limit": 55,
  "offset": 600
}
```

</details>


---

## User <sup>2026/8/10 15:55:35</sup>

<details>
<summary>Tool Result</summary>

```
600	        # 3. Clear the internal states of the connector
601	        if self.connector is not None:
602	            meta: KVConnectorMetadata = self.connector.build_connector_meta(scheduler_output)
603	            scheduler_output.kv_connector_metadata = meta
604	
605	        # Build the connector meta for ECConnector
606	        if self.ec_connector is not None:
607	            ec_meta: ECConnectorMetadata = self.ec_connector.build_connector_meta(scheduler_output)
608	            scheduler_output.ec_connector_metadata = ec_meta
609	
610	        with record_function_or_nullcontext("schedule: update_after_schedule"):
611	            self._update_after_schedule(scheduler_output)
612	        return scheduler_output
613	
614	
615	class BalanceDPEngineCoreProc(DPEngineCoreProc):
616	    def run_busy_loop(self):
617	        """Core busy loop of the EngineCore for data parallel case."""
618	
619	        # Loop until process is sent a SIGINT or SIGTERM
620	        while True:
621	          
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:56:50</sup>


---

## Assistant <sup>2026/8/10 15:56:52</sup>

我来确认一下虚拟批处理（dummy batch）是如何设置 `num_computed_tokens`/`seq_lens` 的——这就是决定解码（decode）是否读取之前真实 KV 的关键点。


---

## Assistant <sup>2026/8/10 15:56:52</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 75,
  "offset": 8441
}
```

</details>


---

## User <sup>2026/8/10 15:56:52</sup>

<details>
<summary>Tool Result</summary>

```
8441	            for_cudagraph_capture=is_graph_capturing,
8442	        )
8443	        if self.use_cp:
8444	            self.pcp_manager.init_batch_info(
8445	                num_scheduled_tokens,
8446	                num_reqs,
8447	                self.input_batch.num_computed_tokens_cpu,
8448	                self.input_batch.num_prompt_tokens,
8449	            )
8450	            if self.speculative_config:
8451	                self.pcp_manager.query_lens_pcp_full.cpu[:num_reqs] = torch.from_numpy(num_scheduled_tokens)
8452	                self.pcp_manager.query_lens_pcp_full.copy_to_gpu()
8453	        if cudagraph_runtime_mode is None:
8454	            cudagraph_runtime_mode = _cudagraph_mode
8455	        else:
8456	            assert cudagraph_runtime_mode == _cudagraph_mode, (
8457	                f"Cudagraph runtime mode mismatch in dummy_run. "
8458	                f"Expected {_cudagraph_mode}, but got {cudagraph_runtime_mode}."
8459	            )
8460	        num_tokens_padded =
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 15:59:08</sup>


---

## Assistant <sup>2026/8/10 15:59:09</sup>

让我来验证一下这个关键细节：dummy run 是在 *live*（实时）的 `input_batch`（包含真实请求的 KV 状态）之上操作，还是使用一个全新的、已清零的 batch。这将决定 decode 路径是否真的会读取到真实的 KV。


---

## Assistant <sup>2026/8/10 15:59:09</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 70,
  "offset": 8515
}
```

</details>


---

## User <sup>2026/8/10 15:59:09</sup>

<details>
<summary>Tool Result</summary>

```
8515	
8516	            cum_num_tokens = self._get_cumsum_and_arange(
8517	            num_scheduled_tokens, self.query_pos.np)
8518	            self.query_start_loc.np[1 : num_reqs_padded + 1] = cum_num_tokens
8519	            copy_snapshot_to_gpu(self.query_start_loc)
8520	            if self._has_gdn:
8521	                self.gdn_query_start_loc.np[1 : num_reqs_padded + 1] = cum_num_tokens
8522	                copy_snapshot_to_gpu(self.gdn_query_start_loc)
8523	
8524	            if not profile_cpp:
8525	                num_reqs_padded = self._pad_query_start_loc_for_fia(
8526	                    self.query_start_loc,
8527	                    num_tokens_padded,
8528	                    num_reqs_padded,
8529	                    num_reqs,
8530	                    cudagraph_runtime_mode,
8531	                    batch_desc.num_reqs,
8532	                )
8533	
8534	            # Dummy graph runs do not go through _prepare_inputs(), but GDN/Mamba
8535	            # metadata reads block_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:00:20</sup>


---

## Assistant <sup>2026/8/10 16:00:45</sup>

我已经验证了关键的结构性事实。修改原因如代码注释中所述，但让我结合实际代码路径来解释*为什么*它专门在边云 PD-separation + DP 场景中出现，以及*为什么* `uniform_decode=False` 能解决问题。

（注：这是一个未提交的工作树修改 — `git diff HEAD` 显示原始代码为 `uniform_decode=True`。）

## 直接原因:decode 路径会读取真实 KV cache → softmax 溢出 NaN

dummy 跑在**活跃的 `input_batch` 之上**,不是隔离的空 batch。关键证据在 [model_runner_v1.py:8537](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8537):

```python
# Dummy graph runs do not go through _prepare_inputs(), but GDN/Mamba
# metadata reads block_table[:num_reqs_padded] below. Sync padded
# rows as well so device-side metadata does not see stale block ids.
self.input_batch.block_table.commit_block_table(num_reqs_padded)
```

dummy 直接用真实 `input_batch` 的 `block_table`(指向真实 KV 块)。而 [model_runner_v1.py:8554-8557](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8554-L8557) 把 `slot_mapping` 填成 `-1`:

```python
if not is_graph_capturing:
    for kv_cache_gid in range(...):
        blk_table = self.input_batch.block_table[kv_cache_gid]
        blk_table.slot_mapping.gpu.fill_(-1)
```

`slot_mapping=-1` 表示**不写 KV**(dummy 不会污染真实 cache),但 `block_table`(读侧)仍是真实的。于是:

- `uniform_decode=True` → 走 **decode attention**(FULL 均匀解码图 / Flashdecode / paged attention)。decode attention 的本质就是:**query 去 KV cache 里(经 block_table)读历史的 K、V**。在 PD-separation 下这些块里是大幅值的**真实 KV**,dummy 的 query(零/假输入派生)与大真实 K 做点积 → logits 过大 → softmax 溢出 → NaN。
- `uniform_decode=False` → 走 **prefill(causal)attention**。prefill 是**从当前 token embedding 现算 K、V 并因果自注意力**,不读 paged cache(再加 `slot_mapping=-1` 也不写)。于是 dummy query 只会与"同样是 dummy 来源"的 K、V 相作用 → 有界 → 不溢出。

这正是注释 [worker.py:1956-1961](vllm-ascend/vllm_ascend/worker/worker.py#L1956-L1961) 所说的:"decode reads KV … prefill is causal (only writes KV, doesn't read)"。

## 为什么是 PD-separation + DP 场景才触发

需要两个条件同时成立,dummy 才会"读到真实 KV":

**条件一:dummy 在推理进行中(而非 warmup)触发 —— 由 DP>1 提供。**
DP 并行下,某个 DP rank 本步没有可执行请求、但另一个 DP rank 有工作时,空闲 rank **必须跑一个 dummy 前向**来保持跨 DP 的 all_reduce / wave 配对。这是上游 vLLM 机制,见 [llm_engine.py:188-194](vllm/vllm/v1/engine/llm_engine.py#L188-L194) 和 [core.py:1944-1948](vllm/vllm/v1/engine/core.py#L1944-L1948),Ascend 的 balance 调度器同样如此,见 [patch_balance_schedule.py:634-636](vllm-ascend/vllm_ascend/patch/platform/patch_balance_schedule.py#L634-L636):

```python
# We are in a running state and so must execute a dummy pass
# if the model didn't execute any ready requests.
self.execute_dummy_batch()
```

这个 dummy 是**推理中途**跑的,不是初始化 warmup。

**条件二:此刻 KV cache 里有真实大幅值数据 —— 由 PD-separation 提供。**
边云 PD-separation 中,边侧 decode 引擎正在服务真实 decode 请求,其 cache 块里就是大幅值真实 KV。当中途的空闲-rank dummy 在这个引擎上触发时,decode 路径就会去读这些真实 KV。(在 warmup / 还没真实流量时,cache 是空/零,decode dummy 读到零 → 不会溢出 —— 这正是原来 `uniform_decode=True` 在非此场景下能跑的原因。)

DP 提供了"dummy 在推理中途跑"的时机,PD-separation 提供了"cache 里满是真实 KV"的条件,两者缺一不可,所以问题集中在这个场景。PD 侧还通过 zmq dummy-middle 协议来保持云端跨 DP all_reduce 配对,见 [patch_engine_core.py:1396-1441](vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py#L1396-L1441)。

## 为什么改成 False 是安全的

1. **`num_tokens` 不变**(`decode_token_per_req` 没动)→ 前向的逻辑 token 数、进而跨 DP 配对的形状不变,只换了 attention 模式,不会破坏 DP 配对。
2. dummy 在这里的职责是 **rank 保活(跑一个前向让 all_reduce 配对)**,不是产出有效输出,也不是捕获图(图捕获在 init 阶段 `is_graph_capturing=True` 时做,keepalive dummy 走的是 `is_graph_capturing=False`)。所以 decode→prefill 的切换不影响正确性。
3. `slot_mapping=-1` 已经保证 dummy 不写 cache,真实 KV 不会被污染。

## 代价

keepalive dummy 不再走 FULL 均匀解码(Flashdecode)图路径;但该路径在初始化时已捕获/预热,keepalive 不负责预热它,所以没有实质损失 —— keepalive 只需要一个能跑通的前向。真正的 trade-off 只是 dummy 这一步用了 prefill/causal kernel 而非 decode kernel,性能可忽略(dummy 本就是空跑)。

一句话总结:**DP>1 让空闲 rank 在推理中途必须跑 dummy,PD-separation 让此刻 cache 里存着大幅值真实 KV;`uniform_decode=True` 的 decode attention 会去读这些真实 KV,与 dummy 的假 query 做点积导致 softmax 溢出 NaN。改成 `False` 走 causal prefill(现算 K/V、不读 cache),dummy 只与自身 dummy 数据作用,规避溢出,且 `num_tokens` 不变不影响 DP 配对。**


---

## User <sup>2026/8/10 16:03:33</sup>

C:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py的execute_dummy_batch增加uniform_decode参数，默认是True，边云PD-separation场景，dp并行场景才改成False


---

## Assistant <sup>2026/8/10 16:03:48</sup>


---

## Assistant <sup>2026/8/10 16:03:49</sup>

我将添加一个 `uniform_decode` 参数，默认值为 `True`，并仅在 PD-separation + DP 场景下将其覆盖为 `False`。首先，让我确认一下该 worker 是如何检测这些条件的，以便与现有的模式保持一致。


---

## Assistant <sup>2026/8/10 16:03:50</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"pd_separation\\|edge_cloud_config\\|is_edge_node\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/worker.py\" 2>/dev/null | head -30",
  "description": "Find PD-separation/edge-cloud checks in worker.py"
}
```

</details>


---

## Assistant <sup>2026/8/10 16:03:52</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"pd_separation\\.enabled\\|edge_cloud_config\\.pd_separation\\|is_edge_node\\|data_parallel_size\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/edge_cloud/\" 2>/dev/null | head -30",
  "description": "Find how pd_separation and is_edge_node are accessed elsewhere"
}
```

</details>


---

## User <sup>2026/8/10 16:03:52</sup>

<details>
<summary>Tool Result</summary>

```
646:            # scheduler_config.pd_separation_enabled (a dynamic attribute that
654:            _ec = _ac.get("edge_cloud_config", {}) if isinstance(_ac, dict) else {}
655:            _pd = _ec.get("pd_separation", {}) if isinstance(_ec, dict) else {}
658:                and not getattr(_pc, "is_edge_node", True)
```

</details>


---

## User <sup>2026/8/10 16:03:53</sup>

<details>
<summary>Tool Result</summary>

```
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:742:        self.dp_size = vllm_config.parallel_config.data_parallel_size
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:816:            expected_role = "edge" if self.parallel_config.is_edge_node else "cloud"
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:1196:            expected_role = "edge" if self.parallel_config.is_edge_node else "cloud"
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:4651:                            and self.parallel_config.data_parallel_size > 1
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:5140:        if self._edge_cloud_enabled and not self.parallel_config.is_edge_node:
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:5230:        if self._edge_cloud_enabled and not self.parallel_config.is_edge_node:
c:/v0.23.0_lwd_acc_test_br/vllm-asce
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:03:57</sup>


---

## Assistant <sup>2026/8/10 16:03:57</sup>

让我看一下 `worker.py` 本身（640-660行）中现有的 `PD-separation` 检测模式，以便完全复刻它。


---

## Assistant <sup>2026/8/10 16:03:58</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "limit": 35,
  "offset": 635
}
```

</details>


---

## User <sup>2026/8/10 16:03:58</sup>

<details>
<summary>Tool Result</summary>

```
635	                ),
636	            )
637	
638	            # [CHER] Cloud-side hidden early-receive is a built-in part of
639	            # PD-separation masking: always active on a PD-separated cloud
640	            # worker (local_rank==0), so _execute_model_cloud consults the
641	            # early-recv cache via get_or_post_early_recv.  Stays False on the
642	            # edge role (EHER is separate) and when PD is off.
643	            # Read from vllm_config (not ascend_config) for a uniform,
644	            # init-order-independent source of truth.  PD-enabled comes from
645	            # additional_config (a serialized dict field) rather than
646	            # scheduler_config.pd_separation_enabled (a dynamic attribute that
647	            # may not reach every process).
648	            #
649	            # Only local_rank==0 (PP-NPU0, the rank that issues the cross-node
650	            # hidden irecv) needs early-recv; other cloud ranks receive hidden
651	            # via 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:05:17</sup>


---

## Assistant <sup>2026/8/10 16:05:17</sup>

该文件已经从 `vllm_config.additional_config` 中检测到了 PD-separation（第 652-660 行），以避免初始化顺序问题。让我检查一下 worker 是否缓存了任何 edge-cloud/PD 标志，并确认 edge role 的映射，这样我就能正确地进行处理了。


---

## Assistant <sup>2026/8/10 16:05:19</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"_edge_cloud_enabled\\|_pd_sep\\|pd_separation\\|enable_edge_cloud\\|_cloud_hidden_early_recv\\|self\\.vllm_config\\|self\\.parallel_config\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/worker.py\" 2>/dev/null | head -40",
  "description": "Find cached edge-cloud/PD flags and config attrs on worker"
}
```

</details>


---

## User <sup>2026/8/10 16:05:20</sup>

<details>
<summary>Tool Result</summary>

```
223:        self.use_v2_model_runner = self.vllm_config.use_v2_model_runner
249:        self._cloud_hidden_early_recv_enabled: bool = False
336:        hidden_size = self.vllm_config.model_config.hf_text_config.hidden_size
338:        if self.vllm_config.quant_config is None and (tags is None or "weights" in tags):
486:            parallel_config = self.parallel_config
547:            setup_ascend_local_comm_res(self.local_rank, self.vllm_config.kv_transfer_config)
568:            self.parallel_config.data_parallel_size > 1
569:            and self.parallel_config.data_parallel_size_local > 0
570:            and self.parallel_config.distributed_executor_backend not in ["ray", "external_launcher"]
571:            and self.vllm_config.parallel_config.data_parallel_backend != "ray"
572:            and self.vllm_config.parallel_config.nnodes_within_dp == 1
575:            assert self.parallel_config.local_world_size <= visible_device_count, (
576:                f"local_world_size ({self.p
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:05:26</sup>


---

## Assistant <sup>2026/8/10 16:05:27</sup>

在 `model_runner` 上有一个干净的 `_edge_cloud_enabled` 标志（第 613、1028 行）。让我检查一下它的定义，以及 `model_runner` 是否也缓存了 `pd_separation` 子标志。


---

## Assistant <sup>2026/8/10 16:05:28</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"_edge_cloud_enabled\\s*=\\|_edge_cloud_enabled\\|pd_separation\\|_pd_sep\\|self\\.dp_size\\|data_parallel_size\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head -30",
  "description": "Find _edge_cloud_enabled and pd_separation flags in model_runner"
}
```

</details>


---

## User <sup>2026/8/10 16:05:29</sup>

<details>
<summary>Tool Result</summary>

```
742:        self.dp_size = vllm_config.parallel_config.data_parallel_size
805:        self._edge_cloud_enabled = self.edge_cloud_cfg.enabled
810:        if self._edge_cloud_enabled:
1189:        self._edge_cloud_enabled = self.edge_cloud_cfg.enabled
1190:        if self._edge_cloud_enabled:
1293:                self._edge_cloud_enabled
1978:        if self.dp_size == 1:
1982:            num_tokens_after_padding = torch.tensor([num_tokens] * self.dp_size, device="cpu", dtype=torch.int32)
1993:        packed_tensor = torch.zeros(3, self.dp_size, device=device_str, dtype=torch.int32)
2030:                [max_tokens_across_dp] * self.dp_size, device="cpu", dtype=torch.int32
2066:            self._edge_cloud_enabled
3173:                self._edge_cloud_enabled
3365:            and self._edge_cloud_enabled
3383:            or not self._edge_cloud_enabled
4213:            self._edge_cloud_enabled
4226:            self._edge_cloud_enabled
4296:                    if self.dp_size > 1:
4348:  
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:05:33</sup>


---

## Assistant <sup>2026/8/10 16:05:33</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 22,
  "offset": 800
}
```

</details>


---

## User <sup>2026/8/10 16:05:33</sup>

<details>
<summary>Tool Result</summary>

```
800	        set_weight_prefetch_method(self.ascend_config.weight_prefetch_config)
801	
802	        # Edge-cloud initialization must happen before _set_up_drafter
803	        # because the drafter setup needs to know whether edge-cloud is enabled.
804	        self.edge_cloud_cfg = self.ascend_config.edge_cloud_config
805	        self._edge_cloud_enabled = self.edge_cloud_cfg.enabled
806	        # This flag is set per-step in execute_model; initialize it here so
807	        # that code paths reaching _prepare_inputs before the first execute_model
808	        # call (e.g. profile_run or unit tests) do not hit AttributeError.
809	        self._is_edge_cloud_tail_segment = False
810	        if self._edge_cloud_enabled:
811	            if not self.parallel_config.enable_edge_cloud:
812	                raise ValueError(
813	                    "additional_config.edge_cloud_config.enabled requires "
814	                    "--enable-edge-cloud."
815	                )
816	            expected_r
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:05:35</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -rn \"pd_separation\\|class EdgeCloudConfig\\|edge_cloud_cfg\\s*=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py\" 2>/dev/null | head -20; echo \"=== edge_cloud cfg def ===\"; grep -rn \"pd_separation\\|class EdgeCloud\\|class PdSeparation\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20",
  "description": "Find edge_cloud_cfg and pd_separation config definition"
}
```

</details>


---

## User <sup>2026/8/10 16:05:37</sup>

<details>
<summary>Tool Result</summary>

```
899:                "pd_separation": {
941:class EdgeCloudConfig:
956:        self.pd_separation = PDSeparationConfig(
957:            user_config.get("pd_separation", {}) or {}
1047:            f"pd_separation={self.pd_separation})"
=== edge_cloud cfg def ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py:899:                "pd_separation": {
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py:941:class EdgeCloudConfig:
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py:956:        self.pd_separation = PDSeparationConfig(
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py:957:            user_config.get("pd_separation", {}) or {}
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py:1047:            f"pd_separation={self.pd_separation})"
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/compilation/acl_graph_edge_cloud.py:107:class EdgeCloudACLGraphWrapper(ACLGraphWrapper):
c:/v0.23.0_lwd_acc_test_b
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:06:46</sup>


---

## Assistant <sup>2026/8/10 16:06:46</sup>

我来确认一下 v2 model runner 是否也设置了 `edge_cloud_cfg`（worker 使用了 v1 和 v2 runner），这样属性访问对于两者都是安全的。


---

## Assistant <sup>2026/8/10 16:06:47</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 12,
  "offset": 1184
}
```

</details>


---

## User <sup>2026/8/10 16:06:47</sup>

<details>
<summary>Tool Result</summary>

```
1184	            self.kvcomp_meta_data = initialize_kvcomp_metadata(max_num_reqs=self.max_num_reqs,
1185	                block_size=self.block_size, device=self.device, vllm_config=self.vllm_config,
1186	                parallel_config=self.parallel_config, dtype=self.dtype)
1187	
1188	        self.edge_cloud_cfg = self.ascend_config.edge_cloud_config
1189	        self._edge_cloud_enabled = self.edge_cloud_cfg.enabled
1190	        if self._edge_cloud_enabled:
1191	            if not self.parallel_config.enable_edge_cloud:
1192	                raise ValueError(
1193	                    "additional_config.edge_cloud_config.enabled requires "
1194	                    "--enable-edge-cloud."
1195	                )
```

</details>


---

## Assistant <sup>2026/8/10 16:06:48</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"class NPUModelRunnerV2\\|class NPUModelRunner\\b\\|self.edge_cloud_cfg\\s*=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head",
  "description": "Confirm edge_cloud_cfg set in both runner classes"
}
```

</details>


---

## User <sup>2026/8/10 16:06:49</sup>

<details>
<summary>Tool Result</summary>

```
680:class NPUModelRunner(GPUModelRunner):
804:        self.edge_cloud_cfg = self.ascend_config.edge_cloud_config
1188:        self.edge_cloud_cfg = self.ascend_config.edge_cloud_config
```

</details>


---

## Assistant <sup>2026/8/10 16:07:40</sup>


---

## Assistant <sup>2026/8/10 16:07:41</sup>

两个 runner 类都在 `edge_cloud_cfg.pd_separation.enabled` 处设置了 `self.edge_cloud_cfg` (model_runner_v1.py:804 和 :1188)，并且 `self.parallel_config` 在 worker 上可用。我已经具备了所需的一切。

让我来进行修改 —— 添加 `uniform_decode: bool = True` 参数，仅针对 edge-cloud PD-separation + DP>1 自动覆盖为 `False`，并将解析后的值传递给 `_dummy_run`。


---

## Assistant <sup>2026/8/10 16:07:52</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\worker.py",
  "old_string": "    def execute_dummy_batch(self, layer_slice_info: Any = None) -> None:\n        # PD-separation: use uniform_decode=False (prefill-style attention)\n        # instead of True (decode-style). Decode attention reads from the KV\n        # cache which has real data from previous forwards, causing softmax\n        # overflow -> NaN when the dummy's query (from zero input) interacts\n        # with large real KV values. Prefill-style attention is causal (only\n        # writes KV, doesn't read), avoiding the NaN.\n        _lsi = layer_slice_info\n        logger.info(\n            \"[SLICE-DIAG] execute_dummy_batch entry: layer_slice_info=%s \"\n            \"is_first=%s is_last=%s start=%s end=%s total=%s\",\n            type(_lsi).__name__ if _lsi is not None else \"None\",\n            getattr(_lsi, \"is_first_slice\", None) if _lsi is not None else None,\n            getattr(_lsi, \"is_last_slice\", None) if _lsi is not None else None,\n            getattr(_lsi, \"start_layer\", None) if _lsi is not None else None,\n            getattr(_lsi, \"end_layer\", None) if _lsi is not None else None,\n            getattr(_lsi, \"total_slices\", None) if _lsi is not None else None,\n        )\n        self.model_runner._dummy_run(\n            num_tokens=self.model_runner.decode_token_per_req,\n            uniform_decode=False,\n            layer_slice_info=layer_slice_info,\n        )",
  "new_string": "    def execute_dummy_batch(\n        self,\n        layer_slice_info: Any = None,\n        uniform_decode: bool = True,\n    ) -> None:\n        # ``uniform_decode`` defaults to True (original decode-style dummy),\n        # which is correct for warmup / non-PD-separation runs where the KV\n        # cache is still empty.\n        #\n        # In edge-cloud PD-separation with DP>1, the idle-rank keepalive\n        # dummy fires mid-inference 
...(truncated)
```

</details>


---

## User <sup>2026/8/10 16:07:53</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/10 16:08:03</sup>


---

## Assistant <sup>2026/8/10 16:08:03</sup>

现在让我来验证一下该修改在语法上是否正确，以及现有的 `execute_dummy_batch` 调用者是否仍然兼容（其中一个调用者传递了参数）。


---

## Assistant <sup>2026/8/10 16:08:04</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/worker/worker.py', encoding='utf-8').read()); print('worker.py: syntax OK')\" 2>&1",
  "description": "Syntax check worker.py"
}
```

</details>


---

## Assistant <sup>2026/8/10 16:08:05</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\v1\\executor\\multiproc_executor.py",
  "limit": 18,
  "offset": 1196
}
```

</details>


---

## User <sup>2026/8/10 16:09:04</sup>

<details>
<summary>Tool Result</summary>

```
worker.py: syntax OK
```

</details>


---

## User <sup>2026/8/10 16:09:04</sup>

<details>
<summary>Tool Result</summary>

```
1196	                        # _wait_pp_send_work (which, for the dummy's
1197	                        # batch_type=DECODE_FIRST, waits the DECODE hidden channel)
1198	                        # before reaching _execute_model_cloud's dummy branch - that
1199	                        # makes a cloud dummy block on a prior real step's
1200	                        # un-recv'd isend and skews the cross-DP pairing.
1201	                        # execute_dummy_batch goes straight to _dummy_run (no PP send
1202	                        # wait), matching how the edge handles its own dummies and
1203	                        # keeping the cloud/edge dummy paths symmetric.
1204	                        try:
1205	                            if scheduler_output.total_num_scheduled_tokens == 0:
1206	                                output = self.worker.execute_dummy_batch(
1207	                                    layer_slice_info=slice_info,
1208	                                )
1209	                   
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:09:16</sup>


---

## Assistant <sup>2026/8/10 16:09:17</sup>

语法检查通过，并且 [multiproc_executor.py:1206-1208](vllm/vllm/v1/executor/multiproc_executor.py#L1206-L1208) 处的调用者传入了 `layer_slice_info=slice_info`（关键字参数）——与新签名兼容。让我对编辑后的方法进行最后一次完整性检查。


---

## Assistant <sup>2026/8/10 16:09:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && grep -n \"def execute_dummy_batch\\|uniform_decode: bool = True\\|_pd_sep_enabled\\|data_parallel_size > 1\\|uniform_decode=uniform_decode\\|uniform_decode=%s\" vllm_ascend/worker/worker.py",
  "description": "Confirm key lines of the edit are present"
}
```

</details>


---

## User <sup>2026/8/10 16:09:19</sup>

<details>
<summary>Tool Result</summary>

```
568:            self.parallel_config.data_parallel_size > 1
1955:    def execute_dummy_batch(
1958:        uniform_decode: bool = True,
1982:            _pd_sep_enabled = getattr(
1985:            if _pd_sep_enabled and self.parallel_config.data_parallel_size > 1:
1992:            "uniform_decode=%s",
2003:            uniform_decode=uniform_decode,
2020:            and parallel_config.data_parallel_size > 1
```

</details>


---

## Assistant <sup>2026/8/10 16:09:26</sup>


---

## Assistant <sup>2026/8/10 16:09:37</sup>

完成。修改内容在 [worker.py:1955-2005](vllm-ascend/vllm_ascend/worker/worker.py#L1955-L2005)。

## 改动要点

`execute_dummy_batch` 新增 `uniform_decode: bool = True` 参数,默认 `True`(恢复原始 decode-style 行为),仅当检测到**边云 PD-separation 且 DP>1** 时才自动改写为 `False`:

```python
def execute_dummy_batch(
    self,
    layer_slice_info: Any = None,
    uniform_decode: bool = True,
) -> None:
    ...
    if uniform_decode:
        _ec_cfg = getattr(self.model_runner, "edge_cloud_cfg", None)
        _pd_sep_enabled = getattr(
            getattr(_ec_cfg, "pd_separation", None), "enabled", False
        )
        if _pd_sep_enabled and self.parallel_config.data_parallel_size > 1:
            uniform_decode = False
    ...
    self.model_runner._dummy_run(
        num_tokens=self.model_runner.decode_token_per_req,
        uniform_decode=uniform_decode,
        layer_slice_info=layer_slice_info,
    )
```

## 行为矩阵

| 场景 | `uniform_decode` |
|---|---|
| warmup / 非 PD-separation(默认调用) | `True`(原始行为) |
| 边云 PD-separation + DP>1 | 自动 `False`(规避 NaN) |
| 边云 PD-separation 但 DP=1 | `True`(无空闲 rank dummy,不会触发) |
| 调用方显式传 `uniform_decode=False` | `False` |

## 几点说明

- **检测方式**:沿用 model_runner 上已有的 `edge_cloud_cfg.pd_separation.enabled`([model_runner_v1.py:804/1188](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L804) 处设置,v1/v2 runner 都有),配合 `self.parallel_config.data_parallel_size > 1`。用 `getattr` 防御性访问,任一属性缺失都不会报错。
- **未限定 `is_edge_node`**:PD-sep+DP 下 edge 和 cloud 两侧都可能跑 keepalive dummy,而 `uniform_decode=False` 对两侧都安全(prefill attention 不读 paged cache),所以不按角色限定,避免漏掉 cloud 侧可能的 NaN。
- **强制覆盖**:`if uniform_decode:` 表示即便调用方在 PD-sep+DP 下显式传 `True` 也会被改写为 `False`,因为那会重新引入 NaN。
- **向后兼容**:现有调用方如 [multiproc_executor.py:1206](vllm/vllm/v1/executor/multiproc_executor.py#L1206) 的 `execute_dummy_batch(layer_slice_info=slice_info)` 不受影响;`num_tokens` 不变,跨 DP 配对形状不变。
- **日志**:在 `[SLICE-DIAG]` 日志里加了 `uniform_decode=%s`,方便你继续调试时确认实际取值。

已通过语法检查(`ast.parse` OK)。


---

## User <sup>2026/8/10 16:42:25</sup>

<ide_selection>The user selected the lines 1980 to 1980 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\worker.py:
uniform_decode

This may or may not be related to the current task.</ide_selection>

C:\theroadtofree_github目录下的代码，边云PD-separation场景，dp并行场景功能正常；本工程代码C:\v0.23.0_lwd_acc_test_br\vllm和C:\v0.23.0_lwd_acc_test_br\vllm-ascend，边云PD-separation场景，dp并行场景，打一个请求就卡死，原因是云dp的dummy run卡死，卡死栈信息Thread 100777 (idle): "MainThread"
clock_nanosleep (libc.so.6)
nanosleep (libc.so.6)
rtStreamSynchronizeWithTimeout (libruntime.so)
aclrtSynchronizeStreamWithTimeoutImpl (libacl_rt_impl.so)
at::ops::local_scalar_dense::call (libtorch_cpu.so)
at::native::item (libtorch_cpu.so)
c10::impl::wrap_kernel_functor_unboxed<c10::impl::detail::WrapFunctionIntoFunctor<c10::CompileTimeFunctionPointer<c10::Scalar(at::Tensor const&), &at::(anonymous namespace)::(anonymous namespace)::wrapper_CompositeImplicitAutograd__item(at::Tensor const&)>, c10::Scalar, c10::guts::typelist::typelist<at::Tensor const&> >, c10::Scalar(at::Tensor const&)>::call (libtorch_cpu.so)
at::_ops::item::call (libtorch_cpu.so)
torch::autograd::THPVariable_item (libtorch_python.so)
_dummy_run (vllm_ascend/worker/model_runner_v1.py:8814)
decorate_context (torch/utils/_contextlib.py:124)
execute_dummy_batch (vllm_ascend/worker/worker.py:1956)
worker_busy_loop (vllm/v1/executor/multiproc_executor.py:1206)


---

## Assistant <sup>2026/8/10 16:43:18</sup>


---

## Assistant <sup>2026/8/10 16:43:20</sup>

云侧 DP 的 dummy 卡在了 `_dummy_run` 内部第 8814 行的 `.item()` 调用上（NPU stream sync 一直未完成）。这是一个典型的表现，说明 cross-DP 的集合通信配对出现了问题。让我检查一下卡死的位置，以及工作版本 (`theroadtofree_github`) 是否可以进行 diff 对比。


---

## Assistant <sup>2026/8/10 16:43:20</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 45,
  "offset": 8790
}
```

</details>


---

## User <sup>2026/8/10 16:43:20</sup>

<details>
<summary>Tool Result</summary>

```
8790	                    else:
8791	                        hidden_states, _ = outputs
8792	                elif isinstance(outputs, IntermediateTensors):
8793	                    hidden_states = outputs["hidden_states"]
8794	                else:
8795	                    hidden_states = outputs
8796	
8797	                # Layer-sliced dummy: save intermediate state for the
8798	                # next slice (mirrors execute_model's layerwise state
8799	                # saving for real prefill).
8800	                if (
8801	                    layer_slice_info is not None
8802	                    and not layer_slice_info.is_last_slice
8803	                    and isinstance(outputs, IntermediateTensors)
8804	                ):
8805	                    self._layerwise_intermediate = outputs
8806	                    # Also save positions / attn_metadata for continuation.
8807	                    self._layerwise_positions = positions
8808	                    self._layerwise_attn_metada
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:43:21</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "ls -d \"C:/theroadtofree_github\" 2>/dev/null && echo \"=== EXISTS ===\" && ls \"C:/theroadtofree_github\" 2>/dev/null | head -30 || echo \"=== NOT FOUND at C:/theroadtofree_github ===\"",
  "description": "Check if theroadtofree_github reference checkout exists"
}
```

</details>


---

## User <sup>2026/8/10 16:43:22</sup>

<details>
<summary>Tool Result</summary>

```
C:/theroadtofree_github
=== EXISTS ===
log
vllm
vllm-ascend
```

</details>


---

## Assistant <sup>2026/8/10 16:44:12</sup>


---

## Assistant <sup>2026/8/10 16:44:14</sup>

找到了卡死位置：[model_runner_v1.py:8814](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8814) 是一行 **diagnostic** 代码，它在 `hidden_states` 上调用了 `.item()`，这会同步 NPU stream 且永远无法返回。工作版本的检出代码位于 `C:/theroadtofree_github`。让我对比一下两个代码库在 dummy/DP 路径下的关键差异。


---

## Assistant <sup>2026/8/10 16:44:16</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== CURRENT: PD-DIAG/SLICE-DIAG .item() diagnostics in model_runner_v1.py ===\"; grep -n \"PD-DIAG\\|SLICE-DIAG\\|\\.item()\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head -40\necho \"\"\necho \"=== THEROADTOFREE: same diagnostics in model_runner_v1.py ===\"; grep -n \"PD-DIAG\\|SLICE-DIAG\\|has_nan.*item\\|isnan.*item\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head -40",
  "description": "Compare diagnostic logging between the two checkouts"
}
```

</details>


---

## User <sup>2026/8/10 16:44:17</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT: PD-DIAG/SLICE-DIAG .item() diagnostics in model_runner_v1.py ===
2002:        self._peer_batch_type_id = int(packed_tensor[2, 1 - self.dp_rank].item())
2024:        max_tokens_across_dp = int(num_tokens_across_dp.max().item())
3900:                actual_step = int(actual_step.item())
7946:                num_tokens_padded = int(num_tokens_across_dp[dp_rank].item())
8008:            max_seq_len = self.optimistic_seq_lens_cpu.numpy()[:num_reqs].max().item()
8363:        # [SLICE-DIAG] Log whether _dummy_run receives layer_slice_info.
8366:            "[SLICE-DIAG] _dummy_run: layer_slice_info=%s "
8642:                            "[PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): "
8645:                            float(_diag_hs.float().norm().item()),
8646:                            float(_diag_hs.float().mean().item()),
8814:                    _has_nan = bool(torch.isnan(hidden_states).any().item()) if hasattr(hidden_states, 'shape') and hidden_states.dim() > 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:44:41</sup>


---

## Assistant <sup>2026/8/10 16:44:43</sup>

两个检出版本中都有相同的 `.item()` 诊断信息——所以该同步点并不是导致回归的原因；它只是卡住流（stream）显现的地方。在 theroadtofree 中，流在该点之前就已完成，但在此处却没有。让我检查一下工作版本中的 `execute_dummy_batch` 使用了什么（`uniform_decode` 值很重要），并对比一下 dummy 路径下的跨 DP 通信逻辑。


---

## Assistant <sup>2026/8/10 16:44:44</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== THEROADTOFREE: execute_dummy_batch in worker.py ===\"; grep -n \"def execute_dummy_batch\" -A 30 \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/worker.py\" 2>/dev/null | head -40",
  "description": "Check theroadtofree execute_dummy_batch impl"
}
```

</details>


---

## User <sup>2026/8/10 16:44:45</sup>

<details>
<summary>Tool Result</summary>

```
=== THEROADTOFREE: execute_dummy_batch in worker.py ===
1713:    def execute_dummy_batch(self, layer_slice_info: Any = None) -> None:
1714-        # PD-separation: use uniform_decode=False (prefill-style attention)
1715-        # instead of True (decode-style). Decode attention reads from the KV
1716-        # cache which has real data from previous forwards, causing softmax
1717-        # overflow -> NaN when the dummy's query (from zero input) interacts
1718-        # with large real KV values. Prefill-style attention is causal (only
1719-        # writes KV, doesn't read), avoiding the NaN.
1720-        _lsi = layer_slice_info
1721-        logger.info(
1722-            "[SLICE-DIAG] execute_dummy_batch entry: layer_slice_info=%s "
1723-            "is_first=%s is_last=%s start=%s end=%s total=%s",
1724-            type(_lsi).__name__ if _lsi is not None else "None",
1725-            getattr(_lsi, "is_first_slice", None) if _lsi is not None else None,
1726-            getattr(_lsi, "
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:44:45</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== CURRENT worker.py execute_dummy_batch callers / cloud dummy in multiproc_executor ===\"; grep -n \"execute_dummy_batch\\|is_pd_dummy\\|dummy\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/executor/multiproc_executor.py\" 2>/dev/null | head -30\necho \"\"\necho \"=== THEROADTOFREE multiproc_executor cloud dummy ===\"; grep -n \"execute_dummy_batch\\|is_pd_dummy\\|dummy\" \"C:/theroadtofree_github/vllm/vllm/v1/executor/multiproc_executor.py\" 2>/dev/null | head -30",
  "description": "Compare cloud dummy path in multiproc_executor"
}
```

</details>


---

## User <sup>2026/8/10 16:44:47</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT worker.py execute_dummy_batch callers / cloud dummy in multiproc_executor ===
398:    def execute_dummy_batch(self) -> None:
399:        self.collective_rpc("execute_dummy_batch", unique_reply_rank=self.output_rank)
1176:                            else " dummy"
1192:                        # PD-separation: route a dummy-middle
1194:                        # _patched_execute_dummy_batch) to execute_dummy_batch
1196:                        # _wait_pp_send_work (which, for the dummy's
1198:                        # before reaching _execute_model_cloud's dummy branch - that
1199:                        # makes a cloud dummy block on a prior real step's
1201:                        # execute_dummy_batch goes straight to _dummy_run (no PP send
1203:                        # keeping the cloud/edge dummy paths symmetric.
1206:                                output = self.worker.execute_dummy_batch(
1270:            # Skip execute_model / execute_dummy_batch from cross-node MQ on
1
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:45:15</sup>


---

## Assistant <sup>2026/8/10 16:45:16</sup>

关键发现：theroadtofree 的 `execute_dummy_batch` 也硬编码了 `uniform_decode=False` (worker.py:1733) —— 与当前项目在 PD-sep+DP 下的效果相同。因此，`uniform_decode` **不是**导致此挂起的原因。回归问题必定在于两个版本中 `_dummy_run` 的 cloud-dummy 路径存在差异。我来对比一下这两个函数。


---

## Assistant <sup>2026/8/10 16:45:20</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== CURRENT _dummy_run bounds ===\"; grep -n \"def _dummy_run\\|^    def \" \"$CUR\" | awk '/_dummy_run/{print} $1>_dummy_run_line && /def / && !/_dummy_run/{print; exit}' | head -3\necho \"=== find next def after _dummy_run (current) ===\"; awk 'NR>=8342 && /^    def [a-zA-Z]/ && NR>8342 {print NR\": \"$0; exit}' \"$CUR\"\necho \"=== find next def after _dummy_run (theroadtofree) ===\"; awk 'NR>=7200 && /def _dummy_run/{print NR\": \"$0}' \"$TRF\" | head -1\nawk 'NR>=7280 && /^    def [a-zA-Z]/ && NR>7280 {print NR\": \"$0; exit}' \"$TRF\"",
  "description": "Find _dummy_run bounds in both files"
}
```

</details>


---

## User <sup>2026/8/10 16:45:24</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT _dummy_run bounds ===
318:    def __init__(
=== find next def after _dummy_run (current) ===
8936:     def profile_run(self) -> None:
=== find next def after _dummy_run (theroadtofree) ===
7295:     def _dummy_run(
7865:     def profile_run(self) -> None:
```

</details>


---

## Assistant <sup>2026/8/10 16:45:33</sup>


---

## Assistant <sup>2026/8/10 16:45:35</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\n# Extract _dummy_run body from both (current 8342-8935, theroadtofree 7295-7864)\nsed -n '8342,8935p' \"$CUR\" > /tmp/cur_dummy.py\nsed -n '7295,7864p' \"$TRF\" > /tmp/trf_dummy.py\necho \"=== DIFF (current vs theroadtofree) _dummy_run ===\"\ndiff /tmp/trf_dummy.py /tmp/cur_dummy.py | head -200",
  "description": "Diff _dummy_run between the two checkouts"
}
```

</details>


---

## User <sup>2026/8/10 16:45:41</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF (current vs theroadtofree) _dummy_run ===
105a106,107
>                 self.input_batch.num_computed_tokens_cpu,
>                 self.input_batch.num_prompt_tokens,
134a137,140
>         
>         if self.dynamic_eplb:
>             self.update_eplb_heat_collection_status(num_tokens_padded)
>         
172c178
<             self.query_start_loc.copy_to_gpu()
---
>             copy_snapshot_to_gpu(self.query_start_loc)
175c181
<                 self.gdn_query_start_loc.copy_to_gpu()
---
>                 copy_snapshot_to_gpu(self.gdn_query_start_loc)
179c185,190
<                     num_tokens_padded, num_reqs_padded, num_reqs, cudagraph_runtime_mode, batch_desc.num_reqs
---
>                     self.query_start_loc,
>                     num_tokens_padded,
>                     num_reqs_padded,
>                     num_reqs,
>                     cudagraph_runtime_mode,
>                     batch_desc.num_reqs,
181a193,197
>             # Dummy graph runs do not go thro
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:46:29</sup>


---

## Assistant <sup>2026/8/10 16:46:31</sup>

`_dummy_run` 的差异主要是小幅重构，除了中间张量的创建方式发生了变化。挂起发生在 forward 产生 `hidden_states` 之后的 `.item()` 处——所以是 forward 流中的某些操作没有完成。我来检查一下 dummy 路径中 cross-DP/collective 的操作，以及 cloud-dummy 输入的处理方式与工作版本有何不同。


---

## Assistant <sup>2026/8/10 16:46:33</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== CURRENT: collectives / num_tokens_across_dp / PP recv in _dummy_run (8342-8935) ===\"\nawk 'NR>=8342 && NR<=8935 && /all_reduce|num_tokens_across_dp|intermediate_tensors|recv|isend|pp_group|get_pp_group|cross_dp|dummy_middle|is_pd_dummy|segment_a|segment_e/' \"$CUR\" | head -50",
  "description": "Find collectives and PP ops in current _dummy_run"
}
```

</details>


---

## User <sup>2026/8/10 16:52:59</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT: collectives / num_tokens_across_dp / PP recv in _dummy_run (8342-8935) ===
        _cudagraph_mode, batch_desc, _, num_tokens_across_dp, _ = self._determine_batch_execution_and_padding(
        if num_tokens_across_dp is not None and num_tokens_padded != num_tokens:
            num_tokens_across_dp[:] = num_tokens_padded
            # 边云模式下根据 role 判断是否需要 intermediate_tensors，
                    intermediate_tensors = None
                        intermediate_tensors = self._layerwise_intermediate
                        # sync_and_slice_intermediate_tensors 亦使用完整 num_tokens）。
                        if self.intermediate_tensors is None:
                            # 首次创建 intermediate_tensors，使用最大可能 token 数
                            self.intermediate_tensors = (
                                self._make_empty_edge_cloud_intermediate_tensors(
                                "[Cloud _dummy_run] Created intermediate_tensors "
                                "hidden_states 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:53:18</sup>


---

## Assistant <sup>2026/8/10 16:53:19</sup>

在当前代码中有一行开发者注释，描述了确切的挂起问题：*"单请求即挂：dp1 dummy 卡在 sync_metadata all_reduce，dp0 real 卡在 forward"* ("hangs on single request: dp1 dummy stuck at sync_metadata all_reduce, dp0 real stuck at forward")。这是一个跨 DP 的 all_reduce 配对死锁。让我来阅读一下该区域的代码。


---

## Assistant <sup>2026/8/10 16:53:24</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== line of the hang comment ===\"; grep -n \"单请求即挂\\|sync_metadata\\|dummy_indices\\|max_num_reqs_across_dp = max_num_reqs\" \"$CUR\" | head -20",
  "description": "Locate the hang comment and sync_metadata all_reduce"
}
```

</details>


---

## User <sup>2026/8/10 16:53:26</sup>

<details>
<summary>Tool Result</summary>

```
=== line of the hang comment ===
745:        # 2=PL, 3=DF, 4=DL). Packed into sync_metadata all_reduce so the
1965:    def _sync_metadata_across_dp(
2004:        # [DPDBG] trace sync_metadata pairing to locate cross-DP misalignment.
4145:        # 1=PF, 2=PL, 3=DF, 4=DL). Packed into sync_metadata all_reduce
4277:                    # all_reduce (_sync_metadata_across_dp) and may run a
4286:                    # _sync_metadata_across_dp, keeping the all_reduce 1:1.
4515:            # dummy (_dummy_run) always calls _sync_metadata_across_dp. Without
4521:            self._sync_metadata_across_dp(
6806:        # (which calls _determine_batch_execution_and_padding -> sync_metadata
6808:        # (1=PF/2=PL/3=DF/4=DL) to the peer. Without this, sync_metadata runs
7282:        # _sync_metadata_across_dp) does not deadlock.  The returned
7285:        self._sync_metadata_across_dp(
7934:            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(
8672:          
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:53:32</sup>


---

## Assistant <sup>2026/8/10 16:53:33</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 110,
  "offset": 8660
}
```

</details>


---

## User <sup>2026/8/10 16:53:33</sup>

<details>
<summary>Tool Result</summary>

```
8660	                    if enable_sp():
8661	                        max_actual_tokens = (self.max_num_tokens + tp_size - 1) // tp_size
8662	                    self.intermediate_tensors = (
8663	                        self._make_empty_edge_cloud_intermediate_tensors(
8664	                            batch_size=max_actual_tokens,
8665	                        )
8666	                    )
8667	                intermediate_tensors = IntermediateTensors(
8668	                    {k: v[:intermediate_tokens] for k, v in self.intermediate_tensors.items()}
8669	                )
8670	
8671	            need_dummy_logits = not is_profile and lmhead_tp_enable()
8672	            max_num_reqs_across_dp = max_num_reqs * self.uniform_decode_query_len
8673	            dummy_indices = torch.zeros(max_num_reqs_across_dp, dtype=torch.int32)
8674	
8675	            def dummy_compute_logits(hidden_states):
8676	                if not need_dummy_logits:
8677	                    return None
8678	           
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:54:01</sup>


---

## Assistant <sup>2026/8/10 16:54:02</sup>

位于 8714-8740 行的 segment-skip 逻辑是根据 `is_edge_cloud_pp_mode()` 进行控制的，并且有一个开发者注释，描述了完全相同的死锁现象。让我检查一下工作版本中是否存在这段逻辑，以及该区域的代码有何不同。


---

## Assistant <sup>2026/8/10 16:54:04</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nCUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== THEROADTOFREE: skip-logic / peer_bt / segment markers ===\"\ngrep -n \"DUMMY matches real DP\\|_peer_bt\\|_skip_head\\|_skip_tail\\|is_edge_cloud_pp_mode\\|sync_metadata\\|segment_a OUTPUT\\|单请求即挂\\|非边云\" \"$TRF\" | head -30\necho \"\"\necho \"=== CURRENT: same markers ===\"\ngrep -n \"DUMMY matches real DP\\|_peer_bt\\|_skip_head\\|_skip_tail\\|is_edge_cloud_pp_mode\\|segment_a OUTPUT\\|单请求即挂\\|非边云\" \"$CUR\" | head -30",
  "description": "Compare skip-logic markers between checkouts"
}
```

</details>


---

## User <sup>2026/8/10 16:54:08</sup>

<details>
<summary>Tool Result</summary>

```
=== THEROADTOFREE: skip-logic / peer_bt / segment markers ===
51:    is_edge_cloud_pp_mode,
286:    缓冲区管理、模块分发与标准（非边云）流程完全一致。
525:        # 2=PL, 3=DF, 4=DL). Packed into sync_metadata all_reduce so the
1140:        # 与标准（非边云）流程对齐：draft/proposer 仅在
1157:            # 与标准（非边云）流程的 ACLGraphWrapper 构造保持一致（model_runner_v1.py:5298），
1160:            #  - 但 draft 段（is_draft_model=True）回放前的 synchronize 屏障决策会与非边云分叉。
1663:    def _sync_metadata_across_dp(
1701:        # [DPDBG] trace sync_metadata pairing to locate cross-DP misalignment.
3559:        # 1=PF, 2=PL, 3=DF, 4=DL). Packed into sync_metadata all_reduce
3678:                    # all_reduce (_sync_metadata_across_dp) and may run a
3687:                    # _sync_metadata_across_dp, keeping the all_reduce 1:1.
3882:            # dummy (_dummy_run) always calls _sync_metadata_across_dp. Without
3888:            self._sync_metadata_across_dp(
4365:            if is_edge_cloud_pp_mode() and isinstance(hidden_states, IntermediateTensors) a
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:54:25</sup>


---

## Assistant <sup>2026/8/10 16:54:26</sup>

两个检出仓库共享相同的跳过逻辑结构。卡死发生在跳过逻辑之后——在 `segment_a` 的前向传播中（`.item()` 同步了一个未完成的集合通信操作）。我来对比一下两个仓库中的 `segment-forward` 区域，并对比一下为虚拟路径提供数据的 `_sync_metadata_across_dp`。


---

## Assistant <sup>2026/8/10 16:54:28</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\n# segment forward region: current 8742-8935, theroadtofree ~7651-7864\nsed -n '8742,8935p' \"$CUR\" > /tmp/cur_seg.py\nsed -n '7651,7864p' \"$TRF\" > /tmp/trf_seg.py\necho \"=== DIFF segment-forward region (trf vs cur) ===\"\ndiff /tmp/trf_seg.py /tmp/cur_seg.py",
  "description": "Diff segment forward region between checkouts"
}
```

</details>


---

## User <sup>2026/8/10 16:54:30</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF segment-forward region (trf vs cur) ===
1,21d0
<                     # Skip both segments: no real data to all_gather.
<                     # Only sync_metadata (already done) keeps the all_reduce
<                     # pairing. This makes DUMMY instant (no MoE forward).
<                     _skip_head = True
<                     _skip_tail = True
<                 elif is_edge_device():
<                     if _peer_bt in (2, 4):  # peer is tail (PL/DL)
<                         _skip_head = True
<                     elif _peer_bt in (1, 3):  # peer is head (PF/DF)
<                         _skip_tail = True
<                     # else: unmatched id - leave both False (run full forward)
<                 # else (cloud, peer real): no skip - full middle forward pairs
<                 # all-toall with the real cloud's middle.
<                 logger.info(
<                     "[DPDBG] _dummy_run: dp_rank=%s role=%s peer_bt=%s "
<                     "skip_head=%s skip
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 16:55:03</sup>


---

## Assistant <sup>2026/8/10 16:55:04</sup>

`_dummy_run` 主体代码在两个检出版本中基本一致。卡死发生在 `segment_a` 前向计算内部的一个未完成的 collective 操作上（cloud dummy 的 MoE/EP all-toall）。我来对比一下 `_sync_metadata_across_dp`（它负责驱动 `peer_bt`，且开发者注释称其与卡死有关）以及 `dispatch path`。


---

## Assistant <sup>2026/8/10 16:55:07</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== _sync_metadata_across_dp bounds ===\"\necho \"CURRENT:\"; grep -n \"def _sync_metadata_across_dp\" \"$CUR\"; awk 'NR>=1965 && /^    def [a-zA-Z]/ && NR>1965{print \"  next def at \"NR; exit}' \"$CUR\"\necho \"THEROADTOFREE:\"; grep -n \"def _sync_metadata_across_dp\" \"$TRF\"; awk 'NR>=1663 && /^    def [a-zA-Z]/ && NR>1663{print \"  next def at \"NR; exit}' \"$TRF\"",
  "description": "Find _sync_metadata_across_dp bounds"
}
```

</details>


---

## User <sup>2026/8/10 17:05:53</sup>

<details>
<summary>Tool Result</summary>

```
=== _sync_metadata_across_dp bounds ===
CURRENT:
1965:    def _sync_metadata_across_dp(
  next def at 2037
THEROADTOFREE:
1663:    def _sync_metadata_across_dp(
  next def at 1734
```

</details>


---

## Assistant <sup>2026/8/10 17:06:06</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nsed -n '1965,2036p' \"$CUR\" > /tmp/cur_sync.py\nsed -n '1663,1733p' \"$TRF\" > /tmp/trf_sync.py\necho \"=== DIFF _sync_metadata_across_dp (trf vs cur) ===\"\ndiff /tmp/trf_sync.py /tmp/cur_sync.py",
  "description": "Diff _sync_metadata_across_dp"
}
```

</details>


---

## User <sup>2026/8/10 17:06:08</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF _sync_metadata_across_dp (trf vs cur) ===
21c21,29
<         packed_tensor = torch.zeros(3, self.dp_size, device="cpu", dtype=torch.int32)
---
>         # On certain devices, CPU-side all_reduce may return dirty data. 
>         # When dp_allreduce_on_npu is True, route DP metadata
>         # synchronization through the NPU device group to avoid data corruption.
>         device_str, group = (
>             ("npu", get_dp_group().device_group)
>             if self.ascend_config.dp_allreduce_on_npu
>             else ("cpu", get_dp_group().cpu_group)
>         )
>         packed_tensor = torch.zeros(3, self.dp_size, device=device_str, dtype=torch.int32)
25,28c33,35
<         import time as _ec_perf_time
<         _sm_t0 = _ec_perf_time.monotonic()
<         dist.all_reduce(packed_tensor, group=get_dp_group().cpu_group)
<         _sm_dt_ms = (_ec_perf_time.monotonic() - _sm_t0) * 1000
---
>         dist.all_reduce(packed_tensor, group=group)
>         if device_str == "npu":
>
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 17:07:21</sup>


---

## Assistant <sup>2026/8/10 17:07:22</sup>

发现了一个关键差异。当前项目修改了 `_sync_metadata_across_dp`，当 `dp_allreduce_on_npu` 开启时，将跨 DP 元数据 `all_reduce` 通过 **NPU device group** 进行路由，而 theroadtofree 总是使用 **CPU group**。我来确认一下 `dp_allreduce_on_npu` 的默认值/用法。


---

## Assistant <sup>2026/8/10 17:07:25</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== dp_allreduce_on_npu definition/default ===\"; grep -rn \"dp_allreduce_on_npu\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20\necho \"\"\necho \"=== theroadtofree: does it have dp_allreduce_on_npu at all? ===\"; grep -rn \"dp_allreduce_on_npu\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -10\necho \"\"\necho \"=== current: all uses of device_group / cpu_group for DP all_reduce ===\"; grep -rn \"device_group\\|cpu_group\\|dp_allreduce_on_npu\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head -20",
  "description": "Check dp_allreduce_on_npu default and usage"
}
```

</details>


---

## User <sup>2026/8/10 17:07:27</sup>

<details>
<summary>Tool Result</summary>

```
=== dp_allreduce_on_npu definition/default ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_config.py:313:        self.dp_allreduce_on_npu = additional_config.get("dp_allreduce_on_npu", False)
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:1986:        # When dp_allreduce_on_npu is True, route DP metadata
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py:1990:            if self.ascend_config.dp_allreduce_on_npu

=== theroadtofree: does it have dp_allreduce_on_npu at all? ===

=== current: all uses of device_group / cpu_group for DP all_reduce ===
1986:        # When dp_allreduce_on_npu is True, route DP metadata
1989:            ("npu", get_dp_group().device_group)
1990:            if self.ascend_config.dp_allreduce_on_npu
1991:            else ("cpu", get_dp_group().cpu_group)
```

</details>


---

## Assistant <sup>2026/8/10 17:08:06</sup>


---

## Assistant <sup>2026/8/10 17:08:08</sup>

`dp_allreduce_on_npu` 默认为 **False** (ascend_config.py:313)，且 theroadtofree 中完全没有该配置——所以除非用户开启了它，否则它不是导致此问题的主动原因。开发者注释中描述的是 *非* edge-cloud 的死锁（由 `is_edge_cloud_pp_mode()` 防护措施修复），这与用户在 edge-cloud 中的症状不同。我需要找到真正的回归问题。让我先看看两个检出仓库之间关键 PD-separation 文件的差异概况，以确定优先级。


---

## Assistant <sup>2026/8/10 17:08:13</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== vllm-ascend PD-separation files: diff line counts (trf vs cur) ===\"\nfor f in vllm_ascend/patch/platform/patch_engine_core.py vllm_ascend/patch/platform/patch_multiproc_executor.py vllm_ascend/patch/platform/patch_balance_schedule.py vllm_ascend/worker/worker.py vllm_ascend/worker/model_runner_v1.py vllm_ascend/worker/edge_cloud/batched_model_runner.py vllm_ascend/patch/platform/patch_dp_device_ids.py; do\n  if [ -f \"C:/theroadtofree_github/vllm-ascend/$f\" ] && [ -f \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/$f\" ]; then\n    n=$(diff \"C:/theroadtofree_github/vllm-ascend/$f\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/$f\" 2>/dev/null | grep -c '^[<>]')\n    echo \"$n  $f\"\n  else\n    echo \"MISSING  $f\"\n  fi\ndone\necho \"\"\necho \"=== vllm side PD files ===\"\nfor f in vllm/v1/executor/multiproc_executor.py vllm/v1/engine/core.py vllm/v1/executor/shared_model_multiproc_executor.py; do\n  base=$(basename \"$f\")\n  if [ -f \"C:/theroadtofree_github/vllm/$f\" ] && [ -f \"c:/v0.23.0_lwd_acc_test_br/vllm/$f\" ]; then\n    n=$(diff \"C:/theroadtofree_github/vllm/$f\" \"c:/v0.23.0_lwd_acc_test_br/vllm/$f\" 2>/dev/null | grep -c '^[<>]')\n    echo \"$n  $f\"\n  fi\ndone",
  "description": "Diff stat of PD-separation files between checkouts"
}
```

</details>


---

## User <sup>2026/8/10 17:11:16</sup>

<details>
<summary>Tool Result</summary>

```
=== vllm-ascend PD-separation files: diff line counts (trf vs cur) ===
50  vllm_ascend/patch/platform/patch_engine_core.py
0  vllm_ascend/patch/platform/patch_multiproc_executor.py
91  vllm_ascend/patch/platform/patch_balance_schedule.py
573  vllm_ascend/worker/worker.py
2738  vllm_ascend/worker/model_runner_v1.py
82  vllm_ascend/worker/edge_cloud/batched_model_runner.py
MISSING  vllm_ascend/patch/platform/patch_dp_device_ids.py

=== vllm side PD files ===
62  vllm/v1/executor/multiproc_executor.py
279  vllm/v1/engine/core.py
0  vllm/v1/executor/shared_model_multiproc_executor.py
```

</details>


---

## Assistant <sup>2026/8/10 17:11:26</sup>


---

## Assistant <sup>2026/8/10 17:11:28</sup>

`model_runner_v1.py` 中有 2738 行差异的代码（准确度相关工作），但我已经确认 `_dummy_run` 的核心逻辑基本没有变化。集合通信配对的回归问题更有可能出现在较小的编排差异中。我来对比一下云 dummy 调度路径：`multiproc_executor.py` (vllm) 和 `patch_engine_core.py`。


---

## Assistant <sup>2026/8/10 17:11:29</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== DIFF vllm/v1/executor/multiproc_executor.py (trf vs cur) ===\"\ndiff \"C:/theroadtofree_github/vllm/vllm/v1/executor/multiproc_executor.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/executor/multiproc_executor.py\"",
  "description": "Diff multiproc_executor.py between checkouts"
}
```

</details>


---

## User <sup>2026/8/10 17:11:29</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF vllm/v1/executor/multiproc_executor.py (trf vs cur) ===
18c18
< from functools import cached_property, partial
---
> from functools import partial
62a63
> from vllm.v1.executor.vllm_net_devices import set_worker_net_device
457,461c458,462
<         logger.info(
<             "[EDGE-ENQUEUE] %s enqueue took %.3f ms",
<             _bt,
<             _dt_ms,
<         )
---
>         # logger.info(
>         #     "[EDGE-ENQUEUE] %s enqueue took %.3f ms",
>         #     _bt,
>         #     _dt_ms,
>         # )
511a513,514
>         initial_count = len(active_procs())
> 
513c516,519
<         logger.debug("Worker Termination: allow workers to gracefully shutdown")
---
>         logger.info(
>             "[shutdown] Executor: waiting for worker exit count=%d",
>             initial_count,
>         )
514a521
>             logger.info_once("[shutdown] Executor: all workers exited gracefully")
518,519c525,531
<         logger.debug("Worker Termination: workers still running send
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 17:11:49</sup>


---

## Assistant <sup>2026/8/10 17:11:51</sup>

`multiproc_executor` 的差异部分属于日志/关闭相关内容，再加上 `set_worker_net_device`（NIC 映射）。我来查看一下 PD-separation 的调度程序 —— `patch_engine_core.py` 和 `patch_balance_schedule.py` —— 因为 dummy-count 不匹配会导致 all-toall 死锁。


---

## Assistant <sup>2026/8/10 17:11:51</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== DIFF patch_engine_core.py (trf vs cur) ===\"\ndiff \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_engine_core.py\"",
  "description": "Diff patch_engine_core.py"
}
```

</details>


---

## User <sup>2026/8/10 17:11:52</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF patch_engine_core.py (trf vs cur) ===
781,782d780
<     import time as _ec_perf_time
<     _ar_t0 = _ec_perf_time.monotonic()
784d781
<     _ar_dt_ms = (_ec_perf_time.monotonic() - _ar_t0) * 1000
786,789d782
<     logger.error(
<         "[EC-PERF][COORD-BT] dp_rank=%s cnt=%s all_reduce=%.3fms bt_ids=%s",
<         dp_rank, _cnt, _ar_dt_ms, bt_ids,
<     )
810,814d802
<             logger.error(
<                 "[EC-PERF][DEFER] dp_rank=%s cnt=%s rule=2(DECODE_LAST) "
<                 "bt_ids=%s waitings=%s -> peer dummy DL step",
<                 dp_rank, _cnt, bt_ids, waitings,
<             )
821,825d808
<                 logger.error(
<                     "[EC-PERF][DEFER] dp_rank=%s cnt=%s rule=1(EMPTY-defer) "
<                     "bt_ids=%s waitings=%s -> DF deferred 1 step (no compute)",
<                     dp_rank, _cnt, bt_ids, waitings,
<                 )
857a841,847
>     # [ascend insert] Merge worker cleanup stashed from EMPTY batches
>     # BEFORE publ
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 17:12:16</sup>


---

## Assistant <sup>2026/8/10 17:12:18</sup>

编排差异（`patch_engine_core`、`multiproc_executor`）是日志记录以及一个 `worker-cleanup-merge` 的正确性修复——而不是集合通信配对的变更。回归问题一定出现在 `model_runner_v1.py` 的 2738 行差异中（准确性工作）——即在前向传播内部。让我完整地读取 `segment_a` 前向传播，看看它运行了哪些集合通信/PP操作。


---

## Assistant <sup>2026/8/10 17:12:18</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 60,
  "offset": 8768
}
```

</details>


---

## User <sup>2026/8/10 17:12:18</sup>

<details>
<summary>Tool Result</summary>

```
8768	                    logger.info(
8769	                        "[MODEL-FWD] _dummy_run _model_forward: "
8770	                        "layer_slice_info=%s",
8771	                        None if layer_slice_info is None else {
8772	                            "start_layer": layer_slice_info.start_layer,
8773	                            "end_layer": layer_slice_info.end_layer,
8774	                            "total_slices": layer_slice_info.total_slices,
8775	                            "slice_index": layer_slice_info.slice_index,
8776	                            "is_first_slice": layer_slice_info.is_first_slice,
8777	                            "is_last_slice": layer_slice_info.is_last_slice,
8778	                        },
8779	                    )
8780	                    outputs = self._model_forward(
8781	                        num_tokens_padded, input_ids, positions,
8782	                        intermediate_tensors, inputs_embeds,
8783	                        layer_slice_in
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 17:13:01</sup>


---

## Assistant <sup>2026/8/10 17:13:03</sup>

调度和 `_dummy_run` 逻辑是一样的；回归问题出在 2738 行的 `model_runner_v1.py` 差异中——即 `segment_a` 调用的前向传播内部。`segment_a` 前向传播调用了 `_model_forward`（包含 TP all-reduces 和可能的跨 DP EP all-toall 的层切片模型运行），然后是 `drafter.dummy_run`。这是一个庞大的对比任务。让我将重点放在前向路径的对比上，委派给一个子智能体来处理，并提供我所掌握的所有上下文。


---

## Assistant <sup>2026/8/10 17:13:25</sup>

<details>
<summary>Tool: <code>Agent</code></summary>

```json
{
  "description": "Find cloud dummy deadlock regression",
  "prompt": "You are debugging a deadlock regression in vllm-ascend. Two checkouts of the same project exist:\n\n- WORKING (no hang): `C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py`\n- BROKEN (hangs): `c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py`\n\n## Scenario\nEdge-cloud PD-separation (Prefill/Decode separation) with DP (data-parallel) > 1. After sending ONE request, the engine hangs. The hang is the CLOUD DP rank's dummy run.\n\n## Hang stack (cloud dummy)\n```\n_dummy_run (vllm_ascend/worker/model_runner_v1.py:8814)   # BROKEN file line numbers\ndecorate_context (torch/utils/_contextlib.py:124)\nexecute_dummy_batch (vllm_ascend/worker/worker.py:1956)\nworker_busy_loop (vllm/v1/executor/multiproc_executor.py:1206)\n```\nLine 8814 in BROKEN is:\n```python\n_has_nan = bool(torch.isnan(hidden_states).any().item()) if hasattr(hidden_states, 'shape') and hidden_states.dim() > 0 else '?'\n```\nThis `.item()` syncs the NPU stream and never returns — meaning a collective op queued earlier on the stream (a TP all_reduce, a cross-DP EP all-toall, or a PP send/recv inside the segment_a forward) never completes because the peer DP rank isn't doing a matching collective. This is a classic cross-DP / cross-PP collective-pairing deadlock.\n\n## What I have ALREADY ruled out (do NOT re-investigate these)\n- `execute_dummy_batch` in worker.py: identical `uniform_decode=False` behavior in both (PD-sep+DP). Not the cause.\n- `_dummy_run` body in model_runner_v1.py: diffed — essentially identical between the two checkouts (only minor refactors: copy_to_gpu→copy_snapshot_to_gpu, dynamic_eplb, eplb_heat_collection_status param, `if self.drafter and not profile_cpp`). The segment-skip logic (`_peer_bt`, `_skip_head/_skip_tail`, `is_edge_cloud_pp_mode()`) is identical.\n- `_sync_metadata_across_dp`: only diff is an added `dp_allreduce_on_npu` option (default False) tha
...(truncated)
```

</details>


---

## User <sup>2026/8/10 17:13:25</sup>

<details>
<summary>Tool Result</summary>

```
Async agent launched successfully. (This tool result is internal metadata — never quote or paste any part of it, including the agentId below, into a user-facing reply.)
agentId: a9ac119ee6614b7d5 (internal ID - do not mention to user. Use SendMessage with to: 'a9ac119ee6614b7d5', summary: '<5-10 word recap>' to continue this agent.)
The agent is working in the background. You will be notified automatically when it completes. You know nothing about its results until that notification arrives — do not report, assume, or predict them; continue other work or respond to the user in the meantime.
Do not duplicate this agent's work — avoid working with the same files or topics it is using.
output_file: C:\Users\root\AppData\Local\Temp\claude\c--v0-23-0-lwd-acc-test-br\f13f2dd8-1b8a-4bb8-86e0-6dd49e41955f\tasks\a9ac119ee6614b7d5.output
Do NOT Read or tail this file via the shell tool — it is the full subagent JSONL transcript and reading it will overflow your context. If the user asks for prog
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 17:13:52</sup>


---

## Assistant <sup>2026/8/10 17:13:54</sup>

在 forward-path 对比运行的同时，我来检查一下非重叠的角度：`engine/core.py` 中的 DP 协调（279 行差异）——它控制着 dummy 何时触发以及 DP step 的配对。这里的变更可能会导致 cloud dummy 的触发次数与 real cloud 的 all-toall 次数不匹配。


---

## Assistant <sup>2026/8/10 17:13:56</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== DIFF vllm/v1/engine/core.py (trf vs cur) — functional (non-logging) changes ===\"\ndiff \"C:/theroadtofree_github/vllm/vllm/v1/engine/core.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/engine/core.py\" | grep -v \"^[<>] .*logger\\.\\|^[<>] .*#\\|^[<>] *$\\|^[<>] .*import time\\|^[<>] .*_ec_perf_time\\|^[<>] .*monotonic\\|^[<>] *\\\".*\\|^[<>] *'.*\\|EC-PERF\\|PD-DIAG\\|DPDBG\\|SLICE-DIAG\" | head -120",
  "description": "Diff engine/core.py filtering out logging noise"
}
```

</details>


---

## User <sup>2026/8/10 17:21:56</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF vllm/v1/engine/core.py (trf vs cur) — functional (non-logging) changes ===
9d8
< import logging
26c25,28
< from vllm.distributed import stateless_destroy_torch_distributed_process_group
---
> from vllm.distributed import (
>     cleanup_dist_env_and_memory,
>     stateless_destroy_torch_distributed_process_group,
> )
28c30
< from vllm.logger import logger
---
> from vllm.logger import init_logger
52a55
> from vllm.v1.core.single_type_kv_cache_manager import register_all_kvcache_specs
76c79
< from vllm.v1.kv_cache_interface import KVCacheConfig
---
> from vllm.v1.kv_cache_interface import KVCacheConfig, get_kv_cache_spec_kind
82c85
< from vllm.v1.utils import compute_iteration_details
---
> from vllm.v1.utils import IterationDetails, compute_iteration_details
84a88,89
> logger = init_logger(__name__)
175c180
---
177c182
<                 content: dict[int, Any] = {}
---
>                 content: dict[tuple[int, int], Any] = {}
181c186
<                 kv_connector.set_xfer_ha
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 17:22:24</sup>


---

## Assistant <sup>2026/8/10 17:22:26</sup>

虽然 forward-path 子代理正在运行，我来检查一个非重叠且明确的假设：即 `dp_allreduce_on_npu` 是否真的在 config 或 launch script 中被开启（theroadtofree 会忽略这个未知的 key -> 使用 CPU -> 正常工作；而当前版本遵循该设置 -> 使用 NPU -> 死锁）。我来搜索一下 config 和 launch 文件。


---

## Assistant <sup>2026/8/10 17:22:29</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== Search for dp_allreduce_on_npu in configs/scripts/yamls across current project ===\"\ngrep -rn \"dp_allreduce_on_npu\" \"c:/v0.23.0_lwd_acc_test_br/\" 2>/dev/null | grep -v \"\\.pyc\\|model_runner_v1.py\\|ascend_config.py\" | head -20\necho \"\"\necho \"=== Any additional_config / edge_cloud_config JSON/YAML with dp_allreduce ===\"\ngrep -rni \"dp_allreduce\" \"c:/v0.23.0_lwd_acc_test_br/\" 2>/dev/null | grep -v \"\\.pyc\\|\\.py:\" | head -20\necho \"\"\necho \"=== launch/example scripts referencing edge_cloud_config or additional_config ===\"\ngrep -rln \"edge_cloud_config\\|additional_config\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/\" 2>/dev/null | grep -iv \"\\.py$\\|\\.pyc\\|locale\" | head",
  "description": "Search for dp_allreduce_on_npu in configs and scripts"
}
```

</details>


---

## User <sup>2026/8/10 19:32:28</sup>

<details>
<summary>Tool Result</summary>

```
=== Search for dp_allreduce_on_npu in configs/scripts/yamls across current project ===
c:/v0.23.0_lwd_acc_test_br/.claude-code-history/2026-08-10_172229_ide_selectionThe-user-selected-the-lin_f13f2dd8.md:3938:>         # When dp_allreduce_on_npu is True, route DP metadata
c:/v0.23.0_lwd_acc_test_br/.claude-code-history/2026-08-10_172229_ide_selectionThe-user-selected-the-lin_f13f2dd8.md:3942:>             if self.ascend_config.dp_allreduce_on_npu
c:/v0.23.0_lwd_acc_test_br/.claude-code-history/2026-08-10_172229_ide_selectionThe-user-selected-the-lin_f13f2dd8.md:3970:发现了一个关键差异。当前项目修改了 `_sync_metadata_across_dp`，当 `dp_allreduce_on_npu` 开启时，将跨 DP 元数据 `all_reduce` 通过 **NPU device group** 进行路由，而 theroadtofree 总是使用 **CPU group**。我来确认一下 `dp_allreduce_on_npu` 的默认值/用法。
c:/v0.23.0_lwd_acc_test_br/.claude-code-history/2026-08-10_172229_ide_selectionThe-user-selected-the-lin_f13f2dd8.md:3983:  "description": "Check dp_allreduce_on_npu default and usage"
c:/v0.23.0_lwd_acc_test_br/.claude-code-hist
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:33:19</sup>


---

## Assistant <sup>2026/8/10 19:33:20</sup>

目前没有仓库配置设置 `dp_allreduce_on_npu=true`（只有代码定义匹配）——因此除非用户的外部配置启用了它，否则它是无效的。在 forward-path 子代理完成工作的同时，让我检查一下非重叠的 DP-step 调度器：`patch_balance_schedule.py`（即触发 dummy 的 `BalanceDPEngineCoreProc` 繁忙循环）。


---

## Assistant <sup>2026/8/10 19:33:21</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== DIFF patch_balance_schedule.py (trf vs cur) - functional only ===\"\ndiff \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/patch/platform/patch_balance_schedule.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/patch/platform/patch_balance_schedule.py\" | grep -v \"^[<>] .*logger\\|^[<>] *#\\|^[<>] *$\\|EC-PERF\\|PD-DIAG\\|DPDBG\" | head -80",
  "description": "Diff patch_balance_schedule.py functional changes"
}
```

</details>


---

## User <sup>2026/8/10 19:33:25</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF patch_balance_schedule.py (trf vs cur) - functional only ===
1a2
> import os
26a28,29
> from vllm_ascend.utils import vllm_version_is
31a35,42
>     try:
>         from vllm_ascend.ascend_config import get_ascend_config
>         return bool(get_ascend_config().enable_balance_scheduling)
>     except Exception:
>         pass
33c44,46
<     return bool(additional_config.get("enable_balance_scheduling", False))
---
>     if "enable_balance_scheduling" in additional_config:
>         return bool(additional_config["enable_balance_scheduling"])
>     return bool(int(os.getenv("VLLM_ASCEND_BALANCE_SCHEDULING", "0")))
71c84
<     def schedule(self) -> SchedulerOutput:
---
>     def schedule(self, throttle_prefills: bool = False) -> SchedulerOutput:
73c86,88
<             return super().schedule()
---
>             if vllm_version_is("0.23.0"):
>                 return super().schedule()
>             return super().schedule(throttle_prefills)
276,278c291
<             skipped_waitin
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:33:50</sup>


---

## Assistant <sup>2026/8/10 19:33:59</sup>

我已经彻底排查了编排层。让我为您提供一份中期状态报告，同时完成前向路径的深度对比。

## 目前为止的发现

**挂起机制（已确认）：** [model_runner_v1.py:8814](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8814) 处的 `.item()` 是一个诊断性的流同步。它从不返回，因为 `segment_a` 前向传播中较早排入队列的集合通信操作（跨 DP EP all-toall 或 TP all_reduce）从未完成——对等 DP rank 没有执行匹配的集合通信。这是一个经典的跨 DP 集合通信配对死锁，而非 `.item()` 本身的问题。

**已排除与 theroadtofree（工作版本）的差异：**
- `execute_dummy_batch` / `uniform_decode` — 两者在 PD-sep+DP 中均为 `False`。✗
- `_dummy_run` 主体（跳过逻辑、`_peer_bt`、segment_a/e） — 实际上完全相同。✗
- 调度 (`multiproc_executor` `worker_busy_loop`，`patch_engine_core` `_patched_execute_dummy_batch`) — 仅日志记录 + 一个工作清理合并。✗
- 调度器 (`patch_balance_schedule` `run_busy_loop` dummy 触发器) — 相同。✗

**两个剩余的嫌疑点：**

1. **`dp_allreduce_on_npu`（如果您的配置启用了它）。** 当前项目添加了此选项（[ascend_config.py:313](vllm-ascend/vllm_ascend/ascend_config.py#L313)，默认为 `False`）；theroadtofree 完全没有此功能。如果您的 `additional_config` 设置了 `dp_allreduce_on_npu: true`，那么 `_sync_metadata_across_dp` 会将跨 DP 元数据 all_reduce 路由到 **NPU stream** 而不是 CPU。这会将元数据 all_reduce 序列化在挂起的跨 DP EP all-toall 之后，从而在 dummy 的 sync_metadata 和实际 rank 的前向传播之间造成循环等待。theroadtofree 会忽略该未知的配置键 → 使用 CPU → 不会死锁。
   - **需要您执行的操作：** 检查您启动时的 `additional_config` / `edge_cloud_config` 是否设置了 `dp_allreduce_on_npu: true`。如果是，请将其设置为 `false`（或删除）— 这将恢复 theroadtofree 的行为。

2. **前向传播路径** (`_model_forward` / MoE all-toall / drafter `dummy_run`) — 在 `model_runner_v1.py` 中有约 2738 行差异的准确性变更。我正在运行一种侧重于此的对比，以精准定位改变了 dummy 所执行的集合通信计数/顺序的函数级变更。一旦完成，我将立即报告。

您能否在分析完成的同时，确认您的配置中是否设置了 `dp_allreduce_on_npu`？这是最有可能的直接原因，如果确认已启用，则可以立即修复。


---

## Assistant <sup>2026/8/10 19:34:01</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== CURRENT: _model_forward bounds ===\"; grep -n \"def _model_forward\\b\" \"$CUR\"; awk 'NR>=8500 && /def _model_forward/{found=NR} found && /^    def [a-zA-Z]/ && NR>found{print \"  next def at \"NR\": \"$0; exit}' \"$CUR\"\necho \"=== THEROADTOFREE: _model_forward bounds ===\"; grep -n \"def _model_forward\\b\" \"$TRF\"; awk 'NR>=7400 && /def _model_forward/{found=NR} found && /^    def [a-zA-Z]/ && NR>found{print \"  next def at \"NR\": \"$0; exit}' \"$TRF\"",
  "description": "Find _model_forward bounds in both"
}
```

</details>


---

## User <sup>2026/8/10 19:34:04</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT: _model_forward bounds ===
6485:    def _model_forward(
=== THEROADTOFREE: _model_forward bounds ===
5772:    def _model_forward(
```

</details>


---

## Assistant <sup>2026/8/10 19:34:08</sup>


---

## Assistant <sup>2026/8/10 19:34:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== CURRENT next def after 6485 ===\"; awk 'NR>6485 && /^    def [a-zA-Z]/ {print NR\": \"$0; exit}' \"$CUR\"\necho \"=== THEROADTOFREE next def after 5772 ===\"; awk 'NR>5772 && /^    def [a-zA-Z]/ {print NR\": \"$0; exit}' \"$TRF\"\necho \"\"\necho \"=== DIFF _model_forward (trf vs cur) ===\"\nsed -n '5772,6484p' \"$TRF\" > /tmp/trf_mf.py\n# current _model_forward end: find it\ncur_end=$(awk 'NR>6485 && /^    def [a-zA-Z]/{print NR-1; exit}' \"$CUR\")\necho \"current _model_forward ends at $cur_end\"\nsed -n \"6485,${cur_end}p\" \"$CUR\" > /tmp/cur_mf.py\ndiff /tmp/trf_mf.py /tmp/cur_mf.py | head -120",
  "description": "Diff _model_forward between checkouts"
}
```

</details>


---

## User <sup>2026/8/10 19:34:14</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT next def after 6485 ===
6721:     def step_has_multimodal_req(self, scheduler_output) -> bool:
=== THEROADTOFREE next def after 5772 ===
5977:     def cloud_prepare_early(self, scheduler_output: "SchedulerOutput") -> None:

=== DIFF _model_forward (trf vs cur) ===
current _model_forward ends at 6720
55a56
>         skip_dsa_fill: bool = False,
62d62
< 
71a72,76
> 
>         Args:
>             skip_dsa_fill: If True, skip filling _dsa_positions_cpu_buf
>                 (caller already filled it, e.g. slow path between first
>                 _prepare_inputs and _run_input_preparation).
88d92
<                 "num_scheduled_tokens_compressed_list": None,
100c104
<                 num_scheduled_tokens_compressed_list,
---
> 
107c111
<                 num_scheduled_tokens_compressed_list,
---
> 
112a117,134
>         # Fill _dsa_positions_cpu_buf for DSA compression.
>         # cloud_prepare_early calls _run_input_preparation directly and
>         # relies on this fill.  T
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:34:45</sup>


---

## Assistant <sup>2026/8/10 19:34:46</sup>

**重大发现。** theroadtofree 中有一个 `cloud_prepare_early` 方法（在工作版本中），其注释*准确*描述了这种死锁：

> *"Without this, sync_metadata runs before execute_model sets `_dp_batch_type_id`... so it uses a stale value (0 from the last DUMMY) -> the peer cloud sees peer_bt=0, treats this as DUMMY and skips the all-toall, while this cloud runs the real all-toall -> cross-DP all-toall mismatch -> deadlock."*

我来核实一下当前（损坏的）项目是否缺失此项，或者未能正确设置 `_dp_batch_type_id`。


---

## Assistant <sup>2026/8/10 19:34:48</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== CURRENT: cloud_prepare_early present? ===\"; grep -n \"def cloud_prepare_early\\|cloud_prepare_early\" \"$CUR\" | head\necho \"=== THEROADTOFREE: cloud_prepare_early present? ===\"; grep -n \"def cloud_prepare_early\\|cloud_prepare_early\" \"$TRF\" | head\necho \"\"\necho \"=== CURRENT: where _dp_batch_type_id is set (relative to sync_metadata) ===\"; grep -n \"_dp_batch_type_id\\s*=\\|_sync_metadata_across_dp\\|cloud_prepare_early\\|def execute_model\" \"$CUR\" | head -30",
  "description": "Check if current has cloud_prepare_early and where _dp_batch_type_id is set"
}
```

</details>


---

## User <sup>2026/8/10 19:34:52</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT: cloud_prepare_early present? ===
4631:                        # cloud_prepare_early).  Return empty output consistent
6554:        ``cloud_prepare_early`` has no prior inline call and passes
6564:        # (e.g. cloud_prepare_early may have cleared all requests).
6602:        # cloud_prepare_early calls _run_input_preparation directly and
6735:        # new reqs this step: cloud recv runs BEFORE cloud_prepare_early builds
6775:    def cloud_prepare_early(self, scheduler_output: "SchedulerOutput") -> None:
6788:            "cloud_prepare_early should only be called in edge-cloud mode"
6791:            "cloud_prepare_early should only be called on cloud side"
6853:        # cloud_prepare_early runs BEFORE the forward pass (outside
=== THEROADTOFREE: cloud_prepare_early present? ===
3977:                        # cloud_prepare_early).  Return empty output consistent
5841:        ``cloud_prepare_early`` has no prior inline call and passes
5846:        # (e.g. cloud_prepare_ear
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:35:14</sup>


---

## Assistant <sup>2026/8/10 19:35:15</sup>

两个检出仓库都包含 `cloud_prepare_early`，且都在 `sync_metadata` 之前设置了 `_dp_batch_type_id`——所以已知的死锁修复在两者中都存在。让我直接对比一下 `cloud_prepare_early`，因为死锁注释就在那里，而且这是决定 all-toall 配对的云真实前向传播设置。


---

## Assistant <sup>2026/8/10 19:35:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\ncur_end=$(awk 'NR>6775 && /^    def [a-zA-Z]/{print NR-1; exit}' \"$CUR\")\ntrf_end=$(awk 'NR>5977 && /^    def [a-zA-Z]/{print NR-1; exit}' \"$TRF\")\necho \"current cloud_prepare_early: 6775-$cur_end; theroadtofree: 5977-$trf_end\"\nsed -n \"6775,${cur_end}p\" \"$CUR\" > /tmp/cur_cpe.py\nsed -n \"5977,${trf_end}p\" \"$TRF\" > /tmp/trf_cpe.py\necho \"=== DIFF cloud_prepare_early (trf vs cur), functional only ===\"\ndiff /tmp/trf_cpe.py /tmp/cur_cpe.py | grep -v \"^[<>] *#\\|^[<>] *$\\|^[<>] .*logger\\|EC-PERF\\|PD-DIAG\\|DPDBG\" | head -90",
  "description": "Diff cloud_prepare_early between checkouts"
}
```

</details>


---

## User <sup>2026/8/10 19:39:26</sup>

<details>
<summary>Tool Result</summary>

```
current cloud_prepare_early: 6775-7386; theroadtofree: 5977-6490
=== DIFF cloud_prepare_early (trf vs cur), functional only ===
7a8,11
>         This method mirrors the normal execute_model slow path STEP BY STEP
>         (same order, same side effects) so that the cloud fast path is
>         observationally identical to not having run early preparation.
75,92d78
<         if (
<             self.use_async_scheduling
<             and self.num_spec_tokens
<             and self.input_batch.prev_req_id_to_index is not None
<         ):
<             for req_id in scheduler_output.scheduled_cached_reqs.req_ids:
<                 if (
<                     req_id not in self.input_batch.prev_req_id_to_index
<                     and (req_state := self.requests.get(req_id)) is not None
<                     and req_state.prev_num_draft_len
<                 ):
<                     req_state.prev_num_draft_len = 0
<         self._update_states(scheduler_output)
96,97c82,83
---
99c85,192

...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:39:50</sup>


---

## Assistant <sup>2026/8/10 19:39:54</sup>

我又发现了一个强有力的线索：当前项目中的 `cloud_prepare_early`（云侧真实前向传播设置）相对于 theroadtofree 进行了**重写**——它不再调用整合后的 `_run_input_preparation()`，而是手动内联了缓慢路径（slow path）（`_update_states`、`_prepare_inputs`、mamba、compress 处理……），并增加了一个 `num_reqs == 0` 的提前返回逻辑。这改变了云侧真实前向传播在跨 DP EP all-toall 之前的输入/形状设置，这可能导致与 dummy 的 all-toall 不再配对。前向路径的深度对比正在进行中，以确定确切的 all-toall 不匹配点。

待子智能体完成后，我会汇报确切的根本原因。在此期间——请您确认 `dp_allreduce_on_npu` 的配置问题仍然很有价值，因为如果启用了它，将是一个直接导致问题的原因。


---

## Assistant <sup>2026/8/10 19:39:54</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 75,
  "offset": 6775
}
```

</details>


---

## User <sup>2026/8/10 19:39:54</sup>

<details>
<summary>Tool Result</summary>

```
6775	    def cloud_prepare_early(self, scheduler_output: "SchedulerOutput") -> None:
6776	        """Pre-compute input preparation on cloud while edge runs segment_a.
6777	
6778	        Caches results in self._cloud_prepare_cache so that when edge data
6779	        arrives, execute_model can skip _update_states, _prepare_inputs,
6780	        _determine_batch_execution_and_padding, and _build_attention_metadata,
6781	        going directly to _preprocess (sync_and_gather) + _model_forward.
6782	
6783	        This method mirrors the normal execute_model slow path STEP BY STEP
6784	        (same order, same side effects) so that the cloud fast path is
6785	        observationally identical to not having run early preparation.
6786	        """
6787	        assert self._edge_cloud_enabled, (
6788	            "cloud_prepare_early should only be called in edge-cloud mode"
6789	        )
6790	        assert self.edge_cloud_cfg.role == "cloud", (
6791	            "cloud_prepare_early should onl
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:40:01</sup>


---

## Assistant <sup>2026/8/10 19:40:08</sup>

我已经梳理了编排层，找到了关键线索。让我总结一下，等待前向路径分析完成（正在运行），然后再推荐具体的修复方案，以免给出不完整的建议。

## 当前进展总结

**挂起原因：** [model_runner_v1.py:8814](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8814) 处的 `.item()` 同步了 NPU 流；`segment_a` 前向传播内部的集合通信（跨 DP EP all-toall）从未完成，因为对等云 DP 没有发出匹配的 all-toall → 导致跨 DP 配对死锁。云 dummy 因此挂起。

**已验证在两个检出库中完全一致**（排除作为原因）：
- `execute_dummy_batch`/`uniform_decode`、`_dummy_run` 跳过逻辑、`_peer_bt`、分发 (`multiproc_executor`/`patch_engine_core`)、调度器 dummy 触发器、`_dp_batch_type_id`-before-`sync_metadata` 修复（两者中 `cloud_prepare_early` 均包含该修复）。

**`model_runner_v1.py` 前向路径中的回归候选**（约 2738 行准确性差异）：
1. `cloud_prepare_early` **重写**为内联慢速路径，而不是调用 `_run_input_preparation()`，并增加了 `num_reqs == 0` 的提前返回 → 改变了云真实前向传播的输入/形状设置，可能导致与 dummy 的 all-toall 不匹配。
2. `_model_forward` 变更：DSA 压缩填充、`_sanitize_placeholder_input_ids_for_forward`、动态 eplb。

**此外（快速检查）：** 如果您的配置设置了 `dp_allreduce_on_npu: true`，这会将 `sync_metadata` all_reduce 路由到 NPU 流 → 导致循环流等待（theroadtofree 完全没有此选项 → 始终使用 CPU）。默认为 `false`，且没有仓库配置启用它，但请确认您的启动配置。

前向路径的深度对比正在确认具体是哪个变更改变了 all-toall 计数/形状。一旦报告完成，我将立即给出确切的根本原因和修复方案。


---

## Assistant <sup>2026/8/10 19:40:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\nTRF=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== CURRENT: execute_model _dp_batch_type_id + skip-logic for REAL cloud (around 4138-4530) ===\"\nsed -n '4138,4160p;4500,4530p' \"$CUR\" 2>/dev/null\necho \"\"\necho \"=== Does CURRENT real-cloud path have the same _peer_bt skip logic as _dummy_run? ===\"\ngrep -n \"_peer_bt\\|_skip_head\\|_skip_tail\\|is_edge_cloud_pp_mode\\|peer_batch_type_id\" \"$CUR\" | awk -F: '$1>=4138 && $1<=5400' | head -20",
  "description": "Check real-cloud execute_model skip logic vs dummy"
}
```

</details>


---

## User <sup>2026/8/10 19:41:12</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT: execute_model _dp_batch_type_id + skip-logic for REAL cloud (around 4138-4530) ===
    def execute_model(
        self,
        scheduler_output: "SchedulerOutput",
        intermediate_tensors: IntermediateTensors | None = None,
        layer_slice_info: Any = None,
    ) -> ModelRunnerOutput | IntermediateTensors | None:
        # PD-separation: encode batch_type for cross-DP sync (0=EMPTY,
        # 1=PF, 2=PL, 3=DF, 4=DL). Packed into sync_metadata all_reduce
        # so the idle DP's DUMMY can match this forward's segment.
        _bt_map = {
            BatchType.EMPTY: 0, BatchType.PREFILL_FIRST: 1,
            BatchType.PREFILL_LAST: 2, BatchType.DECODE_FIRST: 3,
            BatchType.DECODE_LAST: 4,
        }
        self._dp_batch_type_id = _bt_map.get(scheduler_output.batch_type, 0)

        if self.vllm_config.model_config.enable_return_routed_experts:
            if self.routed_experts_initialized:
                self.routed_experts_capturer.clear_buffer()


...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:41:25</sup>


---

## Assistant <sup>2026/8/10 19:41:27</sup>

我正在等待前向路径的深度分析完成，以便在推荐修复方案之前确定具体的不匹配行。在分析运行期间，我上面提供的两项可操作事项仍然有效：

1. **检查您的启动配置中是否包含 `dp_allreduce_on_npu: true`** —— 如果启用了此选项，它是一个直接的死锁原因（theroadtofree 没有此选项，因此始终使用 CPU 并正常工作）。
2. 主要怀疑对象是 `model_runner_v1.py` 中的前向路径重写——特别是 `cloud_prepare_early` 的内联以及 `_model_forward` 的 DSA/sanitize 更改，这些更改改变了云的真实前向 all-toall 配对。

一旦子智能体的前向路径比较报告完成，我将立即提供确切的根本原因和针对性修复。


---

## User <sup>2026/8/10 19:45:16</sup>

<task-notification>
<task-id>a9ac119ee6614b7d5</task-id>
<tool-use-id>call_4b7bd76eca5e4085a8b4b291</tool-use-id>
<output-file>C:\Users\root\AppData\Local\Temp\claude\c--v0-23-0-lwd-acc-test-br\f13f2dd8-1b8a-4bb8-86e0-6dd49e41955f\tasks\a9ac119ee6614b7d5.output</output-file>
<status>completed</status>
<summary>Agent "Find cloud dummy deadlock regression" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>## Report: Cloud Dummy Deadlock Regression Analysis

### Summary

The most likely root cause is the **`set_mc2_tokens_capacity` change** in `c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py` (lines 202-217), which indirectly flips `should_skip_allreduce_across_dp_group` from False to True for the cloud (a KV-consumer MoE rank in PD-sep). This skips the cross-DP metadata all_reduce, desynchronizing the MoE comm-type selection between the dummy and real cloud DP ranks, causing a cross-DP EP all-toall mismatch.

### What I confirmed is NOT the cause

- **`_dummy_run` body** (BROKEN 8342-8844 vs WORKING 7295-7844): essentially identical. The segment_a forward (`_model_forward` at 8780), the skip logic (`_peer_bt`/`_skip_head`/`_skip_tail`), and the drafter guard (`and not profile_cpp`) are all the same.
- **`_model_forward` -&gt; `_edge_cloud_forward` -&gt; `_edge_cloud_forward_cloud`**: identical in both. The cloud forward path is unchanged.
- **`EdgeCloudSegment`** (BROKEN 301 vs WORKING 276): identical.
- **`edge_cloud_compiler.py`** (defines `forward_edge_cloud_segment`): 0 diff lines.
- **MoE ops** (`comm_utils.py` 0 diff, `moe_comm_method.py` minor, `token_dispatcher.py` quant-only, `moe_mlp.py` activation/LoRA-only, `fused_moe_0_23_0.py` functionally equivalent runner): no new cross-DP collectives.
- **Model layers** (`deepseek_v4.py`, `attention/layer.py`): no new collectives.
- **MoE comm type is NOT based on local num_tokens**: `ascend_forward_context.py` line 97-98 selects the comm type using `max_num_tokens = num_tokens_across_dp.max()` (the DP-wide max), NOT the local `num_tokens`. So if the metadata all_reduce runs, dummy and real get the same comm type. The capacity change alone does NOT cause a mismatch when the all_reduce is active.

### The regression: capacity change -&gt; metadata all_reduce skipped -&gt; comm type mismatch

**The causal chain:**

1. **`set_mc2_tokens_capacity`** (`ascend_forward_context.py`):
   - WORKING (line 201-213): `max_num_tokens = min(max_num_reqs * uql, 512)`, so `mc2_tokens_capacity ≈ 512`.
   - BROKEN (line 202-217): `num_tokens_per_tp_rank = min(ceil(max_num_tokens/tp_size), 512)`, so `mc2_tokens_capacity = num_tokens_per_tp_rank * tp_size ≈ 512 * tp_size` (e.g., 4096 for tp_size=8). The 512 cap moved from `max_num_tokens` to `num_tokens_per_tp_rank`, multiplying the effective capacity by `tp_size`.

2. **`should_skip_allreduce_across_dp_group`** (`utils.py`, BROKEN 1230-1275, WORKING 1145-1214):
   - Called by `_sync_metadata_across_dp` (BROKEN `model_runner_v1.py:1981`).
   - For the cloud (KV consumer in PD-sep, MoE model, `recompute_scheduler_enable=False` default), it returns `decode_must_use_mc2 and (prefill_must_use_mc2 or recompute_scheduler_enable)`.
   - `prefill_must_use_mc2 = needs_mc2(max_num_batched_tokens)` calls `select_moe_comm_method(n, vllm_config)` which checks `n &lt;= mc2_tokens_capacity`.
   - **WORKING**: capacity=512. If `max_num_batched_tokens &gt; 512`, `prefill_must_use_mc2 = False`. Result: `True and (False or False) = False`. **All_reduce is DONE.**
   - **BROKEN**: capacity=512*tp_size. If `512 &lt; max_num_batched_tokens &lt;= 512*tp_size`, `prefill_must_use_mc2 = True`. Result: `True and (True or False) = True`. **All_reduce is SKIPPED.**

3. **When the all_reduce is skipped** (BROKEN `model_runner_v1.py:1981-1983`):
   - `num_tokens_across_dp` becomes local-only: `[num_tokens] * dp_size`.
   - `_peer_batch_type_id` is NOT updated (stays at its previous value, initialized to 0 at line 748).
   - In `set_ascend_forward_context` (line 97): `max_num_tokens = num_tokens_across_dp.max()` = the LOCAL num_tokens (not the DP-wide max).

4. **Comm type diverges between dummy and real**:
   - Dummy uses `num_tokens = decode_token_per_req` (small, set at worker.py:1257). Its local `max_num_tokens` is small -&gt; picks **MC2** (all-toall).
   - Real uses `num_tokens = total_num_scheduled_tokens` (large prefill). Its local `max_num_tokens` is large -&gt; picks **ALLTOALL** (A3) or **ALLGATHER** (A2).
   - On A2: MC2 (cross-DP all-toall) vs ALLGATHER (TP all_gather, no cross-DP op) = **deadlock**.
   - On A3: MC2 vs ALLTOALL (both all-toall, but MC2 uses `padded_num_tokens` derived from the now-unsynced `max_tokens_across_dp`, so buffer sizes mismatch) = **hang**.

5. **The dummy reaches `.item()`** (line 8814): The skip logic at line 8714-8733 is guarded by `is_edge_cloud_pp_mode()`. If that returns False (or `_peer_batch_type_id` retains a non-zero stale value from a prior warmup sync), the dummy does NOT skip the forward, runs `_model_forward`, queues the unmatched all-toall on the NPU stream, and the `.item()` sync hangs.

### Why the user's ruling-out missed this

The user ruled out `_sync_metadata_across_dp` saying "only diff is an added `dp_allreduce_on_npu` option." That's true for the method itself. But `should_skip_allreduce_across_dp_group` (a separate function in `utils.py` that `_sync_metadata_across_dp` calls) is **indirectly affected** by the capacity change in `set_mc2_tokens_capacity` -- the `needs_mc2()` helper calls `select_moe_comm_method()` which reads `mc2_tokens_capacity`. This indirect dependency was not part of the diff of `_sync_metadata_across_dp` itself.

### Secondary candidates (lower likelihood)

1. **`deepseek_v4_edge_cloud.py` residual change** (BROKEN): Residual is no longer transmitted across segments; each segment recomputes locally. This is a correctness/OOM optimization (`_make_empty_edge_cloud_intermediate_tensors` creates only "hidden_states"). Not a collective change, but it changes IntermediateTensors keys -- worth verifying the dummy's tensor keys match what the forward expects.

2. **Drafter `dummy_run`** (BROKEN ~8823): Runs AFTER the `.item()` hang point, so cannot cause the FIRST slice's hang. Could cause a LATER slice's hang if the drafter issues an unmatched cross-DP collective (its `_sync_metadata_across_dp(is_draft_model=True)` at `llm_base_proposer.py:599`). The new `step3p5.py` (AscendStep3p5MTPProposer) is new in BROKEN. If the real cloud (middle PP stage) does NOT run the drafter during prefill, the dummy's drafter metadata sync would be unmatched -- but this would hang at the drafter call (line 8823), not at `.item()` (8814).

### Recommended fix to verify

Temporarily force `should_skip_allreduce_across_dp_group` to return False for the cloud dummy (or revert `set_mc2_tokens_capacity` to the WORKING formula) and check if the deadlock disappears. If it does, the fix is to either:
- Not skip the metadata all_reduce when the dummy needs the peer's batch_type for collective pairing, or
- Ensure the dummy uses the DP-wide `max_tokens_across_dp` for comm type selection even when the all_reduce is skipped.

### Key file:line references (BROKEN)

- `ascend_forward_context.py:202-217` -- `set_mc2_tokens_capacity` (changed capacity formula)
- `ascend_forward_context.py:97-98` -- `select_moe_comm_method(max_num_tokens, ...)` uses `num_tokens_across_dp.max()`
- `utils.py:1265-1275` -- `should_skip_allreduce_across_dp_group` with `needs_mc2` depending on capacity
- `model_runner_v1.py:1981-1983` -- skip path in `_sync_metadata_across_dp` (local-only `num_tokens_across_dp`)
- `model_runner_v1.py:748` -- `_peer_batch_type_id = 0` (init, not updated when skipped)
- `model_runner_v1.py:8719` -- `_peer_bt = self._peer_batch_type_id` (stale when skipped)</result>
<usage><subagent_tokens>0</subagent_tokens><tool_uses>80</tool_uses><duration_ms>9111367</duration_ms></usage>
</task-notification>


---

## Assistant <sup>2026/8/10 19:45:26</sup>


---

## Assistant <sup>2026/8/10 19:45:28</sup>

The subagent returned a detailed causal chain. Before relaying it, I need to verify the key links -- subagent analyses can be wrong. The claim: a `set_mc2_tokens_capacity` formula change flips `should_skip_allreduce_across_dp_group` from False→True on the cloud, skipping the metadata all_reduce, leaving `_peer_batch_type_id` stale and `num_tokens_across_dp` local-only, so dummy and real pick different MoE comm types → all-toall mismatch → the `.item()` hang. Let me verify each link directly.


---

## Assistant <sup>2026/8/10 19:45:29</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR_AFC=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py\"\nTRF_AFC=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/ascend_forward_context.py\"\necho \"=== DIFF ascend_forward_context.py (trf vs cur) ===\"\ndiff \"$TRF_AFC\" \"$CUR_AFC\"\necho \"\"\necho \"=== CURRENT set_mc2_tokens_capacity (202-220) ===\"\nsed -n '202,220p' \"$CUR_AFC\"",
  "description": "Verify set_mc2_tokens_capacity diff"
}
```

</details>


---

## User <sup>2026/8/10 19:45:30</sup>

<details>
<summary>Tool Result</summary>

```
=== DIFF ascend_forward_context.py (trf vs cur) ===
1d0
< import logging
12a12
> from vllm.logger import logger
26,27d25
< logger = logging.getLogger(__name__)
< 
75a74
>     eplb_heat_collection_status: bool = False,
179a179,180
>         forward_context.eplb_heat_collection_status = eplb_heat_collection_status
> 
205c206,208
<     if vllm_config.compilation_config.cudagraph_capture_sizes:
---
>     if get_ascend_config().enable_prefill_mc2:
>         max_num_tokens = vllm_config.scheduler_config.max_num_batched_tokens
>     elif vllm_config.compilation_config.cudagraph_capture_sizes:
208,209c211
<         # NOTE: To save memory, we cap the max number of tokens to 512.
<         max_num_tokens = min(max_num_reqs * uniform_decode_query_len, 512)
---
>         max_num_tokens = max_num_reqs * uniform_decode_query_len
212a215,216
>     # NOTE: To save memory, we cap the max number of tokens to 512.
>     num_tokens_per_tp_rank = min(num_tokens_per_tp_rank, 512)
235a240,314
> def _select_a
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:45:58</sup>


---

## Assistant <sup>2026/8/10 19:45:59</sup>

The `set_mc2_tokens_capacity` change is confirmed: BROKEN moves the 512 cap from `max_num_tokens` to `num_tokens_per_tp_rank`, so capacity becomes ~`512*tp_size` (e.g. 4096 for tp=8) vs WORKING's ~512. Now I must verify the decisive links: that `_sync_metadata_across_dp` calls `should_skip_allreduce_across_dp_group`, that function depends on `mc2_tokens_capacity`, and the skip path leaves `_peer_batch_type_id` stale.


---

## Assistant <sup>2026/8/10 19:46:00</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 75,
  "offset": 1965
}
```

</details>


---

## User <sup>2026/8/10 19:46:00</sup>

<details>
<summary>Tool Result</summary>

```
1965	    def _sync_metadata_across_dp(
1966	        self,
1967	        num_tokens: int,
1968	        is_draft_model: bool = False,
1969	        cudagraph_mode: CUDAGraphMode = CUDAGraphMode.NONE,
1970	        allow_dp_padding: bool = False,
1971	    ) -> tuple[int, torch.Tensor | None, CUDAGraphMode]:
1972	        # TODO: In vLLM, the only thing that needs to be synced is num_tokens, but in
1973	        # our case, we still need to sync the other two flags as well. So we need to
1974	        # include them in the all_reduce operation, and more over, we CANNOT skip it
1975	        # even if we are running in eager mode, which harms performance.
1976	        # FIXME: Restore the `or self.vllm_config.model_config.enforce_eager` here
1977	        # immediately once the other two flags are no longer needed.
1978	        if self.dp_size == 1:
1979	            return num_tokens, None, cudagraph_mode
1980	
1981	        if should_skip_allreduce_across_dp_group(self.vllm_config, is_draft_model):
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:46:29</sup>


---

## Assistant <sup>2026/8/10 19:46:30</sup>

Verified the skip path: [model_runner_v1.py:1981-1983](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L1981-L1983) -- when `should_skip_allreduce_across_dp_group` returns True, the all_reduce is skipped, `num_tokens_after_padding` becomes local-only `[num_tokens]*dp_size`, and `_peer_batch_type_id` is NOT updated (stays stale). The normal path sets it at line 2002. Now the make-or-break link: does `should_skip_allreduce_across_dp_group` depend on `mc2_tokens_capacity`?


---

## Assistant <sup>2026/8/10 19:46:31</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR_U=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/utils.py\"\nTRF_U=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/utils.py\"\necho \"=== CURRENT: should_skip_allreduce_across_dp_group + needs_mc2 ===\"\nawk '/def should_skip_allreduce_across_dp_group/,/^def [a-zA-Z]/' \"$CUR_U\" | head -70",
  "description": "Read should_skip_allreduce_across_dp_group in current"
}
```

</details>


---

## User <sup>2026/8/10 19:52:26</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT: should_skip_allreduce_across_dp_group + needs_mc2 ===
def should_skip_allreduce_across_dp_group(vllm_config, is_draft_model: bool = False) -> bool:
```

</details>


---

## Assistant <sup>2026/8/10 19:52:53</sup>


---

## Assistant <sup>2026/8/10 19:52:54</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR_U=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/utils.py\"\nTRF_U=\"C:/theroadtofree_github/vllm-ascend/vllm_ascend/utils.py\"\necho \"=== CURRENT line ===\"; grep -n \"def should_skip_allreduce_across_dp_group\\|def needs_mc2\" \"$CUR_U\"\necho \"=== THEROADTOFREE line ===\"; grep -n \"def should_skip_allreduce_across_dp_group\\|def needs_mc2\" \"$TRF_U\"",
  "description": "Find should_skip and needs_mc2 line numbers"
}
```

</details>


---

## User <sup>2026/8/10 19:52:55</sup>

<details>
<summary>Tool Result</summary>

```
=== CURRENT line ===
1230:def should_skip_allreduce_across_dp_group(vllm_config, is_draft_model: bool = False) -> bool:
1265:    def needs_mc2(n: int) -> bool:
=== THEROADTOFREE line ===
1145:def should_skip_allreduce_across_dp_group(vllm_config, is_draft_model: bool = False) -> bool:
1176:    def needs_mc2(n: int) -> bool:
```

</details>


---

## Assistant <sup>2026/8/10 19:53:12</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\utils.py",
  "limit": 50,
  "offset": 1230
}
```

</details>


---

## User <sup>2026/8/10 19:53:12</sup>

<details>
<summary>Tool Result</summary>

```
1230	def should_skip_allreduce_across_dp_group(vllm_config, is_draft_model: bool = False) -> bool:
1231	    """Decide whether to skip the all-reduce across the DP group.
1232	
1233	    Skipping is applicable for all dense models and for moe models only on ranks
1234	    that act as KV consumers. We skip the DP all-reduce when either:
1235	    - Both the prefill and decode communication methods are MC2 (or FUSED_MC2), or
1236	    - Decode requires MC2 and ascend_config.recompute_scheduler_enable is True.
1237	
1238	    Skipping means each rank may have a different number of tokens, so MC2 needs
1239	    a non-zero global_bs and must NOT receive mc2_mask.
1240	
1241	    Returns False when hierarchy comm is enabled because hierarchy requires
1242	    global_bs=0 (uniform tokens), which is incompatible with skipping allreduce.
1243	
1244	    Recomputed per call (no memoization): potential_max_tokens is a set/get global
1245	    computed once in init, and select_moe_comm_method is just conf
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 19:55:05</sup>


---

## Assistant <sup>2026/8/10 19:55:23</sup>

All four links of the causal chain are now verified in code. Let me present the root cause.

## Root cause: `set_mc2_tokens_capacity` change desyncs the cloud DP dummy/real pairing

The hang is a **cross-DP all-toall pairing deadlock**, and the regression is a capacity-formula change that flips a "skip the metadata all_reduce" flag on for the cloud.

### Verified causal chain

**1. Capacity formula changed** — [ascend_forward_context.py:206-217](vllm-ascend/vllm_ascend/ascend_forward_context.py#L206-L217)

```python
# BROKEN: 512 cap moved onto num_tokens_per_tp_rank
num_tokens_per_tp_rank = (max_num_tokens + tp_size - 1) // tp_size
num_tokens_per_tp_rank = min(num_tokens_per_tp_rank, 512)   # <- cap here
_mc2_tokens_capacity = num_tokens_per_tp_rank * tp_size      # => up to 512*tp_size (e.g. 4096 @ tp=8)
```
theroadtofree caps `max_num_tokens` itself at 512 → capacity ≈ 512. BROKEN caps the per-rank slice → capacity ≈ `512 * tp_size`.

**2. That flips `should_skip_allreduce_across_dp_group` to True for the cloud** — [utils.py:1230-1275](vllm-ascend/vllm_ascend/utils.py#L1230-L1275)

For a MoE **KV-consumer** rank (the cloud in PD-sep), it returns:
```python
decode_must_use_mc2 and (prefill_must_use_mc2 or recompute_scheduler_enable)
# prefill_must_use_mc2 = needs_mc2(max_num_batched_tokens)
#                     = (max_num_batched_tokens <= mc2_tokens_capacity)
```
With capacity inflated to `512*tp`, a typical prefill (`max_num_batched_tokens` ~2048, tp=8 → capacity 4096) now satisfies `<= capacity`, so `prefill_must_use_mc2` becomes **True** → the whole expression flips to **True** (skip). theroadtofree's ~512 capacity keeps it **False** (prefill > 512) → all_reduce runs.

**3. When skipped, the metadata all_reduce is bypassed** — [model_runner_v1.py:1981-1983](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L1981-L1983)

```python
if should_skip_allreduce_across_dp_group(self.vllm_config, is_draft_model):
    num_tokens_after_padding = torch.tensor([num_tokens] * self.dp_size, ...)  # LOCAL only
    return num_tokens, num_tokens_after_padding, cudagraph_mode   # no all_reduce
```
So `_peer_batch_type_id` is **never updated** (stays stale/0, set only at line 2002 in the non-skip path), and `num_tokens_across_dp` becomes **local-only** — each cloud DP rank sees only its own token count.

**4. Comm type / segment decision diverges → all-toall mismatch → hang**

`set_ascend_forward_context` selects the MoE comm type from `num_tokens_across_dp.max()` ([ascend_forward_context.py:97-98](vllm-ascend/vllm_ascend/ascend_forward_context.py#L97-L98)) — now the *local* count, not the DP-wide max. The dummy (`decode_token_per_req`, tiny) and the real cloud (large prefill) pick **different** MoE comm types / segment counts, so the dummy issues a cross-DP all-toall the real cloud doesn't match. The all-toall never completes → the `.item()` stream sync at [model_runner_v1.py:8814](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8814) blocks forever. **This is exactly "云dp的dummy run卡死".**

theroadtofree doesn't flip the flag → both cloud DPs run the all_reduce → agree on the DP-wide max and the same comm type → all-toall pairs 1:1 → no deadlock.

### Why my earlier diff of `_sync_metadata_across_dp` missed it

The `_sync_metadata_across_dp` *method* diff only showed the `dp_allreduce_on_npu` option. The skip itself (`should_skip_allreduce_across_dp_group`, in `utils.py`) is called identically in both checkouts — but its *return value* changes because `mc2_tokens_capacity` changed. It's an indirect dependency, not a code diff in the method.

### Trigger conditions (config-dependent)

The flip happens when `max_num_batched_tokens ≤ 512*tp_size` (BROKEN catches it) but `> 512` (theroadtofree doesn't). So it depends on `max_num_batched_tokens`, `tp_size`, `max_cudagraph_capture_size`, `enable_prefill_mc2`, SoC, and `num_experts`. It requires the cloud to be the KV-consumer MoE rank.

### How to confirm in your logs

- The `[PP-EVT] sync_meta` log ([model_runner_v1.py:2015](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L2015)) prints **only when the all_reduce runs** (it's after the skip-return). If the cloud dummy has **no** `[PP-EVT] sync_meta` line, the skip is active.
- The `[DPDBG] _dummy_run` log ([model_runner_v1.py:8734](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8734)) shows `peer_bt` — if it's `0`/stale while the peer is actually running real work, the desync is confirmed.
- Or at runtime: `get_mc2_tokens_capacity()` and `should_skip_allreduce_across_dp_group(vllm_config)` on the cloud rank.

### Fix options

1. **Targeted (recommended):** make the skip not apply in edge-cloud PD-sep+DP, since dummy/real pairing depends on the metadata all_reduce. In `should_skip_allreduce_across_dp_group`, return `False` when edge-cloud PD-separation is enabled:
   ```python
   if is_edge_cloud_pp_mode():   # or check edge_cloud_config.pd_separation.enabled and dp_size>1
       return False
   ```
   This preserves the capacity/MC2 change for non-PD-sep cases and exactly restores theroadtofree's "all_reduce always runs" behavior where it matters.

2. **Revert the capacity formula** in `set_mc2_tokens_capacity` to cap `max_num_tokens` at 512 (theroadtofree's form). Simplest, but may undo intended MC2-coverage/perf changes on the accuracy branch.

3. **Verify first** via the logs above — if `[PP-EVT] sync_meta` IS present for the cloud dummy (skip not active), then this isn't the trigger and we'd look at the secondary candidates (the `cloud_prepare_early` rewrite, or the drafter's `dummy_run` collective). But the structural chain above is the strongest match for "cloud dummy hangs at `.item()`, single request."

I'd suggest confirming via the `[PP-EVT]`/`[DPDBG]` logs first (option 3), then applying option 1. Want me to implement option 1?


---

## User <sup>2026/8/10 19:57:33</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py in the IDE. This may or may not be related to the current task.</ide_opened_file>

给出中文Root cause和Fix options


---

## Assistant <sup>2026/8/10 19:57:41</sup>


---

## Assistant <sup>2026/8/10 19:58:02</sup>

## Root cause(根因)

**卡死本质:云 DP 的 dummy 与 real 之间的跨 DP all-toall 配对死锁。** `.item()`(model_runner_v1.py:8814)只是一个流同步点,它阻塞是因为 `segment_a` 前向里排队的一个跨 DP 集合通信(MoE EP all-toall)永远完不成——对端云 DP 没有发匹配的 all-toall。

回归点是 `set_mc2_tokens_capacity` 的容量公式改动,它把云侧的 `should_skip_allreduce_across_dp_group` 从 False 翻成了 True,导致跨 DP 元数据 all_reduce 被跳过,dummy 与 real 失去同步。

### 已验证的因果链

**① 容量公式被改** — [ascend_forward_context.py:206-217](vllm-ascend/vllm_ascend/ascend_forward_context.py#L206-L217)

```python
# 本工程(BROKEN):512 上限挪到了 num_tokens_per_tp_rank 上
num_tokens_per_tp_rank = (max_num_tokens + tp_size - 1) // tp_size
num_tokens_per_tp_rank = min(num_tokens_per_tp_rank, 512)   # ← 这里封顶
_mc2_tokens_capacity = num_tokens_per_tp_rank * tp_size      # => 最高 512*tp_size(tp=8 时为 4096)
```
theroadtofree 是对 `max_num_tokens` 本身封顶 512 → 容量 ≈ 512。本工程改成对 per-rank 切片封顶 → 容量 ≈ `512 * tp_size`。

**② 这把云侧 `should_skip_allreduce_across_dp_group` 翻成 True** — [utils.py:1230-1275](vllm-ascend/vllm_ascend/utils.py#L1230-L1275)

对 MoE **KV-consumer** rank(边云 PD-sep 中的云侧),返回:
```python
decode_must_use_mc2 and (prefill_must_use_mc2 or recompute_scheduler_enable)
# prefill_must_use_mc2 = needs_mc2(max_num_batched_tokens)
#                     = (max_num_batched_tokens <= mc2_tokens_capacity)
```
容量被放大到 `512*tp` 后,典型 prefill(`max_num_batched_tokens` ~2048,tp=8 → 容量 4096)落入 `≤ capacity`,`prefill_must_use_mc2` 由 False 变 **True** → 整个表达式翻成 **True(跳过)**。theroadtofree 容量 ~512,prefill>512 → False → all_reduce 正常执行。

**③ 跳过后,元数据 all_reduce 被绕过** — [model_runner_v1.py:1981-1983](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L1981-L1983)

```python
if should_skip_allreduce_across_dp_group(self.vllm_config, is_draft_model):
    num_tokens_after_padding = torch.tensor([num_tokens] * self.dp_size, ...)  # 只有本地值
    return num_tokens, num_tokens_after_padding, cudagraph_mode   # 不做 all_reduce
```
于是 `_peer_batch_type_id` **不再更新**(只在非跳过路径的 2002 行赋值,保持初始/旧值 0),`num_tokens_across_dp` 变成**本地值**——每个云 DP rank 只看到自己的 token 数。

**④ 通信类型/段决策分裂 → all-toall 配对失败 → 卡死**

`set_ascend_forward_context` 用 `num_tokens_across_dp.max()`([ascend_forward_context.py:97-98](vllm-ascend/vllm_ascend/ascend_forward_context.py#L97-L98))选 MoE 通信类型——现在用的是**本地** token 数,不是 DP 全局最大值。dummy(`decode_token_per_req`,很小)和 real 云(大 prefill)选出**不同**的 MoE 通信类型/段数,dummy 发出的跨 DP all-toall 在 real 云侧没有匹配项 → all-toall 永不完成 → 8814 行的 `.item()` 流同步永久阻塞。**这正是「云 dp 的 dummy run 卡死」。**

theroadtofree 不翻这个标志 → 两个云 DP 都做 all_reduce → 对 DP 全局 max 达成一致 → 选同一个通信类型 → all-toall 1:1 配对 → 不死锁。

### 为什么之前 diff `_sync_metadata_across_dp` 没发现

`_sync_metadata_across_dp` 方法本身的 diff 只有 `dp_allreduce_on_npu`。跳过逻辑(`should_skip_allreduce_across_dp_group`,在 `utils.py`)在两个版本里**调用方式完全一样**,但它的**返回值**因为 `mc2_tokens_capacity` 变了而翻转——是间接依赖,不是该方法自身的代码 diff。

### 触发条件(依赖配置)

翻车条件:`max_num_batched_tokens ≤ 512*tp_size`(本工程能覆盖)但 `> 512`(theroadtofree 不覆盖)。所以是否触发取决于 `max_num_batched_tokens`、`tp_size`、`max_cudagraph_capture_size`、`enable_prefill_mc2`、SoC、`num_experts`。且要求云侧是 KV-consumer MoE rank。

### 如何在你的日志里确认

- `[PP-EVT] sync_meta` 日志([model_runner_v1.py:2015](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L2015))**只在 all_reduce 真正执行时打印**(在跳过 return 之后)。如果云 dummy **没有**这行日志,说明被跳过了。
- `[DPDBG] _dummy_run` 日志([model_runner_v1.py:8734](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L8734))会打印 `peer_bt`——如果对端实际在跑 real 而这里 `peer_bt=0`/陈旧,即确认失配。
- 或运行时打印 `get_mc2_tokens_capacity()` 和 `should_skip_allreduce_across_dp_group(vllm_config)` 在云 rank 上的值。

---

## Fix options(修复方案)

### 方案 1(推荐,最小侵入):边云 PD-sep+DP 下强制不跳过

跳过的前提是「两端都用 MC2、对称」,但保活 dummy 打破了对称。dummy/real 配对依赖这个元数据 all_reduce,所以在边云 PD-sep+DP 下不应跳过。在 `should_skip_allreduce_across_dp_group` 开头加守卫:

```python
def should_skip_allreduce_across_dp_group(vllm_config, is_draft_model: bool = False) -> bool:
    # 边云 PD-separation + DP>1:dummy/real 配对依赖此 all_reduce
    # (同步 peer_bt 与 num_tokens_across_dp),跳过会导致 all-toall 配对死锁。
    if is_edge_cloud_pp_mode() and vllm_config.parallel_config.data_parallel_size > 1:
        return False
    ...
```

保留容量/MC2 改动对非边云场景的影响,只在出问题的场景恢复 theroadtofree 的「all_reduce 始终执行」行为。

### 方案 2(最直接):回退容量公式

把 `set_mc2_tokens_capacity` 改回对 `max_num_tokens` 封顶 512(theroadtofree 的形式),容量回到 ~512,`should_skip` 回到 False,all_reduce 恢复执行。最简单,但可能undo 本精度分支有意的 MC2 覆盖/性能改动。

### 方案 3(先验证再修)

先按上面「如何确认」查日志:
- 若云 dummy **没有** `[PP-EVT] sync_meta` 日志、`[DPDBG]` 里 `peer_bt=0`/陈旧 → 确认是本根因,应用方案 1。
- 若 `[PP-EVT] sync_meta` **有**打印(即跳过没生效)→ 本根因不成立,转查次级嫌疑:`cloud_prepare_early` 重写、或 drafter `dummy_run` 的集合通信。

---

**建议顺序:先方案 3 确认,再上方案 1。** 需要我把方案 1 的守卫直接加到 [utils.py:1230](vllm-ascend/vllm_ascend/utils.py#L1230) 吗?


---

## User <sup>2026/8/10 20:09:52</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\log\0810-1.txt in the IDE. This may or may not be related to the current task.</ide_opened_file>

云两dp日志C:\v0.23.0_lwd_acc_test_br\log\0810-1.txt


---

## Assistant <sup>2026/8/10 20:10:20</sup>


---

## Assistant <sup>2026/8/10 20:10:21</sup>

我来检查一下云 DP 日志，以确认元数据 `all_reduce` 是否被跳过。


---

## Assistant <sup>2026/8/10 20:10:23</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0810-1.txt\"\necho \"=== file size / line count ===\"; wc -l \"$LOG\" 2>/dev/null\necho \"\"\necho \"=== sync_meta / DPDBG / dummy markers (counts) ===\"\ngrep -c \"PP-EVT.*sync_meta\" \"$LOG\" 2>/dev/null | sed 's/^/PP-EVT sync_meta: /'\ngrep -c \"DPDBG.*_dummy_run\" \"$LOG\" 2>/dev/null | sed 's/^/DPDBG _dummy_run: /'\ngrep -c \"should_skip\\|skip_allreduce\" \"$LOG\" 2>/dev/null | sed 's/^/should_skip: /'\ngrep -c \"execute_dummy_batch\" \"$LOG\" 2>/dev/null | sed 's/^/execute_dummy_batch: /'\ngrep -c \"MOE-COMM-SELECT\\|MoE comm method\" \"$LOG\" 2>/dev/null | sed 's/^/MOE-COMM-SELECT: /'\ngrep -c \"mc2_tokens_capacity\\|mc2_capacity\" \"$LOG\" 2>/dev/null | sed 's/^/mc2_capacity: /'",
  "description": "Count relevant log markers in cloud DP log"
}
```

</details>


---

## User <sup>2026/8/10 20:10:29</sup>

<details>
<summary>Tool Result</summary>

```
=== file size / line count ===
69 c:/v0.23.0_lwd_acc_test_br/log/0810-1.txt

=== sync_meta / DPDBG / dummy markers (counts) ===
PP-EVT sync_meta: 8
DPDBG _dummy_run: 4
should_skip: 0
execute_dummy_batch: 0
MOE-COMM-SELECT: 0
mc2_capacity: 0
```

</details>


---

## Assistant <sup>2026/8/10 20:10:44</sup>


---

## Assistant <sup>2026/8/10 20:10:44</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\log\\0810-1.txt"
}
```

</details>


---

## User <sup>2026/8/10 20:10:44</sup>

<details>
<summary>Tool Result</summary>

```
1	1、云DP0日志
2	(PassiveEngineCore pid=100722) INFO 08-10 08:14:20 [passive_scheduler.py:325] [DPDBG] PassiveScheduler recv: dp_rank=0 seq=0 kind=DUMMY batch_type=prefill_first tokens=0 kind_counts={'DUMMY': 1}
3	(PassiveEngineCore pid=100722) WARNING 08-10 08:14:20 [passive_scheduler.py:943] [SYNC-QUEUE] rank=0 ready_prefills mismatch: [1, 0]
4	(PassiveEngineCore pid=100722) INFO 08-10 08:14:20 [passive_scheduler.py:627] [COORD-DIAG] _slice_for step=1 bt=prefill_first → no-slice (no decode, no suggest)
5	(PassiveEngineCore pid=100722) INFO 08-10 08:14:20 [passive_core.py:768] [SLICE-DIAG] cloud step enqueue: tokens=0 slices=1 slice_info=None is_first=None is_last=None start=None end=None total=None
6	(PassiveEngineCore pid=100722) INFO 08-10 08:14:20 [passive_core.py:789] [CLOUD-MQ] About to enqueue batch_type=prefill_first total_num_scheduled_tokens=0 seq=0
7	(Worker_DP0_PP1_TP0_EP0 pid=100777) INFO 08-10 08:14:20 [parallel_state.py:1829] [PD] edge_cloud_broadcast_recv: channel=prefill_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 20:12:46</sup>


---

## Assistant <sup>2026/8/10 20:12:50</sup>

这份日志**推翻了我之前的假设**——我需要坦白这一点并转变方向。关键证据：

- `[PP-EVT] sync_meta` **确实**出现了（第 16、22、26、32、54、58、59、62 行）—— `should_skip_allreduce_across_dp_group` 返回了 **False**，`all_reduce` 运行并正确配对（`call=12` 两边都有：虚拟任务 `my_bt=0 peer_bt=1`，真实任务 `my_bt=1 peer_bt=0`）。因此，容量/跳过假设在此处**不成立**。
- 虚拟任务（DP0，`num_tokens=1`，输入 `[1,2048]`）运行了**完整**的前向传播（`skip_head=False skip_tail=False`，第 18/24/28/34 行），启动了 `_model_forward`（第 19/25/29/35 行）——然后**没有 `segment_a OUTPUT` 行**。它在前向传播**内部**挂起了。
- 真实任务（DP1，`num_tokens=1024`）完成了（第 66-70 行有 PP isend + worker done）。

所以挂起是因为虚拟任务（1 token）和真实任务（1024 tokens）在**前向传播内部存在集合通信不匹配**，而不是元数据 `all_reduce` 的问题。让我验证一下 MoE 通信类型使用的是什么 `num_tokens`——这决定了虚拟任务和真实任务是否选择了不同的跨 DP 集合通信。


---

## Assistant <sup>2026/8/10 20:12:51</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ascend_forward_context.py",
  "limit": 60,
  "offset": 60
}
```

</details>


---

## User <sup>2026/8/10 20:12:51</sup>

<details>
<summary>Tool Result</summary>

```
60	    vllm_config: VllmConfig,
61	    num_tokens: int = 0,
62	    num_tokens_across_dp: torch.Tensor | None = None,
63	    in_profile_run: bool = False,
64	    num_actual_tokens: int | None = None,
65	    aclgraph_runtime_mode: CUDAGraphMode = CUDAGraphMode.NONE,
66	    batch_descriptor: BatchDescriptor | None = None,
67	    model_instance: torch.nn.Module = None,
68	    is_draft_model=False,
69	    skip_compiled: bool = False,
70	    max_tokens_across_pcp: int = 0,
71	    draft_attn_metadatas=None,
72	    has_sinks=False,
73	    input_ids=None,
74	    eplb_heat_collection_status: bool = False,
75	):
76	    """A context manager that stores the current forward context,
77	    can be attention metadata, etc.
78	    We add some additional param into forward_context.
79	    """
80	    forward_context_kwargs = {
81	        "attn_metadata": attn_metadata,
82	        "vllm_config": vllm_config,
83	        "num_tokens": num_tokens,
84	        "num_tokens_across_dp": num_tokens_across_dp,
85	 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 20:13:44</sup>


---

## Assistant <sup>2026/8/10 20:14:00</sup>

日志**推翻了我之前的假设**——我需要说明这一点。`[PP-EVT] sync_meta` 确实运行了（两边 `call=12` 都有，`peer_bt` 正确：dummy `my_bt=0 peer_bt=1`，real `my_bt=1 peer_bt=0`）。所以 `should_skip_allreduce_across_dp_group` 返回了 **False**，`all_reduce` 正常配对。容量/跳过假设不成立。

但容量改动**仍是根因**，只是机制不同。关键在 [ascend_forward_context.py:97-98](vllm-ascend/vllm_ascend/ascend_forward_context.py#L97-L98):

```python
max_num_tokens = int(num_tokens_across_dp.max().item()) if num_tokens_across_dp is not None else num_tokens
moe_comm_type = select_moe_comm_method(max_num_tokens, vllm_config, is_draft_model)
```

`all_reduce` 同步后，两边 `max=1024`，**两边按 1024 选同一个通信类型**。容量被放大到 `512*tp_size` 后(tp=4 → 2048)，`1024 ≤ 2048` → 选 **MC2(跨 DP all-toall)**;theroadtofree 容量 ~512,`1024 > 512` → 选 **ALLGATHER/ALLTOALL(非 MC2)**。

## Root cause(日志验证后的修正版)

**容量膨胀让 1024-token prefill 的 MoE 通信类型从「非 MC2」翻成「MC2」,而 MC2 在 dummy(1 token)/real(1024 token) 非均匀 + `should_skip=False`(global_bs=0,MC2 期望均匀)下 all-toall 形状失配 → 死锁。**

日志证据链:
- **云 DP0(dummy)**:`num_tokens=1`,输入 `[1, 2048]`(1 token,**未 pad 到 1024**),`peer_bt=1` → `skip_head=False skip_tail=False` → 跑完整 `_model_forward`(日志 14-19 行)→ **没有 segment_a OUTPUT** → 卡在前向内部。
- **云 DP1(real)**:`num_tokens=1024`,跑完整 prefill,PP isend + worker done(日志 64-70 行)→ **正常完成**。
- `sync_meta` 两边都跑了(`should_skip=False`),`num_tokens_across_dp=[1,1024]`,`max=1024`。
- 两边按 `max=1024` 选通信类型:本工程 `1024 ≤ 2048(capacity)` → **MC2**;theroadtofree `1024 > 512` → **ALLGATHER(A2)/ALLTOALL(A3)**,均不要求 dummy/real 跨 DP 配对。

所以:`should_skip=False` 时 MC2 期望各 rank token 数均匀(`global_bs=0`),但 dummy=1、real=1024 严重不均匀 → MC2 all-toall 形状 1 vs 1024 失配 → dummy 的 all-toall 永不完成 → 前向卡死 → `.item()` 阻塞。theroadtofree 用非 MC2 通信类型(ALLGATHER 无跨 DP 集合通信,或 ALLTOALL 按 token 流式可容忍非均匀),dummy/real 不在跨 DP 集合通信上配对 → 不死锁。

**根因仍是 `set_mc2_tokens_capacity` 的容量公式改动**,但触发路径是「容量膨胀 → 1024 token 落入 MC2 阈值 → MC2 无法容忍 dummy/real 非均匀」,而非我之前说的「跳过 all_reduce」。

## Fix options

### 方案 1(最直接,对齐 theroadtofree):回退容量公式
把 [ascend_forward_context.py:206-217](vllm-ascend/vllm_ascend/ascend_forward_context.py#L206-L217) 改回对 `max_num_tokens` 封顶 512(theroadtofree 形式),容量回到 ~512,`1024 > 512` → 非 MC2 通信类型 → 无跨 DP all-toall 配对问题。最简单,但可能 undo 本分支有意的 MC2 覆盖。

### 方案 2(针对性):dummy 不参与跨 DP EP all-toall
keepalive dummy(1 token)本就不该和 1024-token real 做 MC2 配对。在 dummy 路径里让 MoE 走 TP-only(ALLGATHER)或跳过跨 DP all-toall。但需保证 real 侧也不发跨 DP all-toall,否则 real 侧 all-toall 仍无配对。实质上等价于让此 token 规模不选 MC2。

### 方案 3(若想保留大容量 MC2):dummy pad 到 DP max
让 dummy 的 `num_tokens` pad 到 `num_tokens_across_dp.max()`(1024),使 MC2 各 rank 均匀。但 dummy 输入是 `[1, 2048]`,要 pad 到 1024 token,开销大且违背 keepalive 初衷,不推荐。

### 方案 4(先二次确认)
日志里加一行打印 `mc2_tokens_capacity` 和 `moe_comm_type`(dummy 与 real 各自的值),确认两边都选了 MC2、且 dummy num_tokens=1 未 pad。若确认,上方案 1。

---

**建议:方案 1(回退容量公式)**。它直接对齐已验证可用的 theroadtofree 行为,且日志已确认 `should_skip=False`、dummy num_tokens=1 未 pad、real=1024 完成——这正是 MC2 非均匀失配的死锁特征。要我直接改 `set_mc2_tokens_capacity` 回退成 512 封顶吗?


---

## User <sup>2026/8/10 20:38:01</sup>

<ide_selection>The user selected the lines 209 to 209 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ascend_forward_context.py:
max_num_tokens

This may or may not be related to the current task.</ide_selection>

在set_mc2_tokens_capacity 增加打印，运行是走C:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ascend_forward_context.py的209行，max_num_tokens值是64


---

## Assistant <sup>2026/8/10 20:41:31</sup>


---

## Assistant <sup>2026/8/10 20:41:46</sup>

`max_num_tokens=64` 这个结果**直接否定了我的容量假设**,我需要如实说明。

## 容量假设不成立

line 209 是 else 分支:`max_num_tokens = max_num_reqs * uniform_decode_query_len = 64`。

- 本工程容量:`num_tokens_per_tp_rank = ceil(64/tp_size)`,cap 512 不生效 -> `capacity = ceil(64/4)*4 = 64`(tp=4)。
- theroadtofree else 分支:`max_num_tokens = min(64, 512) = 64` -> 同样 `capacity = 64`。

**两边容量都是 64,容量公式改动在这个配置下根本没产生差异。** 我之前推断的「容量膨胀到 2048 -> 翻成 MC2」是错的。`1024 > 64`,两边都会选非 MC2 通信类型(ALLGATHER/ALLTOALL)。抱歉,这个方向走偏了。

## 日志真正显示的(已确认部分)

- `sync_meta` 正常跑了(`should_skip=False`),`peer_bt` 正确(dummy `peer_bt=1`,real `peer_bt=0`)。
- **dummy(DP0,num_tokens=1,输入 `[1,2048]` 未 pad 到 1024)** 跑完整 `_model_forward`,卡在前向内部(无 segment_a OUTPUT)。
- **real(DP1,num_tokens=1024)** 跑完整 prefill,PP isend + done,**正常完成**。

real 能完成、dummy 卡死,说明是 dummy 前向里某个**跨 DP 集合通信(EP all-toall)形状失配**:dummy 是 1 token、real 是 1024 token,dummy 没有 pad 到 DP 全局 max(1024)。

## 关键缺口:SoC / moe_comm_type

通信类型决定死锁机制,而它取决于 SoC(日志里没打印):

- **若 A2**:`1024 > 64` -> `ALLGATHER`(TP-only,无跨 DP all-toall)。那 dummy 不该因跨 DP all-toall 卡死 -> 卡的是别的东西(TP? PP? 流?),需要换方向查。
- **若 A3**:`1024 > 64` -> `ALLTOALL`(跨 DP)。dummy(1 token)与 real(1024 token)的 ALLTOALL 形状 1 vs 1024 失配 -> 死锁。这与日志完全吻合。

## 建议的下一步:加一行打印确认

在 [ascend_forward_context.py:97-100](vllm-ascend/vllm_ascend/ascend_forward_context.py#L97-L100) 把关键值打出来,跑一次 dummy+real 各看一眼:

```python
max_num_tokens = int(num_tokens_across_dp.max().item()) if num_tokens_across_dp is not None else num_tokens
moe_comm_type = select_moe_comm_method(max_num_tokens, vllm_config, is_draft_model)
import vllm_ascend.envs as _e
logger.info(
    "[MC2-DIAG] dp_rank=%s is_draft=%s local_num_tokens=%s max_across_dp=%s "
    "capacity=%s moe_comm_type=%s soc=%s",
    getattr(vllm_config.parallel_config, "data_parallel_rank", "?"),
    is_draft_model, num_tokens, max_num_tokens,
    get_mc2_tokens_capacity(), moe_comm_type,
    getattr(__import__("vllm_ascend.utils", fromlist=["soc_version"]), "soc_version", lambda: "?")(),
)
```

需要确认两件事:
1. **SoC 是 A2 还是 A3?**(决定是 ALLGATHER 还是 ALLTOALL)
2. **dummy 与 real 的 `moe_comm_type` 是否一致?dummy 的 `local_num_tokens` 是否被 pad 到 `max_across_dp=1024`?**

## 若确认是 A3 / ALLTOALL(最可能)

根因:**cloud dummy 用 `num_tokens=decode_token_per_req=1` 跑完整前向,其跨 DP EP all-toall 形状=1,而 real=1024,dummy 未 pad 到 DP max -> all-toall 形状失配 -> 死锁。** theroadtofree 若在同一 SoC 同样会卡……所以还要核对 theroadtofree 那次跑的 SoC/配置是否和这次一致(很可能不是同一硬件/同一 prefill token 数)。

Fix 方向(待确认后):
- **方案 A**:dummy 前向的 `num_tokens` pad 到 `num_tokens_across_dp.max()`(让 all-toall 形状与 real 对齐)。
- **方案 B**:dummy 不参与跨 DP EP all-toall(走 TP-only / 跳过 MoE all-toall),同时保证 real 侧通信类型也不发跨 DP all-toall(即让此 token 规模不选 ALLTOALL/MC2)。

先把上面那行 `[MC2-DIAG]` 打印跑一下,把 dummy(DP0)和 real(DP1)两行贴出来,我就能定位是 ALLTOALL 形状失配还是别的机制。


---

## User <sup>2026/8/10 20:44:41</sup>

<ide_selection>The user selected the lines 211 to 211 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ascend_forward_context.py:
max_num_reqs

This may or may not be related to the current task.</ide_selection>

soc边云都是a2


---

## Assistant <sup>2026/8/10 20:47:35</sup>


---

## Assistant <sup>2026/8/10 20:47:36</sup>

SoC=A2 是关键。A2 下 `1024 > 64` -> 通信类型是 **ALLGATHER**(不是 MC2/ALLTOALL)。这彻底排除了容量/通信类型翻转的方向。

但 ALLGATHER 是否跨 DP,取决于云侧 EP group 是否跨 DP。如果云 EP group 跨 dp0+dp1,ALLGATHER 就是跨 DP 集合通信,dummy(1 token)和 real(1024 token)形状失配就死锁。让我确认云侧 EP group 的范围。


---

## Assistant <sup>2026/8/10 20:47:38</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== how is EP group built for edge-cloud? search parallel_state / ep group construction ===\"\ngrep -rn \"def get_ep_group\\|create_expert_parallel_group\\|expert_parallel_group\\|ep_group.*edge\\|edge.*ep_group\\|EP group\\|ep_world_size\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/\" 2>/dev/null | grep -v \"\\.pyc\" | head -25",
  "description": "Find EP group construction for edge-cloud"
}
```

</details>


---

## User <sup>2026/8/10 20:47:39</sup>

<details>
<summary>Tool Result</summary>

```
=== how is EP group built for edge-cloud? search parallel_state / ep group construction ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py:574:        # upstream _EP: all edge workers form one EP group and all cloud
```

</details>


---

## Assistant <sup>2026/8/10 20:47:44</sup>


---

## Assistant <sup>2026/8/10 20:47:44</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\distributed\\parallel_state.py",
  "limit": 90,
  "offset": 540
}
```

</details>


---

## User <sup>2026/8/10 20:47:44</sup>

<details>
<summary>Tool Result</summary>

```
540	
541	    In edge-cloud mode vLLM overrides ``get_pp_group().is_first_rank`` to
542	    return ``is_edge_device()`` for the PP group, so we use the explicit
543	    role helpers instead of raw PP rank.  Edge sends e2c; cloud sends c2e.
544	    """
545	    return get_edge_cloud_tensor_meta(
546	        "e2c" if is_edge_device() else "c2e"
547	    )
548	
549	
550	def _select_edge_cloud_meta_for_recv() -> EdgeCloudTensorMeta:
551	    """Pick the recv-direction meta based on this rank's edge/cloud role.
552	
553	    In edge-cloud mode vLLM overrides ``get_pp_group().is_last_rank`` to
554	    return ``is_edge_device()`` for the PP group, so using it would swap
555	    the receive direction and allocate buffers for the wrong tensor key set
556	    (e.g. expecting a residual in embedding_only mode).  Edge receives c2e;
557	    cloud receives e2c.
558	    """
559	    return get_edge_cloud_tensor_meta(
560	        "e2c" if is_cloud_device() else "c2e"
561	    )
562	
563	
564	def init_ascend_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 20:48:42</sup>


---

## Assistant <sup>2026/8/10 20:48:45</sup>

**这是决定性的发现。** [parallel_state.py:591-605](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L591-L605) — 在 edge-cloud 模式下，cloud EP (MC2) group 是通过遍历 `data_parallel_size` 构建的，因此 `ep_cloud_ranks` 包含了**所有 DP 实例中的所有 cloud worker**。Cloud EP group **跨越了 DP** (cloud dp0 + cloud dp1 处于同一个 EP group 中)。

这意味着 MoE collective (A2 ALLGATHER) 是 dummy (dp0, 1 token) 和 real (dp1, 1024 tokens) 之间的**跨 DP 操作**。让我确认一下 dummy 的 forward `num_tokens` 是否被填充到了 DP 的最大值——这是导致不匹配的关键。


---

## Assistant <sup>2026/8/10 20:48:45</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== _determine_batch_execution_and_padding: how it calls _sync_metadata_across_dp (allow_dp_padding?) ===\"\nsed -n '7925,7945p' \"$CUR\"\necho \"\"\necho \"=== _dummy_run: the call to _determine_batch_execution_and_padding (allow_dp_padding?) ===\"\nsed -n '8420,8430p' \"$CUR\"",
  "description": "Check allow_dp_padding in dummy path"
}
```

</details>


---

## User <sup>2026/8/10 20:48:47</sup>

<details>
<summary>Tool Result</summary>

```
=== _determine_batch_execution_and_padding: how it calls _sync_metadata_across_dp (allow_dp_padding?) ===
        num_tokens_padded = batch_descriptor.num_tokens
        if enable_sp(self.vllm_config):
            assert batch_descriptor.num_tokens % self.vllm_config.parallel_config.tensor_parallel_size == 0, (
                "Sequence parallelism requires num_tokens to be a multiple of tensor parallel size"
            )
        # Extra coordination when running data-parallel since we need to coordinate
        # across ranks
        should_ubatch, num_tokens_across_dp = False, None
        if self.vllm_config.parallel_config.data_parallel_size > 1:
            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(
                num_tokens=num_tokens_padded,
                cudagraph_mode=cudagraph_mode,
                allow_dp_padding=((cudagraph_mode != CUDAGraphMode.NONE)
                                  or enable_sp(self.vllm_config)
                 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 20:49:04</sup>


---

## Assistant <sup>2026/8/10 20:49:05</sup>

我来查看一下在 `sync_metadata` 之后 `num_tokens_padded` 是否被更新为 DP 的最大值（即 “Extract DP padding” 部分）——这将决定 dummy 是否被填充以匹配 real。


---

## Assistant <sup>2026/8/10 20:49:05</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 40,
  "offset": 7938
}
```

</details>


---

## User <sup>2026/8/10 20:49:06</sup>

<details>
<summary>Tool Result</summary>

```
7938	                                  or enable_sp(self.vllm_config)
7939	                                  or oproj_tp_enable()
7940	                                  or embedding_tp_enable()),
7941	            )
7942	
7943	            # Extract DP padding if there is any
7944	            if num_tokens_across_dp is not None:
7945	                dp_rank = self.parallel_config.data_parallel_rank
7946	                num_tokens_padded = int(num_tokens_across_dp[dp_rank].item())
7947	                # Re-dispatch with DP padding
7948	                cudagraph_mode, batch_descriptor = dispatch_cudagraph(
7949	                    num_tokens_padded,
7950	                    valid_modes={synced_cudagraph_mode},
7951	                )
7952	                # Assert to make sure the agreed upon token count is correct otherwise
7953	                # num_tokens_across_dp will no-longer be valid
7954	                assert batch_descriptor.num_tokens == num_tokens_padded
7955	        cudagraph_s
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 20:49:51</sup>


---

## Assistant <sup>2026/8/10 20:50:05</sup>

现在我已经了解全貌了。第 7946 行：`num_tokens_padded = int(num_tokens_across_dp[dp_rank].item())` — dummy 仅在 `allow_dp_padding=True` 时才会被填充到 DP 的最大值。

## Root cause(结构上已确认)

**云侧 EP(MC2)group 跨 DP,但 dummy 在 `allow_dp_padding=False` 时没有 pad 到 DP 全局 max,导致跨 DP 的 MoE ALLGATHER 形状 1 vs 1024 失配 -> 死锁。**

因果链:

1. **云 EP group 跨 DP** - [parallel_state.py:595-601](vllm-ascend/vllm_ascend/distributed/parallel_state.py#L595-L601):`for dp_idx in range(data_parallel_size)` 把所有 DP 的云 worker 塞进同一个 `ep_cloud_ranks`。所以云 dp0(dummy)和 dp1(real)在**同一个 EP group**,MoE ALLGATHER 是**跨 DP 集合通信**。

2. **dummy 与 real 的 num_tokens 必须一致才能配对** - [model_runner_v1.py:7946](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7946):`num_tokens_padded = num_tokens_across_dp[dp_rank]`。
   - `allow_dp_padding=True` 时,`num_tokens_across_dp=[1024,1024]`,dummy 也 pad 到 1024 -> 与 real 一致 -> 配对成功。
   - `allow_dp_padding=False` 时,`num_tokens_across_dp=[1,1024]`(本地值),dummy 停在 1 -> 与 real 的 1024 **形状失配** -> 跨 DP ALLGATHER 死锁。

3. **`allow_dp_padding` 的门控** - [model_runner_v1.py:7935-7940](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7935-L7940):
   ```python
   allow_dp_padding=((cudagraph_mode != CUDAGraphMode.NONE)
                     or enable_sp(...) or oproj_tp_enable() or embedding_tp_enable())
   ```
   dummy 走 eager(`cudagraph_mode=NONE`)且 SP/oproj_tp/embedding_tp 都关时 -> `allow_dp_padding=False` -> dummy 不 pad -> 死锁。

4. **"real 完成"是假象**:PP isend 是非阻塞的,real 的 Python 路径没有 `.item()` 同步,所以它继续往下走到 isend + done,但它的 NPU stream 其实也卡在同一个失配的 ALLGATHER 上。dummy 的 `.item()`([PD-DIAG] 诊断同步)才把这个卡住的 stream 暴露出来。所以**两边 stream 都死了,只是 dummy 先在 Python 层阻塞**。

### 为何 theroadtofree 不卡

`allow_dp_padding` 逻辑两边一样。theroadtofree 不卡,大概率是它那次跑的配置让 `allow_dp_padding=True`(用了 cudagraph,或开了 SP/oproj_tp/embedding_tp),dummy 被 pad 到 1024,与 real 一致。本工程这次跑的是 eager + 这些开关都关 -> `allow_dp_padding=False` -> dummy 停在 1。**差异在配置/运行模式,不在 EP 逻辑本身。**

## 先确认(加一行打印)

在 [model_runner_v1.py:7946](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7946) 后加:

```python
num_tokens_padded = int(num_tokens_across_dp[dp_rank].item())
logger.info("[PAD-DIAG] dp_rank=%s allow_dp_padding=%s local=%s padded=%s across_dp=%s",
            dp_rank, allow_dp_padding, num_tokens, num_tokens_padded,
            num_tokens_across_dp.tolist() if num_tokens_across_dp is not None else None)
```

预期:dummy(DP0)`padded=1`(没 pad),real(DP1)`padded=1024`。若如此,根因确认。

## Fix

dummy 参与跨 DP EP 集合通信,其 `num_tokens_padded` 必须等于 DP 全局 max,与 eager/cudagraph 无关。最直接的修法是在边云跨 DP EP 场景下强制 `allow_dp_padding=True`:

[model_runner_v1.py:7935](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7935) 改为:

```python
allow_dp_padding = (
    (cudagraph_mode != CUDAGraphMode.NONE)
    or enable_sp(self.vllm_config)
    or oproj_tp_enable()
    or embedding_tp_enable()
)
# Edge-cloud: 云 EP group 跨 DP,dummy/real 必须都 pad 到 DP max,
# 否则跨 DP MoE 集合通信形状失配(如 dummy=1 vs real=1024)会死锁。
if (self._edge_cloud_enabled
        and self.vllm_config.parallel_config.data_parallel_size > 1
        and not is_edge_device()):
    allow_dp_padding = True
```

这样 dummy 会被 pad 到 `num_tokens_across_dp.max()`(1024),与 real 一致,跨 DP ALLGATHER 形状匹配,死锁解除。

要我直接改这行吗?或者你先跑一下 `[PAD-DIAG]` 确认 dummy padded=1 / real padded=1024 再改。


---

## User <sup>2026/8/10 20:59:55</sup>

先跑一下 [PAD-DIAG] 确认 dummy padded=1 / real padded=1024 再改


---

## Assistant <sup>2026/8/10 21:00:20</sup>


---

## Assistant <sup>2026/8/10 21:00:21</sup>

我会在 [model_runner_v1.py:7946](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7946) 处添加 `[PAD-DIAG]` 打印信息。首先，让我读取一下具体的代码，以便进行精确修改（`allow_dp_padding` 目前是一个内联表达式，所以我将其捕获到一个变量中，以便记录日志）。


---

## Assistant <sup>2026/8/10 21:00:22</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 25,
  "offset": 7930
}
```

</details>


---

## User <sup>2026/8/10 21:00:22</sup>

<details>
<summary>Tool Result</summary>

```
7930	        # Extra coordination when running data-parallel since we need to coordinate
7931	        # across ranks
7932	        should_ubatch, num_tokens_across_dp = False, None
7933	        if self.vllm_config.parallel_config.data_parallel_size > 1:
7934	            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(
7935	                num_tokens=num_tokens_padded,
7936	                cudagraph_mode=cudagraph_mode,
7937	                allow_dp_padding=((cudagraph_mode != CUDAGraphMode.NONE)
7938	                                  or enable_sp(self.vllm_config)
7939	                                  or oproj_tp_enable()
7940	                                  or embedding_tp_enable()),
7941	            )
7942	
7943	            # Extract DP padding if there is any
7944	            if num_tokens_across_dp is not None:
7945	                dp_rank = self.parallel_config.data_parallel_rank
7946	                num_tokens_padded = int(num_tokens_across_dp[dp_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/10 21:00:41</sup>


---

## Assistant <sup>2026/8/10 21:00:44</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "old_string": "            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(\n                num_tokens=num_tokens_padded,\n                cudagraph_mode=cudagraph_mode,\n                allow_dp_padding=((cudagraph_mode != CUDAGraphMode.NONE)\n                                  or enable_sp(self.vllm_config)\n                                  or oproj_tp_enable()\n                                  or embedding_tp_enable()),\n            )\n\n            # Extract DP padding if there is any\n            if num_tokens_across_dp is not None:\n                dp_rank = self.parallel_config.data_parallel_rank\n                num_tokens_padded = int(num_tokens_across_dp[dp_rank].item())",
  "new_string": "            allow_dp_padding = ((cudagraph_mode != CUDAGraphMode.NONE)\n                                or enable_sp(self.vllm_config)\n                                or oproj_tp_enable()\n                                or embedding_tp_enable())\n            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(\n                num_tokens=num_tokens_padded,\n                cudagraph_mode=cudagraph_mode,\n                allow_dp_padding=allow_dp_padding,\n            )\n\n            # Extract DP padding if there is any\n            if num_tokens_across_dp is not None:\n                dp_rank = self.parallel_config.data_parallel_rank\n                num_tokens_padded = int(num_tokens_across_dp[dp_rank].item())\n                logger.info(\n                    \"[PAD-DIAG] dp_rank=%s allow_dp_padding=%s local_num_tokens=%s \"\n                    \"padded=%s across_dp=%s\",\n                    dp_rank, allow_dp_padding, num_tokens, num_tokens_padded,\n                    num_tokens_across_dp.tolist(),\n                )"
}
```

</details>


---

## User <sup>2026/8/10 21:00:45</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/10 21:00:48</sup>


---

## Assistant <sup>2026/8/10 21:00:49</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/worker/model_runner_v1.py', encoding='utf-8').read()); print('model_runner_v1.py: syntax OK')\" 2>&1\necho \"=== confirm PAD-DIAG line ===\"\ngrep -n \"PAD-DIAG\" vllm_ascend/worker/model_runner_v1.py",
  "description": "Syntax check and confirm PAD-DIAG added"
}
```

</details>


---

## User <sup>2026/8/11 14:16:24</sup>

<details>
<summary>Tool Result</summary>

```
model_runner_v1.py: syntax OK
=== confirm PAD-DIAG line ===
7949:                    "[PAD-DIAG] dp_rank=%s allow_dp_padding=%s local_num_tokens=%s "
```

</details>


---

## Assistant <sup>2026/8/11 14:16:47</sup>


---

## Assistant <sup>2026/8/11 14:16:53</sup>

已加好 `[PAD-DIAG]` 打印([model_runner_v1.py:7949](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7949)),语法检查通过。这个打印在 `_determine_batch_execution_and_padding` 里,dummy(经 `_dummy_run`)和 real(经 `execute_model`/`cloud_prepare_early`)都会打。

跑一次,然后在云两 DP 日志里 grep:

```bash
grep "PAD-DIAG" <云日志>
```

## 怎么判读

**若确认根因(预期):**
```
[PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=1   padded=1   across_dp=[1, 1024]   # dummy
[PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1024 padded=1024 across_dp=[1, 1024]   # real
```
- `allow_dp_padding=False`(eager + SP/oproj_tp/embedding_tp 都关)
- dummy `padded=1`(没 pad 到 max),real `padded=1024`
- `across_dp=[1,1024]`(本地值,没统一)

→ 根因坐实:dummy 停在 1,real 1024,跨 DP EP ALLGATHER 形状失配死锁。然后我改 [model_runner_v1.py:7935](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7935) 强制边云云侧 `allow_dp_padding=True`。

**若不是这个(假设又错):**
```
[PAD-DIAG] dp_rank=0 ... padded=1024 across_dp=[1024, 1024]   # dummy 也 pad 到 1024
[PAD-DIAG] dp_rank=1 ... padded=1024 across_dp=[1024, 1024]
```
- dummy 已经 pad 到 1024,与 real 一致 -> 形状失配假设不成立 -> 得换方向(可能要看 MoE all-gather 的实际数据量是否用了 local num_tokens,或别的集合通信)。

把两行 `[PAD-DIAG]`(dp_rank=0 和 dp_rank=1 各一,或多个 TP rank 的)贴出来即可。


---

## User <sup>2026/8/11 14:35:00</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\patch\platform\patch_engine_core.py in the IDE. This may or may not be related to the current task.</ide_opened_file>

(Worker_DP1_TP1_EP5 pid=123274) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_TP3_EP7 pid=123276) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_PP1_TP0_EP4 pid=123273) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_TP2_EP6 pid=123275) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP0_TP1_EP1 pid=123203) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_TP3_EP3 pid=123205) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_PP1_TP0_EP0 pid=123202) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_TP2_EP2 pid=123204) INFO 08-11 06:25:57 [model_runner_v1.py:7948] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]


---

## Assistant <sup>2026/8/11 14:36:05</sup>


---

## Assistant <sup>2026/8/11 14:36:08</sup>

日志**确认了根因**。关键两行:

```
dp_rank=1 allow_dp_padding=False local_num_tokens=1  padded=1  across_dp=[15, 1]   # dummy(DP1)
dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]   # real(DP0)
```

- `allow_dp_padding=False`(两边都是)
- dummy(DP1)`padded=1`,real(DP0)`padded=15`,**没 pad 到统一 max(15)**
- `across_dp=[15, 1]`(本地值,没统一)

dummy 停在 1、real 是 15,跨 DP EP ALLGATHER 形状 1 vs 15 失配 -> 死锁。和之前推断完全一致(只是这次 real 是 15 而非 1024,机制一样)。

现在应用修复:边云 + DP>1 时强制 `allow_dp_padding=True`,让 dummy pad 到 DP max,与 real 一致。对 real 侧(local 已是 max)是 no-op,只把 dummy pad 上去。


---

## Assistant <sup>2026/8/11 14:36:12</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "old_string": "            allow_dp_padding = ((cudagraph_mode != CUDAGraphMode.NONE)\n                                or enable_sp(self.vllm_config)\n                                or oproj_tp_enable()\n                                or embedding_tp_enable())\n            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(\n                num_tokens=num_tokens_padded,\n                cudagraph_mode=cudagraph_mode,\n                allow_dp_padding=allow_dp_padding,\n            )",
  "new_string": "            allow_dp_padding = ((cudagraph_mode != CUDAGraphMode.NONE)\n                                or enable_sp(self.vllm_config)\n                                or oproj_tp_enable()\n                                or embedding_tp_enable())\n            # Edge-cloud: the EP (MC2) group spans all DP instances\n            # (parallel_state.init_ascend_model_parallel builds ep_cloud_ranks /\n            # ep_edge_ranks by looping over data_parallel_size), so the MoE\n            # collective (e.g. A2 ALLGATHER) is cross-DP. The idle DP's dummy\n            # (num_tokens = decode_token_per_req) and the busy DP's real forward\n            # carry different token counts; without DP padding the dummy stays\n            # at its small local count while the real is larger, and the\n            # cross-DP collective shape mismatches -> deadlock (dummy hangs in\n            # _model_forward; the real's PP isend is non-blocking so it only\n            # looks like it completes). Force-padding to the DP max makes both\n            # sides use the same token count for the collective. For the real\n            # side (which already carries the max) this is a no-op.\n            if (self._edge_cloud_enabled\n                    and self.vllm_config.parallel_config.data_parallel_size > 1):\n                allow_dp_padding
...(truncated)
```

</details>


---

## User <sup>2026/8/11 14:36:13</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 14:36:17</sup>


---

## Assistant <sup>2026/8/11 14:36:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/worker/model_runner_v1.py', encoding='utf-8').read()); print('model_runner_v1.py: syntax OK')\" 2>&1\necho \"=== confirm fix + PAD-DIAG ===\"\ngrep -n \"Edge-cloud: the EP (MC2) group spans\\|allow_dp_padding = True\\|PAD-DIAG\" vllm_ascend/worker/model_runner_v1.py",
  "description": "Syntax check and confirm fix in place"
}
```

</details>


---

## User <sup>2026/8/11 14:36:19</sup>

<details>
<summary>Tool Result</summary>

```
model_runner_v1.py: syntax OK
=== confirm fix + PAD-DIAG ===
7938:            # Edge-cloud: the EP (MC2) group spans all DP instances
7952:                allow_dp_padding = True
7964:                    "[PAD-DIAG] dp_rank=%s allow_dp_padding=%s local_num_tokens=%s "
```

</details>


---

## Assistant <sup>2026/8/11 14:36:35</sup>


---

## Assistant <sup>2026/8/11 14:36:40</sup>

修复已应用,语法检查通过。

## 改动总结

[model_runner_v1.py:7938-7953](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7938-L7953):边云 + DP>1 时强制 `allow_dp_padding=True`。

```python
if (self._edge_cloud_enabled
        and self.vllm_config.parallel_config.data_parallel_size > 1):
    allow_dp_padding = True
```

效果:dummy 和 real 都 pad 到 `num_tokens_across_dp.max()`,跨 DP EP ALLGATHER 形状一致 -> 不再死锁。对 real 侧(local 已是 max)是 no-op,只把 dummy 从 1 pad 到 15。

## 跑一次验证

`[PAD-DIAG]` 打印还留着,跑一次看两 DP 的值。**修复生效的预期**:

```
dp_rank=1 allow_dp_padding=True local_num_tokens=1  padded=15 across_dp=[15, 15]   # dummy 现 pad 到 15
dp_rank=0 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]   # real 不变
```

两边 `padded=15`、`across_dp=[15,15]` -> 形状匹配 -> dummy 前向能跑完(出现 `[PD-DIAG] E. _dummy_run segment_a OUTPUT` 行)-> 不再卡死。

## 说明

- 修复对边和云都生效(两个 EP group 都跨 DP,机制一样;你这边复现的是云侧,但边侧同样有该风险)。
- `[PAD-DIAG]` 是诊断打印,确认修复稳定后可删掉。要我现在删,还是先留着观察?
- 如果跑完 dummy 仍卡(或 `[PAD-DIAG]` 显示已 pad 到 15 但仍死锁),说明跨 DP 集合通信的数据量还用了别的量(不是 `num_tokens_padded`),那再查 MoE all-gather 的实际通信 shape。但按当前日志,这个修复应当直接对症。

把修复后的 `[PAD-DIAG]` 两行 + 是否还卡的情况贴出来即可。


---

## User <sup>2026/8/11 14:56:48</sup>

<ide_selection>The user selected the lines 8836 to 8836 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py:
                    

This may or may not be related to the current task.</ide_selection>

日志如下，还是卡死；云侧卡死位置依然是C:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py的8836行；(Worker_DP1_TP2_EP6 pid=128657) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP1_TP1_EP5 pid=128656) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP1_PP1_TP0_EP4 pid=128655) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP1_TP3_EP7 pid=128658) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP0_TP2_EP2 pid=128588) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP0_TP1_EP1 pid=128587) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP0_PP1_TP0_EP0 pid=128586) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP0_TP3_EP3 pid=128589) INFO 08-11 06:45:35 [model_runner_v1.py:7963] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]


---

## Assistant <sup>2026/8/11 14:59:40</sup>


---

## Assistant <sup>2026/8/11 14:59:44</sup>

`[PAD-DIAG]` 显示修复让两边都 pad 到 15 了(`padded=15 across_dp=[15,15]`),num_tokens 形状已一致。**但仍然卡死**,说明 num_tokens 形状失配不是(唯一)根因。我之前的假设又不够。

关键新信息:real 是 15 token(不是 1024),`15 ≤ 64(capacity)` -> 通信类型其实是 **MC2**(不是 ALLGATHER),`should_skip=False`(global_bs=0,MC2 期望均匀)。现在 num_tokens 均匀(15=15),MC2 理论上该配对,但仍卡在 segment_a 的 `_model_forward` 里。

所以问题在别处:很可能 **dummy 和 real 没在同一时刻到达同一个 MC2 all-toall**(real 卡在 `_model_forward` 之前的某处,如 PP recv / cloud_prepare_early),或 **MC2 用的不是 num_tokens_padded 而是别的量**。

我需要精确定位卡在哪个集合通信。先看 `_model_forward` 入口,加一个打印确认 real 是否真的进入了 forward。


---

## Assistant <sup>2026/8/11 14:59:44</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 30,
  "offset": 6485
}
```

</details>


---

## User <sup>2026/8/11 14:59:44</sup>

<details>
<summary>Tool Result</summary>

```
6485	    def _model_forward(
6486	        self,
6487	        num_tokens_padded: int,
6488	        input_ids: torch.Tensor | None = None,
6489	        positions: torch.Tensor | None = None,
6490	        intermediate_tensors: IntermediateTensors | None = None,
6491	        inputs_embeds: torch.Tensor | None = None,
6492	        **model_kwargs: dict[str, Any],
6493	    ):
6494	        """模型前向入口。标准路径与边云路径完全分离，职责单一。"""
6495	
6496	        if self._edge_cloud_enabled:
6497	            return self._edge_cloud_forward(
6498	                num_tokens_padded, input_ids, positions, intermediate_tensors,
6499	                inputs_embeds, **model_kwargs,
6500	            )
6501	
6502	        # ==================== 标准非边云路径（原逻辑完全保留，不做任何修改） ====================
6503	        assert self.model is not None
6504	        hidden_states = self.model(
6505	            input_ids=input_ids,
6506	            positions=positions,
6507	            intermediate_tensors=intermediate_tensors,
6508	            input
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:00:28</sup>


---

## Assistant <sup>2026/8/11 15:00:29</sup>

num_tokens 现在一致(15=15)但仍卡死,且 `15 ≤ 64` -> 通信类型是 **MC2**(不是 ALLGATHER)。我需要确认 real 是否真的进入了 `_model_forward`(可能 real 卡在 PP recv / cloud_prepare_early,没到达 MC2,导致 dummy 的 MC2 等不到对端)。

在 `_model_forward` 入口加一个打印,覆盖 dummy 和 real 两条路径:


---

## Assistant <sup>2026/8/11 15:00:31</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "old_string": "        \"\"\"模型前向入口。标准路径与边云路径完全分离，职责单一。\"\"\"\n\n        if self._edge_cloud_enabled:",
  "new_string": "        \"\"\"模型前向入口。标准路径与边云路径完全分离，职责单一。\"\"\"\n        logger.info(\n            \"[FWD-ENTRY] dp_rank=%s num_tokens_padded=%s bt=%s(is_dummy=%s)\",\n            self.dp_rank, num_tokens_padded, self._dp_batch_type_id,\n            self._dp_batch_type_id == 0,\n        )\n\n        if self._edge_cloud_enabled:"
}
```

</details>


---

## User <sup>2026/8/11 15:00:32</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 15:00:40</sup>


---

## Assistant <sup>2026/8/11 15:00:41</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/worker/model_runner_v1.py', encoding='utf-8').read()); print('syntax OK')\" 2>&1\ngrep -n \"FWD-ENTRY\" vllm_ascend/worker/model_runner_v1.py",
  "description": "Syntax check and confirm FWD-ENTRY print"
}
```

</details>


---

## User <sup>2026/8/11 15:00:44</sup>

<details>
<summary>Tool Result</summary>

```
syntax OK
6496:            "[FWD-ENTRY] dp_rank=%s num_tokens_padded=%s bt=%s(is_dummy=%s)",
```

</details>


---

## Assistant <sup>2026/8/11 15:00:51</sup>


---

## Assistant <sup>2026/8/11 15:00:57</sup>

`[FWD-ENTRY]` 打印已加在 `_model_forward` 入口([model_runner_v1.py:6495](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L6495)),dummy 和 real 都会打(`bt=0` 是 dummy,`bt=1/2/3/4` 是 real)。

跑一次,然后:

```bash
grep -E "FWD-ENTRY|PAD-DIAG" <云两DP日志>
```

## 判读(关键看 real 是否进入 forward)

**情况 A:两边都有 `[FWD-ENTRY]`(dp_rank=0 bt=1 real,dp_rank=1 bt=0 dummy)**
-> real 也进了 `_model_forward`,hang 在里面的 MC2 all-toall。那说明 num_tokens=15 虽然一致,但 MC2 all-toall 还用了别的量(很可能是 **routing 派发量**:dummy 是 1 真+14 pad,real 是 15 真,token 路由到各 expert 的分布不同 -> all-toall 各路 size 不一致 -> 死锁)。下一步要么让 dummy 不走 MC2(跳过 MoE / 强制 ALLGATHER),要么 pad 路由。

**情况 B:只有 dp_rank=1(dummy)有 `[FWD-ENTRY]`,dp_rank=0(real)没有**
-> real 卡在 `_model_forward` 之前(PP recv 等边侧数据没来,或 cloud_prepare_early)。dummy 已经进 MC2,real 还没到 -> dummy 的 MC2 等不到对端 -> 死锁。下一步查 real 的 PP recv / cloud_prepare_early 卡在哪。

把 `[FWD-ENTRY]`(和 `[PAD-DIAG]`)两 DP 的行贴出来,我据此确定是 A 还是 B。


---

## User <sup>2026/8/11 15:15:04</sup>

(Worker_DP0_TP2_EP2 pid=134005) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP0_TP2_EP2 pid=134005) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=0(is_dummy=True)
(Worker_DP0_TP1_EP1 pid=134004) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP0_TP1_EP1 pid=134004) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=0(is_dummy=True)
(Worker_DP0_TP3_EP3 pid=134006) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP0_TP3_EP3 pid=134006) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=0(is_dummy=True)
(Worker_DP0_PP1_TP0_EP0 pid=134003) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=0 allow_dp_padding=True local_num_tokens=1 padded=15 across_dp=[15, 15]
(Worker_DP0_PP1_TP0_EP0 pid=134003) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=0(is_dummy=True)

(Worker_DP1_TP2_EP6 pid=134073) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP1_TP1_EP5 pid=134072) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP1_TP3_EP7 pid=134074) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP1_PP1_TP0_EP4 pid=134071) INFO 08-11 07:07:21 [model_runner_v1.py:7968] [PAD-DIAG] dp_rank=1 allow_dp_padding=True local_num_tokens=15 padded=15 across_dp=[15, 15]
(Worker_DP1_TP2_EP6 pid=134073) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=15 bt=1(is_dummy=False)
(Worker_DP1_TP1_EP5 pid=134072) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=15 bt=1(is_dummy=False)
(Worker_DP1_TP3_EP7 pid=134074) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=15 bt=1(is_dummy=False)
(Worker_DP1_PP1_TP0_EP4 pid=134071) INFO 08-11 07:07:21 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=15 bt=1(is_dummy=False)


---

## Assistant <sup>2026/8/11 15:15:48</sup>


---

## Assistant <sup>2026/8/11 15:15:50</sup>

**情况 A 确认**:两边都进了 `_model_forward`:
- DP0: `bt=0 (is_dummy=True)`,padded=15(dummy,local 1)
- DP1: `bt=1 (is_dummy=False)`,padded=15(real,local 15)

num_tokens 已一致(15=15),但 real 也进了 forward 却仍卡死。所以 hang 在 `_model_forward` 内部的 MC2 all-toall,且不是 num_tokens 形状问题。`15 ≤ 64` -> MC2,`should_skip=False`。

我需要看 cloud forward 的段结构(segment_a/segment_e)和 MC2 all-toall 到底用什么 shape。让我读 `_edge_cloud_forward`。


---

## Assistant <sup>2026/8/11 15:15:52</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== _edge_cloud_forward / _edge_cloud_forward_cloud / segment_a / segment_e locations ===\"\ngrep -n \"def _edge_cloud_forward\\|def _edge_cloud_forward_cloud\\|segment_a\\|segment_e\\|_skip_head\\|_skip_tail\\|EdgeCloudSegment\\|is_edge_cloud_pp_mode\" \"$CUR\" | awk -F: '$1>=6400 && $1<=7400' | head -40",
  "description": "Find edge cloud forward and segment structure"
}
```

</details>


---

## User <sup>2026/8/11 15:16:22</sup>

<details>
<summary>Tool Result</summary>

```
=== _edge_cloud_forward / _edge_cloud_forward_cloud / segment_a / segment_e locations ===
6781:        """Pre-compute input preparation on cloud while edge runs segment_a.
6995:    def _edge_cloud_forward(
7009:        EdgeCloudSegment（局部层范围）。
7013:              • intermediate_tensors is None  → 执行 segment_a（首段，输出 IntermediateTensors）
7014:              • intermediate_tensors is not None → 执行 segment_e（尾段，输出 hidden_states）
7063:                    self.segment_a_wrapper
7065:                    else self.segment_e_wrapper
7085:    def _edge_cloud_forward_edge(
7096:        """Edge 侧分段执行：segment_a（首段）或 segment_e（尾段）。"""
7097:        seg_a = self.segment_a_wrapper if use_graph else self.segment_a
7098:        seg_e = self.segment_e_wrapper if use_graph else self.segment_e
7132:        # 注意：segment_e 与 segment_a 共用同一个 scheduler_output，num_tokens
7159:            # segment_e 执行完毕后恢复原始 layer_idx
7163:    def _edge_cloud_forward_edge(
7174:        """Edge 侧分段执行：segment_a（首段）或 segment_e（尾段）。"
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:16:41</sup>


---

## Assistant <sup>2026/8/11 15:16:41</sup>

我来查看一下 `_edge_cloud_forward`，以了解 segment_a 与 segment_e 是如何选择的，以及每个部分执行了哪些集合通信。


---

## Assistant <sup>2026/8/11 15:16:42</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 90,
  "offset": 6995
}
```

</details>


---

## User <sup>2026/8/11 15:16:42</sup>

<details>
<summary>Tool Result</summary>

```
6995	    def _edge_cloud_forward(
6996	        self,
6997	        num_tokens_padded: int,
6998	        input_ids: torch.Tensor | None = None,
6999	        positions: torch.Tensor | None = None,
7000	        intermediate_tensors: IntermediateTensors | None = None,
7001	        inputs_embeds: torch.Tensor | None = None,
7002	        layer_slice_info: Any = None,
7003	        **model_kwargs: dict[str, Any],
7004	    ):
7005	        """边云场景的分段前向执行。
7006	
7007	        核心设计：每个 segment 由标准 ACLGraphWrapper 包裹（runtime_mode=FULL），
7008	        capture/replay 机制与标准流程完全一致，仅被包裹对象从完整 model 变为
7009	        EdgeCloudSegment（局部层范围）。
7010	
7011	        分段路由逻辑：
7012	          - Edge 角色：
7013	              • intermediate_tensors is None  → 执行 segment_a（首段，输出 IntermediateTensors）
7014	              • intermediate_tensors is not None → 执行 segment_e（尾段，输出 hidden_states）
7015	          - Cloud 角色：始终执行 segment_c（中段，输出 IntermediateTensors）
7016	        """
7017	        assert self.model is not None
7018	       
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:17:30</sup>


---

## Assistant <sup>2026/8/11 15:17:31</sup>

对于云侧，两个检出版本均始终运行 `segment_c` ([model_runner_v1.py:7068](vllm-ascend/vllm_ascend/worker/model_runner_v1.py#L7068))。但 dummy 的 `_dummy_run` 调用了两次 `_model_forward` (segment_a + segment_e，因为 `skip_head=False skip_tail=False`) —— 对于云侧，这两次调用都会映射到 `segment_c`。这可能会导致 collective count 不匹配。我来核实一下 8836 行的具体内容，并重新检查 dummy 的 segment 调用。


---

## Assistant <sup>2026/8/11 15:17:32</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 60,
  "offset": 8815
}
```

</details>


---

## User <sup>2026/8/11 15:17:32</sup>

<details>
<summary>Tool Result</summary>

```
8815	                    if isinstance(outputs, IntermediateTensors):
8816	                        hidden_states = outputs["hidden_states"]
8817	                    else:
8818	                        hidden_states, _ = outputs
8819	                elif isinstance(outputs, IntermediateTensors):
8820	                    hidden_states = outputs["hidden_states"]
8821	                else:
8822	                    hidden_states = outputs
8823	
8824	                # Layer-sliced dummy: save intermediate state for the
8825	                # next slice (mirrors execute_model's layerwise state
8826	                # saving for real prefill).
8827	                if (
8828	                    layer_slice_info is not None
8829	                    and not layer_slice_info.is_last_slice
8830	                    and isinstance(outputs, IntermediateTensors)
8831	                ):
8832	                    self._layerwise_intermediate = outputs
8833	                    # Also save positions / attn_me
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:17:53</sup>


---

## Assistant <sup>2026/8/11 15:17:55</sup>

第 8841 行是 segment_a OUTPUT `.item()`（挂起同步点）。dummy 的第一个 segment (segment_a -> cloud 的 segment_c) 完成了，但其 MC2 在 stream 上卡住了。我来检查一下 `_edge_cloud_forward_cloud`，看看 real cloud 运行 segment_c 是一次还是两次，以及与 dummy 的两次调用（segment_a + segment_e）相比如何。


---

## Assistant <sup>2026/8/11 15:17:56</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== _edge_cloud_forward_cloud def ===\"\ngrep -n \"def _edge_cloud_forward_cloud\" \"$CUR\"",
  "description": "Find _edge_cloud_forward_cloud"
}
```

</details>


---

## User <sup>2026/8/11 15:17:57</sup>

<details>
<summary>Tool Result</summary>

```
=== _edge_cloud_forward_cloud def ===
7616:    def _edge_cloud_forward_cloud(
```

</details>


---

## Assistant <sup>2026/8/11 15:18:01</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 70,
  "offset": 7616
}
```

</details>


---

## User <sup>2026/8/11 15:18:01</sup>

<details>
<summary>Tool Result</summary>

```
7616	    def _edge_cloud_forward_cloud(
7617	        self,
7618	        num_tokens_padded: int,
7619	        positions: torch.Tensor | None,
7620	        intermediate_tensors: IntermediateTensors | None,
7621	        use_graph: bool,
7622	        forward_context,
7623	        layer_slice_info: Any = None,
7624	        **model_kwargs: dict[str, Any],
7625	    ):
7626	        """Cloud 侧分段执行：segment_c（中段）。"""
7627	        assert self.edge_cloud_cfg.role == "cloud", (
7628	            "Cloud segment_c should only be executed when role == 'cloud'"
7629	        )
7630	        # Warmup（profile_run）期间，Cloud 通过 PP non-first rank 路径自行构造
7631	        # minimal intermediate_tensors（仅含 shape 信息）用于图捕获，此时 intermediate_tensors
7632	        # 不为 None 但也是 dummy。运行时 real inference 时，intermediate_tensors 由
7633	        # Worker 层从 Edge 侧接收，为真实的 HiddenStates。区分方式：检查 in_profile_run。
7634	        in_warmup = getattr(forward_context, "in_profile_run", False)
7635	        assert intermediate_tensors is not Non
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:18:44</sup>


---

## Assistant <sup>2026/8/11 15:18:44</sup>

让我检查一下 dummy 的 segment_e 调用（看看 cloud dummy 是否运行了两次 segment_c），并找到 MC2 all-toall 的实现以检查其 shape。让我阅读一下 dummy 的 segment_e 部分并找到 MC2 comm。


---

## Assistant <sup>2026/8/11 15:18:45</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 60,
  "offset": 8874
}
```

</details>


---

## User <sup>2026/8/11 15:18:45</sup>

<details>
<summary>Tool Result</summary>

```
8874	            # ========== Edge 设备特殊处理：Edge 首阶段需要执行最后一层 ==========
8875	            if is_edge_device() and not _skip_tail:
8876	                if outputs is not None:
8877	                    assert isinstance(outputs, IntermediateTensors)
8878	
8879	                # 重新准备 intermediate_tensors（与上文逻辑相同）
8880	                intermediate_tokens = num_tokens_padded
8881	                if enable_sp():
8882	                    tp_size = get_tensor_model_parallel_world_size()
8883	                    intermediate_tokens = (num_tokens_padded + tp_size - 1) // tp_size
8884	                if self.intermediate_tensors is None:  # 增加deepseek-v4判断
8885	                    max_actual_tokens = self.max_num_tokens
8886	                    if enable_sp():
8887	                        max_actual_tokens = (self.max_num_tokens + tp_size - 1) // tp_size
8888	                        # 调用模型方法创建空的中间张量
8889	                    self.intermediate_tensors = self.model.make_empty_intermediate_tensors(
8890
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:19:31</sup>


---

## Assistant <sup>2026/8/11 15:19:33</sup>

第 8875 行：`if is_edge_device() and not _skip_tail:` ——因此 **cloud dummy 不会运行 segment_e**（仅限 edge）。Cloud dummy 只运行一次 segment_a (segment_c)。Real cloud 也运行一次 segment_c。所以不存在数量不匹配的问题。两者都运行一次 segment_c，且 `num_tokens=15`，但 segment_a 的 `.item()` 仍然挂起。

因此，这是一个 MC2 all-toall 的 **shape** 问题。我来查找一下 MC2 comm 的实现，看看它究竟使用了什么 shape。


---

## Assistant <sup>2026/8/11 15:19:36</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== MC2 comm method files ===\"\ngrep -rln \"MC2\\|mc2\\|all_to_all\\|alltoall\\|MoECommType.MC2\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/communication/\" 2>/dev/null | grep -v \"\\.pyc\" | head\necho \"\"\necho \"=== where MoECommType.MC2 is dispatched (the actual all-toall) ===\"\ngrep -rn \"MoECommType.MC2\\|== MoECommType.MC2\\|mc2_mask\\|global_bs\\|def.*mc2\\|dispatch.*mc2\\|token_dispatch\\|moe_comm.*forward\\|def forward.*moe_comm\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_comm_method.py\" 2>/dev/null | head -30",
  "description": "Find MC2 comm implementation"
}
```

</details>


---

## User <sup>2026/8/11 15:19:37</sup>

<details>
<summary>Tool Result</summary>

```
=== MC2 comm method files ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/comm_utils.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe_0_23_0.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_comm_method.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_mlp.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_runtime_args.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_stage_contracts.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_stage_params.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py

=== where MoECommType.MC2 is dispatched (the actual all-toall) ===
32:    build_token_dispatch_input,
40:from vllm_ascend.ops.fused_moe.tok
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:20:15</sup>


---

## Assistant <sup>2026/8/11 15:20:16</sup>

MC2 all-toall 使用了 `mc2_mask` 和 `global_bs` ([moe_comm_method.py:323,343](vllm-ascend/vllm_ascend/ops/fused_moe/moe_comm_method.py#L323))。dummy 的 `intermediate_tensors` 输入为 `[1, 2048]` (1 个 token)，而 `num_tokens_padded=15` —— 存在不一致。我来查看一下 MC2 all-toall 的形状是如何计算的 (mask/global_bs/num_tokens)。


---

## Assistant <sup>2026/8/11 15:20:16</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "limit": 75,
  "offset": 285
}
```

</details>


---

## User <sup>2026/8/11 15:20:16</sup>

<details>
<summary>Tool Result</summary>

```
285	
286	    def fused_experts(
287	        self,
288	        fused_experts_input: MoEFusedExpertsInput,
289	    ):
290	        assert not (fused_experts_input.weights.w1_scale is None or fused_experts_input.weights.w2_scale is None), (
291	            "w1_scale and w2_scale cannot be None for FusedMC2CommImpl."
292	        )
293	
294	        assert isinstance(self.token_dispatcher, TokenDispatcherWithMC2), (
295	            "token_dispatcher must be an instance of TokenDispatcherWithMC2."
296	        )
297	
298	        # Apply log2phy if needed
299	        topk_ids = fused_experts_input.topk_ids
300	        if fused_experts_input.routing.log2phy is not None:
301	            topk_ids = fused_experts_input.routing.log2phy[topk_ids]
302	
303	        expert_tokens = None
304	        if get_ascend_config().enable_fused_mc2 == 1:
305	            assert not (
306	                fused_experts_input.weights.w1_scale_bias is None or fused_experts_input.weights.w2_scale_bias is None
307	       
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:21:36</sup>


---

## Assistant <sup>2026/8/11 15:21:37</sup>

MC2 all-toall 使用了 `mc2_mask`（活动 token）和 `global_bs`。dummy 的输入是 `[1, 2048]`（1 个 token），而 `num_tokens_padded=15` —— 所以 dummy 有 **1 个活动 token**，而 real 有 15 个。我来确认一下 `global_bs`/`mc2_mask` 是如何根据 `should_skip` 设置的，因为这决定了是采用 mask 模式（统一，要求计数相同）还是 global_bs 模式（处理不同计数）。


---

## Assistant <sup>2026/8/11 15:21:39</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== global_bs / mc2_mask / should_skip setup in token_dispatcher & prepare_finalize & moe_runtime_args ===\"\ngrep -rn \"global_bs\\|mc2_mask\\|should_skip\\|skip_allreduce\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_runtime_args.py\" 2>/dev/null | grep -v \"\\.pyc\" | head -40",
  "description": "Find global_bs/mc2_mask/should_skip setup"
}
```

</details>


---

## User <sup>2026/8/11 15:21:40</sup>

<details>
<summary>Tool Result</summary>

```
=== global_bs / mc2_mask / should_skip setup in token_dispatcher & prepare_finalize & moe_runtime_args ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py:49:    should_skip_allreduce_across_dp_group,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py:121:        # Here we need to calculate the global_bs = max_bs_per_rank * ep_world_size to execute
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py:127:        _max_global_bs = num_tokens_per_tp_rank * self.ep_world_size
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py:130:        # use global_bs=0 (uniform mode) and pass mc2_mask.
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py:132:        # use the real global_bs and do NOT pass mc2_mask.
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py:133:        self.global_bs = _max_glob
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:23:11</sup>


---

## Assistant <sup>2026/8/11 15:23:14</sup>

**找到了。** [token_dispatcher.py:133](vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py#L133):

```python
self.global_bs = _max_global_bs if should_skip_allreduce_across_dp_group(vllm_config) else 0
```

以及 182-183 / 261 行：当 `global_bs == 0` 时（即 `should_skip=False`，也就是当前情况），MC2 **接收 `mc2_mask`**（即活跃 token 掩码）。当 `global_bs != 0` 时（即 `should_skip=True`），MC2 **不使用掩码**，而是使用固定的 `global_bs`。

因此，在 `should_skip=False`（当前状态）的情况下，MC2 使用 `mc2_mask`。虚拟节点有 **1 个活跃 token**（其 `[1,2048]` 输入），真实节点有 **15 个** -> MC2 all-toall 活跃计数 1 对 15 导致不匹配 -> **死锁**。我来读取一下具体的代码块以进行确认并应用修复。


---

## Assistant <sup>2026/8/11 15:23:15</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "limit": 75,
  "offset": 110
}
```

</details>


---

## User <sup>2026/8/11 15:23:15</sup>

<details>
<summary>Tool Result</summary>

```
110	        self.ep_rank_id = get_mc2_group().rank_in_group
111	        self.ep_world_size = get_mc2_group().world_size
112	        self.enable_dispatch_v2 = hasattr(torch_npu, "npu_moe_distribute_dispatch_v2")
113	        self.need_extra_args = get_ascend_device_type() in [AscendDeviceType.A3, AscendDeviceType.A5]
114	        self.a5_need_extra_args = get_ascend_device_type() == AscendDeviceType.A5
115	        # NOTE: When in A2, setting the environment variables HCCL_INTRA_PCIE_ENABLE=1 and
116	        # HCCL_INTRA_ROCE_ENABLE=0 can reduce cross-machine communication traffic and significantly
117	        # improve communication performance.
118	        # When enable hierarchical communication, param `expert_scales` need to be passed in.
119	        self.need_expert_scale = is_hierarchical_communication_enabled()
120	
121	        # Here we need to calculate the global_bs = max_bs_per_rank * ep_world_size to execute
122	        # dispatch & combine operators with different input num_to
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 15:28:02</sup>


---

## Assistant <sup>2026/8/11 15:28:03</sup>


---

## Assistant <sup>2026/8/11 15:29:01</sup>


---

## Assistant <sup>2026/8/11 15:29:04</sup>

The mechanism is confirmed. With `should_skip=False`, `global_bs=0` and MC2 passes `mc2_mask` (line 182-183). The dummy has 1 active token (its `[1,2048]` input), the real has 15 → MC2 active-count mismatch → deadlock.

The fix: force MC2 into `global_bs` mode (no mask, fixed shape that tolerates different per-rank counts) for the cloud in edge-cloud DP. This is exactly what `should_skip=True` mode does, but I'll keep the all_reduce running (so comm-type selection stays synced) and only flip the MC2 mode. First, let me revert the `allow_dp_padding=True` force (it padded num_tokens but not the dummy's input, creating an input/num_tokens_padded inconsistency) — the global_bs mode handles the count difference without needing padding.


---

## Assistant <sup>2026/8/11 15:29:08</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "old_string": "            allow_dp_padding = ((cudagraph_mode != CUDAGraphMode.NONE)\n                                or enable_sp(self.vllm_config)\n                                or oproj_tp_enable()\n                                or embedding_tp_enable())\n            # Edge-cloud: the EP (MC2) group spans all DP instances\n            # (parallel_state.init_ascend_model_parallel builds ep_cloud_ranks /\n            # ep_edge_ranks by looping over data_parallel_size), so the MoE\n            # collective (e.g. A2 ALLGATHER) is cross-DP. The idle DP's dummy\n            # (num_tokens = decode_token_per_req) and the busy DP's real forward\n            # carry different token counts; without DP padding the dummy stays\n            # at its small local count while the real is larger, and the\n            # cross-DP collective shape mismatches -> deadlock (dummy hangs in\n            # _model_forward; the real's PP isend is non-blocking so it only\n            # looks like it completes). Force-padding to the DP max makes both\n            # sides use the same token count for the collective. For the real\n            # side (which already carries the max) this is a no-op.\n            if (self._edge_cloud_enabled\n                    and self.vllm_config.parallel_config.data_parallel_size > 1):\n                allow_dp_padding = True\n            _, num_tokens_across_dp, synced_cudagraph_mode = self._sync_metadata_across_dp(\n                num_tokens=num_tokens_padded,\n                cudagraph_mode=cudagraph_mode,\n                allow_dp_padding=allow_dp_padding,\n            )",
  "new_string": "            allow_dp_padding = ((cudagraph_mode != CUDAGraphMode.NONE)\n                                or enable_sp(self.vllm_config)\n                                or oproj_tp_enable()\n                                or embedding_tp_en
...(truncated)
```

</details>


---

## User <sup>2026/8/11 15:29:09</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\worker\model_runner_v1.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 15:29:20</sup>


---

## Assistant <sup>2026/8/11 15:29:21</sup>

Now apply the actual fix in [token_dispatcher.py:133](vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py#L133) - force `global_bs` mode (no mask) for the cloud in edge-cloud DP. Let me check available imports first.


---

## Assistant <sup>2026/8/11 15:29:21</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "sed -n '1,55p' \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py\" | grep -n \"import\\|is_edge_device\\|get_ascend_config\\|edge_cloud\"",
  "description": "Check imports in token_dispatcher"
}
```

</details>


---

## User <sup>2026/8/11 15:29:22</sup>

<details>
<summary>Tool Result</summary>

```
23:from abc import ABC, abstractmethod
24:from typing import Generic
26:import torch
27:import torch_npu
28:from vllm.config import get_current_vllm_config
29:from vllm.distributed.parallel_state import get_ep_group
31:from vllm_ascend.ascend_config import get_ascend_config
32:from vllm_ascend.ascend_forward_context import get_mc2_tokens_capacity
33:from vllm_ascend.device.device_op import DeviceOperator
34:from vllm_ascend.distributed.parallel_state import get_mc2_group
35:from vllm_ascend.ops.fused_moe.comm_utils import async_all_to_all, gather_from_sequence_parallel_region
36:from vllm_ascend.ops.fused_moe.moe_runtime_args import (
44:from vllm_ascend.quantization.quant_type import QuantType
45:from vllm_ascend.utils import (
```

</details>


---

## Assistant <sup>2026/8/11 15:29:29</sup>


---

## Assistant <sup>2026/8/11 15:29:29</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "limit": 12,
  "offset": 45
}
```

</details>


---

## User <sup>2026/8/11 15:29:29</sup>

<details>
<summary>Tool Result</summary>

```
45	from vllm_ascend.utils import (
46	    AscendDeviceType,
47	    get_ascend_device_type,
48	    is_hierarchical_communication_enabled,
49	    should_skip_allreduce_across_dp_group,
50	)
51	
52	EXPERT_TOKEN_NUMS_TYPE_CUMSUM = 0
53	EXPERT_TOKEN_NUMS_TYPE_COUNT = 1
54	
55	
56	def _get_expert_token_nums_type(token_dispatch_input: MoETokenDispatchInput) -> int:
```

</details>


---

## Assistant <sup>2026/8/11 15:29:47</sup>


---

## Assistant <sup>2026/8/11 15:29:48</sup>

`is_edge_device` isn't imported, but `get_ascend_config` is. I'll use `edge_cloud_config.role == "cloud"`. Applying the fix:


---

## Assistant <sup>2026/8/11 15:29:53</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "old_string": "        # When allreduce across DP is not skipped, tokens are uniform across ranks:\n        # use global_bs=0 (uniform mode) and pass mc2_mask.\n        # When allreduce is skipped, tokens may differ per rank:\n        # use the real global_bs and do NOT pass mc2_mask.\n        self.global_bs = _max_global_bs if should_skip_allreduce_across_dp_group(vllm_config) else 0",
  "new_string": "        # When allreduce across DP is not skipped, tokens are uniform across ranks:\n        # use global_bs=0 (uniform mode) and pass mc2_mask.\n        # When allreduce is skipped, tokens may differ per rank:\n        # use the real global_bs and do NOT pass mc2_mask.\n        #\n        # Edge-cloud cloud + DP>1: the cloud EP (MC2) group spans ALL DP\n        # instances (parallel_state builds ep_cloud_ranks by looping over\n        # data_parallel_size), so the idle DP's keepalive dummy (few active\n        # tokens, e.g. decode_token_per_req=1) and the busy DP's real forward\n        # (many active tokens) share one cross-DP MC2 all-toall. In uniform\n        # mode (global_bs=0 + mc2_mask) their active-token counts differ\n        # (1 vs 15) -> all-toall shape mismatch -> the dummy hangs in\n        # _model_forward. Force the global_bs (non-uniform, no-mask) mode,\n        # whose fixed global_bs shape tolerates different per-rank active\n        # counts. Edge and cloud have separate EP groups, so this only\n        # affects the cloud MC2; the all_reduce still runs (comm-type\n        # selection stays synced via num_tokens_across_dp.max()).\n        _ec_cfg = get_ascend_config().edge_cloud_config\n        _force_global_bs = should_skip_allreduce_across_dp_group(vllm_config) or (\n            getattr(_ec_cfg, \"enabled\", False)\n            and vllm_config.parallel_config.data_parallel_size > 1\n            and getattr(_e
...(truncated)
```

</details>


---

## User <sup>2026/8/11 15:29:54</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\token_dispatcher.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 15:30:01</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/token_dispatcher.py', encoding='utf-8').read()); print('token_dispatcher.py: syntax OK')\" 2>&1\npython -c \"import ast; ast.parse(open('vllm_ascend/worker/model_runner_v1.py', encoding='utf-8').read()); print('model_runner_v1.py: syntax OK')\" 2>&1",
  "description": "Syntax check both files"
}
```

</details>


---

## User <sup>2026/8/11 15:42:18</sup>

<details>
<summary>Tool Result</summary>

```
token_dispatcher.py: syntax OK
model_runner_v1.py: syntax OK
```

</details>


---

## Assistant <sup>2026/8/11 15:42:36</sup>


---

## Assistant <sup>2026/8/11 15:42:45</sup>

修复已应用,语法通过。

## 改动总结

**两处改动:**

1. **回退** [model_runner_v1.py](vllm-ascend/vllm_ascend/worker/model_runner_v1.py) 的 `allow_dp_padding=True` 强制(它只 pad 了 num_tokens 没 pad dummy 的输入,造成输入/num_tokens_padded 不一致,且没解决 MC2 mask 失配)。

2. **真正的修复** - [token_dispatcher.py:133](vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py#L133):边云云侧 + DP>1 时强制 `global_bs != 0`(MC2 非均匀/无 mask 模式):
```python
_force_global_bs = should_skip_allreduce_across_dp_group(vllm_config) or (
    getattr(_ec_cfg, "enabled", False)
    and vllm_config.parallel_config.data_parallel_size > 1
    and getattr(_ec_cfg, "role", None) == "cloud"
)
self.global_bs = _max_global_bs if _force_global_bs else 0
```

## 机制(终于坐实)

- `should_skip=False`(all_reduce 跑了,通信类型按 max=15 选 MC2,两边一致)-> `global_bs=0` -> MC2 走 **uniform + mc2_mask** 模式([token_dispatcher.py:182-183](vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py#L182-L183) 传 `x_active_mask=mc2_mask`)。
- dummy 实际只有 **1 个 active token**(输入 `[1,2048]`),real 有 **15 个** -> MC2 all-toall 的 active 计数 1 vs 15 失配 -> 死锁。
- 强制 `global_bs != 0` -> MC2 走 **global_bs 模式(不传 mask)**,all-toall 用固定的 `global_bs = num_tokens_per_tp_rank * ep_world_size`(所有 rank 相同),容忍各 rank active 数不同 -> dummy(1)和 real(15)都按 global_bs all-toall -> 配对成功。
- 边/云 EP group 是分开的,所以只影响云侧 MC2;all_reduce 照跑(通信类型仍按 `num_tokens_across_dp.max()` 同步选)。

## 跑一次验证

`[PAD-DIAG]` / `[FWD-ENTRY]` 还留着。预期:
- `[PAD-DIAG]` 会回到 dummy `padded=1`、real `padded=15`、`across_dp=[1,15]`(allow_dp_padding 回退了)——**这没关系了**,因为 MC2 现在用 global_bs 而不是 mask。
- dummy 前向能跑完,出现 `[PD-DIAG] E. _dummy_run segment_a OUTPUT: ...` 行。
- 不再卡死,请求能继续。

把跑后的结果(是否还卡、有没有 segment_a OUTPUT 行)贴出来。确认稳定后我再删掉 `[PAD-DIAG]`/`[FWD-ENTRY]` 诊断打印。


---

## User <sup>2026/8/11 16:10:01</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\token_dispatcher.py in the IDE. This may or may not be related to the current task.</ide_opened_file>

还是卡死 (Worker_DP1_TP2_EP6 pid=139559) INFO 08-11 07:59:39 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_TP2_EP6 pid=139559) INFO 08-11 07:59:39 [model_runner_v1.py:8653] [PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): shape=[1, 2048] norm=0.000000 mean=0.000000
(Worker_DP1_TP2_EP6 pid=139559) INFO 08-11 07:59:39 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=1 bt=0(is_dummy=True)
(Worker_DP1_TP3_EP7 pid=139560) INFO 08-11 07:59:39 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_TP3_EP7 pid=139560) INFO 08-11 07:59:39 [model_runner_v1.py:8653] [PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): shape=[1, 2048] norm=0.000000 mean=0.000000
(Worker_DP1_TP3_EP7 pid=139560) INFO 08-11 07:59:39 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=1 bt=0(is_dummy=True)
(Worker_DP1_PP1_TP0_EP4 pid=139557) INFO 08-11 07:59:39 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_PP1_TP0_EP4 pid=139557) INFO 08-11 07:59:40 [model_runner_v1.py:8653] [PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): shape=[1, 2048] norm=0.000000 mean=0.000000
(Worker_DP1_PP1_TP0_EP4 pid=139557) INFO 08-11 07:59:40 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=1 bt=0(is_dummy=True)
(Worker_DP1_TP1_EP5 pid=139558) INFO 08-11 07:59:40 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_TP1_EP5 pid=139558) INFO 08-11 07:59:40 [model_runner_v1.py:8653] [PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): shape=[1, 2048] norm=0.000000 mean=0.000000
(Worker_DP1_TP1_EP5 pid=139558) INFO 08-11 07:59:40 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=1 num_tokens_padded=1 bt=0(is_dummy=True)

(Worker_DP0_TP2_EP2 pid=139490) INFO 08-11 07:59:39 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_TP3_EP3 pid=139491) INFO 08-11 07:59:39 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_PP1_TP0_EP0 pid=139488) INFO 08-11 07:59:39 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_TP1_EP1 pid=139489) INFO 08-11 07:59:40 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=0 allow_dp_padding=False local_num_tokens=15 padded=15 across_dp=[15, 1]
(Worker_DP0_TP2_EP2 pid=139490) INFO 08-11 07:59:40 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=1(is_dummy=False)
(Worker_DP0_TP3_EP3 pid=139491) INFO 08-11 07:59:40 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=1(is_dummy=False)
(Worker_DP0_PP1_TP0_EP0 pid=139488) INFO 08-11 07:59:40 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=1(is_dummy=False)
(Worker_DP0_TP1_EP1 pid=139489) INFO 08-11 07:59:40 [model_runner_v1.py:6495] [FWD-ENTRY] dp_rank=0 num_tokens_padded=15 bt=1(is_dummy=False)


---

## Assistant <sup>2026/8/11 16:11:03</sup>


---

## Assistant <sup>2026/8/11 16:11:05</sup>

依然卡死。现在 dummy 是 `num_tokens_padded=1`，输入为 `[1,2048]` (1 个 token)，而 real 是 `padded=15`。`global_bs` 强制设置没有生效——很可能是因为即使在 `global_bs` 模式下，MC2 依然在操作 dummy 的 `hidden_states`，即 `[1, 2048]` (1 个 token) 与 real 的 15 个 token 的对比——形状仍然不匹配。

我一直在治标不治本。让我看看 dummy 具体是如何调整其 `intermediate_tensors` (前向输入) 的大小的，因为这才是真正不匹配的地方 (1 个 token 对比 15 个 token)。


---

## Assistant <sup>2026/8/11 16:11:05</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\worker\\model_runner_v1.py",
  "limit": 75,
  "offset": 8595
}
```

</details>


---

## User <sup>2026/8/11 16:11:05</sup>

<details>
<summary>Tool Result</summary>

```
8595	                positions = self.positions[:num_tokens_padded]
8596	
8597	            # update global cos, sin
8598	            update_cos_sin(positions)
8599	
8600	            # ========== 边云模式（Edge-Cloud Mode）中间张量处理 ==========
8601	            # 边云模式下根据 role 判断是否需要 intermediate_tensors，
8602	            # 替代标准 PP（Pipeline Parallelism）的 is_first_rank 判断（pp_size=1 时所有 rank 都是 first）。
8603	            if self._edge_cloud_enabled:
8604	                if self.edge_cloud_cfg.role == "edge":
8605	                    # Edge 端：不需要中间张量（第一阶段）
8606	                    intermediate_tensors = None
8607	                else:
8608	                    # Cloud 端：需要中间张量。
8609	                    # Layer-sliced dummy: non-first slices reuse the
8610	                    # intermediate state saved by the previous slice,
8611	                    # just like _execute_layerwise_continuation.
8612	                    if (
8613	                        layer_slice_info is not None
8614	                   
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:11:55</sup>


---

## Assistant <sup>2026/8/11 16:11:57</sup>

`intermediate_tokens = num_tokens_padded` (第 8620 行) —— 所以当 `allow_dp_padding=True` 时，dummy 的输入确实是 15 (与真实值匹配)，但那次运行仍然挂起了。所以 `num_tokens`/input 并不是问题所在。问题在于 MC2 dispatch 本身 (global_bs / mask / hidden_states)。我需要查看 MC2 dispatch 本身确切的参数。我会在 MC2 dispatch 点添加一个诊断信息。


---

## Assistant <sup>2026/8/11 16:11:57</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "limit": 22,
  "offset": 183
}
```

</details>


---

## User <sup>2026/8/11 16:11:57</sup>

<details>
<summary>Tool Result</summary>

```
183	        # - A5 MXFP communication uses quant_mode=4.
184	        if comm_quant_mode is not None:
185	            quant_mode = comm_quant_mode
186	        elif token_dispatch_input.quant.dispatch_with_quant:
187	            quant_mode = 4 if self.a5_need_extra_args and token_dispatch_input.quant.is_mxfp else 2
188	        else:
189	            quant_mode = 0
190	        self.moe_expert_num = len(expert_map) + global_redundant_expert_num
191	        expert_token_nums_type = _get_expert_token_nums_type(token_dispatch_input)
192	        kwargs_mc2 = {
193	            "x": hidden_states,
194	            "expert_ids": topk_ids,
195	            "expert_shard_type": 0,
196	            "shared_expert_rank_num": 0,
197	            "moe_expert_num": self.moe_expert_num,
198	            "global_bs": self.global_bs,
199	            "expert_token_nums_type": expert_token_nums_type,
200	        }
201	        if self.global_bs == 0:
202	            kwargs_mc2["x_active_mask"] = token_dispatch_inpu
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:12:08</sup>


---

## Assistant <sup>2026/8/11 16:12:08</sup>

让我检查一下 `logger` 是否在 token_dispatcher 中可用，然后添加 MC2 诊断。


---

## Assistant <sup>2026/8/11 16:12:09</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"^from vllm.logger\\|^import logging\\|logger\\s*=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py\" | head\necho \"--- if none, check how nearby files log ---\"\ngrep -n \"logger\\|logging\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_comm_method.py\" | head -3",
  "description": "Check logger availability in token_dispatcher"
}
```

</details>


---

## User <sup>2026/8/11 16:12:10</sup>

<details>
<summary>Tool Result</summary>

```
--- if none, check how nearby files log ---
```

</details>


---

## Assistant <sup>2026/8/11 16:12:16</sup>


---

## Assistant <sup>2026/8/11 16:12:16</sup>

`token_dispatcher` 中没有 `logger`。我来添加导入和 MC2 诊断打印。


---

## Assistant <sup>2026/8/11 16:12:17</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "old_string": "from vllm.config import get_current_vllm_config\nfrom vllm.distributed.parallel_state import get_ep_group",
  "new_string": "from vllm.config import get_current_vllm_config\nfrom vllm.distributed.parallel_state import get_ep_group\nfrom vllm.logger import logger"
}
```

</details>


---

## User <sup>2026/8/11 16:12:19</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\token_dispatcher.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 16:12:25</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "old_string": "        if self.global_bs == 0:\n            kwargs_mc2[\"x_active_mask\"] = token_dispatch_input.routing.mc2_mask",
  "new_string": "        if self.global_bs == 0:\n            kwargs_mc2[\"x_active_mask\"] = token_dispatch_input.routing.mc2_mask\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        _mask = token_dispatch_input.routing.mc2_mask\n        logger.info(\n            \"[MC2-DIAG] rank=%s global_bs=%s hs=%s topk=%s mask=%s\",\n            _rk, self.global_bs, list(hidden_states.shape),\n            list(topk_ids.shape),\n            (list(_mask.shape) if _mask is not None else None),\n        )"
}
```

</details>


---

## User <sup>2026/8/11 16:12:26</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\token_dispatcher.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 16:12:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/token_dispatcher.py', encoding='utf-8').read()); print('syntax OK')\" 2>&1",
  "description": "Syntax check token_dispatcher"
}
```

</details>


---

## User <sup>2026/8/11 16:12:58</sup>

<details>
<summary>Tool Result</summary>

```
syntax OK
```

</details>


---

## Assistant <sup>2026/8/11 16:13:07</sup>


---

## Assistant <sup>2026/8/11 16:13:15</sup>

`[MC2-DIAG]` 已加在 MC2 dispatch 点([token_dispatcher.py:204](vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py#L204)),dummy 和 real 各自打印 `global_bs / hidden_states shape / topk_ids shape / mask`。

跑一次,然后:

```bash
grep -E "MC2-DIAG|PAD-DIAG|FWD-ENTRY" <云两DP日志>
```

## 关键看三点

1. **`global_bs` 是否 != 0**(我上个修复有没有生效):
   - 若 `global_bs=0` -> 云侧 role 判断没命中,修复没生效,mask 模式仍开着。
   - 若 `global_bs!=0` 且 `mask=None` -> 修复生效了,但 MC2 仍卡,说明 hidden_states 形状还在失配。

2. **`hs`(hidden_states)形状**:dummy 是 `[1, H]` 还是 `[15, H]`,real 是 `[15, H]`。MC2 all-toall 的实际通信量取决于这个,不是 num_tokens_padded。若 dummy `[1,H]` vs real `[15,H]` -> all-toall 形状失配死锁。

3. **是否两边都打了 `[MC2-DIAG]`**:若只有 dummy 打了、real 没打 -> real 根本没到 MC2(卡在更前面)。

---

另外,我连续几轮假设都没中,想跟你确认一个关键前提,避免继续走偏:**theroadtofree 能跑通的那次,real 侧 prefill 的 token 数是多少?是像现在这样 15(小,落入 MC2),还是 > 64(大,走 ALLGATHER 无跨 DP 集合通信)?**

因为目前看代码层面 `_dummy_run`/`token_dispatcher`/EP group 两边基本一致,我怀疑 theroadtofree 那次 real token 数较大(`> mc2_tokens_capacity=64`)走的是 ALLGATHER(TP-only,无跨 DP all-toall),dummy/real 不在跨 DP 集合通信上配对,所以不卡;而本工程这次 real=15 落入 MC2(跨 DP all-toall),dummy(1)和 real(15)配对失败才卡。若这个前提成立,修复方向就是「云侧 dummy 不要走跨 DP MC2」而非继续调 global_bs/mask。

把 `[MC2-DIAG]` 日志 + theroadtofree 那次的 real token 数贴出来,我据此定方向。


---

## User <sup>2026/8/11 16:19:38</sup>

C:\theroadtofree_github是20.0版本，边云dp并行功能是完全调通的，不同输入长度都是ok的； 当前工程是23.0版本，同步了边云dp并行功能，prefill 的 token数是15是因为打curl问题输入是15，如果打bench输入是1k也是挂死的


---

## Assistant <sup>2026/8/11 16:20:22</sup>


---

## Assistant <sup>2026/8/11 16:20:25</sup>

这是关键的背景信息。theroadtofree 是 **v0.20.0**（边云 DP 功能已完全调通，适用所有输入长度），当前是 **v0.23.0**，同步了该功能。它在**所有**输入长度（15 或 1k）下都会挂起——所以这并非 token 数量或场景的问题，而是 **0.20 到 0.23 的同步引入了回归**。

而且 1k token 也会挂起，这意味着它**不是** MC2 特有的问题（1k > 64 → ALLGATHER）。无论是 MC2 还是 ALLGATHER，云 EP 组都是跨 DP 的，因此 dummy（1 个 token）和 real（N 个 token）在**每种** comm 类型下都会出现形状不匹配。在 0.20 版本中这是正常的——所以同步过程改变了某些东西。我来对比一下这两个版本在 EP 组和 MoE 通信逻辑上的差异。


---

## Assistant <sup>2026/8/11 16:20:27</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== EP group construction: theroadtofree(0.20) vs current(0.23) ===\"\ndiff <(sed -n '564,610p' \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/distributed/parallel_state.py\") <(sed -n '564,610p' \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py\")\necho \"\"\necho \"=== token_dispatcher.py diff (0.20 vs 0.23), excluding my diag additions ===\"\ndiff \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py\" | grep -v \"MC2-DIAG\\|FWD-ENTRY\\|from vllm.logger\" | head -80",
  "description": "Diff EP group and token_dispatcher 0.20 vs 0.23"
}
```

</details>


---

## User <sup>2026/8/11 16:20:33</sup>

<details>
<summary>Tool Result</summary>

```
=== EP group construction: theroadtofree(0.20) vs current(0.23) ===
1,26c1,27
<             prefill_per_dp = num_prefill // dp_size
<             decode_per_dp = num_decode // dp_size
<             for dp_rank in range(dp_size):
<                 peer_rank = dp_rank + 1
<                 prefill_start = dp_rank * prefill_per_dp + 1
<                 decode_start = dp_rank * decode_per_dp + 1
<                 channel_peers.extend(
<                     (
<                         HiddenChannelType.prefill(channel_idx),
<                         peer_rank,
<                     )
<                     for channel_idx in range(
<                         prefill_start,
<                         prefill_start + prefill_per_dp,
<                     )
<                 )
<                 channel_peers.extend(
<                     (
<                         HiddenChannelType.decode(channel_idx),
<                         peer_rank,
<                     )
<                     for channel
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:20:44</sup>


---

## Assistant <sup>2026/8/11 16:20:47</sup>

`token_dispatcher` 的 `global_bs`/`mask` 逻辑在 0.20 和 0.23 版本中是一样的——而且 0.20 版本在 `global_bs=0`+`mask` 的配置下运行正常。所以我的 `global_bs` 假设又错了。让我撤销那个修改，去其他地方找找同步时的回归问题。我来检查一下 0.20 版本中的云 EP 组是否是跨 DP 的（就像 0.23 版本那样）。


---

## Assistant <sup>2026/8/11 16:20:47</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== 0.20: EP/MC2 group construction (ep_cloud_ranks / mc2 init) ===\"\ngrep -n \"ep_cloud_ranks\\|ep_edge_ranks\\|init_model_parallel_group\\|_MC2 =\\|data_parallel_size\\|enable_edge_cloud\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/distributed/parallel_state.py\" | head -30",
  "description": "Find EP group construction in 0.20"
}
```

</details>


---

## User <sup>2026/8/11 16:20:48</sup>

<details>
<summary>Tool Result</summary>

```
=== 0.20: EP/MC2 group construction (ep_cloud_ranks / mc2 init) ===
17:    init_model_parallel_group,
548:            dp_size = parallel_config.data_parallel_size
670:    if parallel_config.enable_edge_cloud:
685:            ep_edge_ranks = [0]
686:            ep_cloud_ranks = list(
688:                      1 + parallel_config.data_parallel_size * cloud_npu_count))
691:            ep_edge_ranks = []
692:            ep_cloud_ranks = []
693:            for dp_idx in range(parallel_config.data_parallel_size):
695:                ep_edge_ranks.extend(range(base, base + edge_npu_count))
696:                ep_cloud_ranks.extend(
698:        _MC2 = init_model_parallel_group(
699:            [ep_edge_ranks, ep_cloud_ranks],
713:                dp_size = parallel_config.data_parallel_size
755:    global_dp_size = parallel_config.data_parallel_size
798:        _P_TP = init_model_parallel_group(group_ranks, get_world_group().local_rank, backend, group_name=f"p_tp_{num}")
811:    _MC2 = init_mod
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:21:20</sup>


---

## Assistant <sup>2026/8/11 16:21:21</sup>

0.20 版本同样具有 cross-DP cloud EP 组（第 691-698 行）以及相同的 global_bs/mask 逻辑。所以这些并不是导致差异的原因。不同之处在于 dummy 的 `num_tokens`/mask 是如何相对于 real 进行设置的。让我对比一下 0.20 版本和 0.23 版本中 `allow_dp_padding` 的逻辑以及 mask 的计算方式。


---

## Assistant <sup>2026/8/11 16:21:23</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== 0.20: allow_dp_padding in _determine_batch_execution_and_padding ===\"\ngrep -n \"allow_dp_padding\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" | head\necho \"\"\necho \"=== 0.23: allow_dp_padding ===\"\ngrep -n \"allow_dp_padding\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" | head\necho \"\"\necho \"=== 0.20: allow_dp_padding context (the condition) ===\"\ngrep -n \"allow_dp_padding=\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== 0.23: allow_dp_padding context ===\"\ngrep -n \"allow_dp_padding=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"",
  "description": "Compare allow_dp_padding between 0.20 and 0.23"
}
```

</details>


---

## User <sup>2026/8/11 16:21:25</sup>

<details>
<summary>Tool Result</summary>

```
=== 0.20: allow_dp_padding in _determine_batch_execution_and_padding ===
1668:        allow_dp_padding: bool = False,
1725:        if allow_dp_padding or is_draft_model:
6873:                allow_dp_padding=(cudagraph_mode != CUDAGraphMode.NONE) or enable_sp(self.vllm_config),

=== 0.23: allow_dp_padding ===
1970:        allow_dp_padding: bool = False,
2028:        if allow_dp_padding or is_draft_model:
7939:            allow_dp_padding = ((cudagraph_mode != CUDAGraphMode.NONE)
7946:                allow_dp_padding=allow_dp_padding,
7954:                    "[PAD-DIAG] dp_rank=%s allow_dp_padding=%s local_num_tokens=%s "
7956:                    dp_rank, allow_dp_padding, num_tokens, num_tokens_padded,

=== 0.20: allow_dp_padding context (the condition) ===
6873:                allow_dp_padding=(cudagraph_mode != CUDAGraphMode.NONE) or enable_sp(self.vllm_config),
=== 0.23: allow_dp_padding context ===
7946:                allow_dp_padding=allow_dp_padding,
7954:                    "[
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:22:05</sup>


---

## Assistant <sup>2026/8/11 16:22:07</sup>

`allow_dp_padding` 是一样的（此处均为 False）。所以 dummy 在两个版本中都是 1 个 token，real 是 15 个 token，但 **0.20 版本可以运行，0.23 版本会挂起**。并且 1k (ALLGATHER) 也会挂起——所以**每种**通信类型下的跨 DP MoE 集体通信在 0.23 版本中都出现了不匹配，但在 0.20 版本中却没有。同步过程改变了 MoE 通信或 dummy 的设置。我来对比一下 0.20 和 0.23 版本之间的 MoE 通信文件。


---

## Assistant <sup>2026/8/11 16:22:10</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "for f in comm_utils.py moe_comm_method.py prepare_finalize.py moe_runtime_args.py moe_stage_contracts.py; do\n  n=$(diff \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/ops/fused_moe/$f\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/$f\" 2>/dev/null | grep -c '^[<>]')\n  echo \"$n  $f\"\ndone\necho \"\"\necho \"=== prepare_finalize.py functional diff (0.20 vs 0.23) ===\"\ndiff \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py\" | grep -v \"^[<>] *#\\|^[<>] *$\\|^[<>] *\\\".*\\|docstring\" | head -60",
  "description": "Diff MoE comm files 0.20 vs 0.23"
}
```

</details>


---

## User <sup>2026/8/11 16:22:29</sup>

<details>
<summary>Tool Result</summary>

```
0  comm_utils.py
15  moe_comm_method.py
46  prepare_finalize.py
27  moe_runtime_args.py
14  moe_stage_contracts.py

=== prepare_finalize.py functional diff (0.20 vs 0.23) ===
37c37
< from vllm_ascend.utils import enable_sp, enable_sp_by_pass, npu_stream_switch, prefill_context_parallel_enable
---
> from vllm_ascend.utils import enable_sp, enable_sp_by_pass, npu_stream_switch
369,370c369,373
<         elif quant_type == QuantType.MXFP8:
<             hidden_states, pertoken_scale = torch_npu.npu_dynamic_mx_quant(hidden_states, dst_type=torch.float8_e4m3fn)
---
>         elif quant_type in (QuantType.MXFP8, QuantType.W4A8MXFP):
>             hidden_states, pertoken_scale = torch_npu.npu_dynamic_mx_quant(
>                 hidden_states,
>                 dst_type=torch.float8_e4m3fn,
>             )
372,374c375,379
<             pass
---
>             hidden_states, pertoken_scale = torch_npu.npu_dynamic_mx_quant(
>                 hidden_states,
>                 dst_type=torch_npu.floa
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:23:36</sup>


---

## Assistant <sup>2026/8/11 16:23:38</sup>

关键认识：0.20 版本在 `global_bs=0` + `mask` 模式下可以正常工作（我确认过它的 `token_dispatcher` 是一样的）。我对 `global_bs!=0` 的强制修改与 0.20 版本**产生了偏差**，而且也没有解决问题。所以我错了——让我撤销那个修改，以匹配 0.20 版本。问题出现在其他地方。


---

## Assistant <sup>2026/8/11 16:23:42</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "old_string": "        # When allreduce across DP is not skipped, tokens are uniform across ranks:\n        # use global_bs=0 (uniform mode) and pass mc2_mask.\n        # When allreduce is skipped, tokens may differ per rank:\n        # use the real global_bs and do NOT pass mc2_mask.\n        #\n        # Edge-cloud cloud + DP>1: the cloud EP (MC2) group spans ALL DP\n        # instances (parallel_state builds ep_cloud_ranks by looping over\n        # data_parallel_size), so the idle DP's keepalive dummy (few active\n        # tokens, e.g. decode_token_per_req=1) and the busy DP's real forward\n        # (many active tokens) share one cross-DP MC2 all-toall. In uniform\n        # mode (global_bs=0 + mc2_mask) their active-token counts differ\n        # (1 vs 15) -> all-toall shape mismatch -> the dummy hangs in\n        # _model_forward. Force the global_bs (non-uniform, no-mask) mode,\n        # whose fixed global_bs shape tolerates different per-rank active\n        # counts. Edge and cloud have separate EP groups, so this only\n        # affects the cloud MC2; the all_reduce still runs (comm-type\n        # selection stays synced via num_tokens_across_dp.max()).\n        _ec_cfg = get_ascend_config().edge_cloud_config\n        _force_global_bs = should_skip_allreduce_across_dp_group(vllm_config) or (\n            getattr(_ec_cfg, \"enabled\", False)\n            and vllm_config.parallel_config.data_parallel_size > 1\n            and getattr(_ec_cfg, \"role\", None) == \"cloud\"\n        )\n        self.global_bs = _max_global_bs if _force_global_bs else 0",
  "new_string": "        # When allreduce across DP is not skipped, tokens are uniform across ranks:\n        # use global_bs=0 (uniform mode) and pass mc2_mask.\n        # When allreduce is skipped, tokens may differ per rank:\n        # use the real global_bs and do NOT pa
...(truncated)
```

</details>


---

## User <sup>2026/8/11 16:23:43</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\token_dispatcher.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 16:24:10</sup>


---

## Assistant <sup>2026/8/11 16:24:11</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/token_dispatcher.py', encoding='utf-8').read()); print('token_dispatcher syntax OK')\" 2>&1\necho \"=== confirm global_bs reverted to 0.20 logic ===\"\ngrep -n \"self.global_bs = \" vllm_ascend/ops/fused_moe/token_dispatcher.py",
  "description": "Verify revert"
}
```

</details>


---

## User <sup>2026/8/11 16:26:15</sup>

<details>
<summary>Tool Result</summary>

```
token_dispatcher syntax OK
=== confirm global_bs reverted to 0.20 logic ===
134:        self.global_bs = _max_global_bs if should_skip_allreduce_across_dp_group(vllm_config) else 0
```

</details>


---

## Assistant <sup>2026/8/11 16:26:45</sup>


---

## Assistant <sup>2026/8/11 16:26:56</sup>

已回退 `global_bs` 到 0.20 的逻辑(`global_bs=0` + mask 模式),`[MC2-DIAG]` 打印保留。

## 关键结论(需要调整方向)

0.20 和 0.23 的 **PD-separation 逻辑完全一致**(EP group 跨 DP、`_dummy_run`、`token_dispatcher` 的 global_bs/mask、`allow_dp_padding` 都一样),而 0.20 全 OK、0.23 全挂。**所以回归不在这些逻辑里,而在 0.20→0.23 的同步/基座差异中**(我前面几轮改 global_bs / allow_dp_padding 都改错了方向,因为 0.20 用这些逻辑是能跑的)。

MoE 通信文件 diff 也不大(comm_utils 0、moe_comm_method 15、prepare_finalize 46 行,主要是 PCP/quant)。0.23 `prepare_finalize` 里 PCP all_gather 的门控从 `prefill_context_parallel_enable() and pcp_size>1` 改成了只看 `pcp_size>1`——这是可疑点之一,但需验证。

## 最可靠的定位方式:0.20 vs 0.23 同位置对比

`[MC2-DIAG]` 现在在 0.23 的 MC2 dispatch 点打印 `global_bs / hidden_states shape / topk shape / mask`。请:

**1. 跑 0.23(当前),贴出两 DP 的 `[MC2-DIAG]` 行。**

**2. 在 0.20(theroadtofree)的 `token_dispatcher.py` 里加同样的打印**(它的 `get_dispatch_mc2_kwargs` 里也有 `if self.global_bs == 0: kwargs_mc2["x_active_mask"] = token_dispatch_input.routing.mc2_mask` 这行,在它后面加):

```python
        if self.global_bs == 0:
            kwargs_mc2["x_active_mask"] = token_dispatch_input.routing.mc2_mask
        try:
            _rk = torch.distributed.get_rank()
        except Exception:
            _rk = -1
        _mask = token_dispatch_input.routing.mc2_mask
        logger.info(
            "[MC2-DIAG] rank=%s global_bs=%s hs=%s topk=%s mask=%s",
            _rk, self.global_bs, list(hidden_states.shape),
            list(topk_ids.shape),
            (list(_mask.shape) if _mask is not None else None),
        )
```

(0.20 的 `token_dispatcher.py` 顶部如果没有 `from vllm.logger import logger`,也加上。)

跑 0.20,贴出它两 DP 的 `[MC2-DIAG]` 行。

## 对比看什么

把 0.20(能跑)和 0.23(挂死)的 `[MC2-DIAG]` 逐项对比:
- `global_bs` 是否一致(应都是 0)。
- dummy 与 real 的 `hs`/`topk`/`mask` 形状,0.20 是怎么配对的,0.23 哪里不一样。
- 0.20 的 real 有没有走 PCP all_gather(`hs` 形状是否被 PCP 放大),0.23 是否不同。

**0.20 能跑的那组参数就是基准**。0.23 哪个参数偏离了 0.20,就是回归点。这样能直接定位而不是继续猜。

如果加打印到 0.20 不方便,也可以先只贴 0.23 的 `[MC2-DIAG]`,我先看 dummy/real 的 hs/mask 是否明显失配,再决定下一步。


---

## User <sup>2026/8/11 16:39:21</sup>

<ide_selection>The user selected the lines 191 to 191 from c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\token_dispatcher.py:
MC2-DIAG

This may or may not be related to the current task.</ide_selection>

本工程服务拉起和打一个请求直至卡死，没有[MC2-DIAG]信息


---

## Assistant <sup>2026/8/11 16:40:10</sup>


---

## Assistant <sup>2026/8/11 16:40:12</sup>

关键：**没有 `[MC2-DIAG]`** = MC2 dispatch 甚至没有被触发。因此，通信类型不是 MC2。对于 A2，当 `ep_world_size < 16` 时选择 ALLGATHER —— 并且云 EP 组只有 8 个 ranks（2 DP × 4 cloud），所以 `8 < 16` → **ALLGATHER**，而不是 MC2。我之前在 MC2 路径下的诊断是错误的。程序卡死是在 ALLGATHER 路径下（或者在 MoE 之前的 attention 中）。让我找一下 MoE comm dispatch（所有类型）和 ALLGATHER 路径。


---

## Assistant <sup>2026/8/11 16:40:13</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "limit": 70,
  "offset": 80
}
```

</details>


---

## User <sup>2026/8/11 16:40:13</sup>

<details>
<summary>Tool Result</summary>

```
80	    before_combine_evt: torch.npu.Event | None = None
81	    # For dynamic_eplb
82	    group_list_type: int = 1
83	    expert_tokens: torch.Tensor | None = None
84	    swiglu_limit: float = 0.0
85	
86	
87	class MoECommMethod(ABC):
88	    """Base class for MoE communication methods."""
89	
90	    def __init__(self, moe_config: FusedMoEConfig):
91	        self.moe_config = moe_config
92	
93	        self.token_dispatcher = self._get_token_dispatcher()
94	        self.prepare_finalize = self._get_prepare_finalize()
95	        self.use_fusion_ops = set_gmmswigluquant_method()
96	
97	    def prepare(
98	        self,
99	        hidden_states: torch.Tensor,
100	        router_logits: torch.Tensor,
101	        enable_shared_expert_dp: bool = False,
102	        replace_allreduce: bool = False,
103	        quant_type: QuantType = QuantType.NONE,
104	    ) -> MoEPrepareOutput:
105	        return self.prepare_finalize.prepare(
106	            hidden_states,
107	            router_logits,
108	  
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 16:40:36</sup>


---

## Assistant <sup>2026/8/11 16:40:37</sup>

`fused_experts`（第 122 行）是**所有**通信类型（MC2/ALLGATHER/ALLTOALL）的通用 MoE 入口。由于没有触发 MC2，说明卡死发生在 ALLGATHER 路径或 MoE 之前。我会在 `fused_experts` 的起始处添加一个诊断打印，以确认是否到达了 MoE 层以及具体的通信类型。


---

## Assistant <sup>2026/8/11 16:40:38</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "grep -n \"^from vllm.logger\\|^import logging\\|^from vllm\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/moe_comm_method.py\" | head -5",
  "description": "Check logger import in moe_comm_method"
}
```

</details>


---

## User <sup>2026/8/11 16:40:39</sup>

<details>
<summary>Tool Result</summary>

```
22:from vllm.model_executor.layers.fused_moe import FusedMoEConfig
24:from vllm_ascend.ascend_config import get_ascend_config
25:from vllm_ascend.ascend_forward_context import _EXTRA_CTX, MoECommType
26:from vllm_ascend.ops.fused_moe.moe_mlp import unified_apply_mlp
27:from vllm_ascend.ops.fused_moe.moe_runtime_args import (
```

</details>


---

## Assistant <sup>2026/8/11 16:40:47</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "from vllm.model_executor.layers.fused_moe import FusedMoEConfig",
  "new_string": "from vllm.model_executor.layers.fused_moe import FusedMoEConfig\nfrom vllm.logger import logger"
}
```

</details>


---

## User <sup>2026/8/11 16:40:48</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 16:40:58</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "        # Check constraints\n        assert fused_experts_input.hidden_states.dtype in [\n            torch.float32,\n            torch.float16,\n            torch.bfloat16,\n            torch.int8,\n            torch.float8_e4m3fn,\n            torch.uint8,\n        ], f\"Unsupported hidden_states dtype: {fused_experts_input.hidden_states.dtype}\"\n\n        moe_comm_method = _EXTRA_CTX.moe_comm_method",
  "new_string": "        # Check constraints\n        assert fused_experts_input.hidden_states.dtype in [\n            torch.float32,\n            torch.float16,\n            torch.bfloat16,\n            torch.int8,\n            torch.float8_e4m3fn,\n            torch.uint8,\n        ], f\"Unsupported hidden_states dtype: {fused_experts_input.hidden_states.dtype}\"\n\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n            list(fused_experts_input.topk_ids.shape),\n        )\n\n        moe_comm_method = _EXTRA_CTX.moe_comm_method"
}
```

</details>


---

## User <sup>2026/8/11 16:40:59</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 16:41:11</sup>


---

## Assistant <sup>2026/8/11 16:41:11</sup>

我还会在 `prepare` 阶段（路由 + PCP all_gather）添加一个诊断打印，它运行在 `fused_experts` 之前——0.23 在此处添加了 PCP all_gather，这是一个主要的可疑点。


---

## Assistant <sup>2026/8/11 16:41:12</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "limit": 20,
  "offset": 98
}
```

</details>


---

## User <sup>2026/8/11 16:41:12</sup>

<details>
<summary>Tool Result</summary>

```
98	    def prepare(
99	        self,
100	        hidden_states: torch.Tensor,
101	        router_logits: torch.Tensor,
102	        enable_shared_expert_dp: bool = False,
103	        replace_allreduce: bool = False,
104	        quant_type: QuantType = QuantType.NONE,
105	    ) -> MoEPrepareOutput:
106	        return self.prepare_finalize.prepare(
107	            hidden_states,
108	            router_logits,
109	            enable_shared_expert_dp,
110	            replace_allreduce,
111	            quant_type,
112	        )
113	
114	    def finalize(
115	        self,
116	        hidden_states: torch.Tensor,
117	        reduce_results: bool,
```

</details>


---

## Assistant <sup>2026/8/11 16:41:20</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "    ) -> MoEPrepareOutput:\n        return self.prepare_finalize.prepare(",
  "new_string": "    ) -> MoEPrepareOutput:\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[PREP-DIAG] rank=%s comm_type=%s hs=%s router=%s pcp=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type, list(hidden_states.shape),\n            list(router_logits.shape), self.moe_config.pcp_size,\n        )\n        return self.prepare_finalize.prepare("
}
```

</details>


---

## User <sup>2026/8/11 16:41:21</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 16:41:27</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/moe_comm_method.py', encoding='utf-8').read()); print('moe_comm_method syntax OK')\" 2>&1\necho \"=== confirm diag prints ===\"\ngrep -n \"MOE-DIAG\\|PREP-DIAG\" vllm_ascend/ops/fused_moe/moe_comm_method.py",
  "description": "Syntax check and confirm diag prints"
}
```

</details>


---

## User <sup>2026/8/11 16:45:49</sup>

<details>
<summary>Tool Result</summary>

```
moe_comm_method syntax OK
=== confirm diag prints ===
111:            "[PREP-DIAG] rank=%s comm_type=%s hs=%s router=%s pcp=%s",
151:            "[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s",
```

</details>


---

## Assistant <sup>2026/8/11 16:46:00</sup>


---

## Assistant <sup>2026/8/11 16:46:07</sup>

加了两个打印(覆盖所有通信类型,不只是 MC2):
- `[PREP-DIAG]`:MoE prepare 阶段(路由 + PCP all_gather)入口
- `[MOE-DIAG]`:`fused_experts`(专家计算 + 通信)入口

跑一次(拉起 + 打一个请求到卡死),然后:

```bash
grep -E "PREP-DIAG|MOE-DIAG|FWD-ENTRY" <云两DP日志> | head -40
```

## 判读

1. **`comm_type` 是什么?** 预期 `ALLGATHER`(云 EP group=8 < 16,A2 走 ALLGATHER,不是 MC2--这解释了为什么没有 `[MC2-DIAG]`)。

2. **`[PREP-DIAG]` 有没有?`[MOE-DIAG]` 有没有?**
   - 都没有 -> 卡在 MoE 之前(attention/embedding)。
   - 只有 `[PREP-DIAG]`,没有 `[MOE-DIAG]` -> 卡在 **prepare 阶段**(路由/PCP all_gather)。0.23 在 prepare_finalize 里把 PCP all_gather 的门控从 `prefill_context_parallel_enable() and pcp_size>1` 改成只看 `pcp_size>1`--若 `pcp_size>1`,这是头号嫌疑。
   - 两个都有 -> 卡在 `fused_experts`(ALLGATHER 的 all_gather)。

3. **`pcp_size` 是多少?** 若 >1,PCP all_gather 会触发,dummy(1 token)和 real(15 token)的 PCP all_gather 形状可能失配。

4. **dummy 与 real 的 `hs` 形状**:dummy `[1,H]`、real `[15,H]`?还是被 PCP 放大后变成别的?

把这几种行各贴几条(尤其 dummy 侧 DP 和 real 侧 DP 的对比),我就能确定卡在 prepare 还是 fused_experts,以及是不是 PCP all_gather 引入的。


---

## User <sup>2026/8/11 17:37:37</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\log\0810-2.txt in the IDE. This may or may not be related to the current task.</ide_opened_file>

云侧完整日志C:\v0.23.0_lwd_acc_test_br\log\0810-2.txt


---

## Assistant <sup>2026/8/11 17:38:05</sup>


---

## Assistant <sup>2026/8/11 17:38:07</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0810-2.txt\"\necho \"=== line count ===\"; wc -l \"$LOG\"\necho \"=== marker counts ===\"\nfor m in \"PREP-DIAG\" \"MOE-DIAG\" \"FWD-ENTRY\" \"PAD-DIAG\" \"MC2-DIAG\" \"segment_a OUTPUT\" \"segment_e OUTPUT\"; do\n  printf \"%-20s %s\\n\" \"$m\" \"$(grep -c \"$m\" \"$LOG\" 2>/dev/null)\"\ndone\necho \"\"\necho \"=== comm_type values seen ===\"\ngrep -oE \"comm_type=[A-Za-z_]+\" \"$LOG\" | sort | uniq -c\necho \"=== pcp_size values seen ===\"\ngrep -oE \"pcp=[0-9]+\" \"$LOG\" | sort | uniq -c",
  "description": "Count markers and comm_type in cloud log"
}
```

</details>


---

## User <sup>2026/8/11 17:38:16</sup>

<details>
<summary>Tool Result</summary>

```
=== line count ===
697 c:/v0.23.0_lwd_acc_test_br/log/0810-2.txt
=== marker counts ===
PREP-DIAG            304
MOE-DIAG             304
FWD-ENTRY            8
PAD-DIAG             8
MC2-DIAG             0
segment_a OUTPUT     0
segment_e OUTPUT     0

=== comm_type values seen ===
    608 comm_type=MoECommType
=== pcp_size values seen ===
    304 pcp=1
```

</details>


---

## Assistant <sup>2026/8/11 17:41:14</sup>

API Error: Request rejected (429) · You have exceeded the 5-hour usage quota. It will reset at 2026-08-11 19:13:55 +0800 CST. We recommend upgrading your plan for more quota, or waiting for the reset. Request id: 021786441117155ab0d945beb4db31a8925a4a25f6e05d93548b0


---

## User <sup>2026/8/11 17:43:21</sup>

<ide_opened_file>The user opened the file c:\Users\root\AppData\Roaming\Trae CN\User\settings.json in the IDE. This may or may not be related to the current task.</ide_opened_file>

继续


---

## Assistant <sup>2026/8/11 17:46:31</sup>

API Error: Request rejected (429) · You have exceeded the 5-hour usage quota. It will reset at 2026-08-11 19:13:55 +0800 CST. We recommend upgrading your plan for more quota, or waiting for the reset. Request id: 021786441433543ab0d945beb4db31a8925a4a25f6e05d951438b


---

## User <sup>2026/8/11 19:20:22</sup>

<ide_opened_file>The user opened the file c:\Users\root\AppData\Roaming\Trae CN\User\settings.json in the IDE. This may or may not be related to the current task.</ide_opened_file>

继续


---

## Assistant <sup>2026/8/11 19:21:03</sup>


---

## Assistant <sup>2026/8/11 19:21:05</sup>

关键信号：`MOE-DIAG` 触发了 304 次，但 `segment_a OUTPUT` 为 0 —— 因此前向传播在启动 `fused_experts` 后，在内部**卡住了**（死锁发生在最后一次打印的 `fused_experts` 的 dispatch/combine 中）。`pcp=1`，所以 PCP 不是问题所在。我来获取实际的 `comm_type`，并查看挂起点附近的最后几行诊断信息，以比较 dummy 和 real。


---

## Assistant <sup>2026/8/11 19:21:06</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0810-2.txt\"\necho \"=== actual comm_type values ===\"\ngrep -oE \"comm_type=MoECommType\\.[A-Za-z_]+\" \"$LOG\" | sort | uniq -c\necho \"\"\necho \"=== which DP is dummy vs real (FWD-ENTRY) ===\"\ngrep \"FWD-ENTRY\" \"$LOG\" | grep -oE \"dp_rank=[0-9]+ num_tokens_padded=[0-9]+ bt=[0-9]+\" | sort | uniq -c\necho \"\"\necho \"=== LAST 12 MOE-DIAG lines (where it hangs) ===\"\ngrep \"MOE-DIAG\" \"$LOG\" | tail -12\necho \"\"\necho \"=== LAST 4 PREP-DIAG lines ===\"\ngrep \"PREP-DIAG\" \"$LOG\" | tail -4",
  "description": "Get comm_type and last diagnostic lines"
}
```

</details>


---

## User <sup>2026/8/11 19:21:14</sup>

<details>
<summary>Tool Result</summary>

```
=== actual comm_type values ===
    608 comm_type=MoECommType.ALLGATHER

=== which DP is dummy vs real (FWD-ENTRY) ===
      4 dp_rank=0 num_tokens_padded=1 bt=0
      4 dp_rank=1 num_tokens_padded=15 bt=1

=== LAST 12 MOE-DIAG lines (where it hangs) ===
(Worker_DP1_TP3_EP7 pid=155594) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=9 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP1_PP1_TP0_EP4 pid=155591) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=6 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP1_TP2_EP6 pid=155593) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=8 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP1_TP3_EP7 pid=155594) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=9 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP1_TP2_EP6 pid=155593) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=8 comm_type=MoECommType.ALLGATHE
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:21:46</sup>


---

## Assistant <sup>2026/8/11 19:21:48</sup>

现在情况清楚了：**comm_type = ALLGATHER**，DP0=dummy (1 个 token)，DP1=real (15 个 token)。最后几行 MOE-DIAG 日志全是 DP1 (real) —— **dummy (DP0) 停止得更早**，所以 dummy 在更早的 MoE 层就卡住了。real 的 `hs=[15,2048]→[30,2048]`，dummy 应该是 `[1,2048]`。ALLGATHER all_gather 的形状是 token 数量 —— 1 对 15/30 的不匹配。我来确认一下 dummy 的形状以及它具体卡在哪里。


---

## Assistant <sup>2026/8/11 19:21:51</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0810-2.txt\"\necho \"=== MOE-DIAG count per DP ===\"\ngrep -c \"Worker_DP0.*MOE-DIAG\" \"$LOG\" | sed 's/^/DP0(dummy): /'\ngrep -c \"Worker_DP1.*MOE-DIAG\" \"$LOG\" | sed 's/^/DP1(real):   /'\necho \"\"\necho \"=== dummy (DP0) hs shapes seen in MOE-DIAG ===\"\ngrep \"Worker_DP0.*MOE-DIAG\" \"$LOG\" | grep -oE \"hs=\\[[0-9]+, [0-9]+\\]\" | sort | uniq -c\necho \"=== real (DP1) hs shapes seen in MOE-DIAG ===\"\ngrep \"Worker_DP1.*MOE-DIAG\" \"$LOG\" | grep -oE \"hs=\\[[0-9]+, [0-9]+\\]\" | sort | uniq -c\necho \"\"\necho \"=== LAST 6 DP0(dummy) MOE-DIAG ===\"\ngrep \"Worker_DP0.*MOE-DIAG\" \"$LOG\" | tail -6\necho \"\"\necho \"=== LAST 6 DP0(dummy) PREP-DIAG ===\"\ngrep \"Worker_DP0.*PREP-DIAG\" \"$LOG\" | tail -6",
  "description": "Compare dummy vs real MoE hs shapes and hang point"
}
```

</details>


---

## User <sup>2026/8/11 19:22:01</sup>

<details>
<summary>Tool Result</summary>

```
=== MOE-DIAG count per DP ===
DP0(dummy): 152
DP1(real):   152

=== dummy (DP0) hs shapes seen in MOE-DIAG ===
    152 hs=[30, 2048]
=== real (DP1) hs shapes seen in MOE-DIAG ===
    152 hs=[30, 2048]

=== LAST 6 DP0(dummy) MOE-DIAG ===
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:23:15</sup>


---

## Assistant <sup>2026/8/11 19:23:16</sup>

重大发现：DP0 (dummy) 和 DP1 (real) **均有 152 个 MOE-DIAG，且 `hs=[30,2048]` 是一致的**。因此，它们处于 lockstep 状态，且在 `fused_experts` 中形状一致——这里不存在形状不匹配的问题。但 `segment_a OUTPUT=0`，所以卡死发生在 `fused_experts` 内部（最后一个开始但未完成的操作）。我来在 dispatch 和 combine 周围添加打印信息，以精准定位究竟是在哪一步卡住。


---

## Assistant <sup>2026/8/11 19:23:16</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "limit": 35,
  "offset": 155
}
```

</details>


---

## User <sup>2026/8/11 19:23:16</sup>

<details>
<summary>Tool Result</summary>

```
155	        )
156	
157	        moe_comm_method = _EXTRA_CTX.moe_comm_method
158	        assert moe_comm_method is not None, "Missing communication context"
159	
160	        before_dispatch_evt = torch.npu.current_stream().record_event()
161	        routed_topk_ids = fused_experts_input.topk_ids
162	        if fused_experts_input.routing.log2phy is not None:
163	            routed_topk_ids = fused_experts_input.routing.log2phy[routed_topk_ids]
164	
165	        token_dispatch_input = build_token_dispatch_input(
166	            fused_experts_input=fused_experts_input,
167	            topk_ids=routed_topk_ids,
168	        )
169	        token_dispatch_output = self.token_dispatcher.token_dispatch(token_dispatch_input=token_dispatch_input)
170	
171	        mlp_compute_input = build_mlp_compute_input(
172	            fused_experts_input=fused_experts_input,
173	            token_dispatch_output=token_dispatch_output,
174	            use_fusion_ops=self.use_fusion_ops,
175	        )
176	
177	 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:24:29</sup>


---

## Assistant <sup>2026/8/11 19:24:31</sup>

打印是异步的（不会同步流），因此 152 个计数并不能确定是哪一层或哪个阶段出现了问题。但关键事实如下：形状匹配 (30=30)，`pcp=1`，卡死在 `fused_experts` 中。让我检查一下 ALLGATHER all_gather 是 **cross-DP**（通过 8-rank EP group）还是 within-TP ——这决定了是否存在跨 DP 集体通信死锁。让我找到 ALLGATHER dispatcher 及其 all_gather group。


---

## Assistant <sup>2026/8/11 19:24:32</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "TD=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/token_dispatcher.py\"\necho \"=== AllGather dispatcher class + all_gather group ===\"\ngrep -n \"class .*Dispatcher\\|all_gather\\|reduce_scatter\\|all_to_all\\|get_ep_group\\|get_mc2_group\\|get_tp_group\\|group_name\\|moe_all_to_all_group_name\\|def token_dispatch\\|def token_combine\" \"$TD\" | head -40",
  "description": "Find ALLGATHER dispatcher and its comm group"
}
```

</details>


---

## User <sup>2026/8/11 19:24:33</sup>

<details>
<summary>Tool Result</summary>

```
=== AllGather dispatcher class + all_gather group ===
29:from vllm.distributed.parallel_state import get_ep_group
35:from vllm_ascend.distributed.parallel_state import get_mc2_group
36:from vllm_ascend.ops.fused_moe.comm_utils import async_all_to_all, gather_from_sequence_parallel_region
65:class MoETokenDispatcher(ABC, Generic[TMoECombineMetadata]):
76:        return get_ep_group().device_group
80:        return get_ep_group().rank_in_group
84:        return get_ep_group().world_size
87:    def token_dispatch(
94:    def token_combine(
103:class TokenDispatcherWithMC2(MoETokenDispatcher[MoEMC2CombineMetadata]):
106:        device_group = get_mc2_group().device_group
110:        self.moe_all_to_all_group_name = backend.get_hccl_comm_name(local_rank)
111:        self.ep_rank_id = get_mc2_group().rank_in_group
112:        self.ep_world_size = get_mc2_group().world_size
146:        device_group = get_mc2_group().device_group
149:        self.moe_all_to_all_group_name = backend.get_hccl_co
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:24:42</sup>


---

## Assistant <sup>2026/8/11 19:24:43</sup>

ALLGATHER 分发器使用 `get_ep_group()` (vllm 的 EP 组，第 76 行)，而 MC2 使用 `get_mc2_group()`。在 edge-cloud 中，`get_ep_group()` 可能与跨 DP 的 MC2 组不同。让我读取一下 ALLGATHER 的 `token_dispatch`，看看它执行的是哪种 all_gather，以及在哪个组上进行。


---

## Assistant <sup>2026/8/11 19:24:43</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "limit": 85,
  "offset": 354
}
```

</details>


---

## User <sup>2026/8/11 19:24:43</sup>

<details>
<summary>Tool Result</summary>

```
354	class TokenDispatcherWithAllGather(MoETokenDispatcher[MoEAllGatherCombineMetadata]):
355	    def __init__(self, **kwargs):
356	        super().__init__(**kwargs)
357	        self.max_num_tokens = kwargs.get("max_num_tokens")
358	        num_experts_local = kwargs.get("num_local_experts", 0)
359	        self.num_experts_local = (
360	            num_experts_local.item() if torch.is_tensor(num_experts_local) else int(num_experts_local)
361	        )
362	
363	    def token_dispatch(
364	        self,
365	        token_dispatch_input: MoETokenDispatchInput,
366	    ):
367	        quant_type = token_dispatch_input.quant.quant_type
368	        dynamic_scale = token_dispatch_input.routing.pertoken_scale
369	        unquantized_mxfp4_dispatch = quant_type == QuantType.MXFP4 and dynamic_scale is None
370	        # Without prepare-stage scales, MXFP4 stays unquantized in dispatch and
371	        # is quantized again inside the MLP path.
372	        with_quant = token_dispatch_input.quant.dis
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:24:54</sup>


---

## Assistant <sup>2026/8/11 19:24:54</sup>

ALLGATHER 的 `token_dispatch` 是**本地的**（仅包含 `npu_moe_init_routing`，无集合通信）。因此，集合通信必然在 `token_combine` 或 MLP 中。让我检查一下 `token_combine`。


---

## Assistant <sup>2026/8/11 19:24:54</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\token_dispatcher.py",
  "limit": 15,
  "offset": 440
}
```

</details>


---

## User <sup>2026/8/11 19:24:54</sup>

<details>
<summary>Tool Result</summary>

```
440	    def token_combine(self, hidden_states, combine_metadata, bias=None):
441	        final_hidden_states = DeviceOperator.npu_moe_token_unpermute(
442	            permuted_tokens=hidden_states,
443	            sorted_indices=combine_metadata.expanded_row_idx,
444	            probs=combine_metadata.topk_weights,
445	        )
446	        if len(combine_metadata.restore_shape) == 3:
447	            final_hidden_states = final_hidden_states.view(combine_metadata.restore_shape)
448	
449	        # these values are no longer used, so they need to be set to None for memory release.
450	        return final_hidden_states
451	
452	
453	class TokenDispatcherWithAll2AllV(MoETokenDispatcher[MoEAllToAllCombineMetadata]):
454	    """
```

</details>


---

## Assistant <sup>2026/8/11 19:25:40</sup>


---

## Assistant <sup>2026/8/11 19:25:42</sup>

ALLGATHER dispatch 和 combine 都是 **local** (无集合通信)。因此，ALLGATHER 模式下每层不会从 dispatcher 发起跨 DP 集合通信。但是 dummy 的 `hs` 从 1 变成了 30 (PREP→MOE)，所以 `prepare_finalize` 对其进行了扩展。我来检查一下 `prepare_finalize` 是否执行了跨 DP 的 all_gather/reduce (那将会是卡住的地方)。


---

## Assistant <sup>2026/8/11 19:25:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "PF=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py\"\necho \"=== collectives in prepare_finalize ===\"\ngrep -n \"all_gather\\|reduce_scatter\\|all_to_all\\|get_ep_group\\|get_mc2_group\\|get_tp_group\\|get_pp_group\\|get_pcp_group\\|gather_from_sequence\\|reduce_results\\|replace_allreduce\\|enable_shared_expert_dp\" \"$PF\" | head -40",
  "description": "Find collectives in prepare_finalize"
}
```

</details>


---

## User <sup>2026/8/11 19:25:44</sup>

<details>
<summary>Tool Result</summary>

```
=== collectives in prepare_finalize ===
25:    get_pcp_group,
34:from vllm_ascend.distributed.utils import fc3_all_gather_and_maybe_unpad_impl
66:        enable_shared_expert_dp: bool = False,
67:        replace_allreduce: bool = False,
79:            enable_shared_expert_dp (bool): Skip DP communication for shared experts
80:            replace_allreduce (bool): Bypass default all-reduce behavior
96:        reduce_results: bool,
108:            reduce_results (bool): Whether to apply all-reduce across TP/EP groups
136:        enable_shared_expert_dp: bool = False,
137:        replace_allreduce: bool = False,
146:        Skips if `enable_shared_expert_dp` or `replace_allreduce` is True.
151:        self.replace_allreduce = replace_allreduce
152:        self.enable_shared_expert_dp = enable_shared_expert_dp
155:        if not (self.replace_allreduce or self.enable_shared_expert_dp):
183:        if not (self.replace_allreduce or self.enable_shared_expert_dp):
196:        reduce_results: 
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:26:43</sup>


---

## Assistant <sup>2026/8/11 19:26:45</sup>

`prepare_finalize` 中包含一个 DP 路径 (`_prepare_with_dp_group`)，其中有 `maybe_all_gather_and_maybe_unpad`（第 385-388 行）——这是一个跨 DP 的 all_gather。dummy 的 `hs` 从 1 变为 30，real 的从 15 变为 30，这表明此 all_gather 将每一个都填充（pad）到了 DP 最大值，然后进行了拼接。如果 dummy 没有正确填充，这个 all_gather 就会导致不匹配。让我查看一下那个 prepare 路径。


---

## Assistant <sup>2026/8/11 19:26:45</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\prepare_finalize.py",
  "limit": 60,
  "offset": 370
}
```

</details>


---

## User <sup>2026/8/11 19:26:45</sup>

<details>
<summary>Tool Result</summary>

```
370	            hidden_states, pertoken_scale = torch_npu.npu_dynamic_mx_quant(
371	                hidden_states,
372	                dst_type=torch.float8_e4m3fn,
373	            )
374	        elif quant_type == QuantType.MXFP4:
375	            hidden_states, pertoken_scale = torch_npu.npu_dynamic_mx_quant(
376	                hidden_states,
377	                dst_type=torch_npu.float4_e2m1fn_x2,
378	                round_mode="round",
379	            )
380	
381	        if self.multistream_overlap_gate:
382	            assert PrepareAndFinalize.quant_stream is not None
383	            PrepareAndFinalize.quant_stream.wait_stream(torch.npu.current_stream())
384	            with npu_stream_switch(PrepareAndFinalize.quant_stream, enabled=self.multistream_overlap_gate):
385	                hidden_states = fc3_all_gather_and_maybe_unpad_impl(hidden_states)
386	        else:
387	            hidden_states = torch.ops.vllm.maybe_all_gather_and_maybe_unpad(hidden_states, True, True)
388	     
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:28:00</sup>


---

## Assistant <sup>2026/8/11 19:28:02</sup>

ALLGATHER dispatch/combine 是**本地**的，但 `prepare_finalize`（在 `fused_experts` 之前运行）执行了 `maybe_all_gather_and_maybe_unpad`（跨 DP）。`hs` 1->30 的扩展就在那里。异步打印无法判断该 all_gather 是否完成。让我**在 `fused_experts` 的起始处添加一个流同步** —— 这可以明确判断卡顿是发生在 `prepare` 的 DP all_gather（在此同步之前）还是在 `fused_experts` 本身。


---

## Assistant <sup>2026/8/11 19:28:06</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "        # Check constraints\n        assert fused_experts_input.hidden_states.dtype in [\n            torch.float32,\n            torch.float16,\n            torch.bfloat16,\n            torch.int8,\n            torch.float8_e4m3fn,\n            torch.uint8,\n        ], f\"Unsupported hidden_states dtype: {fused_experts_input.hidden_states.dtype}\"\n\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n            list(fused_experts_input.topk_ids.shape),\n        )",
  "new_string": "        # Check constraints\n        assert fused_experts_input.hidden_states.dtype in [\n            torch.float32,\n            torch.float16,\n            torch.bfloat16,\n            torch.int8,\n            torch.float8_e4m3fn,\n            torch.uint8,\n        ], f\"Unsupported hidden_states dtype: {fused_experts_input.hidden_states.dtype}\"\n\n        # DIAG: sync here to force the prepare-stage DP all_gather (queued on the\n        # stream before fused_experts) to complete. If this sync hangs, the\n        # prepare all_gather is the deadlock; if it returns, the hang is inside\n        # fused_experts (dispatch/mlp/combine) or later.\n        torch.npu.current_stream().synchronize()\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[MOE-SYNC] rank=%s pre-fused sync OK comm=%s hs=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n        )\n\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n  
...(truncated)
```

</details>


---

## User <sup>2026/8/11 19:28:07</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 19:28:13</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/moe_comm_method.py', encoding='utf-8').read()); print('syntax OK')\" 2>&1\ngrep -n \"MOE-SYNC\\|MOE-DIAG\" vllm_ascend/ops/fused_moe/moe_comm_method.py",
  "description": "Verify MOE-SYNC added"
}
```

</details>


---

## User <sup>2026/8/11 19:28:18</sup>

<details>
<summary>Tool Result</summary>

```
syntax OK
156:            "[MOE-SYNC] rank=%s pre-fused sync OK comm=%s hs=%s",
162:            "[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s",
```

</details>


---

## Assistant <sup>2026/8/11 19:28:30</sup>


---

## Assistant <sup>2026/8/11 19:28:37</sup>

`[MOE-SYNC]` 加在 `fused_experts` 入口(同步流,强制 prepare 阶段的 DP all_gather 完成)。跑一次:

```bash
LOG=<云日志>
echo "MOE-SYNC count:"; grep -c "MOE-SYNC" "$LOG"
echo "=== last 6 MOE-SYNC ==="; grep "MOE-SYNC" "$LOG" | tail -6
echo "=== per-DD count ==="
grep -c "Worker_DP0.*MOE-SYNC" "$LOG" | sed 's/^/DP0: /'
grep -c "Worker_DP1.*MOE-SYNC" "$LOG" | sed 's/^/DP1: /'
```

## 判读(决定性)

**情况 A:`MOE-SYNC` 数量很少(比如 0 或只有几层,远少于之前的 152)**
-> 卡在 **prepare 阶段的 DP all_gather**(`maybe_all_gather_and_maybe_unpad`,跨 DP)。dummy 的 hidden_states 是 `[1,2048]`、real 是 `[15,2048]`,这个 all_gather 没把 dummy pad 到一致就 all_gather -> 形状失配死锁。这就是回归点(0.20 的 `maybe_all_gather_and_maybe_unpad` 会先 pad,0.23 的 vllm 基座可能改了)。

**情况 B:`MOE-SYNC` 还是 152(每层都过了)**
-> prepare all_gather 正常,卡在 **fused_experts 内部**(dispatch/mlp/combine,都是 local kernel)。那就在 dispatch/mlp/combine 各加 sync 进一步定位,或查 0.23 的 local kernel 改动。

**情况 C:dummy(DP0)和 real(DP1)的 `MOE-SYNC` 数量不一样**
-> 一侧先卡,说明两侧进度不一致(某侧多做了 collective)。

把 `MOE-SYNC` 的 count 和最后几行贴出来,就能确定是 prepare all_gather 还是 fused_experts 内部。

---

说明:这个 sync 是逐层加的(诊断用,会拖慢但能定位),确认后我会删掉所有诊断打印并给最终修复。我已经连续几轮假设没中,这次用 sync 直接逼出卡死点,不再猜。


---

## User <sup>2026/8/11 19:49:22</sup>

(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe_0_23_0.py", line 122, in forward_impl
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] result = layer.shared_forward_impl(hidden_states, router_logits)
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe_0_23_0.py", line 693, in shared_forward_impl
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] fused_moe_results = self.forward_impl(
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe_0_23_0.py", line 497, in forward_impl
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] fused_experts_results: FusedExpertsResult = self.quant_method.apply(
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe.py", line 257, in apply
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] final_hidden_states = moe_comm_method.fused_experts(
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/ops/fused_moe/moe_comm_method.py", line 150, in fused_experts
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] torch.npu.current_stream().synchronize()
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/usr/local/python3.11.15/lib/python3.11/site-packages/torch_npu/npu/streams.py", line 85, in synchronize
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] super(Stream, self).synchronize()
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] RuntimeError: synchronize:../torch_npu/csrc/core/npu/NPUStream.cpp:361 NPU function error: c10_npu::acl::AclrtSynchronizeStreamWithTimeout(stream()), error code is 107027
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] [ERROR] 2026-08-11-11:40:43 (PID:55600, Device:0, RankID:-1) ERR00100 PTA call acl api failed.
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] EE9999: Inner Error!
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] EE9999[PID: 55600] 2026-08-11-11:40:43.179.688 (EE9999): Not allow to synchronize captured-stream, stream_id=33.[FUNC:StreamSynchronize][FILE:api_error.cc][LINE:1016]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] TraceBack (most recent call last):
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] rtStreamSynchronizeWithTimeout execution failed, reason=stream is captured[FUNC:FuncErrorReason][FILE:error_message_manage.cc][LINE:65]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] synchronize stream with timeout failed, runtime result = 107027[FUNC:ReportCallError][FILE:log_inner.cpp][LINE:148]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] During handling of the above exception, another exception occurred:
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] Traceback (most recent call last):
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/worker/model_runner_v1.py", line 10798, in _torch_cuda_wrapper
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] yield
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/worker/model_runner_v1.py", line 10660, in capture_model
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] with _torch_cuda_wrapper(), _replace_gpu_model_runner_function_wrapper(parent_module_name):
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/usr/local/python3.11.15/lib/python3.11/contextlib.py", line 158, in exit
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] self.gen.throw(typ, value, traceback)
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] File "/vllm-workspace/vllm-ascend/vllm_ascend/worker/model_runner_v1.py", line 10833, in _replace_gpu_model_runner_function_wrapper
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] raise RuntimeError(f"NPUModelRunner failed, error is {e}")
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] RuntimeError: NPUModelRunner failed, error is synchronize:../torch_npu/csrc/core/npu/NPUStream.cpp:361 NPU function error: c10_npu::acl::AclrtSynchronizeStreamWithTimeout(stream()), error code is 107027
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] [ERROR] 2026-08-11-11:40:43 (PID:55600, Device:0, RankID:-1) ERR00100 PTA call acl api failed.
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] EE9999: Inner Error!
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] EE9999[PID: 55600] 2026-08-11-11:40:43.179.688 (EE9999): Not allow to synchronize captured-stream, stream_id=33.[FUNC:StreamSynchronize][FILE:api_error.cc][LINE:1016]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] TraceBack (most recent call last):
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] rtStreamSynchronizeWithTimeout execution failed, reason=stream is captured[FUNC:FuncErrorReason][FILE:error_message_manage.cc][LINE:65]
(Worker_DP1_PP0_EP1 pid=55600) ERROR 08-11 11:40:43 [multiproc_executor.py:1344] synchronize stream with timeout failed, runtime result = 107027[FUNC:ReportCallError][FILE:log_inner.cpp][LINE:148]


---

## Assistant <sup>2026/8/11 19:50:32</sup>


---

## Assistant <sup>2026/8/11 19:50:33</sup>

错误很明显：**`stream is captured`** —— 我的 `synchronize()` 在 **cudagraph capture** (`capture_model`) 期间运行，此时无法同步流。所以我的同步逻辑不仅没起作用，反而导致捕获阶段崩溃了。我来移除这个同步（恢复为异步打印），然后去其他地方寻找真正的原因。


---

## Assistant <sup>2026/8/11 19:50:37</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "        # Check constraints\n        assert fused_experts_input.hidden_states.dtype in [\n            torch.float32,\n            torch.float16,\n            torch.bfloat16,\n            torch.int8,\n            torch.float8_e4m3fn,\n            torch.uint8,\n        ], f\"Unsupported hidden_states dtype: {fused_experts_input.hidden_states.dtype}\"\n\n        # DIAG: sync here to force the prepare-stage DP all_gather (queued on the\n        # stream before fused_experts) to complete. If this sync hangs, the\n        # prepare all_gather is the deadlock; if it returns, the hang is inside\n        # fused_experts (dispatch/mlp/combine) or later.\n        torch.npu.current_stream().synchronize()\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[MOE-SYNC] rank=%s pre-fused sync OK comm=%s hs=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n        )\n\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n            list(fused_experts_input.topk_ids.shape),\n        )",
  "new_string": "        # Check constraints\n        assert fused_experts_input.hidden_states.dtype in [\n            torch.float32,\n            torch.float16,\n            torch.bfloat16,\n            torch.int8,\n            torch.float8_e4m3fn,\n            torch.uint8,\n        ], f\"Unsupported hidden_states dtype: {fused_experts_input.hidden_states.dtype}\"\n\n        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n  
...(truncated)
```

</details>


---

## User <sup>2026/8/11 19:50:38</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 19:52:15</sup>


---

## Assistant <sup>2026/8/11 19:52:16</sup>

同步逻辑在 `cudagraph` 捕获期间运行（无法同步被捕获的流）——已移除。现在让我检查一下 `prepare` 的 `all_gather` 究竟是 **cross-DP** 还是 within-TP，因为这决定了 dummy/real 是否会产生交互。我来查看一下 `_prepare_with_dp_group`（用于 DP>1 的 prepare 路径）。


---

## Assistant <sup>2026/8/11 19:52:16</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\prepare_finalize.py",
  "limit": 60,
  "offset": 428
}
```

</details>


---

## User <sup>2026/8/11 19:52:16</sup>

<details>
<summary>Tool Result</summary>

```
428	    def _prepare_with_dp_group(
429	        self,
430	        hidden_states: torch.Tensor,
431	        router_logits: torch.Tensor,
432	        enable_shared_expert_dp: bool = False,
433	        replace_allreduce: bool = False,
434	        quant_type=QuantType.NONE,
435	    ) -> MoEPrepareOutput:
436	        """
437	        Preparation steps:
438	          1. Fetch max token count across DP group from forward context.
439	          2. Pad local tensors to that size.
440	          3. All-gather across DP group to form global input tensor.
441	
442	        Returns:
443	            MoEPrepareOutput with global tensors.
444	        """
445	        self.enable_shared_expert_dp = enable_shared_expert_dp
446	        if self.moe_config.dp_size > 1:
447	            max_tokens_across_dp = _EXTRA_CTX.max_tokens_across_dp
448	
449	            self.num_tokens = hidden_states.shape[0]
450	            pad_size = max_tokens_across_dp - self.num_tokens
451	            if pad_size > 0:
452	         
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:52:35</sup>


---

## Assistant <sup>2026/8/11 19:52:37</sup>

`_prepare_with_dp_group` 会填充到 `_EXTRA_CTX.max_tokens_across_dp`，然后进行全 DP 范围的 all-gather。因此，如果 `max_tokens_across_dp` 是同步后的最大值 (15)，dummy 也会被填充到 15 -> 匹配。但如果它对于 dummy 来说是**本地**的 (1)，那么 dummy 填充到 1 -> 就会产生 1 与 15 的不匹配 -> 导致死锁。让我检查一下 `max_tokens_across_dp` 是如何设置的。


---

## Assistant <sup>2026/8/11 19:52:38</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== where max_tokens_across_dp is SET ===\"\ngrep -rn \"max_tokens_across_dp\\s*=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\\|max_tokens_across_pcp\\|max_tokens_across_dp -\" | head -20\necho \"\"\necho \"=== in ascend_forward_context (where forward_context is built) ===\"\ngrep -n \"max_tokens_across_dp\\|num_tokens_across_dp\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py\" | head -20",
  "description": "Find where max_tokens_across_dp is set"
}
```

</details>


---

## User <sup>2026/8/11 19:52:40</sup>

<details>
<summary>Tool Result</summary>

```
=== where max_tokens_across_dp is SET ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py:167:            max_tokens_across_dp = dp_meta.num_tokens_across_dp_cpu.max().item()
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py:174:            max_tokens_across_dp = num_tokens
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ascend_forward_context.py:176:        forward_context.max_tokens_across_dp = max_tokens_across_dp
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py:447:            max_tokens_across_dp = _EXTRA_CTX.max_tokens_across_dp
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py:487:            max_tokens_across_dp = _EXTRA_CTX.max_tokens_across_dp
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/platform.py:1079:            max_tokens_across_dp = dp_metadata.num_tokens_across_dp_cpu.max().item()
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/plat
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:52:47</sup>


---

## Assistant <sup>2026/8/11 19:52:47</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ascend_forward_context.py",
  "limit": 30,
  "offset": 158
}
```

</details>


---

## User <sup>2026/8/11 19:52:47</sup>

<details>
<summary>Tool Result</summary>

```
158	        forward_context.is_draft_model = is_draft_model
159	        forward_context.is_draft_model_prefill = False
160	
161	        if num_tokens is None and attn_metadata is not None:
162	            num_tokens = attn_metadata.num_actual_tokens
163	
164	        dp_world_size = get_dp_group().world_size
165	        if dp_world_size > 1 and forward_context.dp_metadata is not None:
166	            dp_meta = forward_context.dp_metadata
167	            max_tokens_across_dp = dp_meta.num_tokens_across_dp_cpu.max().item()
168	            if forward_context.flash_comm_v1_enabled or forward_context.flashcomm_v2_enabled:
169	                padded_length = (max_tokens_across_dp + tp_world_size - 1) // tp_world_size * tp_world_size
170	                pad_size = padded_length - num_tokens
171	                forward_context.padded_length = padded_length
172	                forward_context.pad_size = pad_size
173	        else:
174	            max_tokens_across_dp = num_tokens
175	
176	       
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:52:58</sup>


---

## Assistant <sup>2026/8/11 19:53:00</sup>

**这是关键所在。** `max_tokens_across_dp` 使用 `dp_meta.num_tokens_across_dp_cpu.max()`（同步后的最大值）—— **仅当 `forward_context.dp_metadata is not None` 时**（第 165 行）。否则，它会回退到本地的 `num_tokens`（第 174 行）→ dummy 填充到 1 → all_gather 1 对 15 导致不匹配 → 死锁。让我检查一下 dummy 是否设置了 `dp_metadata`。


---

## Assistant <sup>2026/8/11 19:53:01</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "CUR=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\"\necho \"=== where dp_metadata is SET in current (0.23) ===\"\ngrep -n \"dp_metadata\\s*=\\|dp_metadata=\\|\\.dp_metadata =\\|DPMetadata\\|num_tokens_across_dp_cpu\" \"$CUR\" | head -20\necho \"\"\necho \"=== where dp_metadata is SET in 0.20 (theroadtofree) ===\"\ngrep -n \"dp_metadata\\s*=\\|dp_metadata=\\|\\.dp_metadata =\\|DPMetadata\\|num_tokens_across_dp_cpu\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" | head -20",
  "description": "Find where dp_metadata is set, 0.20 vs 0.23"
}
```

</details>


---

## User <sup>2026/8/11 19:53:03</sup>

<details>
<summary>Tool Result</summary>

```
=== where dp_metadata is SET in current (0.23) ===

=== where dp_metadata is SET in 0.20 (theroadtofree) ===
```

</details>


---

## Assistant <sup>2026/8/11 19:53:09</sup>


---

## Assistant <sup>2026/8/11 19:53:09</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== 0.23: where dp_metadata is assigned (whole vllm-ascend) ===\"\ngrep -rn \"\\.dp_metadata\\s*=\\|dp_metadata=\\|class DPMetadata\\|DPMetadata(\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20\necho \"\"\necho \"=== 0.20: where dp_metadata is assigned ===\"\ngrep -rn \"\\.dp_metadata\\s*=\\|dp_metadata=\\|class DPMetadata\\|DPMetadata(\" \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20",
  "description": "Find dp_metadata assignment in both"
}
```

</details>


---

## User <sup>2026/8/11 19:53:11</sup>

<details>
<summary>Tool Result</summary>

```
=== 0.23: where dp_metadata is assigned (whole vllm-ascend) ===

=== 0.20: where dp_metadata is assigned ===
```

</details>


---

## Assistant <sup>2026/8/11 19:53:17</sup>


---

## Assistant <sup>2026/8/11 19:53:18</sup>

`dp_metadata` 是在 **vllm** 中设置的，而不是 vllm-ascend。我来找一下它是在 vllm 中的哪里被设置的，并对比 vllm 0.20 和 0.23。


---

## Assistant <sup>2026/8/11 19:53:19</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== vllm 0.23: dp_metadata assignment ===\"\ngrep -rn \"\\.dp_metadata\\s*=\\|dp_metadata=\\|class DPMetadata\\|DPMetadata(\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20\necho \"\"\necho \"=== vllm 0.20 (theroadtofree): dp_metadata assignment ===\"\ngrep -rn \"\\.dp_metadata\\s*=\\|dp_metadata=\\|class DPMetadata\\|DPMetadata(\" \"C:/theroadtofree_github/vllm/vllm/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20",
  "description": "Find dp_metadata in vllm 0.20 vs 0.23"
}
```

</details>


---

## User <sup>2026/8/11 19:53:22</sup>

<details>
<summary>Tool Result</summary>

```
=== vllm 0.23: dp_metadata assignment ===
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/forward_context.py:73:class DPMetadata:
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/forward_context.py:96:        return DPMetadata(num_tokens_across_dp_cpu)
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/forward_context.py:225:        dp_metadata=dp_metadata,
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/forward_context.py:301:        dp_metadata=dp_metadata,
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/worker/gpu_ubatch_wrapper.py:357:                    dp_metadata=dp_metadata[i],
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/worker/gpu_ubatch_wrapper.py:496:                dp_metadata=ubatch_dp_metadata,
c:/v0.23.0_lwd_acc_test_br/vllm/vllm/v1/worker/gpu_ubatch_wrapper.py:522:                dp_metadata=ubatch_dp_metadata,

=== vllm 0.20 (theroadtofree): dp_metadata assignment ===
C:/theroadtofree_github/vllm/vllm/forward_context.py:74:class DPMetadata:
C:/theroadtofree_github/vllm/vllm/forward_context.py:97:        return DPMetadata(num_to
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:53:35</sup>


---

## Assistant <sup>2026/8/11 19:53:36</sup>

`dp_metadata` 是由 vllm 的 `set_forward_context` 设置的。vllm-ascend 的 `set_ascend_forward_context` 会调用它（第 89 行），但可能没有传递 `dp_metadata`。我来查看一下 vllm 的 `set_forward_context`，看看它是如何从 `num_tokens_across_dp` 构建 `dp_metadata` 的，并对比 0.20 和 0.23 版本。


---

## Assistant <sup>2026/8/11 19:53:36</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\forward_context.py",
  "limit": 50,
  "offset": 200
}
```

</details>


---

## User <sup>2026/8/11 19:53:36</sup>

<details>
<summary>Tool Result</summary>

```
200	def is_forward_context_available() -> bool:
201	    return _forward_context is not None
202	
203	
204	def create_forward_context(
205	    attn_metadata: Any,
206	    vllm_config: VllmConfig,
207	    dp_metadata: DPMetadata | None = None,
208	    cudagraph_runtime_mode: CUDAGraphMode = CUDAGraphMode.NONE,
209	    batch_descriptor: BatchDescriptor | None = None,
210	    ubatch_slices: UBatchSlices | None = None,
211	    slot_mapping: dict[str, torch.Tensor] | list[dict[str, torch.Tensor]] | None = None,
212	    additional_kwargs: dict[str, Any] | None = None,
213	    skip_compiled: bool = False,
214	):
215	    if vllm_config.compilation_config.fast_moe_cold_start:
216	        all_moe_layers = vllm_config.compilation_config.static_all_moe_layers
217	    else:
218	        all_moe_layers = None
219	
220	    return ForwardContext(
221	        no_compile_layers=vllm_config.compilation_config.static_forward_context,
222	        all_moe_layers=all_moe_layers,
223	        attn_metadata=attn_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:53:42</sup>


---

## Assistant <sup>2026/8/11 19:53:43</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm\\vllm\\forward_context.py",
  "limit": 60,
  "offset": 249
}
```

</details>


---

## User <sup>2026/8/11 19:53:43</sup>

<details>
<summary>Tool Result</summary>

```
249	@contextmanager
250	def set_forward_context(
251	    attn_metadata: Any,
252	    vllm_config: VllmConfig,
253	    num_tokens: int | None = None,
254	    num_tokens_across_dp: torch.Tensor | None = None,
255	    cudagraph_runtime_mode: CUDAGraphMode = CUDAGraphMode.NONE,
256	    batch_descriptor: BatchDescriptor | None = None,
257	    ubatch_slices: UBatchSlices | None = None,
258	    slot_mapping: dict[str, torch.Tensor] | list[dict[str, torch.Tensor]] | None = None,
259	    skip_compiled: bool = False,
260	):
261	    """A context manager that stores the current forward context,
262	    can be attention metadata, etc.
263	    Here we can inject common logic for every model forward pass.
264	    """
265	    global forward_start_time
266	    need_to_track_batchsize = track_batchsize and attn_metadata is not None
267	    if need_to_track_batchsize:
268	        forward_start_time = time.perf_counter()
269	
270	    dp_metadata: DPMetadata | None = None
271	    if (
272	        vllm_conf
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:54:15</sup>


---

## Assistant <sup>2026/8/11 19:54:16</sup>

准备阶段的 all-gather 会填充到同步后的最大值并完成 (30=30)。因此，卡死出现在 all-gather 之后 —— 很可能是在 **finalize** 阶段（跨 TP/EP 的 expert-output reduce）或 MLP 中。我来检查一下 finalize 是否有跨 DP 的 reduce。


---

## Assistant <sup>2026/8/11 19:54:18</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "PF=\"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py\"\necho \"=== finalize methods + reduce groups ===\"\ngrep -n \"def finalize\\|all_reduce\\|reduce_scatter\\|reduce_results\\|tp_group\\|ep_group\\|dp_group\\|mc2_group\\|get_tp_group\\|get_ep_group\\|get_dp_group\" \"$PF\" | head -30\necho \"\"\necho \"=== 0.23 vs 0.20 diff of prepare_finalize finalize region (functional) ===\"\ndiff \"C:/theroadtofree_github/vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py\" \"$PF\" | grep -E \"^[<>].*(all_reduce|reduce_scatter|reduce_results|def finalize|dp_group|ep_group|tp_group)\" | head -20",
  "description": "Check finalize for cross-DP reduce"
}
```

</details>


---

## User <sup>2026/8/11 19:54:23</sup>

<details>
<summary>Tool Result</summary>

```
=== finalize methods + reduce groups ===
24:    get_dp_group,
93:    def finalize(
96:        reduce_results: bool,
108:            reduce_results (bool): Whether to apply all-reduce across TP/EP groups
193:    def finalize(
196:        reduce_results: bool,
219:                dist.all_gather(list(split_hidden_states), hidden_states, self.moe_config.tp_group.device_group)
325:    1. _prepare_with_dp_group/_finalize_with_dp_group: When sequence parallelism is not enabled,
332:    2. _prepare_with_ep_group/_finalize_with_ep_group: When sequence parallelism is enabled,
359:            return self._prepare_with_ep_group(hidden_states, router_logits, quant_type)
361:        return self._prepare_with_dp_group(hidden_states, router_logits, enable_shared_expert_dp, replace_allreduce)
363:    def _prepare_with_ep_group(
390:        # TODO(fuzhihong): To adapt to self.num_token in the all_gather_input_id_with_dp_group method,
428:    def _prepare_with_dp_group(
456:            hidden_states = s
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:54:57</sup>


---

## Assistant <sup>2026/8/11 19:54:58</sup>

让我完整读取一下 `_finalize_with_dp_group` ——其中的 `reduce_scatter` (cross-DP) 很可能是导致不匹配的原因，这取决于 combine 输出的形状。


---

## Assistant <sup>2026/8/11 19:54:58</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\prepare_finalize.py",
  "limit": 25,
  "offset": 531
}
```

</details>


---

## User <sup>2026/8/11 19:54:58</sup>

<details>
<summary>Tool Result</summary>

```
531	    def _finalize_with_dp_group(self, hidden_states: torch.Tensor, reduce_results: bool) -> torch.Tensor:
532	        """
533	        Finalization steps:
534	          1. If DP > 1 and not shared expert, reduce-scatter output across DP group.
535	          2. Slice to original local token count.
536	          3. If `reduce_results=True` and TP/EP > 1, apply tensor_model_parallel_all_reduce.
537	
538	        Returns:
539	            Tensor with shape [original_local_num_tokens, hidden_size]
540	        """
541	        if self.moe_config.dp_size > 1 and not self.enable_shared_expert_dp:
542	            hidden_states = get_dp_group().reduce_scatter(hidden_states, 0)
543	            hidden_states = hidden_states[: self.num_tokens]
544	
545	        if self.moe_config.pcp_size > 1:
546	            hidden_states = get_pcp_group().reduce_scatter(hidden_states, dim=0)
547	            hidden_states = hidden_states[: self.num_tokens_pcp]
548	        return hidden_states
549
```

</details>


---

## Assistant <sup>2026/8/11 19:55:29</sup>


---

## Assistant <sup>2026/8/11 19:55:29</sup>

MoE 路径是匹配的（prepare all-gather、dispatch、combine 和 finalize reduce_scatter 在 30=30 / 15=15 时均匹配）。所以卡死很可能出现在 **attention** 中（在 MoE 之前，处理 dummy 的 1 个 token 对比 real 的 15 个 token）。让我检查一下 attention (MLA) 是否存在跨 DP 的集合通信。


---

## Assistant <sup>2026/8/11 19:55:31</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== 0.23: cross-DP collectives in attention ===\"\ngrep -rn \"get_dp_group\\|dp_group\\|all_reduce\\|all_to_all\\|reduce_scatter\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/\" 2>/dev/null | grep -v \"\\.pyc\" | head -20\necho \"\"\necho \"=== does dummy's attn use num_tokens=1 while real=15? check attn_metadata num_tokens in _dummy_run ===\"\ngrep -n \"num_actual_tokens\\|num_tokens\\|attn_metadata\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" | awk -F: '$1>=8500 && $1<=8790' | head -15",
  "description": "Check attention for cross-DP collectives"
}
```

</details>


---

## User <sup>2026/8/11 19:55:40</sup>

<details>
<summary>Tool Result</summary>

```
=== 0.23: cross-DP collectives in attention ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/attention_cp.py:931:            dist.all_to_all_single(dcp_context_attn_output, local_context_attn_output, group=self.dcp_group)
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/common_cp.py:123:        dist.all_to_all_single(attn_out_lse_all2all, attn_out_lse, group=dcp_group)
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/dsa_cp.py:1222:            skip_all_to_all=full_gather_wo_a_enabled,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/dsa_cp.py:1506:        skip_all_to_all: bool = False,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/dsa_cp.py:1520:        if self.tp_size == 1 or skip_all_to_all:
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/context_parallel/dsa_cp.py:1530:        dist.all_to_all_single(recv, send, group=sel
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:55:52</sup>


---

## Assistant <sup>2026/8/11 19:55:53</sup>

**强线索。** `dsa_v1.py:1593` 中提到“Pad to a static exchange size so the all_to_all / reduce_scatter”，并且在 `oproj_group`（第 1620、1645 行）上进行了 `all_to_all_single` + `reduce_scatter_tensor`。如果 `oproj_group` 是跨 DP 的，且 dummy（1 个 token）和 real（15 个 token）之间的静态交换大小不同，这就是导致死锁的原因。让我读取一下该区域。


---

## Assistant <sup>2026/8/11 19:55:53</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\attention\\dsa_v1.py",
  "limit": 70,
  "offset": 1585
}
```

</details>


---

## User <sup>2026/8/11 19:55:53</sup>

<details>
<summary>Tool Result</summary>

```
1585	                    "n_local_groups must be divisible by "
1586	                    f"oproj_tensor_parallel_size, got {self.n_local_groups} "
1587	                    f"and {oproj_tp_size}."
1588	                )
1589	
1590	            groups_per_rank = self.n_local_groups // oproj_tp_size
1591	
1592	            o_proj_input = o_proj_input.view(num_tokens, oproj_tp_size, groups_per_rank, group_hidden_dim)
1593	            # Pad to a static exchange size so the all_to_all / reduce_scatter
1594	            # shapes are identical across all ACL graph buckets — variable
1595	            # shapes desync the HCCL communicator during graph replay.
1596	            # potential_max_tokens is computed once in the model runner __init__,
1597	            # so reading it here is a cheap global lookup.
1598	            exchange_num_tokens = get_potential_max_tokens()
1599	            if exchange_num_tokens < num_tokens:
1600	                raise ValueError(
1601	                    "oproj sta
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:56:10</sup>


---

## Assistant <sup>2026/8/11 19:56:12</sup>

DSA attention 使用 `exchange_num_tokens = get_potential_max_tokens()` ——这是一种针对 all_to_all/reduce_scatter 的**静态**交换大小。如果 `get_potential_max_tokens()` 在所有 rank 上都相同，则形状匹配；如果它因 rank 而异（dummy 与 real），它们就会不匹配 -> 导致死锁。让我检查一下 `get_potential_max_tokens()` 是如何设置的。


---

## Assistant <sup>2026/8/11 19:56:13</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== get_potential_max_tokens definition + setter ===\"\ngrep -rn \"def get_potential_max_tokens\\|potential_max_tokens\\s*=\\|set_potential_max_tokens\\|_potential_max_tokens\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/\" 2>/dev/null | grep -v \"\\.pyc\" | head -15\necho \"\"\necho \"=== where it's called to SET (in model_runner __init__ / init) ===\"\ngrep -rn \"set_potential_max_tokens\\|potential_max_tokens\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/worker/model_runner_v1.py\" 2>/dev/null | head -10",
  "description": "Find get_potential_max_tokens definition and setter"
}
```

</details>


---

## User <sup>2026/8/11 19:56:15</sup>

<details>
<summary>Tool Result</summary>

```
=== get_potential_max_tokens definition + setter ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/dsa_v1.py:39:    get_potential_max_tokens,
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/attention/dsa_v1.py:1598:            exchange_num_tokens = get_potential_max_tokens()
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/vocab_parallel_embedding.py:42:from vllm_ascend.utils import embedding_tp_enable, get_potential_max_tokens, lmhead_tp_enable
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/vocab_parallel_embedding.py:176:        capacity = get_potential_max_tokens()
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/utils.py:1173:def _compute_potential_max_tokens(vllm_config) -> int:
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/utils.py:1177:    set_potential_max_tokens (model runner __init__) and then reused everywhere
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/utils.py:1178:    via get_potential_max_tokens. Cheap (no select_moe_comm_met
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 19:56:39</sup>


---

## Assistant <sup>2026/8/11 19:56:40</sup>

DSA attention 也使用了一个**静态**交换大小（`get_potential_max_tokens()`，根据 config 计算得出——在所有 rank 上都是相同的）。所以 MoE 和 attention 的形状都是匹配的。一定存在 **collective count/order** 不匹配的问题，而不是形状不匹配。我来检查一下 0810-2 日志中每个 DP 的跨 DP `sync_meta` all_reduce 计数——如果 dummy 和 real 执行的次数不同，那就是死锁原因。


---

## Assistant <sup>2026/8/11 19:56:43</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0810-2.txt\"\necho \"=== sync_meta (PP-EVT) count per DP ===\"\ngrep -c \"Worker_DP0.*sync_meta\" \"$LOG\" 2>/dev/null | sed 's/^/DP0: /'\ngrep -c \"Worker_DP1.*sync_meta\" \"$LOG\" 2>/dev/null | sed 's/^/DP1: /'\necho \"\"\necho \"=== sync_meta my_bt/peer_bt sample (first 4 each DP) ===\"\ngrep \"Worker_DP0.*sync_meta\" \"$LOG\" 2>/dev/null | grep -oE \"dp_rank=[0-9]+ call=[0-9]+ my_bt=[0-9]+ peer_bt=[0-9]+ num_tokens=[0-9]+\" | head -4\ngrep \"Worker_DP1.*sync_meta\" \"$LOG\" 2>/dev/null | grep -oE \"dp_rank=[0-9]+ call=[0-9]+ my_bt=[0-9]+ peer_bt=[0-9]+ num_tokens=[0-9]+\" | head -4\necho \"\"\necho \"=== last sync_meta call number per DP ===\"\ngrep \"Worker_DP0.*sync_meta\" \"$LOG\" 2>/dev/null | grep -oE \"call=[0-9]+\" | tail -1\ngrep \"Worker_DP1.*sync_meta\" \"$LOG\" 2>/dev/null | grep -oE \"call=[0-9]+\" | tail -1\necho \"\"\necho \"=== any tail_sync_meta or drafter sync mentions ===\"\ngrep -c \"tail_sync_meta\\|is_draft_model=True\\|drafter\" \"$LOG\" 2>/dev/null",
  "description": "Check sync_meta count per DP in 0810-2"
}
```

</details>


---

## User <sup>2026/8/11 19:56:52</sup>

<details>
<summary>Tool Result</summary>

```
=== sync_meta (PP-EVT) count per DP ===
DP0: 4
DP1: 4

=== sync_meta my_bt/peer_bt sample (first 4 each DP) ===
dp_rank=0 call=12 my_bt=0 peer_bt=1 num_tokens=1
dp_rank=0 call=12 my_bt=0 peer_bt=1 num_tokens=1
dp_rank=0 call=12 my_bt=0 peer_bt=1 num_tokens=1
dp_rank=0 call=12 my_bt=0 peer_bt=1 num_tokens=1
dp_rank=1 call=12 my_bt=1 peer_bt=0 num_tokens=15
dp_rank=1 call=12 my_bt=1 peer_bt=0 num_tokens=15
dp_rank=1 call=12 my_bt=1 peer_bt=0 num_tokens=15
dp_rank=1 call=12 my_bt=1 peer_bt=0 num_tokens=15

=== last sync_meta call number per DP ===
call=12
call=12

=== any tail_sync_meta or drafter sync mentions ===
0
```

</details>


---

## Assistant <sup>2026/8/11 19:58:00</sup>


---

## Assistant <sup>2026/8/11 19:58:11</sup>

我已经验证了 0.23 中所有的跨 DP 通信操作在 **shape 和 count 上都是匹配的**：
- `sync_meta` all_reduce：DP0=4，DP1=4，call=12 均符合，peer_bt 正确。
- MoE prepare all_gather → 填充到同步后的最大值 (15→30，两者皆然)。
- MoE finalize reduce_scatter → [30,2048] 两者皆是。
- DSA attention oproj → 静态交换尺寸 (`get_potential_max_tokens()`，全局配置，相同)。
- MOE-DIAG 计数：152/152 (38 层 × 4 TP，相同)。

因此，回归问题**不是**这些通信操作中 shape 或 count 不匹配导致的。经过多次错误的假设（capacity、allow_dp_padding、global_bs）后，我必须坦诚地说：在 0.23 中一切看起来都是匹配的，所以回归问题很隐蔽——可能是多了一个/少了一个通信操作，或者是 vllm 基础版本的变更——仅靠静态分析无法定位，因为 0.23 本身看起来是内部一致的。

最可靠的定位方法是：**在运行时对比 0.20 (正常) 和 0.23 (卡死) 的表现**。你本地有 0.20 版本。请在 0.20 上添加相同的诊断代码，运行相同的场景（15-token curl，edge-cloud PD-sep DP），并比较两者在何处出现差异。

## 0.20 需要加的打印(三处，和 0.23 一致)

1. **`vllm_ascend/worker/model_runner_v1.py`** — `_model_forward` 入口(在 `if self._edge_cloud_enabled:` 之前):
```python
logger.info("[FWD-ENTRY] dp_rank=%s num_tokens_padded=%s bt=%s",
            self.dp_rank, num_tokens_padded, self._dp_batch_type_id)
```

2. **`vllm_ascend/ops/fused_moe/moe_comm_method.py`** — `fused_experts` 入口(assert 之后):
```python
try: _rk = torch.distributed.get_rank()
except: _rk = -1
logger.info("[MOE-DIAG] rank=%s comm=%s hs=%s",
            _rk, _EXTRA_CTX.moe_comm_type, list(fused_experts_input.hidden_states.shape))
```

3. **`vllm_ascend/worker/model_runner_v1.py`** — `_sync_metadata_across_dp` 里已有的 `[PP-EVT] sync_meta`(0.20 应该也有,确认开着)。

跑 0.20 同样场景,**把 0.20 能跑通时的 `[FWD-ENTRY]`/`[MOE-DIAG]`/`sync_meta` 贴出来**。

## 对比看什么

- 0.20 的 dummy/real `[MOE-DIAG]` `hs` 形状、`comm` 类型、层数(count)。
- 0.20 的 `sync_meta` 调用次数和 `num_tokens`。
- **0.20 和 0.23 哪一项不同**,就是回归点。

特别关注:
- 0.20 的 `comm` 是不是也是 `ALLGATHER`?还是 `MC2`/别的?(0.23 是 ALLGATHER)
- 0.20 的 dummy `hs` 进 `fused_experts` 是多少?和 0.23 的 `[30,2048]` 一样吗?
- 0.20 的 `sync_meta` `num_tokens` dummy/real 是多少?

---

如果你不方便改 0.20,另一个办法:**把 0.23 当前 0810-2 日志里 dummy(DP0)和 real(DP1)各自的最后一条 `[MOE-DIAG]` 的时间戳和层数贴出来**——如果两侧最后到达的层不同(一侧多跑了几层),就说明有一侧多做了 collective(进度错位),那是 count/order 回归。我现在已确认 shape 和 count 都一致,所以重点转向“顺序/额外 collective”,这需要 0.20 基线对比。

你觉得哪种方式方便?


---

## User <sup>2026/8/11 20:05:29</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\log\0810-2.txt in the IDE. This may or may not be related to the current task.</ide_opened_file>

把 0.23 当前 0810-2 日志里 dummy(DP0)和 real(DP1)各自的最后一条 [MOE-DIAG] 的时间戳和层数贴出来


---

## Assistant <sup>2026/8/11 20:05:47</sup>


---

## Assistant <sup>2026/8/11 20:05:51</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0810-2.txt\"\necho \"=== MOE-DIAG count per worker (TP rank) ===\"\nfor w in DP0_PP1_TP0_EP0 DP0_TP1_EP1 DP0_TP2_EP2 DP0_TP3_EP3 DP1_PP1_TP0_EP4 DP1_TP1_EP5 DP1_TP2_EP6 DP1_TP3_EP7; do\n  n=$(grep -c \"Worker_${w}.*MOE-DIAG\" \"$LOG\")\n  echo \"$w: $n\"\ndone\necho \"\"\necho \"=== LAST MOE-DIAG per DP (with timestamp) ===\"\necho \"--- DP0 (dummy) last 3 ---\"\ngrep \"Worker_DP0.*MOE-DIAG\" \"$LOG\" | tail -3\necho \"--- DP1 (real) last 3 ---\"\ngrep \"Worker_DP1.*MOE-DIAG\" \"$LOG\" | tail -3\necho \"\"\necho \"=== FIRST and LAST timestamp per DP ===\"\ngrep \"Worker_DP0.*MOE-DIAG\" \"$LOG\" | head -1 | grep -oE \"[0-9]{2}:[0-9]{2}:[0-9]{2}\" | sed 's/^/DP0 first: /'\ngrep \"Worker_DP0.*MOE-DIAG\" \"$LOG\" | tail -1 | grep -oE \"[0-9]{2}:[0-9]{2}:[0-9]{2}\" | sed 's/^/DP0 last:  /'\ngrep \"Worker_DP1.*MOE-DIAG\" \"$LOG\" | head -1 | grep -oE \"[0-9]{2}:[0-9]{2}:[0-9]{2}\" | sed 's/^/DP1 first: /'\ngrep \"Worker_DP1.*MOE-DIAG\" \"$LOG\" | tail -1 | grep -oE \"[0-9]{2}:[0-9]{2}:[0-9]{2}\" | sed 's/^/DP1 last:  /'",
  "description": "Extract MOE-DIAG count and timestamps per worker/DP"
}
```

</details>


---

## User <sup>2026/8/11 20:08:44</sup>

<details>
<summary>Tool Result</summary>

```
=== MOE-DIAG count per worker (TP rank) ===
DP0_PP1_TP0_EP0: 38
DP0_TP1_EP1: 38
DP0_TP2_EP2: 38
DP0_TP3_EP3: 38
DP1_PP1_TP0_EP4: 38
DP1_TP1_EP5: 38
DP1_TP2_EP6: 38
DP1_TP3_EP7: 38

=== LAST MOE-DIAG per DP (with timestamp) ===
--- DP0 (dummy) last 3 ---
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP0_TP3_EP3 pid=155664) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
--- DP1 (real) last 3 ---
(Worker_DP1_TP3_EP7 pid=155594) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=9 comm_type=MoECommType.ALLGATHER hs=[30, 2048] topk=[30, 8]
(Worker_DP1_TP3_EP7 pid=155594) INFO 08-11 09:26:04 [moe_comm_method.py:150] [MOE-DIAG] rank=9 comm_type
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 20:09:42</sup>


---

## Assistant <sup>2026/8/11 20:09:45</sup>

## 结果:dummy 和 real 完全同步

| | DP0 (dummy) | DP1 (real) |
|---|---|---|
| MOE-DIAG 层数(每 TP rank) | **38** | **38** |
| 最后时间戳 | 09:26:04 | 09:26:04 |
| 最后 hs | [30, 2048] | [30, 2048] |
| comm | ALLGATHER | ALLGATHER |
| sync_meta | call=12, my_bt=0/peer_bt=1 | call=12, my_bt=1/peer_bt=0 |

8 个 TP rank 全是 38 层,时间戳一致。**两侧完全 lockstep,没有进度错位**。所以卡死是在**第 38 层(最后一层 MoE)的 `fused_experts` 内部**,两侧同时卡住--不是某一侧多做了 collective。

由于形状/层数/通信类型全匹配,卡在最里层且两侧同步,最可能是 **finalize 的 `reduce_scatter` 所用的 DP group 在边云下不对**(或 prepare 的 all_gather 同理)。让我确认边云下 `get_dp_group()` / `moe_config.dp_group` 是否正确包含两个云 DP。


---

## Assistant <sup>2026/8/11 20:09:47</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "echo \"=== 0.23: how is moe_config.dp_group / get_dp_group set up? ===\"\ngrep -rn \"dp_group\\s*=\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe_0_23_0.py\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe.py\" 2>/dev/null | grep -v \"\\.pyc\" | head\necho \"\"\necho \"=== get_dp_group definition + edge-cloud DP group init ===\"\ngrep -rn \"def get_dp_group\\|_DP_GROUP\\s*=\\|init_dp_group\\|data_parallel_group\\|dp_group.*=.*init_model_parallel\" \"c:/v0.23.0_lwd_acc_test_br/vllm/vllm/distributed/parallel_state.py\" 2>/dev/null | head -10\necho \"\"\necho \"=== edge-cloud: is standard DP group created? (parallel_state init_ascend_model_parallel) ===\"\ngrep -n \"get_dp_group\\|_DATA_PARALLEL\\|data_parallel_group\\|dp_group\\|create_dp\" \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/distributed/parallel_state.py\" | head -15",
  "description": "Check DP group setup in edge-cloud"
}
```

</details>


---

## User <sup>2026/8/11 20:09:50</sup>

<details>
<summary>Tool Result</summary>

```
=== 0.23: how is moe_config.dp_group / get_dp_group set up? ===
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe_0_23_0.py:187:        self.moe_config.dp_group = get_dp_group()
c:/v0.23.0_lwd_acc_test_br/vllm-ascend/vllm_ascend/ops/fused_moe/fused_moe.py:367:            self.moe_config.dp_group = get_dp_group()

=== get_dp_group definition + edge-cloud DP group init ===
1424:def get_dp_group() -> GroupCoordinator:

=== edge-cloud: is standard DP group created? (parallel_state init_ascend_model_parallel) ===
783:            odp_group_ranks: list[list[int]] = [
786:            for dp_group_index in range(global_dp_size):
788:                    dp_pp_serial_index = dp_group_index * global_pp_size + pp_group_index
800:                            odp_group_index = odp_base_index + j
801:                            odp_group_ranks[odp_group_index].append(global_rank)
808:                odp_group_ranks, get_world_group().local_rank, backend, group_name="flashcomm2_
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 20:11:03</sup>


---

## Assistant <sup>2026/8/11 20:11:06</sup>

**关键结论:两侧完全 lockstep。** 8 个 TP rank 全是 38 层,最后时间戳都是 09:26:04,hs=[30,2048],ALLGATHER。所以卡死是在**第 38 层 `fused_experts` 内部**,两侧同时卡--不是进度错位,不是 count/order 不匹配。

形状/层数/通信类型全匹配,但就是卡在最里层。剩下的可能性:prepare 的 all_gather 或 finalize 的 reduce_scatter(都在 `get_dp_group()` 上)实际没完成(async 打印看不出来),或某个 local kernel 在 `[15零+15真]` 数据上挂住。

之前那个 sync 诊断是对的方向(逼出卡死点),只是没避开 capture。我重新加一个**带 capture 守卫的 sync**(capture 时 captured-stream 会抛异常,try/except 跳过;dummy 是 eager 不会抛),就能确定是 prepare all_gather 卡还是 fused_experts 内部卡。


---

## Assistant <sup>2026/8/11 20:11:09</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n            list(fused_experts_input.topk_ids.shape),\n        )",
  "new_string": "        try:\n            _rk = torch.distributed.get_rank()\n        except Exception:\n            _rk = -1\n        # DIAG: force the prepare-stage DP all_gather (queued before\n        # fused_experts) to complete. Guarded: during ACL graph capture the\n        # stream is captured and synchronize raises -> skip. At runtime (eager)\n        # it returns (prepare all_gather OK) or blocks (prepare all_gather\n        # stuck). The count of OK lines reveals how many layers' all_gather\n        # completed before the hang.\n        try:\n            torch.npu.current_stream().synchronize()\n            logger.info(\"[MOE-SYNC] rank=%s OK hs=%s\", _rk,\n                        list(fused_experts_input.hidden_states.shape))\n        except Exception:\n            pass  # captured stream (graph capture) - skip\n        logger.info(\n            \"[MOE-DIAG] rank=%s comm_type=%s hs=%s topk=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type,\n            list(fused_experts_input.hidden_states.shape),\n            list(fused_experts_input.topk_ids.shape),\n        )"
}
```

</details>


---

## User <sup>2026/8/11 20:11:10</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 20:11:16</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/moe_comm_method.py', encoding='utf-8').read()); print('syntax OK')\" 2>&1",
  "description": "Syntax check"
}
```

</details>


---

## User <sup>2026/8/11 20:11:17</sup>

<details>
<summary>Tool Result</summary>

```
syntax OK
```

</details>


---

## Assistant <sup>2026/8/11 20:11:29</sup>


---

## Assistant <sup>2026/8/11 20:11:34</sup>

`[MOE-SYNC]` 已重新加上(capture 时 captured-stream 抛异常被 try/except 跳过,dummy 是 eager 不会抛)。跑一次:

```bash
LOG=<云日志>
echo "=== MOE-SYNC OK count per DP (dummy run, eager) ==="
grep -c "Worker_DP0.*MOE-SYNC.*OK" "$LOG" | sed 's/^/DP0(dummy): /'
grep -c "Worker_DP1.*MOE-SYNC.*OK" "$LOG" | sed 's/^/DP1(real):   /'
echo "=== per TP rank OK count ==="
for w in DP0_PP1_TP0_EP0 DP0_TP1_EP1 DP0_TP2_EP2 DP0_TP3_EP3 DP1_PP1_TP0_EP4 DP1_TP1_EP5 DP1_TP2_EP6 DP1_TP3_EP7; do
  echo "$w: $(grep -c "Worker_${w}.*MOE-SYNC.*OK" "$LOG")"
done
echo "=== last MOE-SYNC OK per DP ==="
grep "Worker_DP0.*MOE-SYNC.*OK" "$LOG" | tail -1
grep "Worker_DP1.*MOE-SYNC.*OK" "$LOG" | tail -1
```

## 判读(决定性)

`[MOE-SYNC] OK` = 该层 fused_experts 之前的所有 op(attention + prepare 的 DP all_gather)都已完成。

- **每 TP rank OK = 38** -> prepare all_gather 全部完成,卡在 **fused_experts 内部**(dispatch/mlp/combine/finalize 的 reduce_scatter)。下一步在 dispatch/combine 后加 sync 定位。
- **每 TP rank OK < 38**(比如 0 或 N) -> 卡在**第 N+1 层的 prepare all_gather**(或该层 attention)。说明 all_gather 实际没完成(尽管 async 形状看着是 [30,2048])。
- **DP0 和 DP1 的 OK 数不同** -> 一侧先卡。

注意:dummy 是 eager,如果 all_gather 真卡住,这个 sync 会**阻塞**(和原来 .item() 一样卡死),所以你会看到 OK 打到第 N 层后就不再打印(卡住)。那个 N 就是答案。

把 MOE-SYNC OK 的 count 和最后一行贴出来。


---

## User <sup>2026/8/11 20:25:12</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\log\0811-1.txt in the IDE. This may or may not be related to the current task.</ide_opened_file>

云侧日志C:\v0.23.0_lwd_acc_test_br\log\0811-1.txt


---

## Assistant <sup>2026/8/11 20:25:25</sup>


---

## Assistant <sup>2026/8/11 20:25:29</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0811-1.txt\"\necho \"=== line count ===\"; wc -l \"$LOG\"\necho \"=== MOE-SYNC OK count per DP ===\"\ngrep -c \"Worker_DP0.*MOE-SYNC.*OK\" \"$LOG\" | sed 's/^/DP0(dummy): /'\ngrep -c \"Worker_DP1.*MOE-SYNC.*OK\" \"$LOG\" | sed 's/^/DP1(real):   /'\necho \"=== per TP rank OK count ===\"\nfor w in DP0_PP1_TP0_EP0 DP0_TP1_EP1 DP0_TP2_EP2 DP0_TP3_EP3 DP1_PP1_TP0_EP4 DP1_TP1_EP5 DP1_TP2_EP6 DP1_TP3_EP7; do\n  echo \"$w: $(grep -c \"Worker_${w}.*MOE-SYNC.*OK\" \"$LOG\")\"\ndone\necho \"=== last MOE-SYNC OK per DP ===\"\ngrep \"Worker_DP0.*MOE-SYNC.*OK\" \"$LOG\" | tail -1\ngrep \"Worker_DP1.*MOE-SYNC.*OK\" \"$LOG\" | tail -1\necho \"=== FWD-ENTRY (who's dummy/real) ===\"\ngrep \"FWD-ENTRY\" \"$LOG\" | grep -oE \"dp_rank=[0-9]+ num_tokens_padded=[0-9]+ bt=[0-9]+\" | sort | uniq -c\necho \"=== total MOE-DIAG vs MOE-SYNC OK ===\"\necho \"MOE-DIAG: $(grep -c 'MOE-DIAG' \"$LOG\")\"\necho \"MOE-SYNC OK: $(grep -c 'MOE-SYNC.*OK' \"$LOG\")\"",
  "description": "Analyze MOE-SYNC OK counts in 0811-1"
}
```

</details>


---

## User <sup>2026/8/11 20:25:47</sup>

<details>
<summary>Tool Result</summary>

```
=== line count ===
93 c:/v0.23.0_lwd_acc_test_br/log/0811-1.txt
=== MOE-SYNC OK count per DP ===
DP0(dummy): 0
DP1(real):   0
=== per TP rank OK count ===
DP0_PP1_TP0_EP0: 0
DP0_TP1_EP1: 0
DP0_TP2_EP2: 0
DP0_TP3_EP3: 0
DP1_PP1_TP0_EP4: 0
DP1_TP1_EP5: 0
DP1_TP2_EP6: 0
DP1_TP3_EP7: 0
=== last MOE-SYNC OK per DP ===
=== FWD-ENTRY (who's dummy/real) ===
      4 dp_rank=0 num_tokens_padded=15 bt=1
      4 dp_rank=1 num_tokens_padded=1 bt=0
=== total MOE-DIAG vs MOE-SYNC OK ===
MOE-DIAG: 0
MOE-SYNC OK: 0
```

</details>


---

## Assistant <sup>2026/8/11 20:26:47</sup>


---

## Assistant <sup>2026/8/11 20:26:48</sup>

0 `[MOE-SYNC] OK` 和 0 `[MOE-DIAG]` -- 但 FWD-ENTRY 已触发（两者均进入了 `_model_forward`）。因此，卡顿发生在**第一个 MoE 层的 `fused_experts` 之前** -- 即在第 1 层的 attention 或 prepare all_gather 中。同步阻塞在第 1 层的 `fused_experts` 处。我来检查一下是否到达了 `PREP-DIAG`（prepare）阶段，以区分是 attention 还是 all_gather 卡顿。


---

## Assistant <sup>2026/8/11 20:26:51</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0811-1.txt\"\necho \"=== PREP-DIAG count per DP ===\"\ngrep -c \"Worker_DP0.*PREP-DIAG\" \"$LOG\" | sed 's/^/DP0: /'\ngrep -c \"Worker_DP1.*PREP-DIAG\" \"$LOG\" | sed 's/^/DP1: /'\necho \"=== FWD-ENTRY count ===\"\ngrep -c \"FWD-ENTRY\" \"$LOG\"\necho \"=== ALL distinct log markers and counts ===\"\ngrep -oE \"\\[(FWD-ENTRY|PREP-DIAG|MOE-DIAG|MOE-SYNC|PAD-DIAG|PP-EVT)[^]]*\\]\" \"$LOG\" | sed 's/ rank=[0-9]*//;s/ hs=[^ ]*//;s/ hs=[^ ]*//;s/ dp_rank=[0-9]*//;s/ num_tokens_padded=[0-9]*//;s/ bt=[0-9]*//;s/ local_num_tokens=[0-9]*//;s/ padded=[0-9]*//;s/ across_dp=[^ ]*//' | sort | uniq -c\necho \"=== last 8 lines of the log (where it hangs) ===\"\ntail -8 \"$LOG\"",
  "description": "Check if PREP-DIAG reached and last lines"
}
```

</details>


---

## User <sup>2026/8/11 20:27:03</sup>

<details>
<summary>Tool Result</summary>

```
=== PREP-DIAG count per DP ===
DP0: 4
DP1: 4
=== FWD-ENTRY count ===
8
=== ALL distinct log markers and counts ===
      8 [FWD-ENTRY]
      8 [PAD-DIAG]
      8 [PP-EVT]
      8 [PREP-DIAG]
=== last 8 lines of the log (where it hangs) ===
(Worker_DP1_TP2_EP6 pid=170974) INFO 08-11 12:16:29 [moe_comm_method.py:110] [PREP-DIAG] rank=8 comm_type=MoECommType.ALLGATHER hs=[1, 2048] router=[1, 256] pcp=1
(Worker_DP1_TP1_EP5 pid=170973) INFO 08-11 12:16:29 [model_runner_v1.py:2015] [PP-EVT] sync_meta: rank=7 dp_rank=1 call=12 my_bt=0 peer_bt=1 num_tokens=1
(Worker_DP1_TP1_EP5 pid=170973) INFO 08-11 12:16:29 [model_runner_v1.py:7953] [PAD-DIAG] dp_rank=1 allow_dp_padding=False local_num_tokens=1 padded=1 across_dp=[15, 1]
(Worker_DP1_TP1_EP5 pid=170973) INFO 08-11 12:16:29 [model_runner_v1.py:8653] [PD-DIAG] D. cloud _dummy_run INPUT (intermediate_tensors): shape=[1, 2048] norm=0.000000 mean=0.000000
(Worker_DP1_TP1_EP5 pid=170973) INFO 08-11 12:16:29 [model_runner_v1.py:8746] [DPDBG] _du
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 20:27:47</sup>


---

## Assistant <sup>2026/8/11 20:27:49</sup>

**卡死定位到了:第 1 层 MoE 的 prepare all_gather。** PREP-DIAG 两 DP 都打了(8 条,进到了第 1 层 prepare),但 MOE-DIAG/MOE-SYNC 都是 0(没进 fused_experts)。所以卡在 prepare 的 `_prepare_with_dp_group` 的 all_gather([prepare_finalize.py:456](vllm-ascend/vllm_ascend/ops/fused_moe/prepare_finalize.py#L456))。

all_gather 输入是 pad 到 `max_tokens_across_dp` 的。如果 dummy 的 `max_tokens_across_dp` 是本地值 1(而非同步的 15),all_gather 就是 1 vs 15 失配死锁。`max_tokens_across_dp` 在 dp_metadata 为 None 时回退到本地 num_tokens([ascend_forward_context.py:165-174](vllm-ascend/vllm_ascend/ascend_forward_context.py#L165-L174))。让我加打印确认。


---

## Assistant <sup>2026/8/11 20:27:51</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\moe_comm_method.py",
  "old_string": "        logger.info(\n            \"[PREP-DIAG] rank=%s comm_type=%s hs=%s router=%s pcp=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type, list(hidden_states.shape),\n            list(router_logits.shape), self.moe_config.pcp_size,\n        )",
  "new_string": "        logger.info(\n            \"[PREP-DIAG] rank=%s comm_type=%s hs=%s router=%s pcp=%s max_tokens_across_dp=%s dp_meta=%s\",\n            _rk, _EXTRA_CTX.moe_comm_type, list(hidden_states.shape),\n            list(router_logits.shape), self.moe_config.pcp_size,\n            getattr(_EXTRA_CTX, \"max_tokens_across_dp\", \"?\"),\n            None if getattr(_EXTRA_CTX, \"dp_metadata\", None) is None else \"set\",\n        )"
}
```

</details>


---

## User <sup>2026/8/11 20:27:52</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\moe_comm_method.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 20:28:06</sup>


---

## Assistant <sup>2026/8/11 20:28:07</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/moe_comm_method.py', encoding='utf-8').read()); print('syntax OK')\" 2>&1",
  "description": "Syntax check"
}
```

</details>


---

## User <sup>2026/8/11 20:28:08</sup>

<details>
<summary>Tool Result</summary>

```
syntax OK
```

</details>


---

## Assistant <sup>2026/8/11 20:28:16</sup>


---

## Assistant <sup>2026/8/11 20:28:20</sup>

`[PREP-DIAG]` 现在多打了 `max_tokens_across_dp` 和 `dp_meta`(set/None)。跑一次:

```bash
LOG=<云日志>
grep "PREP-DIAG" "$LOG" | head -8
```

## 判读(决定性)

看 dummy(hs=[1,2048])那行的 `max_tokens_across_dp`:

- **dummy `max_tokens_across_dp=1` 且 `dp_meta=None`** -> 确认根因:dummy 的 `dp_metadata` 没建出来,`max_tokens_across_dp` 回退到本地 num_tokens(1),prepare 的 all_gather 输入 dummy=[1,2048] vs real=[15,2048] -> 形状失配死锁。real 那行应是 `max_tokens_across_dp=15`。修复方向:让 dummy 的 forward context 也建出 `dp_metadata`(或让 `max_tokens_across_dp` 用同步的 max)。

- **dummy `max_tokens_across_dp=15` 且 `dp_meta=set`** -> dp_metadata 正常,max=15,all_gather 该匹配。那卡死是 all_gather 的 group 问题或别的,再查。

注意这次 run 里 DP1 是 dummy(hs=[1,2048])、DP0 是 real(hs=[15,2048])。把两 DP 的 PREP-DIAG 行贴出来即可。


---

## User <sup>2026/8/11 20:44:46</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\log\0811-2.txt in the IDE. This may or may not be related to the current task.</ide_opened_file>

边侧日志C:\v0.23.0_lwd_acc_test_br\log\0811-2.txt


---

## Assistant <sup>2026/8/11 20:45:12</sup>


---

## Assistant <sup>2026/8/11 20:45:15</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "LOG=\"c:/v0.23.0_lwd_acc_test_br/log/0811-2.txt\"\necho \"=== line count ===\"; wc -l \"$LOG\"\necho \"=== worker roles present (PP0=edge, PP1=cloud) ===\"\ngrep -oE \"Worker_DP[01]_PP[01]\" \"$LOG\" | sort | uniq -c\necho \"\"\necho \"=== PREP-DIAG with max_tokens_across_dp (first 8) ===\"\ngrep \"PREP-DIAG\" \"$LOG\" | head -8\necho \"\"\necho \"=== PREP-DIAG max_tokens_across_dp values: edge(PP0) vs cloud(PP1) ===\"\necho \"-- cloud (PP1) --\"; grep \"Worker_DP._PP1.*PREP-DIAG\" \"$LOG\" | grep -oE \"hs=\\[[0-9]+, [0-9]+\\] router=\\[[0-9]+, [0-9]+\\] pcp=[0-9]+ max_tokens_across_dp=[0-9?]+ dp_meta=[a-z?]+\" | sort | uniq -c\necho \"-- edge (PP0) --\"; grep \"Worker_DP._PP0.*PREP-DIAG\" \"$LOG\" | grep -oE \"hs=\\[[0-9]+, [0-9]+\\] router=\\[[0-9]+, [0-9]+\\] pcp=[0-9]+ max_tokens_across_dp=[0-9?]+ dp_meta=[a-z?]+\" | sort | uniq -c",
  "description": "Check edge log for PREP-DIAG max_tokens_across_dp"
}
```

</details>


---

## User <sup>2026/8/11 20:45:27</sup>

<details>
<summary>Tool Result</summary>

```
=== line count ===
89 c:/v0.23.0_lwd_acc_test_br/log/0811-2.txt
=== worker roles present (PP0=edge, PP1=cloud) ===
      9 Worker_DP0_PP1
     12 Worker_DP1_PP1

=== PREP-DIAG with max_tokens_across_dp (first 8) ===
(Worker_DP0_TP2_EP2 pid=176350) INFO 08-11 12:38:05 [moe_comm_method.py:110] [PREP-DIAG] rank=3 comm_type=MoECommType.ALLGATHER hs=[15, 2048] router=[15, 256] pcp=1 max_tokens_across_dp=15 dp_meta=None
(Worker_DP0_TP1_EP1 pid=176349) INFO 08-11 12:38:05 [moe_comm_method.py:110] [PREP-DIAG] rank=2 comm_type=MoECommType.ALLGATHER hs=[15, 2048] router=[15, 256] pcp=1 max_tokens_across_dp=15 dp_meta=None
(Worker_DP0_PP1_TP0_EP0 pid=176348) INFO 08-11 12:38:05 [moe_comm_method.py:110] [PREP-DIAG] rank=1 comm_type=MoECommType.ALLGATHER hs=[15, 2048] router=[15, 256] pcp=1 max_tokens_across_dp=15 dp_meta=None
(Worker_DP0_TP3_EP3 pid=176351) INFO 08-11 12:38:05 [moe_comm_method.py:110] [PREP-DIAG] rank=4 comm_type=MoECommType.ALLGATHER hs=[15, 2048] router=[15, 256] pcp=1 max_token
...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 20:46:33</sup>


---

## Assistant <sup>2026/8/11 20:46:34</sup>

**关键发现:dummy 和 real 都 `max_tokens_across_dp=15`**(dp_meta=None 是我打印取错了对象,忽略)。所以两边 prepare 的 all_gather 输入都是 `[15, 2048]`,**形状匹配**。但 all_gather 仍然卡死(0 MOE-DIAG)。

形状匹配却卡死,说明 all_gather 的 **group 不对**(不是正确的云 DP group,或包含了错误的 rank),或 prepare 走了不同的分支。让我读 prepare 的分支判断和 dp_group 来源。


---

## Assistant <sup>2026/8/11 20:46:35</sup>

<details>
<summary>Tool: <code>Read</code></summary>

```json
{
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\prepare_finalize.py",
  "limit": 28,
  "offset": 338
}
```

</details>


---

## User <sup>2026/8/11 20:46:35</sup>

<details>
<summary>Tool Result</summary>

```
338	    into EP Reduce-Scatter to improve communication performance. The optimized process is as follows:
339	
340	    TP AG → Attn → TP RS → EP AG → MoE → EP RS
341	    """
342	
343	    def prepare(
344	        self,
345	        hidden_states: torch.Tensor,
346	        router_logits: torch.Tensor,
347	        enable_shared_expert_dp: bool = False,
348	        replace_allreduce: bool = False,
349	        quant_type=QuantType.NONE,
350	    ) -> MoEPrepareOutput:
351	        """
352	        Preparation steps:
353	          AllGather hidden_states and router_logits to form global tensors.
354	
355	        Returns:
356	            MoEPrepareOutput with global tensors.
357	        """
358	        if enable_sp() or enable_sp_by_pass():
359	            return self._prepare_with_ep_group(hidden_states, router_logits, quant_type)
360	
361	        return self._prepare_with_dp_group(hidden_states, router_logits, enable_shared_expert_dp, replace_allreduce)
362	
363	    def _prepare_with_ep_group(

...(truncated)
```

</details>


---

## Assistant <sup>2026/8/11 20:47:27</sup>


---

## Assistant <sup>2026/8/11 20:47:29</sup>

两者都有 `max_tokens_across_dp=15` -> all_gather 输入 `[15,2048]` 一致，但仍然挂起。所以要么是 all_gather **group** 错误（例如 world 组有 8 个 rank，而不是 2 个 cloud DP），要么是 all_gather 本身卡住了。让我向 `_prepare_with_dp_group` 添加一个诊断信息：打印 `dp_group.world_size`，并在 all_gather 之后添加一个受保护的同步，以确认它是否是卡住的地方。


---

## Assistant <sup>2026/8/11 20:47:31</sup>

<details>
<summary>Tool: <code>Edit</code></summary>

```json
{
  "replace_all": false,
  "file_path": "c:\\v0.23.0_lwd_acc_test_br\\vllm-ascend\\vllm_ascend\\ops\\fused_moe\\prepare_finalize.py",
  "old_string": "            # All-gather across DP group\n            hidden_states = self.moe_config.dp_group.all_gather(hidden_states, 0)\n            router_logits = self.moe_config.dp_group.all_gather(router_logits, 0)",
  "new_string": "            # All-gather across DP group\n            try:\n                _ag_ws = self.moe_config.dp_group.world_size\n            except Exception:\n                _ag_ws = \"?\"\n            logger.info(\n                \"[PREP-AG] rank=%s dp_group_ws=%s max=%s local=%s pad_in=%s\",\n                torch.distributed.get_rank() if torch.distributed.is_initialized() else -1,\n                _ag_ws, max_tokens_across_dp, self.num_tokens,\n                list(hidden_states.shape),\n            )\n            hidden_states = self.moe_config.dp_group.all_gather(hidden_states, 0)\n            router_logits = self.moe_config.dp_group.all_gather(router_logits, 0)\n            try:\n                torch.npu.current_stream().synchronize()\n                logger.info(\"[PREP-AG] rank=%s all_gather DONE out=%s\",\n                            torch.distributed.get_rank() if torch.distributed.is_initialized() else -1,\n                            list(hidden_states.shape))\n            except Exception:\n                pass  # captured stream (graph capture) - skip"
}
```

</details>


---

## User <sup>2026/8/11 20:47:32</sup>

<details>
<summary>Tool Result</summary>

```
The file c:\v0.23.0_lwd_acc_test_br\vllm-ascend\vllm_ascend\ops\fused_moe\prepare_finalize.py has been updated successfully. (file state is current in your context — no need to Read it back)
```

</details>


---

## Assistant <sup>2026/8/11 20:47:39</sup>

<details>
<summary>Tool: <code>Bash</code></summary>

```json
{
  "command": "cd \"c:/v0.23.0_lwd_acc_test_br/vllm-ascend\" && python -c \"import ast; ast.parse(open('vllm_ascend/ops/fused_moe/prepare_finalize.py', encoding='utf-8').read()); print('syntax OK')\" 2>&1\ngrep -n \"from vllm.logger\\|^import logging\\|logger\" vllm_ascend/ops/fused_moe/prepare_finalize.py | head -3",
  "description": "Syntax check and verify logger import in prepare_finalize"
}
```

</details>


---

## User <sup>2026/8/11 20:47:43</sup>

<details>
<summary>Tool Result</summary>

```
syntax OK
460:            logger.info(
470:                logger.info("[PREP-AG] rank=%s all_gather DONE out=%s",
```

</details>


---

## Assistant <sup>2026/8/11 20:50:50</sup>

API Error: Request rejected (429) · You have exceeded the 5-hour usage quota. It will reset at 2026-08-12 00:17:53 +0800 CST. We recommend upgrading your plan for more quota, or waiting for the reset. Request id: 021786452492827af1c03b407b5481158c5af10bf203617db50cc


---

## User <sup>2026/8/11 20:58:09</sup>

<ide_opened_file>The user opened the file c:\v0.23.0_lwd_acc_test_br\log\0811-2.txt in the IDE. This may or may not be related to the current task.</ide_opened_file>

继续


---

## Assistant <sup>2026/8/11 21:01:22</sup>

API Error: Request rejected (429) · You have exceeded the 5-hour usage quota. It will reset at 2026-08-12 00:17:53 +0800 CST. We recommend upgrading your plan for more quota, or waiting for the reset. Request id: 021786453125137d03dabef5070a0dea5c356b99a83e9aff8384a


---

## User <sup>2026/8/11 21:02:26</sup>

<ide_opened_file>The user opened the file c:\Users\root\AppData\Roaming\Trae CN\User\settings.json in the IDE. This may or may not be related to the current task.</ide_opened_file>

继续


---

## Assistant <sup>2026/8/11 21:05:34</sup>

Prompt is too long


---
