# 测试CUDA是否正常工作


# # 在 Python 中测试
# python -c "import torch; torch.cuda.init(); print(torch.cuda.is_available())"

import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA device: {torch.cuda.get_device_name(0)}")
    print(f"CUDA capability: {torch.cuda.get_device_capability(0)}")
    # 简单测试
    x = torch.randn(3, 3).cuda()
    print(f"Tensor on GPU: {x}")
else:
    print("CUDA is not available")
