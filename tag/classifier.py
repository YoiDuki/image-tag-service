import os
import platform
import csv
import threading
import numpy as np
from PIL import Image
from huggingface_hub import hf_hub_download

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
_CLIP_MODEL_PATH = os.path.join(_MODELS_DIR, "open_clip_model.safetensors")

_WD_SESSION = None
_WD_TAGS_LIST = None
_WD_TAG_CATEGORIES = None
_WD_LOCK = threading.Lock()
_CLIP_MODEL = None
_CLIP_TOKENIZER = None
_CLIP_PREPROCESS = None
_CLIP_LOCK = threading.Lock()


def _detect_device():
    if os.environ.get("CLASSIFIER_DEVICE"):
        return os.environ["CLASSIFIER_DEVICE"]
    if platform.processor() == "arm":
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _get_ort():
    import importlib
    mod = importlib.import_module("onnxruntime")
    if "CUDAExecutionProvider" in mod.get_available_providers():
        print("[classifier] ONNX using CUDA")
    else:
        print("[classifier] ONNX using CPU")
    return mod


def _download_wd_model():
    repo = "SmilingWolf/wd-swinv2-tagger-v3"
    os.makedirs(_MODELS_DIR, exist_ok=True)
    model_path = hf_hub_download(
        repo_id=repo, filename="model.onnx", cache_dir=_MODELS_DIR
    )
    tags_path = hf_hub_download(
        repo_id=repo, filename="selected_tags.csv", cache_dir=_MODELS_DIR
    )
    return model_path, tags_path


def _load_wd_tagger():
    global _WD_SESSION, _WD_TAGS_LIST, _WD_TAG_CATEGORIES
    if _WD_SESSION is not None:
        return
    with _WD_LOCK:
        if _WD_SESSION is not None:
            return
        print("[classifier] Loading WD tagger model (anime tagging)...")
        model_path, tags_path = _download_wd_model()
        ort = _get_ort()
        import torch
        torch_lib = os.path.join(os.path.dirname(torch.__file__), "lib")
        if torch_lib not in os.environ.get("PATH", ""):
            os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = 2
        sess_opts.inter_op_num_threads = 1
        _WD_SESSION = ort.InferenceSession(model_path, sess_opts, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
        _WD_TAGS_LIST = []
        _WD_TAG_CATEGORIES = {}
        with open(tags_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["name"]
                cat = int(row["category"])
                _WD_TAGS_LIST.append(name)
                _WD_TAG_CATEGORIES[len(_WD_TAGS_LIST) - 1] = cat
        print(f"[classifier] WD tagger loaded: {len(_WD_TAGS_LIST)} tags")


def _preprocess_wd(image_path, target_size=448):
    img = Image.open(image_path).convert("RGB")
    img = img.resize((target_size, target_size), Image.LANCZOS)
    arr = np.array(img).astype(np.float32)
    # The WD swinv2 ONNX export bakes normalization in; feed RAW [0,255] pixels.
    arr = np.expand_dims(arr, axis=0).astype(np.float32)
    return arr


def _run_wd_tagger(image_path):
    _load_wd_tagger()
    input_tensor = _preprocess_wd(image_path)
    input_name = _WD_SESSION.get_inputs()[0].name
    # Model output is already probabilities (sigmoid baked in); use directly.
    probs = _WD_SESSION.run(None, {input_name: input_tensor})[0][0]
    results = {
        "rating": {},
        "general": [],
        "artist": [],
        "character": [],
        "special": [],
    }
    for i, prob in enumerate(probs):
        label = _WD_TAGS_LIST[i] if i < len(_WD_TAGS_LIST) else f"tag_{i}"
        cat = _WD_TAG_CATEGORIES.get(i, 0)
        prob = float(prob)
        if cat == 9:
            results["rating"][label] = prob
        elif cat == 0:
            results["general"].append({"label": label, "confidence": round(prob, 4)})
        elif cat == 4:
            results["character"].append({"label": label, "confidence": round(prob, 4)})
    results["general"].sort(key=lambda x: x["confidence"], reverse=True)
    results["artist"].sort(key=lambda x: x["confidence"], reverse=True)
    results["character"].sort(key=lambda x: x["confidence"], reverse=True)
    return results


def _nsfw_from_wd(wd_result, threshold=0.4):
    rating = wd_result.get("rating", {})
    rating_explicit = rating.get("explicit", 0)
    rating_questionable = rating.get("questionable", 0)
    if rating_explicit > threshold or rating_questionable > threshold:
        return True
    return False


def _load_clip():
    global _CLIP_MODEL, _CLIP_TOKENIZER, _CLIP_PREPROCESS
    if _CLIP_MODEL is not None:
        return
    with _CLIP_LOCK:
        if _CLIP_MODEL is not None:
            return
        print("[classifier] Loading OpenCLIP model ...")
        import torch as _torch
        _torch.set_num_threads(2)
        import open_clip
        device = _detect_device()
        _CLIP_MODEL, _, _CLIP_PREPROCESS = open_clip.create_model_and_transforms(
            "ViT-H-14", pretrained=_CLIP_MODEL_PATH
        )
        _CLIP_TOKENIZER = open_clip.get_tokenizer("ViT-H-14")
        if device != "cpu":
            try:
                import torch
                _CLIP_MODEL = _CLIP_MODEL.to(device)
            except Exception:
                pass
        print(f"[classifier] OpenCLIP loaded on {device}")


_PROMPTS = [
    # Media type (0-3)
    "a photograph taken by a camera, real world scene, realistic lighting and texture",
    "a digital illustration, painting, drawing, artwork, creative illustration",
    "a manga panel, comic page, sequential art with speech bubbles, comic strip, storyboard",
    "a tutorial, educational guide, step by step instruction, software screenshot, drawing tutorial, workflow demonstration",
    # Photo style (4-9)
    "portrait photography, a person, people, human face, model shoot",
    "street photography, urban cityscape, buildings, street scene, candid",
    "landscape photography, nature scenery, mountain ocean forest, wide view",
    "still life photography, object, food, product on table, arranged composition",
    "animal photography, mammal, bird, wildlife, pet, animal portrait",
    "plant photography, botanical, garden, leaves, flowers, nature close up",
    # Illustration style (10-13)
    "anime style, Japanese animation, vibrant anime artwork, cel shaded",
    "realistic digital painting, oil painting, semi realistic, detailed rendering",
    "rakugaki, doodle, rough sketch, casual drawing, quick sketch, line art",
    "scenery illustration, background art, environment design, landscape painting",
    # Manga style (14-15)
    "colored manga, color comic page, colored comic panel, colorful manga art",
    "monochrome manga, black and white comic, greyscale manga, ink drawing",
]

_CLIP_TAG_PROMPTS = {}
_CLIP_TAG_EMBEDDINGS = None


def _is_monochrome(image_path, threshold=0.05):
    img = Image.open(image_path).convert("HSV")
    arr = np.array(img).astype(np.float32)
    sat = arr[:, :, 1] / 255.0
    return sat.mean() < threshold


def _load_clip_tag_embeddings():
    global _CLIP_TAG_EMBEDDINGS, _CLIP_TAG_PROMPTS
    if _CLIP_TAG_EMBEDDINGS is not None:
        return
    from .database import get_tag_meta_prompts
    prompts = get_tag_meta_prompts()
    if not prompts:
        _CLIP_TAG_PROMPTS = {}
        _CLIP_TAG_EMBEDDINGS = []
        return
    _CLIP_TAG_PROMPTS = prompts
    _load_clip()
    import torch
    device = _detect_device()
    texts = _CLIP_TOKENIZER(list(prompts.values()))
    if device != "cpu":
        texts = texts.to(device)
    with torch.no_grad():
        features = _CLIP_MODEL.encode_text(texts)
        features /= features.norm(dim=-1, keepdim=True)
    _CLIP_TAG_EMBEDDINGS = features


def _classify_media(image_path):
    _load_clip()
    _load_clip_tag_embeddings()
    import torch
    device = _detect_device()

    img = Image.open(image_path).convert("RGB")
    img_tensor = _CLIP_PREPROCESS(img).unsqueeze(0)
    if device != "cpu":
        img_tensor = img_tensor.to(device)
    texts = _CLIP_TOKENIZER(_PROMPTS)
    if device != "cpu":
        texts = texts.to(device)

    with torch.no_grad():
        image_features = _CLIP_MODEL.encode_image(img_tensor)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        text_features = _CLIP_MODEL.encode_text(texts)
        text_features /= text_features.norm(dim=-1, keepdim=True)
        sim = (100.0 * image_features @ text_features.T).softmax(dim=-1)

        if isinstance(_CLIP_TAG_EMBEDDINGS, list) and len(_CLIP_TAG_EMBEDDINGS) == 0:
            tag_scores = []
        else:
            tag_sim = image_features @ _CLIP_TAG_EMBEDDINGS.T
            tag_scores = tag_sim[0].cpu().tolist()

    scores = sim[0].cpu().tolist()

    # Media type (indices 0-3)
    media_scores = [scores[0], scores[1], scores[2], scores[3]]
    media_labels = ["photograph", "illustration", "manga", "tutorial"]
    media_type = media_labels[media_scores.index(max(media_scores))]

    style = None
    if media_type == "photograph":
        style_scores = scores[4:10]
        style_labels = ["portrait", "street", "landscape", "still_life", "animal", "plants"]
        style = style_labels[style_scores.index(max(style_scores))]
    elif media_type == "illustration":
        style_scores = scores[10:14]
        style_labels = ["anime", "realistic", "rakugaki", "scenery"]
        style = style_labels[style_scores.index(max(style_scores))]
    elif media_type == "manga":
        if _is_monochrome(image_path):
            style = "monochrome"
        else:
            style_scores = scores[14:16]
            style = "colored" if style_scores[0] >= style_scores[1] else "monochrome"
    # tutorial: no style

    clip_tags = {}
    for i, name in enumerate(_CLIP_TAG_PROMPTS):
        if i >= len(tag_scores):
            break
        score = tag_scores[i]
        if score > 0.25:
            clip_tags[name] = round(score, 4)

    return {
        "media_type": media_type,
        "style": style,
        "clip_tags": clip_tags,
        "scores": scores,
    }


def unload_model():
    global _WD_SESSION, _CLIP_MODEL, _CLIP_TOKENIZER, _CLIP_PREPROCESS
    _WD_SESSION = None
    _CLIP_MODEL = None
    _CLIP_TOKENIZER = None
    _CLIP_PREPROCESS = None
    import gc
    gc.collect()
    try:
        import torch
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass


def extract_palette(image_path, n_colors=8, max_iter=20, resize_to=128):
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    if max(w, h) > resize_to:
        ratio = resize_to / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    pixels = np.array(img).reshape(-1, 3).astype(np.float32)
    rng = np.random.default_rng(0)
    idx = rng.choice(len(pixels), n_colors, replace=False)
    centroids = pixels[idx]
    for _ in range(max_iter):
        distances = np.linalg.norm(pixels[:, None] - centroids[None, :], axis=2)
        labels = np.argmin(distances, axis=1)
        new_centroids = []
        for i in range(n_colors):
            mask = labels == i
            if mask.any():
                new_centroids.append(pixels[mask].mean(axis=0))
            else:
                new_centroids.append(centroids[i])
        new_centroids = np.array(new_centroids)
        if np.allclose(centroids, new_centroids, atol=1.0):
            break
        centroids = new_centroids
    unique, counts = np.unique(labels, return_counts=True)
    count_map = dict(zip(unique, counts))
    total = len(pixels)
    palette = []
    for i in range(n_colors):
        count = count_map.get(i, 0)
        percentage = round(count / total, 4)
        r, g, b = (
            int(round(centroids[i][0])),
            int(round(centroids[i][1])),
            int(round(centroids[i][2])),
        )
        palette.append(
            {
                "rgb": [r, g, b],
                "hex": f"#{r:02x}{g:02x}{b:02x}",
                "percentage": percentage,
            }
        )
    palette.sort(key=lambda x: x["percentage"], reverse=True)
    return palette


def classify_image(image_path, existing_palette=None):
    wd_result = _run_wd_tagger(image_path)
    media = _classify_media(image_path)
    if existing_palette is None:
        palette = extract_palette(image_path)
    else:
        palette = existing_palette
    nsfw = _nsfw_from_wd(wd_result, threshold=0.35)

    artist_threshold = 0.5
    character_threshold = 0.5
    general_threshold = 0.7
    exclude_tags = {
        "1girl", "1boy", "1other", "solo", "no_humans",
        "multiple_girls", "multiple_boys", "group",
        "2girls", "3girls", "4girls", "5girls", "6+girls",
        "2boys", "3boys", "4boys", "5boys", "6+boys",
        "blue_skin",
    }

    artists = [
        e for e in wd_result.get("artist", []) if e["confidence"] >= artist_threshold
    ]
    characters = [
        e
        for e in wd_result.get("character", [])
        if e["confidence"] >= character_threshold
    ]
    tags = [
        e["label"]
        for e in wd_result.get("general", [])
        if e["confidence"] >= general_threshold and e["label"] not in exclude_tags
    ]

    seen = set(tags)
    for ct in media.get("clip_tags", {}):
        if ct not in seen:
            tags.append(ct)
            seen.add(ct)

    return {
        "tags": tags,
        "media_type": media["media_type"],
        "style": media["style"],
        "nsfw": nsfw,
        "palette": palette,
        "artists": artists,
        "characters": characters,
        "clip_scores": media["scores"],
        "clip_tags": media["clip_tags"],
    }
