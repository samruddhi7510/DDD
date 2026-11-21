"""
Mathematical geometry module for Eye Aspect Ratio (EAR),
Mouth Aspect Ratio (MAR), and 3D Head Pose Estimation via OpenCV solvePnP.
"""

import numpy as np
import cv2
from typing import Tuple, List, Optional

from config import (
    LEFT_EYE_INDICES,
    RIGHT_EYE_INDICES,
    MOUTH_INNER_TOP,
    MOUTH_INNER_BOTTOM,
    MOUTH_INNER_LEFT_TOP,
    MOUTH_INNER_LEFT_BOTTOM,
    MOUTH_INNER_RIGHT_TOP,
    MOUTH_INNER_RIGHT_BOTTOM,
    MOUTH_LEFT_CORNER,
    MOUTH_RIGHT_CORNER,
    POSE_LANDMARK_INDICES
)


def euclidean_dist(p1: np.ndarray, p2: np.ndarray) -> float:
    """Calculates Euclidean distance between two 2D/3D points."""
    return float(np.linalg.norm(p1[:2] - p2[:2]))


def calculate_ear(eye_landmarks: np.ndarray) -> float:
    """
    Computes Eye Aspect Ratio (EAR) for a single eye given 6 ordered landmark points:
    P1 (outer), P2 (top-left), P3 (top-right), P4 (inner), P5 (bottom-right), P6 (bottom-left)
    EAR = (||P2 - P6|| + ||P3 - P5||) / (2.0 * ||P1 - P4||)
    """
    if eye_landmarks is None or eye_landmarks.shape[0] < 6:
        return 0.0
        
    p1, p2, p3, p4, p5, p6 = eye_landmarks[:6]
    v1 = euclidean_dist(p2, p6)
    v2 = euclidean_dist(p3, p5)
    h = euclidean_dist(p1, p4)
    
    if h <= 1e-6:
        return 0.0
    return float((v1 + v2) / (2.0 * h))


def calculate_mar(all_landmarks: np.ndarray) -> float:
    """
    Computes Mouth Aspect Ratio (MAR) using 3 vertical inner-lip distances divided by horizontal width:
    MAR = (||P13 - P14|| + ||P81 - P178|| + ||P311 - P402||) / (3.0 * ||P61 - P291||)
    """
    try:
        p_top = all_landmarks[MOUTH_INNER_TOP]
        p_bottom = all_landmarks[MOUTH_INNER_BOTTOM]
        p_ltop = all_landmarks[MOUTH_INNER_LEFT_TOP]
        p_lbottom = all_landmarks[MOUTH_INNER_LEFT_BOTTOM]
        p_rtop = all_landmarks[MOUTH_INNER_RIGHT_TOP]
        p_rbottom = all_landmarks[MOUTH_INNER_RIGHT_BOTTOM]
        p_left = all_landmarks[MOUTH_LEFT_CORNER]
        p_right = all_landmarks[MOUTH_RIGHT_CORNER]
        
        v1 = euclidean_dist(p_top, p_bottom)
        v2 = euclidean_dist(p_ltop, p_lbottom)
        v3 = euclidean_dist(p_rtop, p_rbottom)
        h = euclidean_dist(p_left, p_right)
        
        if h <= 1e-6:
            return 0.0
        return float((v1 + v2 + v3) / (3.0 * h))
    except (IndexError, TypeError):
        return 0.0


# 3D generic anthropomorphic facial reference model for head pose
FACE_3D_MODEL_POINTS = np.array([
    (0.0, 0.0, 0.0),            # Nose tip (landmark 1)
    (0.0, -330.0, -65.0),       # Chin (landmark 152)
    (-225.0, 170.0, -135.0),    # Left eye outer corner (landmark 33)
    (225.0, 170.0, -135.0),     # Right eye outer corner (landmark 263)
    (-150.0, -150.0, -125.0),   # Left mouth corner (landmark 61)
    (150.0, -150.0, -125.0)     # Right mouth corner (landmark 291)
], dtype=np.float64)


def estimate_head_pose(all_landmarks_px: np.ndarray, frame_shape: Tuple[int, int]) -> Tuple[float, float, float]:
    """
    Estimates 3D Head Pose (Pitch, Yaw, Roll) in degrees using OpenCV solvePnP.
    Returns:
        (pitch, yaw, roll)
        - Pitch: Positive = nodding down (chin toward chest), Negative = tilting up
        - Yaw: Turn left/right
        - Roll: Tilt left/right
    """
    img_h, img_w = frame_shape[:2]
    
    try:
        image_points = np.array([
            all_landmarks_px[idx][:2] for idx in POSE_LANDMARK_INDICES
        ], dtype=np.float64)
        
        # Approximate camera intrinsic matrix based on focal length
        focal_length = img_w
        center = (img_w / 2.0, img_h / 2.0)
        camera_matrix = np.array([
            [focal_length, 0.0, center[0]],
            [0.0, focal_length, center[1]],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)
        
        success, rvec, tvec = cv2.solvePnP(
            FACE_3D_MODEL_POINTS,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )
        
        if not success:
            return 0.0, 0.0, 0.0
            
        rmat, _ = cv2.Rodrigues(rvec)
        # Decompose rotation matrix into Euler angles
        proj_matrix = np.hstack((rmat, tvec))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)
        
        pitch = float(euler_angles[0, 0])
        yaw = float(euler_angles[1, 0])
        roll = float(euler_angles[2, 0])
        
        return pitch, yaw, roll
    except Exception:
        return 0.0, 0.0, 0.0
