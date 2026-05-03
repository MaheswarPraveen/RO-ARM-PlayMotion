#!/usr/bin/env python3
import json
import time
import sys
import argparse
from roarm_driver import RoArmDriver

def play_path(arm, waypoints):
    """Executes a single run of the recorded waypoints."""
    for idx, pos in enumerate(waypoints):
        # Extract values safely
        x = pos.get('x', 0)
        y = pos.get('y', 0)
        z = pos.get('z', 0)
        t = pos.get('t', 3.14)
        spd = pos.get('spd', 0.25)
        
        print(f"  -> Moving to WP {idx+1}/{len(waypoints)}: X:{x:.1f} Y:{y:.1f} Z:{z:.1f}")
        arm.move_xyz(x, y, z, t, speed=spd)
        # The driver handles the safety delay internally

def main():
    parser = argparse.ArgumentParser(description="Ro-Arm PlayMotion: Playback a recorded JSON path.")
    parser.add_argument('filename', nargs='?', default="motion_path.json", help="Path to the JSON file (default: motion_path.json)")
    parser.add_argument('-l', '--loop', action='store_true', help="Play the path continuously in a loop")
    args = parser.parse_args()
        
    try:
        with open(args.filename, "r") as f:
            waypoints = json.load(f)
    except FileNotFoundError:
        print(f"\n[!] Error: {args.filename} not found.")
        print("Please run teach.py first to record a path.")
        sys.exit(1)

    if not waypoints:
        print("\n[!] Error: No waypoints found in file.")
        sys.exit(1)

    print("Connecting to RoArm M2-S...")
    arm = RoArmDriver(port='/dev/ttyUSB0')
    try:
        arm.connect()
    except Exception:
        print("\n[!] Failed to connect to arm on /dev/ttyUSB0.")
        sys.exit(1)

    print("Enabling torque for Playback Mode...")
    arm.enable_torque()
    
    print("\n" + "="*40)
    print(" 🤖 Ro-Arm PlayMotion : PLAY MODE")
    print("="*40)
    print(f" Loaded {len(waypoints)} waypoints from {args.filename}")
    print(f" Mode: {'CONTINUOUS LOOP' if args.loop else 'SINGLE RUN (ONCE)'}")
    print(" Press Ctrl+C to stop at any time.")
    print("="*40 + "\n")
    
    try:
        if args.loop:
            cycle = 1
            while True:
                print(f"\n--- Starting Loop {cycle} ---")
                play_path(arm, waypoints)
                cycle += 1
                time.sleep(1.0) # Brief pause before restarting loop
        else:
            play_path(arm, waypoints)
            print("\n✅ Playback complete.")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Playback interrupted by user.")
    finally:
        print("\nRe-enabling torque to lock position and disconnecting...")
        arm.enable_torque()
        arm.disconnect()

if __name__ == "__main__":
    main()
