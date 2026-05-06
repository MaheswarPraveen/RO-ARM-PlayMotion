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
OUTPUT_FILE = 'physical_path.json'

print(f"Connecting to {PORT} at {BAUD} baud...")
try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)

# Disable Torque for Physical Mode
print("Disabling Torque...")
ser.write(b'{"T":210,"cmd":0}\n')
ser.flush()
time.sleep(0.5)

waypoints = []

print(f"""
=================================================
  PHYSICAL TEACH MODE (Freedrive)
=================================================
  The arm is now LOOSE. Move it by hand!
  
  [R] - Record current position as a waypoint
  [S] - Save all waypoints to {OUTPUT_FILE} and Quit
  [Q] - Quit without saving
=================================================
""")

old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())

def get_feedback():
    ser.reset_input_buffer()
    ser.write(b'{"T":105}\n')
    ser.flush()
    time.sleep(0.05)
    
    # Read until we get 1051
    for _ in range(20):
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        if line:
            try:
                data = json.loads(line)
                if data.get("T") == 1051:
                    return {
                        "b": round(math.degrees(data.get("b", 0)), 2),
                        "s": round(math.degrees(data.get("s", 0)), 2),
                        "e": round(math.degrees(data.get("e", 0)), 2),
                        "h": round(math.degrees(data.get("t", 0)), 2)
                    }
            except:
                pass
    return None

try:
    while True:
        pos = get_feedback()
        if pos:
            sys.stdout.write(f"\rLIVE | Base: {pos['b']:>6.1f} | Shoulder: {pos['s']:>6.1f} | Elbow: {pos['e']:>6.1f} | Hand: {pos['h']:>6.1f}   [WPs: {len(waypoints)}]")
            sys.stdout.flush()

        if select.select([sys.stdin], [], [], 0.05)[0]:
            keys = sys.stdin.read(1).lower()
            while select.select([sys.stdin], [], [], 0)[0]:
                keys += sys.stdin.read(1).lower()

            for c in keys:
                if c == 'q':
                    raise KeyboardInterrupt
                elif c == 'r':
                    if pos:
                        waypoints.append(pos)
                        print(f"\n[RECORDED] Waypoint {len(waypoints)} saved.")
                elif c == 's':
                    with open(OUTPUT_FILE, 'w') as f:
                        json.dump(waypoints, f, indent=4)
                    print(f"\n[SAVED] {len(waypoints)} waypoints saved to {OUTPUT_FILE}!")
                    raise KeyboardInterrupt

except KeyboardInterrupt:
    pass
finally:
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    # Re-enable torque so it doesn't slam down
    print("\nRe-enabling Torque...")
    ser.write(b'{"T":210,"cmd":1}\n')
    ser.flush()
    ser.close()
    print("Exited.")
