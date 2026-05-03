#!/usr/bin/env python3
"""
Ro-Arm PlayMotion : TEACH MODE
Disables torque so you can move the arm by hand.
Shows live XYZ coordinates in real-time.
Press [R] to record a waypoint, [S] to save, [Q] to quit.
"""
import sys
import os
import tty
import termios
import json
import time
import threading
import select
from roarm_driver import RoArmDriver


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
    running = True
    live_pos = {"x": 0.0, "y": 0.0, "z": 0.0, "t": 0.0}
    lock = threading.Lock()

    # ── Background thread: poll arm position ──
    def poll_position():
        nonlocal live_pos
        while running:
            pos = arm.get_xyz()
            if pos and 'x' in pos:
                with lock:
                    live_pos = pos
            time.sleep(0.15)  # ~6 Hz polling rate

    poller = threading.Thread(target=poll_position, daemon=True)
    poller.start()

    # ── Display header ──
    print("\n" + "=" * 50)
    print("  🤖 Ro-Arm PlayMotion : TEACH MODE")
    print("=" * 50)
    print("  The arm is now loose. Move it by hand.")
    print("  Live coordinates are shown below.\n")
    print("  Controls:")
    print("    [R]  Record current position as waypoint")
    print("    [S]  Save all waypoints and Quit")
    print("    [Q]  Quit without saving")
    print("=" * 50 + "\n")

    # ── Set terminal to raw mode for instant keypress ──
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)  # cbreak mode: instant keys but allows Ctrl+C

        while running:
            # ── Print live coordinates ──
            with lock:
                x = live_pos.get('x', 0.0)
                y = live_pos.get('y', 0.0)
                z = live_pos.get('z', 0.0)
                t = live_pos.get('t', 0.0)

            status = f"  LIVE | X: {x:>7.1f}  Y: {y:>7.1f}  Z: {z:>7.1f}  T: {t:>5.2f}  | WPs: {len(waypoints)}"
            sys.stdout.write(f"\r{status}    ")
            sys.stdout.flush()

            # ── Check for keypress (non-blocking) ──
            if select.select([sys.stdin], [], [], 0.1)[0]:
                char = sys.stdin.read(1).lower()

                if char == 'r':
                    with lock:
                        snapshot = dict(live_pos)
                    waypoints.append(snapshot)
                    sys.stdout.write(f"\r\n  ✅ Recorded WP {len(waypoints)}: X:{snapshot.get('x',0):.1f}  Y:{snapshot.get('y',0):.1f}  Z:{snapshot.get('z',0):.1f}\n")
                    sys.stdout.flush()

                elif char == 's':
                    running = False
                    if waypoints:
                        filename = "motion_path.json"
                        with open(filename, "w") as f:
                            json.dump(waypoints, f, indent=4)
                        sys.stdout.write(f"\r\n  💾 Saved {len(waypoints)} waypoints to {filename}.\n")
                    else:
                        sys.stdout.write("\r\n  ⚠️  No waypoints recorded. Nothing saved.\n")
                    sys.stdout.flush()

                elif char == 'q' or char == '\x03':
                    running = False
                    sys.stdout.write("\r\n  🛑 Quitting without saving.\n")
                    sys.stdout.flush()

    except KeyboardInterrupt:
        running = False
        sys.stdout.write("\r\n  🛑 Interrupted by user.\n")
        sys.stdout.flush()
    finally:
        # Restore terminal
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        # Wait for poller thread to stop
        poller.join(timeout=1.0)

        print("  Re-enabling torque...")
        arm.enable_torque()
        arm.disconnect()
        print("  Done.\n")


if __name__ == "__main__":
    main()
