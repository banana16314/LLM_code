# llama.cpp部署

## 国内镜像源下载
有cuda，所以下载cuda加速的
```bash
docker pull ghcr.nju.edu.cn/ggml-org/llama.cpp:full-cuda
```

## 开启服务
full-cuda更消耗资源和显存，在2080ti 22GB无法开启64K上下文。

server-cuda在2080ti 22GB可以开启64K上下文，推荐服务部署使用server-cuda。

```bash
docker run --runtime nvidia  --gpus all\
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
```

说明如下：
1. 开启服务，采用的是ghcr.nju.edu.cn/ggml-org/llama.cpp:server-cuda；
2. -c 65536说明context上下文的长度64K
3. -ngl 99：GPU 层数卸载（Number of GPU Layers）
   - lama.cpp 采用 CPU+GPU 混合推理 架构
   - -ngl 99 表示：把最多 99 层计算任务交给 GPU，剩余层由 CPU 处理
   - 对于 27B 模型，总层数约 60~80 层，设为 99 实际等于 "全部上 GPU"

# 🔍 `llama.cpp:full-cuda` 是否包含 `server-cuda`？

## ✅ 简短回答：**包含二进制文件，但不等于"开箱即用"**

根据 llama.cpp 官方 Docker 文档 [[10]]：

| 镜像标签 | 包含的可执行文件 | 默认 Entrypoint | 适用场景 |
|---------|----------------|----------------|---------|
| `full-cuda` | ✅ `llama-cli` + `llama-completion` + ✅ **`llama-server`** + 转换工具 | `llama-cli` 或 `--run` 模式 | 模型转换/测试/多工具 |
| `server-cuda` | ✅ **仅 `llama-server`** | `/app/llama-server` | 🎯 直接启动 API 服务 |

---

## 🔧 关键区别：默认行为不同

### `full-cuda` 镜像
```bash
# ❌ 直接运行会尝试启动 llama-cli（不支持 --port/--host）
docker run ghcr.nju.edu.cn/ggml-org/llama.cpp:full-cuda \
  --port 8000 --host 0.0.0.0
# 报错：error: unknown argument: --port

# ✅ 正确用法 1：显式指定 entrypoint
docker run --gpus all \
  --entrypoint /app/llama-server \
  ghcr.nju.edu.cn/ggml-org/llama.cpp:full-cuda \
  -m /models/model.gguf --port 8000 --host 0.0.0.0

# ✅ 正确用法 2：使用 --run-server 标志（如果镜像支持）
docker run --gpus all \
  ghcr.nju.edu.cn/ggml-org/llama.cpp:full-cuda \
  --run-server -m /models/model.gguf --port 8000
```

### `server-cuda` 镜像（推荐用于服务部署）
```bash
# ✅ 开箱即用，默认就是 llama-server
docker run --gpus all \
  ghcr.nju.edu.cn/ggml-org/llama.cpp:server-cuda \
  -m /models/model.gguf --port 8000 --host 0.0.0.0
```

---

## 🎯 如何选择？

| 需求 | 推荐镜像 | 原因 |
|-----|---------|------|
| 🔹 仅启动 API 服务 | `server-cuda` | 体积小（~2-3GB）、启动快、参数直接兼容 |
| 🔹 需要模型转换/量化 | `full-cuda` | 包含 `convert_*.py`、`quantize` 等工具 |
| 🔹 调试/测试多个工具 | `full-cuda` | 一个镜像包含所有 CLI 工具 |
| 🔹 生产环境部署 | `server-cuda` | 精简、安全、资源占用少 |

---

## 🛠️ 命令修复方案

```bash
# 方案 A：改用 server-cuda（最推荐 ✅）
docker run --runtime nvidia --gpus all \
    --net=host \
    -v /home/hcq/LLM/model/llama_models:/models \
    --name qwen35-27 \
    -d \
    ghcr.nju.edu.cn/ggml-org/llama.cpp:server-cuda \  # ← 改这里
    -m /models/Qwen3.5-27B.Q4_K_M.gguf \
    --port 8000 --host 0.0.0.0 \
    -c 65536 \
    --n-gpu-layers 99

# 方案 B：保留 full-cuda 但指定 entrypoint
docker run --runtime nvidia --gpus all \
    --net=host \
    -v /home/hcq/LLM/model/llama_models:/models \
    --name qwen35-27 \
    -d \
    --entrypoint /app/llama-server \  # ← 添加这行
    ghcr.nju.edu.cn/ggml-org/llama.cpp:full-cuda \
    -m /models/Qwen3.5-27B.Q4_K_M.gguf \
    --port 8000 --host 0.0.0.0 \
    -c 65536 \
    --n-gpu-layers 99
```

---

## 💡 额外建议

1. **参数格式**：优先使用长参数 `--n-gpu-layers` 而非 `-ngl`，兼容性更好
2. **显存检查**：27B Q4_K_M + 64K 上下文 ≈ 需 24GB+ 显存，启动前执行 `nvidia-smi` 确认
3. **日志调试**：添加 `--log-file /models/server.log` 便于排查问题
4. **后台运行**：加 `-d` 参数让容器后台运行：`docker run -d ...`

> 📌 **总结**：`full-cuda` 确实包含 `llama-server` 二进制文件，但因默认 entrypoint 不同，**直接传 server 参数会报错**。生产部署建议直接用 `server-cuda` 镜像，省心且资源占用更小 [[10]]。