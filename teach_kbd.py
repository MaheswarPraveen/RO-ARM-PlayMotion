#!/usr/bin/env python3
import serial
import json
import time
import sys
import select
import termios
import tty
import math

PORT = '/dev/ttyUSB0'
BAUD = 115200

# Current joint angles (degrees)
angles = {"b": 0, "s": 0, "e": 90, "h": 180}
step_size = 2.0  # Finer movements!
mission_name = "spray_path"

print(f"Connecting to {PORT} at {BAUD} baud...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)

def get_feedback():
    ser.reset_input_buffer()
    ser.write(b'{"T":105}\n')
    ser.flush()
    time.sleep(0.1)
    for _ in range(10):
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line:
            try:
                data = json.loads(line)
                if data.get("T") == 1051:
                    global angles
                    angles["b"] = math.degrees(data.get("b", 0))
                    angles["s"] = math.degrees(data.get("s", 0))
                    angles["e"] = math.degrees(data.get("e", 1.5707))
                    angles["h"] = math.degrees(data.get("t", 3.1415))
                    return True
            except:
                pass
    return False

def move_arm():
    cmd = {
        "T": 122,
        "b": round(angles["b"], 1),
        "s": round(angles["s"], 1),
        "e": round(angles["e"], 1),
        "h": round(angles["h"], 1),
        "spd": 0,  # 0 = max speed (no artificial delay)
        "acc": 0   # 0 = max acceleration
    }
    ser.write((json.dumps(cmd) + "\n").encode())
    ser.flush()

def record_step():
    cmd = {"T": 223, "name": mission_name, "spd": 0.25}
    ser.write((json.dumps(cmd) + "\n").encode())
    ser.flush()
    print(f"\r\n[RECORDED] Point saved to mission '{mission_name}' in ESP32 Flash.\r")

def play_mission():
    cmd = {"T": 242, "name": mission_name, "times": 1}
    ser.write((json.dumps(cmd) + "\n").encode())
    ser.flush()
    print(f"\r\n[PLAYING] Running mission '{mission_name}'...\r")

def clear_mission():
    cmd = {"T": 220, "name": mission_name, "intro": "Keyboard teach"}
    ser.write((json.dumps(cmd) + "\n").encode())
    ser.flush()
    print(f"\r\n[CLEARED] Mission '{mission_name}' wiped and recreated.\r")

print("Syncing initial position...")
get_feedback()
move_arm()

print("""
=================================================
  KEYBOARD JOG MODE - Control each servo!
=================================================
  Base (Left/Right)   : [A] / [D]
  Shoulder (Up/Down)  : [W] / [S]
  Elbow (Up/Down)     : [I] / [K]
  Hand (Open/Close)   : [J] / [L]
  
  [R] - Record current position to path
  [P] - Play recorded path
  [C] - Clear path completely
  [Q] - Quit
=================================================
""")

old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())

try:
    while True:
        if select.select([sys.stdin], [], [], 0.05)[0]:
            keys = sys.stdin.read(1).lower()
            
            # Drain input buffer to prevent lag from held keys
            while select.select([sys.stdin], [], [], 0)[0]:
                keys += sys.stdin.read(1).lower()

            moved = False
            for c in keys:
                if c == 'q':
                    raise KeyboardInterrupt
                elif c == 'a':
                    angles["b"] += step_size
                    moved = True
                elif c == 'd':
                    angles["b"] -= step_size
                    moved = True
                elif c == 'w':
                    angles["s"] += step_size
                    moved = True
                elif c == 's':
                    angles["s"] -= step_size
                    moved = True
                elif c == 'i':
                    angles["e"] -= step_size
                    moved = True
                elif c == 'k':
                    angles["e"] += step_size
                    moved = True
                elif c == 'j':
                    angles["h"] -= step_size
                    moved = True
                elif c == 'l':
                    angles["h"] += step_size
                    moved = True
                elif c == 'r':
                    record_step()
                elif c == 'p':
                    play_mission()
                elif c == 'c':
                    clear_mission()

            if moved:
                # Clamp values roughly
                angles["b"] = max(-180, min(180, angles["b"]))
                angles["s"] = max(-90, min(90, angles["s"]))
                angles["e"] = max(0, min(180, angles["e"]))
                angles["h"] = max(45, min(315, angles["h"]))
                sys.stdout.write(f"\rBase:{angles['b']:.1f} Shoulder:{angles['s']:.1f} Elbow:{angles['e']:.1f} Hand:{angles['h']:.1f}      ")
                sys.stdout.flush()
                move_arm()
except KeyboardInterrupt:
    pass
finally:
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    ser.close()
    print("\nExited.")
