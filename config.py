"""
Configuration and Dataclasses for AI Driver Drowsiness Detection System.
Includes landmark indices, thresholds, adaptive parameters, and state models.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

# MediaPipe Face Landmarker Landmark Indices (468/478 Mesh Model)

# Left Eye Landmark Indices (6-point EAR calculation & contour)
# P1 (Outer corner), P2 (Top 1), P3 (Top 2), P4 (Inner corner), P5 (Bottom 2), P6 (Bottom 1)
LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]

# Right Eye Landmark Indices (6-point EAR calculation & contour)
RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]

# Eyeball / Iris center landmarks
LEFT_IRIS_CENTER = 468
RIGHT_IRIS_CENTER = 473

# Mouth Landmark Indices (MAR calculation)
MOUTH_INNER_TOP = 13
MOUTH_INNER_BOTTOM = 14
MOUTH_INNER_LEFT_TOP = 81
MOUTH_INNER_LEFT_BOTTOM = 178
MOUTH_INNER_RIGHT_TOP = 311
MOUTH_INNER_RIGHT_BOTTOM = 402
MOUTH_LEFT_CORNER = 61
MOUTH_RIGHT_CORNER = 291

# Standard 3D facial landmarks for solvePnP head pose estimation
# 1: Nose tip, 152: Chin, 33: Left eye outer, 263: Right eye outer, 61: Left mouth, 291: Right mouth
POSE_LANDMARK_INDICES = [1, 152, 33, 263, 61, 291]


@dataclass
class DrowsinessConfig:
    """Configurable system thresholds and adaptive parameters."""
    # Population default thresholds (used before calibration or as fallback)
    default_ear_threshold: float = 0.23      # EAR below this indicates eye closure
    default_mar_threshold: float = 0.55      # MAR above this indicates open mouth / yawn
    
    # Active thresholds (dynamically updated by Adaptive Baseline Calibration)
    ear_threshold: float = 0.23
    mar_threshold: float = 0.55
    pitch_offset: float = 0.0                # Zeroes out dashboard phone mounting angle
    
    # Adaptive scaling ratio: EAR_thresh = EAR_alert * ear_scale_ratio
    ear_scale_ratio: float = 0.78
    
    # Duration thresholds (seconds of sustained behavior to trigger states)
    drowsy_time_thresh: float = 0.75          # Continuous eye closed duration for immediate DROWSY warning (reduced from 1.2s for prompt wake-up)
    sleep_time_thresh: float = 2.0           # Continuous eye closed duration for critical SLEEPING siren (reduced from 3.0s)
    yawn_time_thresh: float = 1.6            # Continuous mouth open duration for YAWNING state
    
    # Blink physiological validity boundaries (seconds)
    min_blink_duration: float = 0.08         # Less than 80ms is noise/saccade
    max_blink_duration: float = 0.45         # Greater than 450ms is prolonged closure/droop
    
    # Head nod threshold (degrees downward relative to calibrated mounting pitch)
    head_pitch_down_thresh: float = 18.0
    
    # Risk score fusion weights
    weight_eye_closure: float = 0.45
    weight_deep_learning: float = 0.25
    weight_yawning: float = 0.15
    weight_blink_anomaly: float = 0.10
    weight_head_posture: float = 0.05
    
    # Audio Alert Configuration
    enable_audio_alerts: bool = True
    audio_volume: float = 0.9


@dataclass
class CalibrationProfile:
    """Stores driver personalized baseline parameters."""
    driver_name: str = "Default Driver"
    is_calibrated: bool = False
    calibration_duration_sec: float = 0.0
    total_frames_sampled: int = 0
    
    # Baseline physiological values
    baseline_alert_ear: float = 0.28
    baseline_blink_duration: float = 0.22
    baseline_blink_rate_per_min: float = 14.0
    baseline_resting_mar: float = 0.05
    mounting_pitch_offset: float = 0.0
    
    # Computed dynamic thresholds
    personalized_ear_threshold: float = 0.218
    personalized_mar_threshold: float = 0.55
    
    # Calibration quality assessment
    quality_score: float = 1.0               # 0.0 - 1.0 (based on lighting and landmark stability)
    flagged_fatigued: bool = False           # True if driver was already tired during calibration


@dataclass
class DetectionPayload:
    """Frame-by-frame telemetry and decision payload streamed to client."""
    timestamp: float
    face_detected: bool = False
    
    # Landmark metrics
    left_ear: float = 0.0
    right_ear: float = 0.0
    avg_ear: float = 0.0
    eye_closed: bool = False
    eye_closed_duration: float = 0.0
    
    # Blink statistics
    total_blinks: int = 0
    blink_rate_per_min: float = 0.0
    avg_blink_duration: float = 0.0
    perclos: float = 0.0                     # Percentage of eye closure over 60s
    rapid_blinking: bool = False             # 3+ blinks within 2.5s window
    
    # Yawn & Mouth
    mar: float = 0.0
    yawning: bool = False
    yawn_duration: float = 0.0
    total_yawns: int = 0
    
    # 3D Head Pose
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    head_nodding: bool = False
    
    # Deep Learning Dual-Model Predictions
    mobilenet_drowsy_prob: float = 0.0
    yolo_drowsy_prob: float = 0.0
    fused_dl_score: float = 0.0
    dl_entropy_uncertainty: float = 0.0       # Shannon entropy (0 = certain, 1 = uncertain)
    
    # Adaptive Baseline status
    is_personalized: bool = False
    active_ear_threshold: float = 0.23
    
    # Decision States & Alarms
    drowsiness_score: float = 0.0             # 0 - 100% composite score
    risk_level: str = "ALERT"                 # ALERT (Green), WARNING (Yellow), HIGH DROWSINESS (Red)
    state_label: str = "AWAKE"                # AWAKE, DROWSY, SLEEPING, YAWNING, NO FACE
    trigger_warning_alarm: bool = False
    trigger_critical_alarm: bool = False
    
    # Frame performance
    fps: float = 0.0
    latency_ms: float = 0.0
