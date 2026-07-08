import torch
import os

_original_load = torch.load

def _patched_load(*args, **kwargs):
    """Patch pentru torch.load care permite încărcarea modelelor custom"""
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return _original_load(*args, **kwargs)

torch.load = _patched_load

print("[PATCH] PyTorch load patched to allow custom model loading")
