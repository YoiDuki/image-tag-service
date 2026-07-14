# NVIDIA GPU 迁移说明

## 1. 安装 CUDA + cuDNN

确保系统已装：
- **CUDA Toolkit 11.8+**（推荐 12.x）
- **cuDNN** 对应版本
- **Python 3.10+**

验证：
```powershell
nvidia-smi
```

## 2. 创建环境 + 安装依赖

```powershell
# 用 uv（推荐）
uv init
uv add "torch>=2.0" --index-url https://download.pytorch.org/whl/cu121
uv add flask pillow numpy huggingface-hub open-clip-torch onnxruntime-gpu

# 或用 pip
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install flask pillow numpy huggingface-hub open-clip-torch onnxruntime-gpu
```

## 3. 修改 `classifier.py`（自动生效，无需手动改）

现有代码已支持 CUDA 自动检测：

```python
# _detect_device() 会自动返回 "cuda"
# _get_ort() 会自动加载 onnxruntime-gpu
```

| 组件 | 自动选择的 provider |
|------|-------------------|
| WD Tagger | `CUDAExecutionProvider` |
| OpenCLIP | `device="cuda"` |

如果默认 CUDA 显存不足，可强制切回 CPU：

```powershell
set CLASSIFIER_DEVICE=cpu
python app.py
```

## 4. 启动

```powershell
# uv
uv run python app.py

# pip
python app.py
```

## 5. 性能对比参考

| 图片数 (448×448) | Mac MPS | NVIDIA RTX 4090 |
|-----------------|---------|----------------|
| WD Tagger 推理 | ~80 img/s | ~400 img/s |
| OpenCLIP ViT-H-14 | ~3 img/s | ~12 img/s |
| K-means 8色 | ~15 img/s | ~15 img/s |
