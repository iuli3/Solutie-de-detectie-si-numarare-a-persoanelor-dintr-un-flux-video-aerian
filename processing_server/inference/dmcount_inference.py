"""
dmcount_inference.py
Wrapper pentru DM-Count folosind arhitectura ORIGINALA din repo-ul oficial.

Pune acest fisier in acelasi folder cu inference_server.py:
    /mnt/ssd/iuliana.turcanu/

Structura folderelor:
    /mnt/ssd/iuliana.turcanu/
    ├── inference_server.py
    ├── yolo_inference.py
    ├── dmcount_inference.py          ← fisierul asta
    └── DM-Count/
        ├── models.py
        └── pretrained_models/
            ├── model_qnrf.pth        ← 83MB 
            └── model_nwpu.pth        ← 83MB 
"""

import sys
import os
import torch
import torchvision.transforms as T
import cv2
import numpy as np
import base64
from typing import Tuple, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DMCOUNT_REPO = os.path.join(BASE_DIR, 'DM-count')

import importlib.util as _ilu
_models_path = os.path.join(DMCOUNT_REPO, 'models.py')
if not os.path.exists(_models_path):
    raise ImportError(f"[DMCount]  Nu gasesc {_models_path}")
_spec = _ilu.spec_from_file_location("dmcount_models_internal", _models_path)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
dmcount_vgg19 = _mod.vgg19
print(f"[DMCount]  Arhitectura originala importata din {_models_path}")

class DMCountInference:
    """
    Wrapper de inferenta pentru DM-Count cu arhitectura VGG19 originala.

    Folosire:
        dmc = DMCountInference(checkpoint_path=".../DM-Count/pretrained_models/model_qnrf.pth")
        count, heatmap_b64 = dmc.predict(frame_bgr)
    """

    TRANSFORM = T.Compose([
        T.ToTensor(),
        T.Normalize(mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225])
    ])

    MAX_SIDE = 768

    def __init__(self, checkpoint_path: str, device: str = "cuda:1"):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")

        print(f"[DMCount] Se incarca backbone VGG19 (ImageNet weights)...")
        self.model = dmcount_vgg19()
        self.model = self.model.to(self.device)

        if os.path.exists(checkpoint_path):
            state = torch.load(checkpoint_path, map_location=self.device)
            if isinstance(state, dict) and 'model' in state:
                state = state['model']

            state = {k.replace('module.', ''): v for k, v in state.items()}
            missing, unexpected = self.model.load_state_dict(state, strict=False)
            if missing:
                print(f"[DMCount]   Chei lipsa: {missing[:3]}...")
            print(f"[DMCount]  Checkpoint incarcat: {os.path.basename(checkpoint_path)}")
        else:
            print(f"[DMCount]   Checkpoint negasit: {checkpoint_path}")

        self.model.eval()
        print(f"[DMCount]  Model gata pe {self.device}")

    @torch.no_grad()
    def predict(self, frame_bgr: np.ndarray) -> Tuple[float, Optional[str]]:
        """
        Args:
            frame_bgr: frame OpenCV BGR uint8

        Returns:
            (count_estimate, heatmap_b64)
        """
        h, w = frame_bgr.shape[:2]

        scale = self.MAX_SIDE / max(h, w)
        if scale < 1.0:
            new_w = max(32, (int(w * scale) // 32) * 32)
            new_h = max(32, (int(h * scale) // 32) * 32)
        else:
            new_w = max(32, (w // 32) * 32)
            new_h = max(32, (h // 32) * 32)

        resized = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = self.TRANSFORM(rgb).unsqueeze(0).to(self.device)

        mu, mu_normed = self.model(tensor)
        density_map = mu.squeeze().cpu().numpy()

        count_estimate = float(density_map.sum())
        heatmap_b64 = self._density_to_heatmap_b64(density_map, target_size=(w, h))

        return count_estimate, heatmap_b64

    def _density_to_heatmap_b64(self, density_map: np.ndarray, target_size: Tuple[int, int]) -> str:
        dm = density_map.copy()
        dm_max = dm.max()
        if dm_max > 0:
            dm_norm = (dm / dm_max * 255).astype(np.uint8)
        else:
            dm_norm = np.zeros_like(dm, dtype=np.uint8)

        heatmap_gray = cv2.resize(dm_norm, target_size, interpolation=cv2.INTER_CUBIC)

        heatmap_color = cv2.applyColorMap(heatmap_gray, cv2.COLORMAP_INFERNO)

        _, buffer = cv2.imencode('.jpg', heatmap_color, [cv2.IMWRITE_JPEG_QUALITY, 55])
        return base64.b64encode(buffer).decode('utf-8')

_dmcount_instances = {}

def get_dmcount(checkpoint_path: str = None, device: str = "cuda:1", model_name: str = "qnrf") -> Optional[DMCountInference]:
    """
    Returneaza instanta singleton DM-Count pentru modelul cerut.
    model_name: 'qnrf' sau 'nwpu'
    """
    global _dmcount_instances

    if model_name in _dmcount_instances:
        return _dmcount_instances[model_name]

    if checkpoint_path is None or not os.path.exists(checkpoint_path):
        candidates = {
            "qnrf": os.path.join(BASE_DIR, 'models/model_qnrf.pth'),
            "nwpu": os.path.join(BASE_DIR, 'models/model_nwpu.pth'),
        }
        checkpoint_path = candidates.get(model_name, candidates["qnrf"])
        print(f"[DMCount] Auto-detected checkpoint: {os.path.basename(checkpoint_path)}")

    try:
        instance = DMCountInference(checkpoint_path, device)
        _dmcount_instances[model_name] = instance
        print(f"[DMCount]  Model '{model_name}' incarcat si cached.")
    except Exception as e:
        print(f"[DMCount]  Initializare esuata pentru '{model_name}': {e}")
        _dmcount_instances[model_name] = None

    return _dmcount_instances[model_name]