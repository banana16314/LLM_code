docker rm -f funasr-api-server || true

export CUDA_VISIBLE_DEVICES=0

docker run -d \
  --name funasr-api-server \
  --gpus all \
  --restart=always \
  -p 7000:8000 \
  -e ENABLED_MODELS=qwen3-asr-1.7b \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e MULTI_GPU_READY_TIMEOUT=3600 \
  -e QWEN_ASR_MODEL_PATH=/root/.cache/huggingface/hub/Qwen/Qwen3-ASR-1.7B \
  -e QWEN_ALIGNER_MODEL_PATH=/root/.cache/huggingface/hub/Qwen/Qwen3-ForcedAlign \
  -v /home/trimps/mllm/model:/root/.cache/modelscope/hub/models \
  -v /home/trimps/mllm/model:/root/.cache/huggingface/hub \
  funasr-api:dgx-arm64