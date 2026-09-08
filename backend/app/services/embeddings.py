"""
Visual embedding generation for the provenance layer.

Model choice: a single CLIP ViT-B/32 (openai/clip-vit-base-patch32).
Rationale, per the "smallest complementary set, don't blindly stack
models" principle:

- ~151M params, 512-dim output -- comfortably fits an RTX 3050's 6GB VRAM
  (also already a project dependency: `transformers`+`torch` are in
  requirements.txt for the AI detector, so this adds no new heavy deps).
- Runs fine on CPU too (slower, but this machine has one either way as a
  fallback), which matters because embedding generation must never be a
  hard GPU requirement.
- Strong, well-understood baseline for image-to-image retrieval.

A second model (DINOv2, SigLIP) is deliberately NOT added yet. Per the
spec: measure with the benchmark harness first (Phase 13) whether CLIP
alone misses too many transformed variants (heavy crops/rotations/memes)
before paying the extra VRAM/latency cost of a second embedding per asset.
If/when that's justified, add it as `SECONDARY_MODEL_ID` here and a second
`Embedding` row per asset -- the schema already supports multiple
embeddings per asset (one row per (asset_id, model, model_version)).

Model name/version is stored with every embedding (see
models/provenance.py Embedding.model / model_version) so a future
re-embedding pass with a different model never gets confused with old
vectors.
"""
import logging
import threading
from pathlib import Path
from typing import List

logger = logging.getLogger("embeddings")

MODEL_ID = "openai/clip-vit-base-patch32"
MODEL_NAME = "clip"
EMBEDDING_DIM = 512

_lock = threading.Lock()
_model = None
_processor = None
_device = None


def _load_model():
    """Lazy-loads CLIP once per process. Not done at import time so that
    code paths that never need embeddings (e.g. running just the existing
    forensics/AI-detection pipeline) don't pay the load cost or require
    torch/transformers to be installed."""
    global _model, _processor, _device
    if _model is not None:
        return
    with _lock:
        if _model is not None:  # re-check inside the lock
            return
        import torch
        from transformers import CLIPModel, CLIPProcessor

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading %s on %s", MODEL_ID, _device)
        _model = CLIPModel.from_pretrained(MODEL_ID).to(_device).eval()
        _processor = CLIPProcessor.from_pretrained(MODEL_ID)


def embed_image(path: Path) -> List[float]:
    """Returns a 512-dim L2-normalized embedding for the image at `path`.

    Normalized so that cosine similarity == dot product, which lets
    pgvector's `<#>` (inner product) index operator be used directly for
    fast approximate nearest-neighbor search instead of the more expensive
    `<=>` cosine operator.
    """
    _load_model()
    import torch
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        inputs = _processor(images=im, return_tensors="pt").to(_device)
        with torch.no_grad():
            features = _model.get_image_features(**inputs)
        features = features / features.norm(p=2, dim=-1, keepdim=True)
        return features.squeeze(0).cpu().tolist()


def embed_images_batch(paths: List[Path], batch_size: int = 16) -> List[List[float]]:
    """Batched version for discovery/backfill passes over many candidate
    images at once -- meaningfully faster than one-at-a-time on GPU."""
    _load_model()
    import torch
    from PIL import Image

    all_vectors: List[List[float]] = []
    for i in range(0, len(paths), batch_size):
        batch_paths = paths[i:i + batch_size]
        images = []
        for p in batch_paths:
            with Image.open(p) as im:
                images.append(im.convert("RGB").copy())
        inputs = _processor(images=images, return_tensors="pt").to(_device)
        with torch.no_grad():
            features = _model.get_image_features(**inputs)
        features = features / features.norm(p=2, dim=-1, keepdim=True)
        all_vectors.extend(features.cpu().tolist())
    return all_vectors
