"""
Research Contribution 2: Confidence-Aware Shannon Entropy Fusion & Temporal Smoothing.
Dynamically balances dual deep learning classifiers (MobileNetV2 and YOLOv11)
against facial geometry cues based on predictive certainty (entropy minimization).
"""

import math
import numpy as np
from collections import deque
from typing import Tuple, Dict, Any


def binary_shannon_entropy(p: float) -> float:
    """
    Computes binary Shannon entropy H(p) = - [p*log2(p) + (1-p)*log2(1-p)] in range [0.0, 1.0].
    Measures the uncertainty of a model prediction:
    - p = 0.50 => H(p) = 1.00 (maximum uncertainty / guessing)
    - p = 0.99 or 0.01 => H(p) ~ 0.08 (high certainty)
    """
    p = max(1e-6, min(1.0 - 1e-6, float(p)))
    return - (p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


class ConfidenceAwareFusionEngine:
    """
    Fuses MobileNetV2 and YOLOv11 predictions with dynamic confidence-weighted balancing
    and applies Exponential Moving Average (EMA) temporal smoothing.
    """
    def __init__(self, window_size: int = 5, ema_alpha: float = 0.45):
        self.window_size = window_size
        self.ema_alpha = ema_alpha
        self.recent_scores: deque = deque(maxlen=window_size)
        self.smoothed_score: float = 0.0
        
    def reset(self):
        """Resets temporal smoothing history."""
        self.recent_scores.clear()
        self.smoothed_score = 0.0

    def fuse_models(self, p_mobilenet: float, p_yolo: float) -> Tuple[float, float, float]:
        """
        Dynamically fuses predictions using inverse entropy weighting.
        Returns:
            (fused_prob, entropy_uncertainty, alpha_weight)
        """
        # Calculate uncertainty for both models
        h_m = binary_shannon_entropy(p_mobilenet)
        h_y = binary_shannon_entropy(p_yolo)
        
        # Confidence is inverse of entropy: C = 1 - H(p)
        c_m = max(0.01, 1.0 - h_m)
        c_y = max(0.01, 1.0 - h_y)
        
        # Normalized dynamic weight alpha for MobileNet
        alpha = c_m / (c_m + c_y)
        
        # Weighted probability fusion
        fused_prob = alpha * p_mobilenet + (1.0 - alpha) * p_yolo
        
        # Overall system prediction entropy
        system_entropy = float((h_m + h_y) / 2.0)
        
        # Temporal Exponential Moving Average (EMA) smoothing
        if len(self.recent_scores) == 0:
            self.smoothed_score = fused_prob
        else:
            self.smoothed_score = self.ema_alpha * fused_prob + (1.0 - self.ema_alpha) * self.smoothed_score
            
        self.recent_scores.append(fused_prob)
        return float(self.smoothed_score), system_entropy, float(alpha)
