#!/usr/bin/env python3
"""
play.py — Path Playback & Management for RoArm M2-S
Enhanced version with:
1. Interactive Menu (Play/Delete)
2. Global Motor Speed override
3. Zero-delay looping
"""

import sys
import os
import time
import json
import glob
import math
from playmotion_driver import RoArmDriver

# ─────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────
PORT = '/dev/ttyUSB0'
BAUD = 115200
RECORDINGS_DIR = '/home/rover/rover/ro-arm-playmotion'

def list_recordings():
    pattern = os.path.join(RECORDINGS_DIR, "*.json")
    files = glob.glob(pattern)
    return sorted(files)

def delete_recording(filename):
    try:
        os.remove(filename)
        print(f"\n[DELETED] {os.path.basename(filename)} has been removed.")
    except Exception as e:
        print(f"\n[ERROR] Could not delete file: {e}")

def play_recording(driver, filename, loop=False, motor_speed=0):
    try:
        with open(filename, 'r') as f:
            waypoints = json.load(f)
    except Exception as e:
        print(f"Error reading {filename}: {e}"); return

    if not waypoints:
        print("No waypoints found in file."); return

    driver.enable_torque()
    print(f"\n🚀 Executing {os.path.basename(filename)} ({len(waypoints)} points)...")
    print(f"   Motor Speed: {'MAX' if motor_speed == 0 else f'{motor_speed}°/s'}")
    print("   (Press Ctrl+C to stop)")

    cycle = 1
    try:
        while True:
            if loop:
                print(f"\n--- PLAYING LOOP {cycle} ---")
            
            for i, pos in enumerate(waypoints):
                # Use raw joint angles if they exist, else try XYZ
                if "b" in pos:
                    # Joint mode
                    cmd = {
                        "T": 122,
                        "b": math.degrees(pos["b"]) if isinstance(pos["b"], (float, int)) else pos["b"],
                        "s": math.degrees(pos["s"]) if isinstance(pos["s"], (float, int)) else pos["s"],
                        "e": math.degrees(pos["e"]) if isinstance(pos["e"], (float, int)) else pos["e"],
                        "h": math.degrees(pos["h"]) if isinstance(pos["h"], (float, int)) else pos["h"],
                        "spd": motor_speed,
                        "acc": 0
                    }
                else:
                    # Cartesian mode
                    cmd = {
                        "T": 104,
                        "x": pos["x"],
                        "y": pos["y"],
                        "z": pos["z"],
                        "t": pos.get("t", 3.14),
                        "spd": motor_speed if motor_speed > 0 else 0.25 # spd in T:104 is a scale factor
                    }

                driver._send_command(cmd, wait_time=0.05)
                
                # Feedback loop to wait for arrival
                reached = False
                timeout = time.time() + 5.0
                while not reached and time.time() < timeout:
                    curr = driver.get_xyz()
                    if curr:
                        # Check tolerance
                        if "b" in pos:
                            # Simple angle check
                            if (abs(math.degrees(curr["b"]) - math.degrees(pos["b"])) < 2.0 and
                                abs(math.degrees(curr["s"]) - math.degrees(pos["s"])) < 2.0):
                                reached = True
                        else:
                            # XYZ distance check
                            dist = math.sqrt((curr["x"]-pos["x"])**2 + (curr["y"]-pos["y"])**2 + (curr["z"]-pos["z"])**2)
                            if dist < 10.0: reached = True
                    time.sleep(0.05)

            if not loop: break
            cycle += 1
            # Zero delay loop restart as requested
    except KeyboardInterrupt:
        print("\n\n🛑 Playback stopped by user.")

def main():
    print("=" * 50)
    print("  🤖 RO-ARM PLAYMOTION : ENHANCED PLAYBACK")
    print("=" * 50)

    # 1. Connect
    driver = RoArmDriver(port=PORT, baudrate=BAUD)
    try:
        driver.connect()
    except:
        print(f"[!] Could not connect to arm on {PORT}. Check permissions."); return

    while True:
        # 2. List files
        files = list_recordings()
        print("\nAVAILABLE RECORDINGS:")
        if not files:
            print("  (No .json recordings found)")
        else:
            for i, f in enumerate(files):
                print(f"  [{i+1}] {os.path.basename(f)}")

        # 3. User choice
        prompt = "\nSelect file number to play, 'd<num>' to delete (e.g. d1), or 0 to exit: "
        choice = input(prompt).strip().lower()

        if choice == '0' or not choice:
            break
        
        if choice.startswith('d'):
            try:
                idx = int(choice[1:]) - 1
                if 0 <= idx < len(files):
                    confirm = input(f"Are you sure you want to delete {os.path.basename(files[idx])}? (y/n): ")
                    if confirm.lower() == 'y':
                        delete_recording(files[idx])
                else:
                    print("Invalid index.")
            except:
                print("Invalid format. Use 'd1' to delete.")
            continue

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(files)):
                print("Invalid selection.")
                continue
            
            target_file = files[idx]
            
            # 4. Speed & Loop Options
            print("\nMOTOR SPEED SETTINGS:")
            print("  0   = MAX Speed (Servos spin as fast as possible)")
            print("  10  = Very Slow")
            print("  100 = Fast")
            speed_input = input("Enter motor speed [default: 0]: ").strip()
            motor_speed = int(speed_input) if speed_input else 0
            
            loop = input("Play continuously in a loop? (y/n) [default: n]: ").lower() == 'y'
            
            # 5. Play!
            play_recording(driver, target_file, loop, motor_speed)
            
        except ValueError:
            print("Please enter a number or 'd<num>'.")
        except Exception as e:
            print(f"An error occurred: {e}")

    driver.disconnect()
    print("\nGoodbye.")

if __name__ == "__main__":
    main()
