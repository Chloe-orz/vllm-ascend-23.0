from ais_bench.benchmark.models import VLLMCustomAPIChatStream
from ais_bench.benchmark.utils.model_postprocessors import extract_non_reasoning_content

models = [
    dict(
        attr="service",
        type=VLLMCustomAPIChatStream,
        abbr='vllm-api-stream-chat',
        path="",
        model="",
        request_rate = 0.9,
        retry = 2,
        host_ip = "76.76.26.18",
        host_port = 7621,
        max_out_len = 10240,
        batch_size=40,
        trust_remote_code=False,
        generation_kwargs = dict(
            temperature = 0.5,
            top_k = 10,
            top_p = 0.95,
            seed = None,
            repetition_penalty = 1.03,
        ),
        pred_postprocessor=dict(type=extract_non_reasoning_content)
    )
]


# from ais_bench.benchmark.models import VLLMCustomAPIChatStream
# from ais_bench.benchmark.utils.model_postprocessors import extract_non_reasoning_content

# models = [
#     dict(
#         attr="service",
#         type=VLLMCustomAPIChatStream,
#         abbr='vllm-api-stream-chat',
#         path="",
#         model="",
#         request_rate = 4,
#         retry = 2,
#         host_ip = "76.76.26.18",
#         host_port = 7621,
#         max_out_len = 10240,
#         batch_size=30,
#         trust_remote_code=False,
#         generation_kwargs = dict(
#             temperature = 0,
#             top_k = 1,
#             top_p = 1,
#             seed = None,
#             repetition_penalty = 1,
#         ),
#         pred_postprocessor=dict(type=extract_non_reasoning_content)
#     )
# ]