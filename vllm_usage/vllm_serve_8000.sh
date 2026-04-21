docker rm -f v_qwen36 || true

docker run --gpus all --name v_qwen36 \
    -v /home/deep/hcq/model:/home/deep/hcq/model \
    -e CUDA_VISIBLE_DEVICES=0 \
    --net=host \
    --restart=always \
    -d \
    --entrypoint /usr/bin/python3 \
    docker.1ms.run/vllm/vllm-openai:v0.19.1-cu130-ubuntu2404 \
    -m vllm.entrypoints.openai.api_server \
        --model /home/deep/hcq/model/Qwen/Qwen3.6-35BA3B-FP8 \
        --served-model-name Qwen \
        --max_model_len 163840 \
        --max-num-seqs 128 \
        --gpu-memory-utilization 0.8 \
        --host 0.0.0.0 \
        --port 8000 \
        --enable-auto-tool-choice \
        --tool-call-parser qwen3_coder \
        --trust-remote-code

