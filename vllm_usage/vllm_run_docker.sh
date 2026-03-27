docker run --gpus all --name vllm_qwen35_serve_20260323 \
    -v /home/hcq/LLM:/home/hcq/LLM \
    -e CUDA_VISIBLE_DEVICES=0 \
    --net=host \
    --restart=always \
    --entrypoint /usr/bin/python3 \
    docker.1ms.run/vllm/vllm-openai \
    -m vllm.entrypoints.openai.api_server \
        --model /home/hcq/LLM/Qwen3.5-0.8B/Qwen/Qwen3.5-0.8B \
        --served-model-name Qwen \
        --max_model_len 40960 \
        --max-num-seqs 16 \
        --api-key MYKEY \
        --gpu-memory-utilization 0.7 \
        --host 0.0.0.0 \
        --port 8888 \
        --enable-auto-tool-choice \
        --tool-call-parser hermes \
        --trust-remote-code