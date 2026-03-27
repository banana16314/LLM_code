#模型下载
from modelscope import snapshot_download
model_dir = snapshot_download('Qwen/Qwen3.5-397B-A17B-FP8', local_dir="/home/trimps/mllm/model/Qwen/Qwen3-ForcedAlign")

# ZhipuAI/GLM-4.6V-Flash Qwen/Qwen3-VL-32B-Instruct-FP8 
# Qwen/Qwen3-VL-8B-Instruct


#Dataset Download
# modelscope download --dataset DatatangBeijing/176Hours-SuzhouDialectSpeechDataByMobilePhone --local_dir /home/trimps/mllm/data/SuzhouDialect-datatang


# dataset 
# ASLP-lab/WenetSpeech-Wu-Bench