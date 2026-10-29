"""依目前環境選擇可用的推論裝置。"""
from dataclasses import dataclass
import os


def default_device():
    value = os.environ.get('FINANCIAL_RAG_DEVICE', 'auto').strip().lower()
    if value not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('FINANCIAL_RAG_DEVICE 必須是 auto、cpu 或 cuda')
    return value


@dataclass(frozen=True)
class DeviceSelection:
    requested: str
    actual: str
    reason: str


def select_torch_device(requested: str = 'auto') -> DeviceSelection:
    """回傳 torch 可用裝置；auto 僅在 CUDA 可用時選 GPU。"""
    if requested not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('裝置必須是 auto、cpu 或 cuda')
    if requested == 'cpu':
        return DeviceSelection(requested, 'cpu', '設定指定 CPU')
    try:
        import torch
        available = bool(torch.cuda.is_available())
    except Exception as exc:
        if requested == 'cuda':
            raise RuntimeError(f'指定 CUDA，但無法載入 PyTorch CUDA 支援：{exc}') from exc
        return DeviceSelection(requested, 'cpu', f'GPU 檢查失敗，退回 CPU：{type(exc).__name__}')
    if available:
        return DeviceSelection(requested, 'cuda', 'PyTorch CUDA 可用')
    if requested == 'cuda':
        raise RuntimeError('指定 CUDA，但目前 PyTorch／驅動未提供可用 CUDA GPU')
    return DeviceSelection(requested, 'cpu', '未偵測到可用 CUDA，使用 CPU')
