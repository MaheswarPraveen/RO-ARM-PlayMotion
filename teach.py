#!/usr/bin/env python3
import sys
import tty
import termios
import json
import time
from roarm_driver import RoArmDriver

def getch():
    """Reads a single character from standard input without requiring Enter."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def main():
    print("Connecting to RoArm M2-S...")
    arm = RoArmDriver(port='/dev/ttyUSB0')
    try:
        arm.connect()
    except Exception:
        print("\n[!] Failed to connect to arm on /dev/ttyUSB0.")
        print("Please check your USB connection and permissions.")
        sys.exit(1)

    print("Disabling torque for Teach Mode...")
    arm.disable_torque()
    
    waypoints = []
    
    print("\n" + "="*40)
    print(" 🤖 Ro-Arm PlayMotion : TEACH MODE")
    print("="*40)
    print(" The arm is now loose. Move it by hand to your desired positions.")
    print("")
    print(" Controls:")
    print("   [R]  Record current position")
    print("   [S]  Save all recorded positions and Quit")
    print("   [Q]  Quit without saving")
    print("="*40 + "\n")
    
    try:
        while True:
            char = getch().lower()
            if char == 'r':
                pos = arm.get_xyz()
                if pos and 'x' in pos:
                    waypoints.append(pos)
                    print(f"\r✅ Recorded Waypoint {len(waypoints)}: X:{pos['x']:.1f}  Y:{pos['y']:.1f}  Z:{pos['z']:.1f}          ")
                else:
                    print("\r❌ Failed to read position from arm. Try again.           ")
            elif char == 's':
                filename = "motion_path.json"
                with open(filename, "w") as f:
                    json.dump(waypoints, f, indent=4)
                print(f"\r\n💾 Saved {len(waypoints)} waypoints to {filename}.")
                break
            elif char == 'q' or char == '\x03':  # \x03 is Ctrl+C
                print("\r\n🛑 Quitting without saving.")
                break
    except KeyboardInterrupt:
        print("\r\n🛑 Interrupted by user.")
    finally:
        print("\rRe-enabling torque...")
        arm.enable_torque()
        arm.disconnect()
        print("\rDone. You can now safely close this window.")

if __name__ == "__main__":
    main()
