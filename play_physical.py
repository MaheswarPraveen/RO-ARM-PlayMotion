#!/usr/bin/env python3
import serial
import json
import time
import sys

PORT = '/dev/ttyUSB0'
BAUD = 115200
INPUT_FILE = 'physical_path.json'

print(f"Loading waypoints from {INPUT_FILE}...")
try:
    with open(INPUT_FILE, 'r') as f:
        waypoints = json.load(f)
except Exception as e:
    print(f"Failed to load {INPUT_FILE}: {e}")
    sys.exit(1)

if not waypoints:
    print("No waypoints found in file!")
    sys.exit(1)

print(f"Connecting to {PORT} at {BAUD} baud...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)

# Ensure torque is ON before moving
print("Enabling Torque...")
ser.write(b'{"T":210,"cmd":1}\n')
ser.flush()
time.sleep(0.5)

print(f"Playing {len(waypoints)} waypoints...")

for i, pos in enumerate(waypoints):
    # T:122 is CMD_JOINTS_ANGLE_CTRL
    # spd: 30, acc: 20 makes it move smoothly but not instantly jump
    cmd = {
        "T": 122,
        "b": pos["b"],
        "s": pos["s"],
        "e": pos["e"],
        "h": pos["h"],
        "spd": 30,
        "acc": 20
    }
    
    print(f"Moving to WP {i+1}/{len(waypoints)}: {pos}")
    ser.write((json.dumps(cmd) + "\n").encode())
    ser.flush()
    
    # Wait for the arm to reach the position
    # A simple static delay based on typical movement speeds. 
    # For a robust system, you'd poll T:105 to check if current pos == target pos.
    time.sleep(1.5)

print("Playback complete!")
ser.close()
