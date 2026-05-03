import json
import time
import serial
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
log = logging.getLogger("RoArm")

class RoArmDriver:
    """
    Bulletproof serial driver for the WaveShare RoArm M2-S.
    Handles buffer flushing, strict delays, and safe JSON parsing to prevent crashes.
    """
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Wait for ESP32 to initialize
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            log.info(f"Connected to RoArm on {self.port}")
        except Exception as e:
            log.error(f"Failed to connect: {e}")
            raise

    def disconnect(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            log.info("Disconnected from RoArm")

    def _send_command(self, cmd_dict, wait_time=0.1):
        if not self.ser or not self.ser.is_open:
            log.warning("Serial not open. Reconnect first.")
            return

        try:
            # Aggressive flush to prevent garbled JSON overlap
            self.ser.reset_input_buffer()
            
            payload = json.dumps(cmd_dict) + '\n'
            self.ser.write(payload.encode('ascii'))
            self.ser.flush()
            
            # Enforce strict delay to let ESP32 process
            time.sleep(wait_time)
            
            # Drain and log any responses
            while self.ser.in_waiting > 0:
                resp = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if resp:
                    log.debug(f"Arm response: {resp}")
        except Exception as e:
            log.error(f"Error sending command {cmd_dict}: {e}")

    def disable_torque(self):
        """Disables servo torque so the arm can be moved freely by hand."""
        log.info("Disabling torque (freedrive mode)...")
        self._send_command({"T": 210, "cmd": 0}, wait_time=0.5)

    def enable_torque(self):
        """Enables servo torque to lock the arm in its current position."""
        log.info("Enabling torque (locked mode)...")
        self._send_command({"T": 210, "cmd": 1}, wait_time=0.5)

    def get_xyz(self):
        """Reads the current XYZ Cartesian coordinates + Tool angle."""
        if not self.ser or not self.ser.is_open:
            return None

        self.ser.reset_input_buffer()
        payload = json.dumps({"T": 105}) + '\n'
        self.ser.write(payload.encode('ascii'))
        self.ser.flush()
        
        time.sleep(0.2)
        while self.ser.in_waiting > 0:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "T" in data and data["T"] == 105:
                    return data
            except json.JSONDecodeError:
                pass
        
        log.warning("Failed to get a valid XYZ position from arm.")
        return None

    def move_xyz(self, x, y, z, t=3.14, speed=0.25):
        """Moves the arm to an XYZ position using Inverse Kinematics."""
        cmd = {"T": 104, "x": x, "y": y, "z": z, "t": t, "spd": speed}
        # We enforce a longer wait time here to ensure the arm finishes moving 
        # before the serial buffer receives the next command.
        self._send_command(cmd, wait_time=1.0)
