import os
import time
import requests
import re
import json

# ================= 配置区 =================
# 音频目录
INPUT_DIR = "/home/trimps/mllm/data/asr_data/taicang/20251128"

TEXT_FILE = ""

# 结果主目录
OUTPUT_DIR = "/home/trimps/mllm/results"
# 总体概览文件
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "20260325_funasr_taicang20251128_results.txt")
# 详细字幕/对话记录的存放目录
DETAIL_DIR = os.path.join(OUTPUT_DIR, "detailed_transcripts_taicang20251128")

API_URL = "http://127.0.0.1:7000/v1/audio/transcriptions"
API_KEY = "gass-wlw-ai110"

MODEL_NAME = "qwen3-asr-1.7b"  
# ==========================================

def clean_text(text):
    """清理文本：去除标点符号和多余空格，保证 WER 计算的公平性"""
    if not text:
        return ""
    text = re.sub(r'[^\w\u4e00-\u9fff]', '', text)
    return text.strip()

def calculate_cer(ref, hyp):
    """计算中文的字错率 (Character Error Rate) - 基于编辑距离"""
    ref = clean_text(ref)
    hyp = clean_text(hyp)
    
    if len(ref) == 0:
        return 100.0 if len(hyp) > 0 else 0.0
        
    d = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1): d[i][0] = i
    for j in range(len(hyp) + 1): d[0][j] = j
        
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,      
                d[i][j - 1] + 1,      
                d[i - 1][j - 1] + cost 
            )
            
    cer = (d[len(ref)][len(hyp)] / len(ref)) * 100
    return cer

def load_ground_truth(text_file):
    gt_dict = {}
    if not text_file or not os.path.exists(text_file):
        print(f"找不到标准答案文件: {text_file}")
        print("脚本已自动切换为【无答案模式】：只做语音识别，不计算字错率。")
        return None
        
    with open(text_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                audio_id, text = parts
                gt_dict[audio_id] = text
    return gt_dict

def format_time(seconds):
    """将秒数格式化为 [MM:SS.ms] 格式"""
    m, s = divmod(seconds, 60)
    return f"[{int(m):02d}:{s:05.2f}]"

def save_detailed_transcript(audio_id, result_json):
    """保存带有时间戳和说话人的详细对话记录"""
    detail_file = os.path.join(DETAIL_DIR, f"{audio_id}_detail.txt")
    segments = result_json.get("segments", [])
    
    with open(detail_file, 'w', encoding='utf-8') as f:
        f.write(f"=== 详细对话记录: {audio_id} ===\n\n")
        
        if not segments:
            f.write("未能提取到分段信息。\n")
            # 回退写出纯文本
            f.write(result_json.get("text", ""))
            return detail_file
            
        for seg in segments:
            start_str = format_time(seg.get("start", 0))
            end_str = format_time(seg.get("end", 0))
            speaker = seg.get("speaker", "说话人?")
            text = seg.get("text", "").strip()
            
            # 格式: [00:15.50 -> 00:18.20] [说话人1]: 这是一句测试音频。
            f.write(f"{start_str} -> {end_str} [{speaker}]: {text}\n")
            
    return detail_file

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(DETAIL_DIR, exist_ok=True) # 创建存放详细对话的目录
    
    print("正在初始化评测环境...")
    gt_dict = load_ground_truth(TEXT_FILE)
    is_no_answer_mode = (gt_dict is None)
    
    if not is_no_answer_mode:
        print(f"成功加载 {len(gt_dict)} 条标准答案，进入【评测模式】。")
    
    if not os.path.exists(INPUT_DIR):
        print(f"找不到输入目录 {INPUT_DIR}")
        return
        
    audio_files = sorted([f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.wav', '.mp3', '.m4a'))])
    total_files = len(audio_files)
    
    if total_files == 0:
        print(f"输入目录中找不到音频文件。")
        return

    print(f"\n开始批量处理 (共 {total_files} 个文件)...\n")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f_out:
        if is_no_answer_mode:
            f_out.write("文件名\t模型识别结果\t耗时(秒)\n")
        else:
            f_out.write("文件名\t标准答案\t模型识别结果\t字错率(CER%)\t耗时(秒)\n")
        
        for index, filename in enumerate(audio_files, 1):
            file_path = os.path.join(INPUT_DIR, filename)
            audio_id = filename.rsplit('.', 1)[0]
            
            headers = {"Authorization": f"Bearer {API_KEY}"}
            
            data = {
                "model": MODEL_NAME, 
                "language": "zh", 
                "response_format": "verbose_json", 
                "enable_speaker_diarization": "true",  
                "word_timestamps": "true",             
                "enable_vad": "true",         
                "temperature": "0",         
                # "prompt": "交关 蛮好 晓得",    
            }
            
            print(f"[{index}/{total_files}] 处理: {filename} ...", end=" ", flush=True)
            start_time = time.time()
            
            try:
                with open(file_path, 'rb') as audio_file:
                    mime_type = "audio/mpeg" if filename.lower().endswith('.mp3') else "audio/wav"
                    files = {"file": (filename, audio_file, mime_type)}
                    
                    response = requests.post(API_URL, headers=headers, data=data, files=files)
                    response.raise_for_status() 
                    
                    result_json = response.json()
                    
                    # 1. 提取全局单行文本用于写总览表格
                    recognized_text = result_json.get("text", "").replace("\n", " ")
                    
                    # 2. 提取并保存详细的分段对话轴
                    save_detailed_transcript(audio_id, result_json)
                    
                    elapsed_time = time.time() - start_time
                    
                    # 3. 写出概览表格
                    if is_no_answer_mode:
                        f_out.write(f"{filename}\t{recognized_text}\t{elapsed_time:.2f}\n")
                        f_out.flush()
                        print(f"完成! 耗时: {elapsed_time:.2f}s")
                    else:
                        ground_truth = gt_dict.get(audio_id, "")
                        if ground_truth:
                            cer_score = calculate_cer(ground_truth, recognized_text)
                            cer_str = f"{cer_score:.2f}%"
                        else:
                            cer_str = "N/A(无答案)"
                            ground_truth = "（未在text文件中找到）"
                            
                        f_out.write(f"{filename}\t{ground_truth}\t{recognized_text}\t{cer_str}\t{elapsed_time:.2f}\n")
                        f_out.flush()
                        print(f"CER: {cer_str} | 耗时: {elapsed_time:.2f}s")
                    
            except Exception as e:
                elapsed_time = time.time() - start_time
                print(f"失败! 报错: {str(e)}")
                if is_no_answer_mode:
                    f_out.write(f"{filename}\t[ERROR] {str(e)}\t{elapsed_time:.2f}\n")
                else:
                    f_out.write(f"{filename}\tN/A\t[ERROR] {str(e)}\tERROR\t{elapsed_time:.2f}\n")
                f_out.flush()

    print(f"\n批量任务完成！")
    print(f"总体概览已保存至: {OUTPUT_FILE}")
    print(f"带有时间轴和说话人的详细记录保存在目录: {DETAIL_DIR}")

if __name__ == "__main__":
    main()