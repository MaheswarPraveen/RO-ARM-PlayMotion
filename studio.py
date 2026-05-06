#!/usr/bin/env python3
import serial
import json
import time
import sys
import select
import termios
import tty
import math
import os
import glob

PORT = '/dev/ttyUSB0'
BAUD = 115200

# Connection
try:
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)

def get_feedback():
    ser.reset_input_buffer()
    ser.write(b'{"T":105}\n')
    ser.flush()
    time.sleep(0.05)
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

def move_arm(angles):
    cmd = {
        "T": 122,
        "b": round(angles["b"], 1),
        "s": round(angles["s"], 1),
        "e": round(angles["e"], 1),
        "h": round(angles["h"], 1),
        "spd": 0,  
        "acc": 0   
    }
    ser.write((json.dumps(cmd) + "\n").encode())
    ser.flush()

def setup_terminal():
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    return old_settings

def restore_terminal(settings):
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)

def run_physical_teach():
    print("\n--- PHYSICAL TEACH MODE ---")
    print("Disabling Torque...")
    ser.write(b'{"T":210,"cmd":0}\n')
    ser.flush()
    time.sleep(0.5)

    waypoints = []
    print(f"The arm is LIMP. Move it to desired positions.")
    print(f"Controls: [R] Record | [S] Finish & Save | [Q] Quit without saving\n")

    old_term = setup_terminal()
    should_save = False

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
                            print(f"\n[RECORDED] Point {len(waypoints)} saved.")
                    elif c == 's':
                        should_save = True
                        break
                
                if should_save:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        restore_terminal(old_term)
        print("\nRe-enabling Torque...")
        ser.write(b'{"T":210,"cmd":1}\n')
        ser.flush()

    if should_save and waypoints:
        print("\n--- RECORDING FINISHED ---")
        name = input("Enter name to save recording (default 'path'): ")
        if not name.strip(): name = 'path'
        if not name.endswith('.json'): name += '.json'
        
        with open(name, 'w') as f:
            json.dump(waypoints, f, indent=4)
        print(f"[SAVED] {len(waypoints)} points to {name}.")

def run_keyboard_teach():
    print("\n--- KEYBOARD TEACH MODE ---")
    print("Syncing initial position...")
    angles = get_feedback()
    if not angles:
        print("Failed to get initial position. Exiting.")
        return
    
    move_arm(angles)
    waypoints = []
    step_size = 2.0

    print(f"""
Controls:
  Base     : [A]/[D]
  Shoulder : [W]/[S]
  Elbow    : [I]/[K]
  Hand     : [J]/[L]
  
  [R] Record | [S] Finish & Save | [Q] Quit without saving
""")

    old_term = setup_terminal()
    should_save = False

    try:
        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                keys = sys.stdin.read(1).lower()
                while select.select([sys.stdin], [], [], 0)[0]:
                    keys += sys.stdin.read(1).lower()

                moved = False
                for c in keys:
                    if c == 'q':
                        raise KeyboardInterrupt
                    elif c == 'a': angles["b"] += step_size; moved = True
                    elif c == 'd': angles["b"] -= step_size; moved = True
                    elif c == 'w': angles["s"] += step_size; moved = True
                    elif c == 's': angles["s"] -= step_size; moved = True
                    elif c == 'i': angles["e"] -= step_size; moved = True
                    elif c == 'k': angles["e"] += step_size; moved = True
                    elif c == 'j': angles["h"] -= step_size; moved = True
                    elif c == 'l': angles["h"] += step_size; moved = True
                    elif c == 'r':
                        waypoints.append(angles.copy())
                        print(f"\n[RECORDED] Point {len(waypoints)} saved.")
                    elif c == 's':
                        should_save = True
                        break
                
                if should_save:
                    break

                if moved:
                    angles["b"] = max(-180, min(180, angles["b"]))
                    angles["s"] = max(-90, min(90, angles["s"]))
                    angles["e"] = max(0, min(180, angles["e"]))
                    angles["h"] = max(45, min(315, angles["h"]))
                    sys.stdout.write(f"\rLIVE | Base:{angles['b']:.1f} Shoulder:{angles['s']:.1f} Elbow:{angles['e']:.1f} Hand:{angles['h']:.1f}   [WPs: {len(waypoints)}]   ")
                    sys.stdout.flush()
                    move_arm(angles)
    except KeyboardInterrupt:
        pass
    finally:
        restore_terminal(old_term)

    if should_save and waypoints:
        print("\n--- RECORDING FINISHED ---")
        name = input("Enter name to save recording (default 'path'): ")
        if not name.strip(): name = 'path'
        if not name.endswith('.json'): name += '.json'
        
        with open(name, 'w') as f:
            json.dump(waypoints, f, indent=4)
        print(f"[SAVED] {len(waypoints)} points to {name}.")

def run_playback():
    files = glob.glob("*.json")
    if not files:
        print("\nNo .json recordings found in this directory!")
        return

    print("\n--- AVAILABLE RECORDINGS ---")
    for i, f in enumerate(files):
        print(f"[{i+1}] {f}")
    
    try:
        choice = int(input("Select file number to play (or 0 to cancel): "))
        if choice <= 0 or choice > len(files):
            return
        filename = files[choice-1]
    except ValueError:
        return

    try:
        with open(filename, 'r') as f:
            waypoints = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print("Enabling Torque...")
    ser.write(b'{"T":210,"cmd":1}\n')
    ser.flush()
    time.sleep(0.5)

    print(f"Playing {len(waypoints)} points from {filename}...")
    for i, pos in enumerate(waypoints):
        cmd = {
            "T": 122,
            "b": pos["b"],
            "s": pos["s"],
            "e": pos["e"],
            "h": pos["h"],
            "spd": 30,
            "acc": 20
        }
        print(f"-> WP {i+1}/{len(waypoints)}: Base:{pos['b']} Shoulder:{pos['s']} Elbow:{pos['e']} Hand:{pos['h']}")
        ser.write((json.dumps(cmd) + "\n").encode())
        ser.flush()
        time.sleep(1.5)
    print("Playback complete!")

def main():
    while True:
        print("\n===========================================")
        print("         RO-ARM M2-S STUDIO STUDIO         ")
        print("===========================================")
        print("[1] Physical Teach Mode (Freedrive)")
        print("[2] Keyboard Teach Mode (Jogging)")
        print("[3] Playback a Recording")
        print("[4] Exit")
        choice = input("Select an option: ")

        if choice == '1':
            run_physical_teach()
        elif choice == '2':
            run_keyboard_teach()
        elif choice == '3':
            run_playback()
        elif choice == '4':
            break
        else:
            print("Invalid option.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
