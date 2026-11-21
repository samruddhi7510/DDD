# DrowseGuard AI — Driver Drowsiness Detection System v2.0
### *Deep Learning and Adaptive AI with Real-Time Mobile PWA Cockpit*

**Author:** Ms. Samruddhi Sharad Bhosale  
**Institution:** Annasaheb Dange College of Engineering and Technology, Ashta, Maharashtra, India  

---

## 🌟 Key Research Contributions

1. **Adaptive Baseline Calibration Engine (`calibration.py`):**
   - Implements a 30–45 second non-intrusive pre-drive baseline calibration.
   - Extracts the driver's unique alert eye aperture ($EAR_{\text{alert}}$) using Interquartile Range (IQR) filtering to ignore natural blinks.
   - Computes dynamic personalized thresholds: $EAR_{\text{threshold}} = EAR_{\text{alert}} \times 0.78$.
   - Automatically compensates for dashboard phone mount physical tilt angles ($P_{\text{offset}}$).
   - Eliminates false drowsiness alarms for drivers with naturally narrow eyes or epicanthic folds.

2. **Confidence-Aware Shannon Entropy Fusion (`fusion.py`):**
   - Computes binary Shannon entropy $H(p) = -[p \log_2 p + (1-p) \log_2 (1-p)]$ for both MobileNetV2 and YOLOv11 predictions.
   - Dynamically weights each model based on predictive certainty (minimizing entropy).
   - Merges deep learning classifications with physical 3D facial landmarks (478 points) and PERCLOS.
   - Applies Exponential Moving Average (EMA) temporal smoothing to prevent false alarm spikes.

---

## 📱 Mobile Architecture & UI Workflow

The software is engineered as an **Android-Installable Progressive Web App (PWA)**:
* **Screen 1 (Pre-Drive Alignment):** Live front camera feed, face alignment oval guide, cabin lighting quality meter.
* **Screen 2 (Adaptive Calibration):** 30s circular progress ring, real-time EAR tracking, personal baseline result card.
* **Screen 3 (Live Cockpit HUD):** OLED dark theme, color-coded status banner (🟢 Green / 🟡 Yellow / 🔴 Flashing Red Siren), Drowsiness Risk Score gauge (0–100%), dual-model prediction chips, Web Audio synthesized multi-tone alarm, Android device vibration.
* **Screen 4 (Trip Summary & Telemetry):** Trip duration, average EAR, total blinks, drowsy events logged, 1-click CSV download.

---

## 🚀 Quickstart Guide

### 1. Launch the Server
From this project directory, run:
```powershell
& "D:\AI-Driver-Drowsiness-Detection-main\.venv\Scripts\python.exe" run_server.py
```

The terminal will display:
```
=================================================================
      DROWSEGUARD AI — ADAPTIVE DRIVER SAFETY SYSTEM v2.0
=================================================================
🚀 Server starting...
💻 Open on Laptop Browser:       http://localhost:8000
📱 Open on Android Mobile Phone: http://192.168.x.x:8000
=================================================================
```

### 2. Connect Your Android Mobile Phone
1. Connect your Android phone and laptop to the same Wi-Fi network (or turn on your Android phone's **Mobile Hotspot** and connect your laptop to it).
2. Open **Google Chrome** on your Android phone.
3. Type the address displayed in the terminal: `http://192.168.x.x:8000`.
4. Allow front camera permission.
5. *(Optional PWA Install):* Tap the three dots (⋮) in Chrome and select **"Install app"** or **"Add to Home screen"**. The app will launch in fullscreen mode without any browser address bar!

---

## 🧪 Evaluation & Benchmarking

To run the formal evaluation on the held-out test set (2,091 images: 1,118 Drowsy, 973 Non-Drowsy):
```powershell
& "D:\AI-Driver-Drowsiness-Detection-main\.venv\Scripts\python.exe" evaluate.py
```
This computes True Accuracy, Precision, Recall, F1-Score, and records the Confusion Matrix in `logs/evaluation_results.json`.

---

## 🏋️ Model Training & Export

To train MobileNetV2 and YOLOv11 on the dataset in `D:\safedrive_drowsiness_detection-master\splitted_dataset`:
```powershell
& "D:\safedrive_drowsiness_detection-master\.venv\Scripts\python.exe" train_models.py --quick
```
This produces optimized `.onnx` models inside `models/` for low-latency CPU and mobile inference.
