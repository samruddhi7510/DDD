"""
Research Contribution 1: Adaptive Baseline Calibration Engine.
Constructs personalized driver profiles to prevent false alarms caused by
diverse facial morphology (narrow eyes, epicanthic folds, deep-set eyes, glasses)
and compensates for vehicle camera dashboard mounting tilt angles.
"""

import os
import json
import time
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
from config import CalibrationProfile, DrowsinessConfig


class AdaptiveCalibrationEngine:
    """
    Manages non-intrusive pre-drive baseline calibration.
    Collects statistical distributions of alert driver features, computes dynamic thresholds,
    and conducts sanity checks for pre-existing fatigue or inadequate cabin lighting.
    """
    def __init__(self, target_duration: float = 45.0, min_frames: int = 150):
        self.target_duration = target_duration
        self.min_frames = min_frames
        self.reset()
        
    def reset(self):
        """Resets calibration accumulators for a new driver session."""
        self.start_time: Optional[float] = None
        self.is_active: bool = False
        self.is_completed: bool = False
        
        self.ear_samples: List[float] = []
        self.mar_samples: List[float] = []
        self.pitch_samples: List[float] = []
        self.blink_durations: List[float] = []
        
        # Blink tracking during calibration
        self.eye_closed_start: float = 0.0
        self.eye_was_closed: bool = False
        self.total_blinks: int = 0
        
        # Lighting quality tracking
        self.lighting_scores: List[float] = []
        
        self.profile: CalibrationProfile = CalibrationProfile()

    def start_calibration(self, driver_name: str = "Driver"):
        """Initiates the baseline calibration sequence."""
        self.reset()
        self.profile.driver_name = driver_name
        self.is_active = True
        self.start_time = time.time()

    def process_calibration_frame(
        self,
        current_time: float,
        face_detected: bool,
        avg_ear: float,
        mar: float,
        pitch: float,
        frame_mean_luminance: float = 120.0
    ) -> Dict[str, Any]:
        """
        Ingests frame measurements during the active calibration window.
        Returns live progress dictionary.
        """
        if not self.is_active or self.start_time is None:
            return {"active": False, "progress": 0.0}
            
        elapsed = current_time - self.start_time
        progress = min(1.0, elapsed / self.target_duration)
        
        if face_detected and avg_ear > 0.0:
            self.ear_samples.append(avg_ear)
            self.mar_samples.append(mar)
            self.pitch_samples.append(pitch)
            self.lighting_scores.append(frame_mean_luminance)
            
            # Simple blink detection during calibration to capture natural blink dynamics
            is_blink_closed = avg_ear < 0.16
            if is_blink_closed:
                if not self.eye_was_closed:
                    self.eye_closed_start = current_time
                    self.eye_was_closed = True
            else:
                if self.eye_was_closed:
                    duration = current_time - self.eye_closed_start
                    if 0.08 <= duration <= 0.85:
                        self.blink_durations.append(duration)
                        self.total_blinks += 1
                    self.eye_was_closed = False
                    self.eye_closed_start = 0.0
                    
        # Check if calibration target time reached
        if elapsed >= self.target_duration:
            self.is_active = False
            self.is_completed = True
            self._finalize_profile(elapsed)
            
        return {
            "active": self.is_active,
            "progress": round(progress * 100, 1),
            "elapsed_sec": round(elapsed, 1),
            "target_sec": self.target_duration,
            "frames_collected": len(self.ear_samples),
            "current_ear": round(avg_ear, 3),
            "is_completed": self.is_completed,
            "profile": self.profile.__dict__ if self.is_completed else None
        }

    def _finalize_profile(self, total_elapsed: float):
        """
        Calculates statistically robust baseline values using IQR filtering to reject blinks.
        """
        if len(self.ear_samples) < self.min_frames:
            # Insufficient samples: Fallback to population default
            self.profile.is_calibrated = False
            self.profile.quality_score = 0.4
            self.profile.baseline_alert_ear = 0.28
            self.profile.personalized_ear_threshold = 0.23
            return

        ear_arr = np.array(self.ear_samples)
        
        # Filter out active blinks: Use upper 70% of distribution to estimate open alert eye aperture
        q25 = np.percentile(ear_arr, 25)
        q75 = np.percentile(ear_arr, 75)
        iqr = q75 - q25
        
        # Valid alert eye openings are those above the 25th percentile (filtering downward blink spikes)
        alert_open_ears = ear_arr[ear_arr >= q25]
        median_alert_ear = float(np.median(alert_open_ears)) if len(alert_open_ears) > 0 else float(np.median(ear_arr))
        
        # Sanity check: Ensure EAR is physically plausible for human eyes
        if median_alert_ear < 0.16 or median_alert_ear > 0.45:
            # Anomalous geometry (sunglasses or tracking artifact): safe fallback
            median_alert_ear = 0.28
            
        # Personalized EAR threshold: 78% of driver's alert baseline
        dynamic_ear_thresh = float(median_alert_ear * 0.78)
        
        # Resting MAR & mounting angle pitch offset
        median_mar = float(np.median(self.mar_samples)) if len(self.mar_samples) > 0 else 0.05
        median_pitch = float(np.median(self.pitch_samples)) if len(self.pitch_samples) > 0 else 0.0
        
        # Blink duration baseline
        avg_blink_dur = float(np.mean(self.blink_durations)) if len(self.blink_durations) > 0 else 0.22
        blink_rate_per_min = float(self.total_blinks * (60.0 / max(1.0, total_elapsed)))
        
        # Pre-existing fatigue check:
        # If the driver had blinks averaging > 0.40s or EAR variance was extreme during calibration
        flagged_fatigued = False
        if avg_blink_dur > 0.38 or np.std(ear_arr) > 0.08:
            flagged_fatigued = True
            
        # Lighting quality assessment
        avg_lum = float(np.mean(self.lighting_scores)) if len(self.lighting_scores) > 0 else 120.0
        quality_score = 1.0 if avg_lum >= 40.0 else max(0.3, avg_lum / 40.0)
        
        self.profile.is_calibrated = True
        self.profile.calibration_duration_sec = round(total_elapsed, 1)
        self.profile.total_frames_sampled = len(self.ear_samples)
        self.profile.baseline_alert_ear = round(median_alert_ear, 3)
        self.profile.personalized_ear_threshold = round(dynamic_ear_thresh, 3)
        self.profile.baseline_blink_duration = round(avg_blink_dur, 3)
        self.profile.baseline_blink_rate_per_min = round(blink_rate_per_min, 1)
        self.profile.baseline_resting_mar = round(median_mar, 3)
        self.profile.mounting_pitch_offset = round(median_pitch, 1)
        self.profile.quality_score = round(quality_score, 2)
        self.profile.flagged_fatigued = flagged_fatigued

    def save_profile_to_file(self, filepath: Optional[str] = None):
        """Persists the calibrated profile to JSON."""
        if filepath is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, "logs", "driver_profiles.json")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        data = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
                
        data[self.profile.driver_name] = self.profile.__dict__
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_profile_from_file(self, driver_name: str, filepath: Optional[str] = None) -> Optional[CalibrationProfile]:
        """Loads previously saved profile for instant drive startup."""
        if filepath is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filepath = os.path.join(base_dir, "logs", "driver_profiles.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if driver_name in data:
                prof_dict = data[driver_name]
                prof = CalibrationProfile(**prof_dict)
                self.profile = prof
                self.is_completed = True
                return prof
        except Exception:
            return None
        return None
