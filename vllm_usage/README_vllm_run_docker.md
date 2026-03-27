# vllm推理加速，容器部署
使用容器启动vllm服务，并且vllm服务跟随容器自启动，容器启动那么vllm服务也随之启动，避免手动重启。

```bash
docker run --gpus all --name vllm_qwen35_serve \
    -v /home/hcq/LLM:/home/hcq/LLM \
    -e CUDA_VISIBLE_DEVICES=0 \
    --net=host \
    --restart=always \
    -d \
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
```
这条命令用于使用 Docker 容器部署一个基于 **vLLM** 推理引擎的 **Qwen3.5-0.8B** 大模型服务，并开启 OpenAI 兼容的 API 接口。

下面是对该命令的**逐行详细解析**，包括参数含义、作用以及潜在的注意事项。

---

### 1. 基础命令与容器命名
```bash
docker run --gpus all --name vllm_qwen35_serve \
```
*   `docker run`: 创建并启动一个新的 Docker 容器。
*   `--gpus all`: **GPU 支持**。请求使用宿主机上所有可用的 NVIDIA GPU。需要宿主机安装 `nvidia-container-toolkit`。
*   `--name vllm_qwen35_serve`: **容器名称**。给容器起个别名，方便后续使用 `docker stop vllm_qwen35_serve` 或 `docker logs` 进行管理。
*   `\`: 行继续符，表示命令未结束，下一行是同一命令的一部分。

### 2. 数据卷挂载 (Volume)
```bash
    -v /home/hcq/LLM:/home/hcq/LLM \
```
*   `-v`: **挂载卷**。
*   `/home/hcq/LLM` (左侧): 宿主机的绝对路径，存放模型文件的地方。
*   `/home/hcq/LLM` (右侧): 容器内部的路径。
*   **作用**: 让容器内部能够直接读取宿主机上的模型权重文件，无需将模型拷贝进镜像，节省空间且便于更新模型。

### 3. 环境变量 (Environment)
```bash
    -e CUDA_VISIBLE_DEVICES=0 \
```
*   `-e`: 设置容器内的环境变量。
*   `CUDA_VISIBLE_DEVICES=0`: **限制可见显卡**。虽然上面用了 `--gpus all`，但这个环境变量告诉程序（vLLM/Python）**只使用编号为 0 的显卡**。
*   **注意**: 这里存在逻辑上的“冗余”或“覆盖”。`--gpus all` 允许容器访问所有卡，但 `CUDA_VISIBLE_DEVICES=0` 限制程序只用卡 0。如果你只想用一张卡，通常建议直接写 `--gpus '"device=0"'`。

### 4. 网络配置 (Network)
```bash
    --net=host \
```
*   `--net=host`: **主机网络模式**。容器不使用独立的 Network Namespace，直接共享宿主机的网络栈。
*   **作用**: 性能更好，无需通过 `-p` 映射端口（但后面的 `--port` 是 vLLM 软件层面的监听端口）。
*   **副作用**: 容器内的端口直接占用宿主机端口，需注意端口冲突。

### 5. 重启策略 (Restart Policy)
```bash
    --restart=always \
    -d \
```
*   **作用**: 如果容器停止（非手动停止）或 Docker 守护进程重启，容器会自动尝试重启。适合生产环境部署，保证服务高可用。
*   **作用**: -d 表示后台运行。

### 6. 入口点覆盖 (Entrypoint)
```bash
    --entrypoint /usr/bin/python3 \
```
*   `--entrypoint`: **覆盖镜像默认的启动命令**。
*   `/usr/bin/python3`: 指定容器启动后直接运行 Python 3 解释器。
*   **原因**: 原镜像可能默认执行某个 shell 脚本，这里为了更灵活地控制 vLLM 的启动参数，直接调用 Python 来运行 vLLM 的模块。

### 7. 镜像名称 (Image)
```bash
    docker.1ms.run/vllm/vllm-openai \
```
*   **镜像地址**: 这是 vLLM 的官方或定制镜像。
*   `docker.1ms.run`: 非 Docker Hub 默认，国内镜像加速
*   `vllm/vllm-openai`: 镜像名，表明该镜像预装了 vLLM 且专注于 OpenAI 接口兼容。

### 8. Python 模块与 vLLM 参数
**从这一行开始，参数不再是 `docker` 的参数，而是传递给 `/usr/bin/python3` 的参数。**

```bash
    -m vllm.entrypoints.openai.api_server \
```
*   `-m`: Python 参数，表示运行一个模块。
*   `vllm.entrypoints.openai.api_server`: 启动 vLLM 的 **OpenAI 兼容 API 服务** 入口。

```bash
        --model /home/hcq/LLM/Qwen3.5-0.8B/Qwen/Qwen3.5-0.8B \
```
*   `--model`: vLLM 参数，指定模型路径。
*   **路径**: 必须与上面 `-v` 挂载的容器内路径一致。

```bash
        --served-model-name Qwen \
```
*   **作用**: 客户端（如 API 调用者）在请求中指定的模型名称。例如 `model="Qwen"`。

```bash
        --max_model_len 40960 \
```
*   **作用**: 设置模型支持的**最大上下文长度** (Context Length)。
*   **注意**: 0.8B 的小模型通常支持 32k 或 128k，这里设置为 40960 (约 40k)。需确保模型本身支持此长度，否则会报错或截断。

```bash
        --max-num-seqs 16 \
```
*   **作用**: 最大并发序列数。限制同时处理的请求数量，用于控制显存占用和延迟。

```bash
        --api-key MYKEY \
```
*   **作用**: 设置 API 访问密钥。客户端请求时需在 Header 中携带 `Authorization: Bearer MYKEY`。

```bash
        --gpu-memory-utilization 0.7 \
```
*   **作用**: **显存利用率**。预留 30% 的显存给系统或其他进程，防止 OOM (Out Of Memory)。vLLM 会用这 70% 来加载 KV Cache 和模型权重。

```bash
        --host 0.0.0.0 \
```
*   **作用**: 监听地址。`0.0.0.0` 表示允许外部网络访问（配合 `--net=host` 直接暴露给宿主机所有网卡）。

```bash
        --port 8888 \
```
*   **作用**: 服务监听端口。访问地址为 `http://<宿主机 IP>:8888`。

```bash
        --enable-auto-tool-choice \
```
*   **作用**: 启用**自动工具选择**。这是 Function Calling (函数调用) 功能的一部分，允许模型自动判断是否调用工具。

```bash
        --tool-call-parser hermes \
```
*   **作用**: 指定工具调用的解析器格式。`hermes` 是一种特定的 Prompt 格式解析器，通常用于适配特定微调过的模型（如 Hermes 适配了该格式的 Qwen系列的模型）。

```bash
        --trust-remote-code
```
*   **作用**: **信任远程代码**。允许加载模型时执行模型仓库中的自定义 Python 代码（`modeling_*.py` 等）。
*   **必要性**: 许多新模型（包括 Qwen 系列）需要此参数才能正确加载架构代码，否则加载会失败。

---
