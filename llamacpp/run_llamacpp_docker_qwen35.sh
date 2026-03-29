docker run --gpus all \
    --net=host \
    -v /home/hcq/LLM/model/llama_models:/models \
    --name qwen35-27 \
    --restart=always \
    -d \
    ghcr.nju.edu.cn/ggml-org/llama.cpp:server-cuda \
    -m /models/Qwen3.5-27B.Q4_K_M.gguf \
    --port 8000 --host 0.0.0.0 \
    -c 65536 \
    -ngl 99

# full-cuda更消耗资源和显存，在2080ti 22GB无法开启64K上下文
# server-cuda在2080ti 22GB可以开启64K上下文

# docker run --runtime nvidia  --gpus all \
#     --net=host \
#     -v /home/hcq/LLM/model/llama_models:/models \
#     --name qwen35-27 \
#     -d \
#     --restart=always \
#     --entrypoint /app/llama-server \
#     ghcr.nju.edu.cn/ggml-org/llama.cpp:full-cuda \
#     -m /models/Qwen3.5-27B.Q4_K_M.gguf \
#     --port 8000 --host 0.0.0.0 \
#     -c 32768 \
#     -ngl 99
