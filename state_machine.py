"""
Temporal State Machine, Physiological Blink/Yawn Tracker, PERCLOS Calculator,
and Multi-Factor Composite Drowsiness Risk Engine.
"""

import time
from collections import deque
from typing import List, Tuple, Dict, Any, Optional
from config import DrowsinessConfig, DetectionPayload


class TemporalStateMachine:
    """
    Manages temporal debouncing, state transitions, PERCLOS calculations,
    and composite Drowsiness Risk Score evaluation.
    """
    def __init__(self, config: Optional[DrowsinessConfig] = None):
        self.config = config or DrowsinessConfig()
        self.reset()
        
    def reset(self):
        """Resets all temporal timers and historical metrics."""
        self.eye_closed_start: float = 0.0
        self.eye_was_closed: bool = False
        
        self.mouth_open_start: float = 0.0
        self.mouth_was_open: bool = False
        
        self.total_blinks: int = 0
        self.total_yawns: int = 0
        
        self.blink_timestamps: deque = deque(maxlen=120)
        self.blink_durations: deque = deque(maxlen=60)
        self.yawn_timestamps: deque = deque(maxlen=60)
        
        # PERCLOS tracking (60-second sliding buffer of eye closure states)
        # Stored as (timestamp, is_closed)
        self.eye_closure_history: deque = deque(maxlen=1800) # up to 60s at 30fps
        
        self.smoothed_risk_score: float = 0.0
        
    def update_config(self, config: DrowsinessConfig):
        """Updates runtime configuration thresholds."""
        self.config = config

    def process_frame(
        self,
        current_time: float,
        face_detected: bool,
        left_ear: float = 0.0,
        right_ear: float = 0.0,
        mar: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        roll: float = 0.0,
        fused_dl_score: float = 0.0,
        dl_entropy: float = 0.0,
        p_mobilenet: float = 0.0,
        p_yolo: float = 0.0,
        is_personalized: bool = False
    ) -> DetectionPayload:
        """
        Advances the temporal state machine and computes the composite risk payload.
        """
        payload = DetectionPayload(timestamp=current_time, face_detected=face_detected)
        payload.is_personalized = is_personalized
        payload.active_ear_threshold = self.config.ear_threshold
        payload.mobilenet_drowsy_prob = round(p_mobilenet, 3)
        payload.yolo_drowsy_prob = round(p_yolo, 3)
        payload.fused_dl_score = round(fused_dl_score, 3)
        payload.dl_entropy_uncertainty = round(dl_entropy, 3)
        
        if not face_detected:
            payload.state_label = "NO FACE"
            payload.drowsiness_score = 0.0
            payload.risk_level = "ALERT"
            # Reset active closure counters if face lost
            self.eye_closed_start = 0.0
            self.mouth_open_start = 0.0
            self.eye_was_closed = False
            self.mouth_was_open = False
            return payload
            
        avg_ear = (left_ear + right_ear) / 2.0
        payload.left_ear = round(left_ear, 3)
        payload.right_ear = round(right_ear, 3)
        payload.avg_ear = round(avg_ear, 3)
        payload.mar = round(mar, 3)
        
        # Adjust pitch by camera mounting offset
        adjusted_pitch = pitch - self.config.pitch_offset
        payload.pitch = round(adjusted_pitch, 1)
        payload.yaw = round(yaw, 1)
        payload.roll = round(roll, 1)
        
        # ------------------------------------------------------------------
        # 1. EYE CLOSURE & BLINK DYNAMICS
        # ------------------------------------------------------------------
        is_eye_closed = avg_ear <= self.config.ear_threshold
        payload.eye_closed = is_eye_closed
        
        # Track for PERCLOS (Percentage of Eye Closure over 60s)
        self.eye_closure_history.append((current_time, 1 if is_eye_closed else 0))
        # Purge entries older than 60 seconds
        while len(self.eye_closure_history) > 0 and (current_time - self.eye_closure_history[0][0]) > 60.0:
            self.eye_closure_history.popleft()
            
        if len(self.eye_closure_history) > 0:
            closed_samples = sum(item[1] for item in self.eye_closure_history)
            payload.perclos = round((closed_samples / len(self.eye_closure_history)) * 100.0, 1)
        else:
            payload.perclos = 0.0
            
        if is_eye_closed:
            if not self.eye_was_closed:
                self.eye_closed_start = current_time
                self.eye_was_closed = True
            eye_closed_dur = current_time - self.eye_closed_start
        else:
            if self.eye_was_closed:
                duration = current_time - self.eye_closed_start
                # Valid physiological blink
                if self.config.min_blink_duration <= duration <= self.config.max_blink_duration:
                    self.total_blinks += 1
                    self.blink_timestamps.append(current_time)
                    self.blink_durations.append(duration)
                self.eye_was_closed = False
                self.eye_closed_start = 0.0
            eye_closed_dur = 0.0
            
        payload.eye_closed_duration = round(eye_closed_dur, 2)
        payload.total_blinks = self.total_blinks
        
        # Blink rate (last 60s) and average blink duration
        recent_blinks = [t for t in self.blink_timestamps if current_time - t <= 60.0]
        payload.blink_rate_per_min = round(float(len(recent_blinks)), 1)
        if len(self.blink_durations) > 0:
            payload.avg_blink_duration = round(float(sum(self.blink_durations) / len(self.blink_durations)), 3)
            
        # ------------------------------------------------------------------
        # 2. YAWNING TEMPORAL TRACKER
        # ------------------------------------------------------------------
        is_mouth_open = mar >= self.config.mar_threshold
        if is_mouth_open:
            if not self.mouth_was_open:
                self.mouth_open_start = current_time
                self.mouth_was_open = True
            yawn_dur = current_time - self.mouth_open_start
        else:
            if self.mouth_was_open:
                dur = current_time - self.mouth_open_start
                if dur >= self.config.yawn_time_thresh:
                    self.total_yawns += 1
                    self.yawn_timestamps.append(current_time)
                self.mouth_was_open = False
                self.mouth_open_start = 0.0
            yawn_dur = 0.0
            
        payload.yawn_duration = round(yawn_dur, 2)
        payload.total_yawns = self.total_yawns
        payload.yawning = (yawn_dur >= self.config.yawn_time_thresh) or (is_mouth_open and mar >= self.config.mar_threshold * 1.25)
        
        # ------------------------------------------------------------------
        # 3. HEAD NODDING POSTURE
        # ------------------------------------------------------------------
        payload.head_nodding = adjusted_pitch > self.config.head_pitch_down_thresh
        
        # ------------------------------------------------------------------
        # 4. COMPOSITE DROWSINESS RISK SCORE ENGINE (0 - 100%)
        # ------------------------------------------------------------------
        # A) Eye Closure Score (45%)
        # Normal blinks last 0.08s to 0.45s. A normal blink is NOT drowsiness!
        # Eye closure score ramps up if closure exceeds 0.55s, reaching immediate alert at 0.75s.
        if is_eye_closed:
            if eye_closed_dur >= self.config.sleep_time_thresh: # >= 2.0s
                eye_score = 100.0
            elif eye_closed_dur >= self.config.drowsy_time_thresh: # >= 0.75s
                progress = (eye_closed_dur - self.config.drowsy_time_thresh) / max(0.1, (self.config.sleep_time_thresh - self.config.drowsy_time_thresh))
                eye_score = 75.0 + 25.0 * min(1.0, progress)
            elif eye_closed_dur >= 0.55: # 0.55s to 0.75s (onset of micro-closure beyond normal blink)
                eye_score = 35.0 + ((eye_closed_dur - 0.55) / 0.20) * 40.0
            else:
                # Normal blink (< 0.55s) - completely zero risk score!
                eye_score = 0.0
        else:
            # Partial eye drooping ratio (eyelids heavy but not closed)
            droop_boundary = self.config.ear_threshold * 1.15
            if avg_ear < droop_boundary and avg_ear > self.config.ear_threshold:
                factor = (droop_boundary - avg_ear) / max(1e-4, droop_boundary - self.config.ear_threshold)
                eye_score = min(25.0, factor * 25.0)
            else:
                eye_score = 0.0
                
        # B) Deep Learning Dual-Model Score (25%)
        # Only contribute if models are confident in drowsiness (e.g. > 0.60)
        if fused_dl_score >= 0.60:
            dl_score = (fused_dl_score - 0.60) / 0.40 * 100.0
        else:
            dl_score = 0.0
        
        # C) Yawning Score (15%)
        recent_yawns = [t for t in self.yawn_timestamps if current_time - t <= 120.0]
        if payload.yawning:
            yawn_score = 80.0
        elif len(recent_yawns) > 0:
            yawn_score = min(60.0, len(recent_yawns) * 30.0)
        else:
            yawn_score = 0.0
            
        # D) Blink Dynamics & Rapid Fluttering Score (10%)
        # Rapid eye flutter: 3 or more blinks within 2.5 seconds indicates fighting sleep
        recent_burst_blinks = [t for t in self.blink_timestamps if current_time - t <= 2.5]
        is_rapid_flutter = len(recent_burst_blinks) >= 3
        payload.rapid_blinking = is_rapid_flutter
        
        blink_score = 0.0
        if is_rapid_flutter:
            blink_score = min(100.0, 65.0 + (len(recent_burst_blinks) - 3) * 15.0)
        elif payload.perclos > 25.0:  # PERCLOS > 25% over 60s
            blink_score = min(50.0, (payload.perclos - 25.0) * 2.0)
        elif payload.avg_blink_duration > 0.40: # Sluggish blinks (>400ms)
            blink_score = min(40.0, (payload.avg_blink_duration - 0.40) * 200.0)
            
        # E) Head Posture Score (5%)
        head_score = 0.0
        if payload.head_nodding:
            head_score = min(100.0, (adjusted_pitch - self.config.head_pitch_down_thresh) * 4.0 + 50.0)
            
        raw_risk = (
            eye_score * self.config.weight_eye_closure +
            dl_score * self.config.weight_deep_learning +
            yawn_score * self.config.weight_yawning +
            blink_score * self.config.weight_blink_anomaly +
            head_score * self.config.weight_head_posture
        )
        
        # ------------------------------------------------------------------
        # 5. STATE CLASSIFICATION & ALARM TRIGGERS
        # ------------------------------------------------------------------
        if eye_closed_dur >= self.config.sleep_time_thresh or (eye_closed_dur >= 1.3 and payload.head_nodding):
            payload.state_label = "SLEEPING"
            payload.trigger_critical_alarm = True
            raw_risk = max(raw_risk, 95.0)
            self.smoothed_risk_score = max(self.smoothed_risk_score, 88.0)
        elif eye_closed_dur >= self.config.drowsy_time_thresh or (fused_dl_score > 0.85 and eye_score > 35.0):
            payload.state_label = "DROWSY"
            payload.trigger_warning_alarm = True
            raw_risk = max(raw_risk, 72.0)
            self.smoothed_risk_score = max(self.smoothed_risk_score, 65.0)
        elif is_rapid_flutter:
            payload.state_label = "RAPID BLINKING"
            payload.trigger_warning_alarm = True
            raw_risk = max(raw_risk, 55.0)
        elif payload.yawning:
            payload.state_label = "YAWNING"
            raw_risk = max(raw_risk, 40.0)
        else:
            payload.state_label = "AWAKE"
            
        # Exponential smoothing on risk score for stable visual rendering
        alpha_ema = 0.45
        self.smoothed_risk_score = alpha_ema * raw_risk + (1.0 - alpha_ema) * self.smoothed_risk_score
        payload.drowsiness_score = round(max(0.0, min(100.0, self.smoothed_risk_score)), 1)
        
        # Risk level badge classification
        if payload.drowsiness_score <= 30.0:
            payload.risk_level = "ALERT"
        elif payload.drowsiness_score <= 65.0:
            payload.risk_level = "WARNING"
            payload.trigger_warning_alarm = True
        else:
            payload.risk_level = "HIGH DROWSINESS"
            payload.trigger_critical_alarm = True
            
        return payload
