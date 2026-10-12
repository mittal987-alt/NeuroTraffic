# 🚦 NeuroTraffic: Next-Gen Autonomous Traffic Intelligence & Road Safety Platform

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/YOLOv8-Ultralytics-00ffff?style=for-the-badge&logo=yolo&logoColor=black" alt="YOLOv8" />
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/PyTorch-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white" alt="PyTorch" />
  <img src="https://img.shields.io/badge/Flutter-02569B?style=for-the-badge&logo=flutter&logoColor=white" alt="Flutter" />
  <img src="https://img.shields.io/badge/PostgreSQL-Neon-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Firebase_FCM-FFCA28?style=for-the-badge&logo=firebase&logoColor=black" alt="Firebase FCM" />
</p>

---

## 📌 Overview

**NeuroTraffic** is an end-to-end, AI-powered Smart City surveillance and traffic governance ecosystem. By combining state-of-the-art computer vision models (**YOLOv8**, **ByteTrack**, and **EasyOCR**) with a high-throughput **FastAPI** backend and a reactive **Flutter** mobile client, NeuroTraffic autonomously audits urban roadways in real-time.

From detecting moving violations and identifying potholes to automating **Green Corridors** for life-saving emergency vehicles and generating evidence-backed **E-Challan PDFs**, NeuroTraffic turns ordinary CCTV and IP cameras into intelligent municipal assets.

---

## ⚡ Key Features

### 🎯 1. Multi-Class Vehicle Detection & Tracking
- Detects and categorizes vehicles into **Cars, Motorcycles, Buses, and Trucks** using **YOLOv8**.
- Continuous multi-object tracking powered by **ByteTrack**, preserving vehicle identity across occlusions.
- Bidirectional line crossing counters with dynamic density computation.

### 🚨 2. Automated Violation Detection Suite
- **⚡ Overspeeding Detection**: Real-time velocity computation calibrated using metric pixel-to-meter matrices.
- **⛔ Wrong-Way Driving**: Vector displacement validation against allowable street trajectory profiles.
- **🛑 Red-Light Infringements**: Virtual tripwires and stop-line cross-referencing during signal phases.
- **🪖 No-Helmet Detection**: Spatial correlation of riders and two-wheelers without protective gear.
- **💺 Seatbelt Compliance**: Driver-cockpit area cropping and visual compliance validation.
- **↔️ Lane Departure / Straddling**: Monitors vehicle positions relative to lane markings.

### 💥 3. Incident Management & Hazard Detection
- **💥 Collision & Accident Detection**: Detects abrupt deceleration spikes coupled with bounding-box intersections.
- **🕳️ Pothole & Road Hazard Mapping**: Detects road surface defects, geolocating and deduplicating by coordinates.

### 🚑 4. Smart Signal Preemption & "Green Corridor"
- Identifies **Ambulances, Fire Engines, and Police units** through vision cues and ANPR keyword matching (`108`, `AMBULANCE`, `POLICE`, `FIRE`).
- Automatically triggers **Green Corridor preemption**, holding green lights along the emergency path.

### 🔍 5. ANPR & Automatic E-Challan Generation
- High-accuracy license plate localization and text extraction using **EasyOCR**.
- Generates official, tamper-evident **E-Challan PDFs** (via ReportLab) complete with fine amounts, violator snapshot, license plate, and violation details.

### 📱 6. Multi-Platform Flutter Client
- **Live Stream Viewer**: Zero-latency MJPEG streaming with real-time detection bounding boxes.
- **Interactive Camera Map**: Geographic distribution of deployed camera nodes and their live status.
- **Real-Time Alert Feed**: Push notifications via **Firebase Cloud Messaging (FCM)** and instant **WebSocket** alerts.
- **Traffic Analytics**: Visual dashboards showing density graphs, violation distributions, and speed metrics.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Inputs ["Video & Camera Sources"]
        A1[CCTV / IP Webcam] 
        A2[USB / Local Webcam]
        A3[YouTube Live / MP4 Video]
    end

    subgraph Backend ["NeuroTraffic AI Core (FastAPI)"]
        B1[Frame Capture & Resizing]
        B2[YOLOv8 Vehicle Detection]
        B3[ByteTrack Object Tracker]
        
        B4[ANPR / EasyOCR]
        B5[Violations Engine: Speed / Helmet / Seatbelt / Red Light]
        B6[Emergency & Green Corridor Controller]
        
        B7[(Neon PostgreSQL / SQLite)]
        B8[WebSocket & FCM Dispatcher]
        B9[E-Challan PDF Generator]
    end

    subgraph Client ["Frontend App (Flutter)"]
        C1[Live MJPEG Camera Stream]
        C2[Realtime Alerts & Audio Pings]
        C3[Interactive Camera Map]
        C4[Analytics Dashboard]
    end

    Inputs --> B1
    B1 --> B2 --> B3
    B3 --> B4
    B3 --> B5
    B3 --> B6
    
    B5 --> B7
    B5 --> B8
    B5 --> B9
    B6 --> B8

    B8 -- WebSocket / REST --> Client
```

---

## 📂 Repository Structure

```plaintext
NeuroTraffic/
├── .gitignore                     # Production Git ignore (Secrets, Models, Builds)
├── README.md                      # Documentation & Project Guide
│
├── backend/                       # Python & AI Engine (FastAPI)
│   ├── detection/                 # Detection sub-modules
│   │   ├── accident.py            # Collision & crash detection logic
│   │   ├── density.py             # Road congestion & vehicle count
│   │   ├── emergency.py           # Emergency vehicle & Green Corridor logic
│   │   ├── face.py                # Driver face detection & cropping
│   │   ├── helmet.py              # Motorcycle helmet compliance
│   │   ├── lane.py                # Lane discipline & departures
│   │   ├── pipeline.py            # Main multi-camera inference loop
│   │   ├── plate.py               # ANPR & OCR plate extractor
│   │   ├── pothole.py             # Road pothole & hazard detector
│   │   ├── redlight.py            # Stop-line red-light infringements
│   │   ├── seatbelt.py            # Driver seatbelt compliance
│   │   ├── speed.py               # Pixel-calibrated velocity estimator
│   │   └── wrong_way.py           # Traffic flow vector validation
│   ├── alerts.py                  # Alert deduplication & DB logging
│   ├── auth.py                    # JWT authentication & bcrypt security
│   ├── challan_generator.py       # Automated PDF E-Challan generator
│   ├── config.py                  # Central configuration & tuning parameters
│   ├── database.py                # SQLAlchemy models & DB connection
│   ├── main.py                    # FastAPI server entrypoint & REST routes
│   ├── push_notifications.py      # Firebase Admin FCM dispatcher
│   ├── requirements.txt           # Python backend dependencies
│   ├── signal_state.py            # Traffic light state machine
│   └── websocket_manager.py       # Live client connection manager
│
└── traffic_ai_app/                # Mobile & Web Frontend (Flutter)
    ├── lib/
    │   ├── screens/               # Dashboard, Live View, Map, Alerts, Analytics
    │   ├── services/              # API Client, WebSocket & FCM services
    │   ├── widgets/               # Reusable UI components & stat cards
    │   └── main.dart              # Flutter application entrypoint
    └── pubspec.yaml               # Flutter package configuration
```

---

## 🛠️ Tech Stack

| Domain | Technologies & Libraries |
| :--- | :--- |
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), Pydantic v2 |
| **Computer Vision** | [OpenCV](https://opencv.org/), [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics), [Supervision](https://supervision.roboflow.com/) |
| **Tracking & OCR** | ByteTrack, [EasyOCR](https://github.com/JaidedAI/EasyOCR), Pillow, NumPy, SciPy |
| **Database & ORM** | [Neon PostgreSQL](https://neon.tech/) (or SQLite), [SQLAlchemy 2.0](https://www.sqlalchemy.org/) |
| **Authentication** | OAuth2 with Password Flow, JWT (`python-jose`), `bcrypt` |
| **Mobile & Frontend** | [Flutter 3.x](https://flutter.dev/), Dart, Provider |
| **Realtime & Cloud** | WebSockets, Firebase Cloud Messaging (FCM), [ReportLab](https://www.reportlab.com/) |

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10 to 3.12**
- **Flutter SDK** (3.19+ recommended)
- **Git**

---

### 2. Backend Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mittal987-alt/NeuroTraffic.git
   cd NeuroTraffic/backend
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   # Windows PowerShell
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Create a `.env` file in the `backend/` folder:
   ```env
   # Database (Defaults to SQLite if omitted)
   DATABASE_URL=sqlite:///./traffic.db

   # Security
   JWT_SECRET_KEY=your-super-secret-jwt-key-here

   # Camera Input (0 for local webcam, or IP Webcam URL, or video path)
   CAMERA_1_VIDEO_PATH=0

   # Firebase (Optional: for push notifications)
   FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json
   FCM_DEVICE_TOKEN=PASTE_YOUR_FCM_TOKEN_HERE

   # Detection Calibration
   CONF_THRESHOLD=0.4
   SPEED_LIMIT_KMH=80.0
   PIXELS_PER_METER=8.0
   DETECTION_FRAME_SKIP=4
   ```

5. **Run the Backend Server:**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
   - OpenAPI Documentation will be live at: `http://localhost:8000/docs`

---

### 3. Flutter App Setup

1. **Navigate to the app folder:**
   ```bash
   cd ../traffic_ai_app
   ```

2. **Install Flutter packages:**
   ```bash
   flutter pub get
   ```

3. **Configure Backend IP:**
   Open `lib/services/app_config.dart` and update `customIp` with your PC's local Wi-Fi IP (obtained via `ipconfig` or `ifconfig`):
   ```dart
   static String customIp = "10.135.201.5"; // Your PC's local IPv4 address
   ```

4. **Run on your device or emulator:**
   ```bash
   # Run on connected physical phone or emulator
   flutter run
   ```

---

## ⚙️ Configuration & Tuning

Key tunable options in [backend/config.py](file:///c:/projects/traffic_ai/backend/config.py):

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `CAMERA_1_VIDEO_PATH` | `0` / URL | Input stream source (`0` for USB camera, RTSP/HTTP URL, or file path). |
| `CONF_THRESHOLD` | `0.4` | Minimum confidence score for YOLO object detection. |
| `DETECTION_FRAME_SKIP` | `4` | Runs YOLO every N frames on CPU to ensure high-FPS video streaming. |
| `SPEED_LIMIT_KMH` | `80.0` | Threshold in km/h above which an overspeed alert is triggered. |
| `PIXELS_PER_METER` | `8.0` | Camera calibration constant converting pixel shifts to real-world meters. |
| `JPEG_QUALITY` | `60` | MJPEG streaming compression quality (1–100). |

---

## 📡 Core API & Streaming Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/auth/signup` | Registers a new operator/admin account. |
| `POST` | `/auth/login` | Authenticates credentials and returns a JWT bearer token. |
| `GET` | `/video_feed/{camera_id}` | Live MJPEG video stream with bounding boxes and overlays. |
| `GET` | `/alerts` | Fetches historical violations with filtering options. |
| `GET` | `/challan/{alert_id}` | Downloads an evidence-backed official E-Challan PDF. |
| `GET` | `/analytics/summary` | Aggregated traffic flow, vehicle counts, and violation metrics. |
| `WS` | `/ws/live` | WebSocket endpoint streaming instant alerts and signal states. |

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:
1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
