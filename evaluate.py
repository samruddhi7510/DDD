"""
Model and System Evaluation Engine.
Evaluates MobileNetV2, YOLOv11, and the Fused Hybrid Pipeline
on the held-out test set (2,091 images: 1,118 Drowsy, 973 Non-Drowsy).
Computes Accuracy, Precision, Recall, F1-Score, and Confusion Matrix.
"""

import os
import glob
import json
import time
import cv2
import numpy as np
from typing import Dict, Any, List

from models import DualModelClassifier
from fusion import ConfidenceAwareFusionEngine


def evaluate_test_set(
    dataset_dir: str = "D:\\safedrive_drowsiness_detection-master\\splitted_dataset",
    max_samples: int = 0  # 0 means evaluate ALL 2,091 images on the held-out test split
) -> Dict[str, Any]:
    """
    Evaluates the models on the held-out test split without temporal state leakage.
    """
    test_dir = os.path.join(dataset_dir, "test")
    if not os.path.exists(test_dir):
        raise FileNotFoundError(f"Test directory not found at {test_dir}")
        
    drowsy_images = glob.glob(os.path.join(test_dir, "Drowsy", "*.*"))
    non_drowsy_images = glob.glob(os.path.join(test_dir, "Non Drowsy", "*.*"))
    
    print(f"Found {len(drowsy_images)} Drowsy and {len(non_drowsy_images)} Non-Drowsy test images.")
    
    if max_samples > 0:
        drowsy_images = drowsy_images[:max_samples // 2]
        non_drowsy_images = non_drowsy_images[:max_samples // 2]
        
    total_eval = len(drowsy_images) + len(non_drowsy_images)
    print(f"Evaluating {total_eval} test images across models...")
    
    classifier = DualModelClassifier()
    fusion_engine = ConfidenceAwareFusionEngine()
    
    # Ground truth: 1 for Drowsy, 0 for Non-Drowsy
    y_true: List[int] = []
    y_pred_mobilenet: List[int] = []
    y_pred_yolo: List[int] = []
    y_pred_hybrid: List[int] = []
    
    start_time = time.time()
    
    # Process Drowsy samples (label = 1)
    for p in drowsy_images:
        img = cv2.imread(p)
        if img is None:
            continue
        p_m, p_y = classifier.predict(img)
        # Reset fusion history between independent static images to prevent state leakage
        fusion_engine.reset()
        fused_score, _, _ = fusion_engine.fuse_models(p_m, p_y)
        
        y_true.append(1)
        y_pred_mobilenet.append(1 if p_m >= 0.5 else 0)
        y_pred_yolo.append(1 if p_y >= 0.5 else 0)
        y_pred_hybrid.append(1 if fused_score >= 0.5 else 0)
        
    # Process Non-Drowsy samples (label = 0)
    for p in non_drowsy_images:
        img = cv2.imread(p)
        if img is None:
            continue
        p_m, p_y = classifier.predict(img)
        # Reset fusion history between independent static images to prevent state leakage
        fusion_engine.reset()
        fused_score, _, _ = fusion_engine.fuse_models(p_m, p_y)
        
        y_true.append(0)
        y_pred_mobilenet.append(1 if p_m >= 0.5 else 0)
        y_pred_yolo.append(1 if p_y >= 0.5 else 0)
        y_pred_hybrid.append(1 if fused_score >= 0.5 else 0)
        
    elapsed = time.time() - start_time
    avg_latency_ms = (elapsed / max(1, len(y_true))) * 1000.0
    
    def compute_metrics(y_t, y_p):
        tp = sum(1 for yt, yp in zip(y_t, y_p) if yt == 1 and yp == 1)
        tn = sum(1 for yt, yp in zip(y_t, y_p) if yt == 0 and yp == 0)
        fp = sum(1 for yt, yp in zip(y_t, y_p) if yt == 0 and yp == 1)
        fn = sum(1 for yt, yp in zip(y_t, y_p) if yt == 1 and yp == 0)
        
        total = len(y_t)
        accuracy = (tp + tn) / max(1, total)
        precision = tp / max(1, (tp + fp))
        recall = tp / max(1, (tp + fn))
        f1 = (2 * precision * recall) / max(1e-6, (precision + recall))
        
        return {
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "Accuracy": round(accuracy * 100, 2),
            "Precision": round(precision * 100, 2),
            "Recall": round(recall * 100, 2),
            "F1_Score": round(f1 * 100, 2)
        }
        
    metrics_m = compute_metrics(y_true, y_pred_mobilenet)
    metrics_y = compute_metrics(y_true, y_pred_yolo)
    metrics_h = compute_metrics(y_true, y_pred_hybrid)
    
    results = {
        "evaluation_samples": len(y_true),
        "avg_inference_latency_ms": round(avg_latency_ms, 2),
        "fps_capacity": round(1000.0 / max(1.0, avg_latency_ms), 1),
        "MobileNetV2": metrics_m,
        "YOLOv11": metrics_y,
        "Hybrid_Entropy_Fusion": metrics_h
    }
    
    os.makedirs("logs", exist_ok=True)
    with open("logs/evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 65)
    print("                    EVALUATION BENCHMARK RESULTS")
    print("=" * 65)
    print(f"Total Test Samples Evaluated: {results['evaluation_samples']}")
    print(f"Average Inference Latency:   {results['avg_inference_latency_ms']} ms ({results['fps_capacity']} FPS)")
    print("-" * 65)
    print(f"MobileNetV2:  Acc: {metrics_m['Accuracy']}% | Prec: {metrics_m['Precision']}% | Rec: {metrics_m['Recall']}% | F1: {metrics_m['F1_Score']}%")
    print(f"YOLOv11:      Acc: {metrics_y['Accuracy']}% | Prec: {metrics_y['Precision']}% | Rec: {metrics_y['Recall']}% | F1: {metrics_y['F1_Score']}%")
    print(f"Hybrid Model: Acc: {metrics_h['Accuracy']}% | Prec: {metrics_h['Precision']}% | Rec: {metrics_h['Recall']}% | F1: {metrics_h['F1_Score']}%")
    print("=" * 65)
    return results


if __name__ == "__main__":
    evaluate_test_set()
