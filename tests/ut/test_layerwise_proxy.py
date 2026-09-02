import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from examples.disaggregated_prefill_v1 import (
    load_balance_proxy_layerwise_server_example as proxy,
)


class _Request:
    def __init__(self, payload):
        self.payload = payload
        self.client = SimpleNamespace(host="decoder-host")

    async def json(self):
        return self.payload


class _ProxyState:
    def __init__(self):
        self.req_data_dict = {}
        self.prefillers = [
            SimpleNamespace(
                url="http://prefiller:8001/v1",
                client=MagicMock(),
            )
        ]
        self.released_prefillers = []
        self.released_kv = []
        self.metaserver_locks = {}
        self.completed_metaserver_callbacks = {}

    async def get_metaserver_lock(self, request_id):
        return self.metaserver_locks.setdefault(request_id, asyncio.Lock())

    def get_completed_metaserver_callback(self, request_id):
        return self.completed_metaserver_callbacks.get(request_id)

    def complete_metaserver_callback(self, request_id, response):
        self.req_data_dict.pop(request_id, None)
        self.completed_metaserver_callbacks[request_id] = response

    def select_prefiller(self, _score):
        return 0

    def calculate_prefill_scores(self, request_length):
        return float(request_length)

    def release_prefiller(self, prefiller_idx, score):
        self.released_prefillers.append((prefiller_idx, score))

    def release_prefiller_kv(self, prefiller_idx, score):
        self.released_kv.append((prefiller_idx, score))


class TestLayerwiseProxyMetaserver(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = _ProxyState()
        self.original_state = proxy.proxy_state
        proxy.proxy_state = self.state
        proxy.global_args = SimpleNamespace(max_retries=3, retry_delay=0.001)

    def tearDown(self):
        proxy.proxy_state = self.original_state

    async def test_unknown_decoder_callback_returns_502(self):
        with self.assertRaises(HTTPException) as raised:
            await proxy.metaserver(
                _Request(
                    {
                        "request_id": "chatcmpl-unknown",
                        "do_remote_decode": True,
                    }
                )
            )

        self.assertEqual(raised.exception.status_code, 502)

    async def test_decoder_metadata_is_forwarded_to_prefiller(self):
        callback_request_id = "chatcmpl-trace-id"
        original_request = {"model": "model", "messages": []}
        self.state.req_data_dict[callback_request_id] = (
            original_request,
            42,
            "/chat/completions",
        )
        kv_transfer_params = {
            "request_id": callback_request_id,
            "do_remote_prefill": False,
            "do_remote_decode": True,
            "remote_engine_id": "decode-engine",
            "remote_host": "decoder-host",
            "remote_port": 14579,
            "remote_block_ids": [[1, 2]],
            "remote_cached_tokens": 0,
        }

        with patch.object(
            proxy,
            "send_request_to_service",
            new=AsyncMock(),
        ) as send_request:
            result = await proxy.metaserver(_Request(kv_transfer_params))

        self.assertEqual(result["status"], "ok")
        forwarded_request = send_request.await_args.args[3]
        self.assertEqual(forwarded_request["kv_transfer_params"], kv_transfer_params)
        self.assertEqual(send_request.await_args.args[4], "trace-id")
        self.assertEqual(self.state.released_prefillers, [(0, 42.0)])
        self.assertEqual(self.state.released_kv, [(0, 42.0)])
        self.assertNotIn(callback_request_id, self.state.req_data_dict)

    async def test_duplicate_decoder_callback_dispatches_prefill_once(self):
        callback_request_id = "chatcmpl-duplicate-id"
        self.state.req_data_dict[callback_request_id] = (
            {"model": "model", "messages": []},
            20,
            "/chat/completions",
        )
        callback = _Request(
            {
                "request_id": callback_request_id,
                "do_remote_prefill": False,
                "do_remote_decode": True,
            }
        )

        async def yield_to_duplicate(*_args, **_kwargs):
            await asyncio.sleep(0)

        with patch.object(
            proxy,
            "send_request_to_service",
            new=AsyncMock(side_effect=yield_to_duplicate),
        ) as send_request:
            first, second = await asyncio.gather(
                proxy.metaserver(callback),
                proxy.metaserver(callback),
            )

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "ok")
        self.assertEqual(send_request.await_count, 1)
        self.assertEqual(len(self.state.released_prefillers), 1)
        self.assertEqual(len(self.state.released_kv), 1)


if __name__ == "__main__":
    unittest.main()
