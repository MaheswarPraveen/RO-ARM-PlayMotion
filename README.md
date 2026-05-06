# RoArm M2-S Play Motion

A high-precision path recording and playback system for the **Waveshare RoArm M2-S** robotic arm. Built on top of the Waveshare ESP32 JSON API, this project adds a robust, high-level control layer that allows you to teach the arm complex movements and replay them with precision.

## 🛠️ Credits & Technology

This project is a hybrid implementation that combines official Waveshare technology with our custom autonomous logic:

- **Waveshare (Hardware & Base API)**: We utilize the official **RoArm M2-S** hardware, the underlying ESP32 firmware, and the core JSON-based command structure provided by Waveshare.
- **Our Custom Implementation (Play Motion)**: We have developed the **Playmotion Driver**, which implements critical features not found in the base examples:
    - **Noise Filtering**: Automatically strips out asynchronous servo error messages and boot-spam to prevent serial buffer corruption.
    - **Dual-Mode Teaching**: Created the physical "freedrive" (gravity-off) and keyboard "jogging" interfaces from scratch.
    - **Feedback Sync**: Implemented the coordinate polling logic to ensure 100% movement accuracy during autonomous playback.

---

## 🦾 The Two Teach Modes

The unified `teach.py` script provides two distinct ways to program the robotic arm:

### 1. Physical Teach Mode (Freedrive)
In this mode, the script **disables torque** on all servos, making the arm "limp." 
- **Usage**: You physically guide the arm with your hand through the desired path.
- **Recording**: Press **[R]** on your keyboard to save the current coordinates as a waypoint.
- **Benefit**: Extremely intuitive for complex, organic motions.

### 2. Keyboard Teach Mode (Jogging)
In this mode, the arm remains **under torque** and holds its position.
- **Usage**: Use the keyboard to "jog" the arm along its axes for fine-tuning.
    - **W/S**: Shoulder Up/Down | **A/D**: Base Left/Right
    - **I/K**: Elbow Forward/Back | **J/L**: Hand Pitch
- **Benefit**: Maximum precision for fine-tuning positions or working in tight spaces.

---

## 📂 Project Structure

- **`teach.py`**: Unified programming utility (Physical + Keyboard).
- **`play.py`**: Enhanced playback engine with speed override and instant looping.
- **`playmotion_driver.py`**: The robust core driver for reliable serial communication.
- **`motion_path.json`**: Example movement data format.

---

## 🛠️ Usage Guide

### 1. Connection
Ensure your RoArm M2-S is connected via USB (usually `/dev/ttyUSB0`).

### 2. Teaching a Path
```bash
python3 teach.py
```
- Select mode `1` (Physical) or `2` (Keyboard).
- Press **[R]** to record points, **[F]** to save.

### 3. Playing Back a Path
```bash
python3 play.py
```
- Select the recording number.
- Set the **Motor Speed** (0 for max speed).
- Toggle **Looping** for continuous execution.
- Use **`d<num>`** to delete unwanted recordings (e.g., `d1`).
