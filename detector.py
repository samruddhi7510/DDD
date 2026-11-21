"""
MediaPipe Face Landmarker detection and facial ROI extraction engine.
Provides 478 3D facial landmarks and crops aligned facial regions for deep learning models.
"""

import os
import cv2
import numpy as np
from typing import Tuple, Optional, Dict, Any, List

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class FaceLandmarkerDetector:
    """
    Encapsulates MediaPipe Face Landmarker extraction and face crop bounding box calculation.
    """
    def __init__(self, model_path: str = "models/face_landmarker.task", num_faces: int = 1):
        if not os.path.isabs(model_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(base_dir, model_path)
            if os.path.exists(candidate):
                model_path = candidate
            elif os.path.exists(r"D:\AI-Driver-Drowsiness-Detection-main\face_landmarker.task"):
                model_path = r"D:\AI-Driver-Drowsiness-Detection-main\face_landmarker.task"
                
        self.model_path = model_path
        self.num_faces = num_faces
        
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_faces=self.num_faces,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)

    def process_frame(
        self, frame_bgr: np.ndarray
    ) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray], Optional[Tuple[int, int, int, int]]]:
        """
        Processes BGR image and extracts landmarks + face bounding box (x, y, w, h).

        Returns:
            (face_detected, landmarks_px, landmarks_norm, bbox)
            - landmarks_px: (478, 3) array in pixel coordinates (x, y, z)
            - landmarks_norm: (478, 3) normalized (0.0 to 1.0)
            - bbox: (x, y, w, h) bounding box with 20% contextual margin for CNN input
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return False, None, None, None
            
        h, w = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        
        detection_result = self.landmarker.detect(mp_image)
        
        if not detection_result.face_landmarks or len(detection_result.face_landmarks) == 0:
            return False, None, None, None
            
        face_landmarks = detection_result.face_landmarks[0]
        
        landmarks_norm = np.array([
            [lm.x, lm.y, lm.z] for lm in face_landmarks
        ], dtype=np.float64)
        
        landmarks_px = np.array([
            [lm.x * w, lm.y * h, lm.z * w] for lm in face_landmarks
        ], dtype=np.float64)
        
        # Calculate bounding box with a 20% padding margin for CNN face input
        x_min, y_min = np.min(landmarks_px[:, :2], axis=0)
        x_max, y_max = np.max(landmarks_px[:, :2], axis=0)
        
        box_w = x_max - x_min
        box_h = y_max - y_min
        pad_x = box_w * 0.15
        pad_y = box_h * 0.15
        
        bx = max(0, int(x_min - pad_x))
        by = max(0, int(y_min - pad_y))
        bw = min(w - bx, int(box_w + 2 * pad_x))
        bh = min(h - by, int(box_h + 2 * pad_y))
        
        bbox = (bx, by, bw, bh)
        return True, landmarks_px, landmarks_norm, bbox

    def extract_face_crop(self, frame_bgr: np.ndarray, bbox: Tuple[int, int, int, int], target_size: Tuple[int, int] = (224, 224)) -> Optional[np.ndarray]:
        """Crops and resizes face region for deep learning classifiers."""
        if bbox is None:
            return None
        x, y, w, h = bbox
        if w <= 10 or h <= 10:
            return None
        crop = frame_bgr[y:y+h, x:x+w]
        if crop.size == 0:
            return None
        return cv2.resize(crop, target_size, interpolation=cv2.INTER_LINEAR)

    def close(self):
        """Releases underlying MediaPipe C++ session."""
        if hasattr(self, 'landmarker') and self.landmarker:
            self.landmarker.close()
