"""
Playmotion Driver — Bulletproof serial driver for WaveShare RoArm M2-S.
Handles noisy serial output, correct response parsing, and servo error filtering.
"""
import json
import time
import serial
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
log = logging.getLogger("RoArm")


class RoArmDriver:
    """
    Bulletproof serial driver for the WaveShare RoArm M2-S.
    """
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Wait for ESP32 to initialize
            self._drain()  # Clear any boot spam
            log.info(f"Connected to RoArm on {self.port}")
        except Exception as e:
            log.error(f"Failed to connect: {e}")
            raise

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("Disconnected from RoArm")

    def _drain(self):
        """Drain all pending serial data (noise, servo errors, etc)."""
        if not self.ser:
            return
        self.ser.reset_input_buffer()
        time.sleep(0.1)
        while self.ser.in_waiting > 0:
            self.ser.readline()

    def _send_and_read(self, cmd_dict, wait_time=0.5, retries=3):
        """
        Send a command and collect all JSON responses, filtering out
        noise like 'Servo ID:15 status: failed.' lines.
        Returns a list of parsed JSON dicts.
        """
        if not self.ser or not self.ser.is_open:
            log.warning("Serial not open.")
            return []

        results = []
        for attempt in range(retries):
            self._drain()

            payload = json.dumps(cmd_dict) + '\n'
            self.ser.write(payload.encode('ascii'))
            self.ser.flush()
            time.sleep(wait_time)

            while self.ser.in_waiting > 0:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if not line or 'status: failed' in line:
                    continue  # Skip noise
                try:
                    data = json.loads(line)
                    # Skip the echo (arm echoes back the exact command we sent)
                    if data == cmd_dict:
                        continue
                    results.append(data)
                except json.JSONDecodeError:
                    pass

            if results:
                return results

            log.debug(f"No valid response on attempt {attempt+1}, retrying...")

        return results

    def send_fast(self, cmd_dict):
        """
        Lean fire-and-forget write for high-frequency streaming loops
        (teach.py jog/gravity-comp, play.py trajectory streaming).
        No drain, no read-back, no sleep — caller controls timing.
        """
        if not self.ser or not self.ser.is_open:
            return
        payload = json.dumps(cmd_dict) + '\n'
        self.ser.write(payload.encode('ascii'))
        self.ser.flush()

    def _send_command(self, cmd_dict, wait_time=0.5):
        """Send a command, don't care about response."""
        if not self.ser or not self.ser.is_open:
            log.warning("Serial not open.")
            return
        self._drain()
        payload = json.dumps(cmd_dict) + '\n'
        self.ser.write(payload.encode('ascii'))
        self.ser.flush()
        time.sleep(wait_time)
        self._drain()  # Clear any response/noise

    def disable_torque(self):
        """Disables servo torque so the arm can be moved freely by hand."""
        log.info("Disabling torque (freedrive mode)...")
        # Send multiple times to cut through the servo error noise
        for _ in range(3):
            self._send_command({"T": 210, "cmd": 0}, wait_time=0.3)
        time.sleep(0.5)
        log.info("Torque disabled. You can now move the arm by hand.")

    def enable_torque(self):
        """Enables servo torque to lock the arm in its current position."""
        log.info("Enabling torque (locked mode)...")
        for _ in range(3):
            self._send_command({"T": 210, "cmd": 1}, wait_time=0.3)
        time.sleep(0.5)

    def get_xyz(self):
        """
        Reads the current XYZ Cartesian coordinates + joint angles.
        The arm responds with T:1051 (not T:105).
        Returns dict with keys: x, y, z, t, b, s, e or None on failure.
        """
        responses = self._send_and_read({"T": 105}, wait_time=0.5, retries=3)
        for data in responses:
            # Arm returns T:1051 for XYZ feedback
            if data.get("T") == 1051 and "x" in data:
                return data
        log.warning("Failed to get XYZ position from arm.")
        return None

    def move_xyz(self, x, y, z, t=3.14, speed=0.25):
        """Moves the arm to an XYZ position using Inverse Kinematics."""
        log.info(f"Moving to X:{x:.1f} Y:{y:.1f} Z:{z:.1f}")
        self._send_command(
            {"T": 104, "x": x, "y": y, "z": z, "t": t, "spd": speed},
            wait_time=2.0  # Give the arm time to physically move
        )

    def home(self):
        """Move every joint to the power-on initial position."""
        log.info("Arm → HOME")
        self._send_command({"T": 100}, wait_time=3.0)