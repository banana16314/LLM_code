#!/bin/bash
# 手动进入容器里面，启动vllm服务

# 启动 vLLM 服务
# vllm serve /mllm/model/Qwen/Qwen3.5-27B-FP8 \
#     --max_model_len 40960 \
#     --served-model-name Qwen \
#     --gpu_memory_utilization 0.9 \
#     --max_num_seqs 1024 \
#     --host 0.0.0.0 \
#     --port 8000 \
#     --trust_remote_code 

VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 vllm serve /mllm/model/Qwen/Qwen3.5-27B-FP8 \
  --max-model-len 1010000 \
  --served-model-name Qwen \
  --host 0.0.0.0 \
  --port 8000 \
  --hf-overrides '{"text_config": {"rope_parameters": {
    "mrope_interleaved": true,
    "mrope_section": [11, 11, 10],
    "rope_type": "yarn",
    "rope_theta": 10000000,
    "partial_rotary_factor": 0.25,
    "factor": 4.0,
    "original_max_position_embeddings": 262144
  }}}'
# 
