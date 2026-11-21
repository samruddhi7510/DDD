"""
FastAPI Asynchronous Backend Server with WebSocket Streaming for Mobile PWA.
Coordinates MediaPipe Face Landmarker, Dual Deep Learning Models,
Adaptive Calibration Engine, Confidence-Aware Fusion, and Real-Time Telemetry.
"""

import os
import io
import time
import json
import base64
import asyncio
from typing import Dict, Any, List, Optional

import cv2
import numpy as np
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import DrowsinessConfig, CalibrationProfile, DetectionPayload, LEFT_EYE_INDICES, RIGHT_EYE_INDICES
from detector import FaceLandmarkerDetector
from metrics import calculate_ear, calculate_mar, estimate_head_pose
from calibration import AdaptiveCalibrationEngine
from fusion import ConfidenceAwareFusionEngine
from state_machine import TemporalStateMachine
from models import DualModelClassifier

# ─────────────────────────────────────────────────────────────────────────────
# APPLICATION INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Driver Drowsiness Detection System", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core Engines
print("SERVER: Initializing config...", flush=True)
config = DrowsinessConfig()
print("SERVER: Initializing detector...", flush=True)
detector = FaceLandmarkerDetector()
print("SERVER: Initializing classifier...", flush=True)
classifier = DualModelClassifier()
print("SERVER: Initializing fusion...", flush=True)
fusion_engine = ConfidenceAwareFusionEngine()
print("SERVER: Initializing calibration...", flush=True)
calibration_engine = AdaptiveCalibrationEngine(target_duration=30.0) # 30s fast calibration for demo
print("SERVER: Initializing state machine...", flush=True)
state_machine = TemporalStateMachine(config=config)
print("SERVER: Initializing static...", flush=True)

# In-memory session telemetry log
session_telemetry: List[Dict[str, Any]] = []

# Mount static folder for PWA assets
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
print("SERVER: Setup complete!", flush=True)


@app.get("/", response_class=FileResponse)
async def read_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Driver Drowsiness Detection Server Running</h1>")


@app.get("/manifest.json")
async def get_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
async def get_sw():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")


# ─────────────────────────────────────────────────────────────────────────────
# REST API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────
class CalibrateRequest(BaseModel):
    driver_name: str = "Driver"
    target_seconds: float = 30.0


@app.post("/api/calibrate/start")
async def start_calibration(req: CalibrateRequest):
    calibration_engine.target_duration = req.target_seconds
    calibration_engine.start_calibration(req.driver_name)
    return {"status": "started", "driver_name": req.driver_name, "target_seconds": req.target_seconds}


@app.get("/api/calibrate/status")
async def get_calibration_status():
    return {
        "is_active": calibration_engine.is_active,
        "is_completed": calibration_engine.is_completed,
        "profile": calibration_engine.profile.__dict__ if calibration_engine.profile else None
    }


@app.post("/api/calibrate/apply")
async def apply_calibration():
    if not calibration_engine.is_completed:
        raise HTTPException(status_code=400, detail="Calibration not completed yet")
        
    prof = calibration_engine.profile
    # Dynamically update state machine thresholds
    config.ear_threshold = prof.personalized_ear_threshold
    config.pitch_offset = prof.mounting_pitch_offset
    state_machine.update_config(config)
    calibration_engine.save_profile_to_file()
    
    return {
        "status": "applied",
        "active_ear_threshold": config.ear_threshold,
        "pitch_offset": config.pitch_offset
    }


@app.get("/api/summary")
async def get_trip_summary():
    if not session_telemetry:
        return {"total_frames": 0, "message": "No session telemetry recorded yet."}
        
    df = pd.DataFrame(session_telemetry)
    avg_ear = float(df['avg_ear'].mean()) if 'avg_ear' in df else 0.0
    avg_risk = float(df['drowsiness_score'].mean()) if 'drowsiness_score' in df else 0.0
    total_drowsy_frames = int((df['state_label'] == 'DROWSY').sum()) if 'state_label' in df else 0
    total_sleep_frames = int((df['state_label'] == 'SLEEPING').sum()) if 'state_label' in df else 0
    
    return {
        "total_frames": len(df),
        "avg_ear": round(avg_ear, 3),
        "avg_risk_score": round(avg_risk, 1),
        "total_blinks": int(df['total_blinks'].max()) if 'total_blinks' in df else 0,
        "total_yawns": int(df['total_yawns'].max()) if 'total_yawns' in df else 0,
        "drowsy_events_detected": total_drowsy_frames,
        "sleeping_events_detected": total_sleep_frames,
        "is_personalized": calibration_engine.profile.is_calibrated,
        "personalized_ear_threshold": calibration_engine.profile.personalized_ear_threshold
    }


@app.get("/api/export_csv")
async def export_telemetry_csv():
    if not session_telemetry:
        raise HTTPException(status_code=404, detail="No session telemetry to export")
        
    df = pd.DataFrame(session_telemetry)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, "session_telemetry.csv")
    df.to_csv(csv_path, index=False)
    return FileResponse(csv_path, media_type="text/csv", filename="session_telemetry.csv")


# ─────────────────────────────────────────────────────────────────────────────
# REAL-TIME WEBSOCKET STREAMING ENGINE
# ─────────────────────────────────────────────────────────────────────────────
@app.websocket("/ws/detect")
async def websocket_detect(websocket: WebSocket):
    await websocket.accept()
    last_frame_time = time.time()
    
    try:
        while True:
            # Receive base64 or binary image from client
            message = await websocket.receive_text()
            frame_start = time.time()
            
            # Handle incoming data URI
            if "," in message:
                _, b64data = message.split(",", 1)
            else:
                b64data = message
                
            img_bytes = base64.b64decode(b64data)
            np_arr = np.frombuffer(img_bytes, np.uint8)
            frame_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame_bgr is None or frame_bgr.size == 0:
                await websocket.send_json({"error": "Invalid frame"})
                continue
                
            current_time = time.time()
            frame_luminance = float(np.mean(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)))
            
            # 1. Landmark detection
            face_detected, landmarks_px, landmarks_norm, bbox = detector.process_frame(frame_bgr)
            
            left_ear = 0.0
            right_ear = 0.0
            avg_ear = 0.0
            mar = 0.0
            pitch = 0.0
            yaw = 0.0
            roll = 0.0
            
            if face_detected and landmarks_px is not None:
                left_ear = calculate_ear(landmarks_px[LEFT_EYE_INDICES, :3])
                right_ear = calculate_ear(landmarks_px[RIGHT_EYE_INDICES, :3])
                avg_ear = (left_ear + right_ear) / 2.0
                mar = calculate_mar(landmarks_px)
                pitch, yaw, roll = estimate_head_pose(landmarks_px, frame_bgr.shape)
                
            # 2. Check if Calibration is active
            if calibration_engine.is_active:
                calib_status = calibration_engine.process_calibration_frame(
                    current_time=current_time,
                    face_detected=face_detected,
                    avg_ear=avg_ear,
                    mar=mar,
                    pitch=pitch,
                    frame_mean_luminance=frame_luminance
                )
                calib_status["mode"] = "calibration"
                calib_status["face_detected"] = face_detected
                calib_status["luminance"] = round(frame_luminance, 1)
                await websocket.send_json(calib_status)
                continue
                
            # 3. Active Drive Monitoring Mode: Dual-Model ML + Research Fusion
            p_mobilenet = 0.0
            p_yolo = 0.0
            fused_dl_score = 0.0
            dl_entropy = 0.0
            
            if face_detected and bbox is not None:
                face_crop = detector.extract_face_crop(frame_bgr, bbox)
                if face_crop is not None:
                    p_mobilenet, p_yolo = classifier.predict(face_crop, avg_ear=avg_ear)
                    fused_dl_score, dl_entropy, _ = fusion_engine.fuse_models(p_mobilenet, p_yolo)
                    
            # 4. Advance Temporal State Machine & Multi-factor Risk Engine
            payload: DetectionPayload = state_machine.process_frame(
                current_time=current_time,
                face_detected=face_detected,
                left_ear=left_ear,
                right_ear=right_ear,
                mar=mar,
                pitch=pitch,
                yaw=yaw,
                roll=roll,
                fused_dl_score=fused_dl_score,
                dl_entropy=dl_entropy,
                p_mobilenet=p_mobilenet,
                p_yolo=p_yolo,
                is_personalized=calibration_engine.profile.is_calibrated
            )
            
            # Compute FPS and Latency
            latency_ms = (time.time() - frame_start) * 1000.0
            time_delta = current_time - last_frame_time
            last_frame_time = current_time
            fps = 1.0 / max(1e-4, time_delta)
            
            payload.fps = round(fps, 1)
            payload.latency_ms = round(latency_ms, 1)
            
            response_dict = payload.__dict__
            response_dict["mode"] = "monitoring"
            response_dict["luminance"] = round(frame_luminance, 1)
            
            # Append to session telemetry for analytics (keep max 10,000 frames)
            if len(session_telemetry) < 10000:
                session_telemetry.append({
                    "timestamp": round(current_time, 2),
                    "face_detected": payload.face_detected,
                    "avg_ear": payload.avg_ear,
                    "mar": payload.mar,
                    "pitch": payload.pitch,
                    "mobilenet_prob": payload.mobilenet_drowsy_prob,
                    "yolo_prob": payload.yolo_drowsy_prob,
                    "fused_dl_score": payload.fused_dl_score,
                    "entropy": payload.dl_entropy_uncertainty,
                    "perclos": payload.perclos,
                    "total_blinks": payload.total_blinks,
                    "total_yawns": payload.total_yawns,
                    "drowsiness_score": payload.drowsiness_score,
                    "state_label": payload.state_label,
                    "risk_level": payload.risk_level
                })
                
            await websocket.send_json(response_dict)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket Error]: {e}")
