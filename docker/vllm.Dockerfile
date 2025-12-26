FROM vllm/vllm-openai:latest

# Set working directory
WORKDIR /app

# Environment variables for vLLM configuration
ENV MODEL_NAME=${MODEL_NAME:-"Qwen/Qwen2.5-VL-7B-Instruct"}
ENV MAX_MODEL_LEN=${MAX_MODEL_LEN:-4096}
ENV GPU_MEMORY_UTIL=${GPU_MEMORY_UTIL:-0.92}
ENV HOST=${HOST:-"0.0.0.0"}
ENV PORT=${PORT:-8000}

# Create cache directory
RUN mkdir -p /root/.cache/huggingface

# Expose the API port
EXPOSE 8000

# Start vLLM server with OpenAI-compatible API
CMD ["sh", "-c", "vllm serve ${MODEL_NAME} --host ${HOST} --port ${PORT} --max-model-len ${MAX_MODEL_LEN} --gpu-memory-utilization ${GPU_MEMORY_UTIL} --dtype float16 --quantization fp8 --max-num-seqs 1 --enable-chunked-prefill"]
