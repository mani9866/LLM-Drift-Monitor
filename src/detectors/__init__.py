"""Drift detection strategies.

Each detector takes a conversation dict and returns a float score (0.0 to 1.0).
Signature: (conversation: dict) -> float
"""

import numpy as np
from typing import List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer


# Load model once at module level for efficiency
_model = None


def get_model():
    """Lazy-load Sentence-BERT model."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def normalize_score(score: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clip score to [0, 1] range."""
    return max(min_val, min(max_val, score))


def get_embeddings(texts: List[str]) -> np.ndarray:
    """Get embeddings for a list of texts.
    
    Returns:
        (n_texts, embedding_dim) numpy array
    """
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return np.array(embeddings, dtype=np.float32)


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine distance (1 - cosine_similarity) between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a < 1e-10 or norm_b < 1e-10:
        return 0.0
    similarity = np.dot(a, b) / (norm_a * norm_b)
    return float(1.0 - similarity)


def semantic_drift(conversation: Dict[str, Any]) -> float:
    """Semantic drift: cosine distance between each turn and conversation centroid.
    
    Computes the embedding centroid of all assistant messages, then measures
    the maximum distance from any single turn to that centroid. Higher distance
    indicates potential drift.
    
    Args:
        conversation: Dict with 'turns' list, each turn has 'role' and 'content'
    
    Returns:
        Score 0.0 (coherent) to 1.0 (drifted)
    """
    turns = conversation.get("turns", [])
    if len(turns) < 2:
        return 0.0
    
    # Extract assistant messages
    assistant_messages = [t["content"] for t in turns if t["role"] == "assistant"]
    if not assistant_messages:
        return 0.0
    
    # Get embeddings
    all_texts = [t["content"] for t in turns]
    embeddings = get_embeddings(all_texts)
    
    # Compute centroid
    centroid = embeddings.mean(axis=0)
    
    # Compute max distance from any message to centroid
    distances = [cosine_distance(embeddings[i], centroid) for i in range(len(embeddings))]
    
    # Return normalized max distance
    max_distance = max(distances) if distances else 0.0
    return normalize_score(max_distance)


def rolling_window_drift(conversation: Dict[str, Any]) -> Tuple[float, int]:
    """Rolling window drift: find the optimal drift point.
    
    Sweeps a window through turns, computing the mean embedding distance between
    [0..k] and [k+1..n]. The peak distance indicates the likely drift point.
    
    This detector actually *finds* the drift point, not just "drift happened".
    
    Args:
        conversation: Dict with 'turns' list
    
    Returns:
        (score, drift_index): score 0.0-1.0 and the estimated turn index where drift occurs
    """
    turns = conversation.get("turns", [])
    if len(turns) < 4:  # Need at least 2 on each side
        return 0.0, -1
    
    texts = [t["content"] for t in turns]
    embeddings = get_embeddings(texts)
    
    max_distance = 0.0
    best_split = -1
    
    # Sweep split points
    for split_idx in range(1, len(embeddings) - 1):
        left_embeddings = embeddings[:split_idx]
        right_embeddings = embeddings[split_idx:]
        
        left_mean = left_embeddings.mean(axis=0)
        right_mean = right_embeddings.mean(axis=0)
        
        distance = cosine_distance(left_mean, right_mean)
        
        if distance > max_distance:
            max_distance = distance
            best_split = split_idx
    
    return normalize_score(max_distance), best_split


def response_anomaly(conversation: Dict[str, Any]) -> float:
    """Response latency/length anomaly detector.
    
    Flags conversations with unusual response patterns:
    - Assistant messages that are unusually long or short
    - Unusual variance in response lengths
    
    This is a trivial but realistic observability metric.
    
    Args:
        conversation: Dict with 'turns' list
    
    Returns:
        Score 0.0-1.0
    """
    turns = conversation.get("turns", [])
    if len(turns) < 2:
        return 0.0
    
    # Get assistant message lengths
    assistant_lengths = [
        len(t["content"]) 
        for t in turns 
        if t["role"] == "assistant"
    ]
    
    if len(assistant_lengths) < 2:
        return 0.0
    
    lengths = np.array(assistant_lengths, dtype=np.float32)
    
    # Compute z-scores for each message
    mean_len = lengths.mean()
    std_len = lengths.std()
    
    if std_len < 1e-10:
        return 0.0
    
    z_scores = np.abs((lengths - mean_len) / std_len)
    
    # Flag if any response is >2 std devs from mean, or high variance
    max_z_score = z_scores.max()
    variance_score = min(1.0, std_len / (mean_len + 1e-10))
    
    # Blend: detect outliers + high variance
    anomaly_score = (max_z_score / 3.0) * 0.7 + variance_score * 0.3
    
    return normalize_score(anomaly_score)


def compute_all_scores(conversation: Dict[str, Any]) -> Dict[str, Any]:
    """Compute all three detector scores for a conversation.
    
    Returns:
        {
            "semantic_drift": float,
            "rolling_window_drift": float,
            "rolling_window_drift_index": int,
            "response_anomaly": float,
            "ensemble_score": float  # weighted average
        }
    """
    semantic = semantic_drift(conversation)
    rolling, drift_idx = rolling_window_drift(conversation)
    anomaly = response_anomaly(conversation)
    
    # Weighted ensemble: emphasize rolling_window for drift detection
    ensemble = (semantic * 0.3 + rolling * 0.5 + anomaly * 0.2)
    
    return {
        "semantic_drift": semantic,
        "rolling_window_drift": rolling,
        "rolling_window_drift_index": drift_idx,
        "response_anomaly": anomaly,
        "ensemble_score": ensemble,
    }
