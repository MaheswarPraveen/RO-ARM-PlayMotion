# Ro-Arm PlayMotion

A robust, plug-and-play toolkit for teaching and replaying physical movements on the **WaveShare RoArm M2-S**.

This package solves the common serial communication issues (buffer corruption, missed commands) often seen when controlling the RoArm M2-S via Python. It provides a reliable object-oriented driver and two easy-to-use CLI tools for recording and playing back robotic arm trajectories.

## 🌟 Features
- **Bulletproof Serial Driver:** Aggressively handles serial buffer flushing and parsing to prevent the ESP32 from crashing.
- **Teach Mode (`teach.py`):** Interactive terminal script that disables servo torque, letting you guide the arm by hand and record waypoints with a single keystroke.
- **Play Mode (`play.py`):** Autonomous playback of recorded JSON files, supporting both single-run and continuous loop modes.

## 🛠️ Hardware Requirements
- WaveShare RoArm M2-S
- A Linux host (e.g., Raspberry Pi, PC)
- USB-C cable connecting the host to the RoArm's ESP32 port.

## 📦 Installation

1. Clone or download this repository.
2. Install the required Python dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```
3. Make the scripts executable:
   ```bash
   chmod +x teach.py play.py
   ```

*Note: Ensure your user has permissions to access serial ports (e.g., `sudo usermod -a -G dialout $USER` on Ubuntu/Debian).*

## 📖 Usage

### 1. Teach the Arm (`teach.py`)
Run the teach script to record a new path. The arm will go limp, allowing you to move it physically.

```bash
./teach.py
```
**Controls:**
- **`r`** : Record the current XYZ position of the arm.
- **`s`** : Save the recorded path to `motion_path.json` and exit.
- **`q`** : Quit without saving.

### 2. Playback the Path (`play.py`)
Run the playback script to watch the arm recreate your movements.

**Play Once:**
```bash
./play.py
```

**Play Continuously (Loop Mode):**
```bash
./play.py --loop
```
*(You can also use `-l` instead of `--loop`)*

**Use a Specific File:**
```bash
./play.py my_custom_path.json
```

## 🔌 Integrating into Your Projects
You can easily import the `RoArmDriver` into your own Python projects for reliable control:

```python
from roarm_driver import RoArmDriver

arm = RoArmDriver(port='/dev/ttyUSB0')
arm.connect()

# Move to a specific XYZ position
arm.move_xyz(x=200, y=0, z=150)

arm.disconnect()
```
