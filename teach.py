#!/usr/bin/env python3
"""
Ro-Arm PlayMotion : TEACH MODE (Freedrive & Jogging)
Allows teaching waypoints via Physical Freedrive or Keyboard Jogging.
Saves to JSON in degrees with keys b, s, e, h (fully compatible).
Features a combined Feedforward + Feedback active gravity compensation system
for ultimate precision and zero-lag hold capability.
"""
import sys
import os
import tty
import termios
import json
import time
import threading
import select
import math
from playmotion_driver import RoArmDriver

# Get the script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = '/dev/ttyUSB0'
BAUD = 115200

# ─────────────────────────────────────────────────────────
# GRAVITY COMPENSATOR CONSTANTS
# ─────────────────────────────────────────────────────────
# Baseline joint offsets in degrees when arm links are horizontal (maximum torque)
K_S1 = 4.0  # Shoulder self-weight compensation coefficient
K_S2 = 6.0  # Forearm/Hand leverage compensation coefficient on Shoulder
K_E  = 5.0  # Elbow leverage compensation coefficient

def get_live_angles(arm):
    """Helper to get live angles in degrees."""
    pos = arm.get_xyz()
    if pos and 'b' in pos:
        return {
            "b": round(math.degrees(pos.get("b", 0.0)), 2),
            "s": round(math.degrees(pos.get("s", 0.0)), 2),
            "e": round(math.degrees(pos.get("e", 0.0)), 2),
            "h": round(math.degrees(pos.get("t", 0.0)), 2),
            "x": round(pos.get("x", 0.0), 1),
            "y": round(pos.get("y", 0.0), 1),
            "z": round(pos.get("z", 0.0), 1),
            "t": round(pos.get("t", 0.0), 3)
        }
    return None

def get_feedforward_offsets(angles):
    """Calculates feedforward gravity compensation offsets based on trigonometric arm model."""
    s_deg = angles["s"]
    e_deg = angles["e"]
    
    # Convert to radians for trigonometric functions
    s_rad = math.radians(s_deg)
    se_rad = math.radians(s_deg + e_deg)
    
    # Calculate torque factors based on horizontal projection (cosine of angle relative to horizontal plane)
    ff_s = K_S1 * math.cos(s_rad) + K_S2 * math.cos(se_rad)
    ff_e = K_E * math.cos(se_rad)
    
    # Clamping compensation to safe limits
    return {
        "b": 0.0,
        "s": max(0.0, min(12.0, ff_s)),
        "e": max(0.0, min(12.0, ff_e)),
        "h": 0.0
    }

def move_arm_to_angles(arm, angles, speed=0, acc=20):
    """Helper to send joint angle command using driver's serial connection with smooth ramping."""
    cmd = {
        "T": 122,
        "b": round(angles["b"], 1),
        "s": round(angles["s"], 1),
        "e": round(angles["e"], 1),
        "h": round(angles["h"], 1),
        "spd": speed,
        "acc": acc
    }
    arm._send_command(cmd, wait_time=0.05)

def run_physical_teach(arm):
    print("\n--- PHYSICAL TEACH MODE (Freedrive) ---")
    print("Disabling Torque...")
    arm.disable_torque()

    waypoints = []
    running = True
    live_pos = {}
    lock = threading.Lock()

    def poll_position():
        nonlocal live_pos
        while running:
            pos = get_live_angles(arm)
            if pos:
                with lock:
                    live_pos = pos
            time.sleep(0.15)

    poller = threading.Thread(target=poll_position, daemon=True)
    poller.start()

    print("\n" + "=" * 50)
    print("  The arm is LIMP. Move it to desired positions by hand.")
    print("  Controls:")
    print("    [R] Record current position")
    print("    [F] Finish & Save")
    print("    [Q] Quit without saving")
    print("=" * 50 + "\n")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    should_save = False

    try:
        tty.setcbreak(fd)
        while running:
            with lock:
                b = live_pos.get('b', 0.0)
                s = live_pos.get('s', 0.0)
                e = live_pos.get('e', 0.0)
                h = live_pos.get('h', 0.0)

            status = f"  LIVE | Base: {b:>6.1f}  Shoulder: {s:>6.1f}  Elbow: {e:>6.1f}  Hand: {h:>6.1f}  | WPs: {len(waypoints)}"
            sys.stdout.write(f"\r{status}    ")
            sys.stdout.flush()

            if select.select([sys.stdin], [], [], 0.05)[0]:
                char = sys.stdin.read(1).lower()
                if char == 'r':
                    with lock:
                        if live_pos:
                            waypoints.append(dict(live_pos))
                            sys.stdout.write(f"\r\n  ✅ Recorded WP {len(waypoints)}: Base:{live_pos['b']:.1f} Shoulder:{live_pos['s']:.1f} Elbow:{live_pos['e']:.1f}\n")
                            sys.stdout.flush()
                elif char == 'f':
                    should_save = True
                    running = False
                elif char == 'q' or char == '\x03':
                    running = False

    except KeyboardInterrupt:
        running = False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        running = False
        poller.join(timeout=1.0)
        print("\nRe-enabling Torque...")
        arm.enable_torque()

    if should_save and waypoints:
        save_waypoints(waypoints)

def run_keyboard_teach(arm):
    print("\n--- KEYBOARD TEACH MODE (Jogging) ---")
    print("Syncing initial position...")
    angles = get_live_angles(arm)
    if not angles:
        print("[!] Failed to get initial position. Exiting.")
        return

    # Track target position desired by user
    desired = dict(angles)
    last_actual = dict(angles)

    # Blending offsets for smooth gravity feedback transitions
    target_feedback_offset = {"b": 0.0, "s": 0.0, "e": 0.0, "h": 0.0}
    active_feedback_offset = {"b": 0.0, "s": 0.0, "e": 0.0, "h": 0.0}

    # Initial lock command
    move_arm_to_angles(arm, desired, speed=0, acc=20)
    
    waypoints = []
    step_size = 2.0
    running = True

    print("\n" + "=" * 50)
    print("Controls:")
    print("  Base     : [A]/[D]")
    print("  Shoulder : [W]/[S]")
    print("  Elbow    : [I]/[K]")
    print("  Hand     : [J]/[L]")
    print("  ")
    print("  [R] Record | [F] Finish & Save | [Q] Quit without saving")
    print("=" * 50 + "\n")

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    should_save = False

    last_comp_time = time.time()
    last_jog_time = 0.0      # Timestamp of last user movement input
    last_move_key = None     # Track last pressed jog key to detect direction changes
    
    try:
        tty.setcbreak(fd)
        while running:
            # Main loop runs at 20Hz (every 50ms) to ensure smooth interpolation
            loop_start = time.time()

            # ── 1. Check Keyboard Input (Non-blocking) ──
            if select.select([sys.stdin], [], [], 0.01)[0]:
                keys = sys.stdin.read(1).lower()
                while select.select([sys.stdin], [], [], 0)[0]:
                    keys += sys.stdin.read(1).lower()

                moved = False
                char = keys[0]

                # Optimization: If key direction changes, instantly flush the input buffer
                if char in ['w', 's', 'a', 'd', 'i', 'k', 'j', 'l']:
                    if last_move_key and last_move_key != char:
                        try:
                            termios.tcflush(sys.stdin, termios.TCIFLUSH)
                        except Exception:
                            pass
                    last_move_key = char

                for c in keys:
                    if c == 'q':
                        running = False
                    elif c == 'a': desired["b"] += step_size; moved = True
                    elif c == 'd': desired["b"] -= step_size; moved = True
                    elif c == 'w': desired["s"] += step_size; moved = True
                    elif c == 's': desired["s"] -= step_size; moved = True
                    elif c == 'i': desired["e"] -= step_size; moved = True
                    elif c == 'k': desired["e"] += step_size; moved = True
                    elif c == 'j': desired["h"] -= step_size; moved = True
                    elif c == 'l': desired["h"] += step_size; moved = True
                    elif c == 'r':
                        waypoints.append(desired.copy())
                        sys.stdout.write(f"\r\n  ✅ Recorded WP {len(waypoints)}: Base:{desired['b']:.1f} Shoulder:{desired['s']:.1f} Elbow:{desired['e']:.1f}\n")
                        sys.stdout.flush()
                    elif c == 'f':
                        should_save = True
                        running = False
                        break

                if moved:
                    last_jog_time = time.time()
                    desired["b"] = max(-180, min(180, desired["b"]))
                    desired["s"] = max(-90, min(90, desired["s"]))
                    desired["e"] = max(0, min(180, desired["e"]))
                    desired["h"] = max(45, min(315, desired["h"]))
                    
                    # Reset target feedback offset immediately during active jogs
                    for k in target_feedback_offset:
                        target_feedback_offset[k] = 0.0

            # ── 2. Active Feedback Error Calculation ──
            # Query physical position at 5Hz (every 200ms) to measure remaining error
            now = time.time()
            if now - last_comp_time >= 0.2:
                last_comp_time = now
                
                # Only check physical error if we aren't actively jogging (idle > 0.5s)
                if now - last_jog_time > 0.5:
                    actual = get_live_angles(arm)
                    
                    if actual and last_actual:
                        # Glitch Filtering
                        glitch = False
                        for key in ["b", "s", "e", "h"]:
                            if abs(actual[key] - last_actual[key]) > 15.0:
                                glitch = True
                                break
                        
                        if not glitch:
                            last_actual = dict(actual)
                            
                            # Calculate errors (desired - actual)
                            err_b = desired["b"] - actual["b"]
                            err_s = desired["s"] - actual["s"]
                            err_e = desired["e"] - actual["e"]
                            err_h = desired["h"] - actual["h"]
                            
                            # Proportional feedback correction gain (kp=0.5) for high precision
                            kp = 0.5
                            target_feedback_offset["b"] = max(-10.0, min(10.0, err_b * kp))
                            target_feedback_offset["s"] = max(-10.0, min(10.0, err_s * kp))
                            target_feedback_offset["e"] = max(-10.0, min(10.0, err_e * kp))
                            target_feedback_offset["h"] = max(-10.0, min(10.0, err_h * kp))
                else:
                    # While jogging, feedback offset decays back to 0
                    for k in target_feedback_offset:
                        target_feedback_offset[k] = 0.0

            # ── 3. Smooth Blending & Combined Control Output (20Hz) ──
            # 3a. Interpolate active feedback offset towards target (25% step size)
            for key in ["b", "s", "e", "h"]:
                active_feedback_offset[key] += 0.25 * (target_feedback_offset[key] - active_feedback_offset[key])
            
            # 3b. Calculate instant feedforward offset based on desired target
            ff = get_feedforward_offsets(desired)
            
            # 3c. Sum desired + feedback + feedforward to get final output
            compensated = {
                "b": desired["b"] + active_feedback_offset["b"] + ff["b"],
                "s": desired["s"] + active_feedback_offset["s"] + ff["s"],
                "e": desired["e"] + active_feedback_offset["e"] + ff["e"],
                "h": desired["h"] + active_feedback_offset["h"] + ff["h"]
            }
            
            # Stream control command
            move_arm_to_angles(arm, compensated, speed=0, acc=15)
            
            # Display target position status
            status = f"  LIVE | Base:{desired['b']:>5.1f} Shoulder:{desired['s']:>5.1f} Elbow:{desired['e']:>5.1f} Hand:{desired['h']:>5.1f}  | WPs: {len(waypoints)}"
            sys.stdout.write(f"\r{status}    ")
            sys.stdout.flush()

            # Hold loop rate at 20Hz (50ms interval)
            elapsed = time.time() - loop_start
            time.sleep(max(0.001, 0.05 - elapsed))

    except KeyboardInterrupt:
        running = False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print("\nLocking arm position...")
        arm.enable_torque()

    if should_save and waypoints:
        save_waypoints(waypoints)

def save_waypoints(waypoints):
    print("\n--- RECORDING FINISHED ---")
    
    # Flush terminal stdin buffer to discard buffered keys from jog entries
    try:
        import termios
        import sys
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass
        
    name = input("  Enter filename to save (default 'motion_path.json'): ").strip()
    if not name: name = 'motion_path.json'
    if not name.endswith('.json'): name += '.json'
    
    full_path = os.path.join(SCRIPT_DIR, name)
    with open(full_path, "w") as f:
        json.dump(waypoints, f, indent=4)
    print(f"  💾 Saved {len(waypoints)} waypoints to {full_path}.\n")

def main():
    print("Connecting to RoArm M2-S...")
    arm = RoArmDriver(port=PORT, baudrate=BAUD)
    try:
        arm.connect()
    except Exception:
        print(f"\n[!] Failed to connect to arm on {PORT}.")
        sys.exit(1)

    while True:
        print("\n===========================================")
        print("          TEACH MODE SELECTION           ")
        print("===========================================")
        print("[1] Physical Teach Mode (Freedrive)")
        print("[2] Keyboard Teach Mode (Jogging)")
        print("[Q] Exit")
        
        choice = input("Select an option: ").lower().strip()

        if choice == '1':
            run_physical_teach(arm)
            break
        elif choice == '2':
            run_keyboard_teach(arm)
            break
        elif choice == 'q':
            break
        else:
            print("Invalid option.")

    arm.disconnect()

if __name__ == "__main__":
    main()
