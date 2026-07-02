#!/usr/bin/env python3
"""
play.py — Butter-Smooth Path Playback for RoArm M2-S
Uses Python-side Quintic Trajectory Interpolation, High-Frequency Streaming (25Hz),
and Feedforward Gravity Compensation.
Includes safety limits to prevent servo thermal shutdown.
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

# Get the script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = SCRIPT_DIR

# ─────────────────────────────────────────────────────────
# GRAVITY COMPENSATOR CONSTANTS
# ─────────────────────────────────────────────────────────
# Baseline joint offsets in degrees when arm links are horizontal (maximum torque)
K_S1 = 4.0  # Shoulder self-weight compensation coefficient
K_S2 = 6.0  # Forearm/Hand leverage compensation coefficient on Shoulder
K_E  = 5.0  # Elbow leverage compensation coefficient

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

def send_raw_cmd(driver, cmd_dict):
    """Directly writes command to serial port and clears the RX buffer to prevent congestion."""
    if not driver.ser or not driver.ser.is_open:
        return
    payload = json.dumps(cmd_dict) + '\n'
    driver.ser.write(payload.encode('ascii'))
    driver.ser.flush()
    driver.ser.reset_input_buffer()

def normalize_waypoint(pos):
    """Detects format and returns joint angles normalized to degrees."""
    if "b" in pos:
        b_val = pos["b"]
        s_val = pos["s"]
        e_val = pos["e"]
        h_val = pos.get("h", pos.get("t", 0.0))
        
        # Auto-detect radians vs degrees
        is_radians = False
        if "h" not in pos or max(abs(b_val), abs(s_val), abs(e_val)) <= math.pi:
            is_radians = True
        
        if is_radians:
            return {
                "b": math.degrees(b_val),
                "s": math.degrees(s_val),
                "e": math.degrees(e_val),
                "h": math.degrees(h_val)
            }
        else:
            return {
                "b": b_val,
                "s": s_val,
                "e": e_val,
                "h": h_val
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

def stream_segment(driver, start_pos, end_pos, speed_deg_s, dt=0.04):
    """
    Interpolates between start_pos and end_pos using a Quintic Polynomial profile,
    applies feedforward gravity compensation, and streams commands at 25Hz.
    Uses 4 decimal places of precision to prevent quantization jitter.
    """
    db = end_pos["b"] - start_pos["b"]
    ds = end_pos["s"] - start_pos["s"]
    de = end_pos["e"] - start_pos["e"]
    dh = end_pos["h"] - start_pos["h"]
    
    max_diff = max(abs(db), abs(ds), abs(de), abs(dh))
    if max_diff < 0.1:
        return  # No significant movement
    
    # Calculate duration of this segment based on speed
    T = max_diff / speed_deg_s
    
    steps = int(T / dt)
    if steps < 1:
        steps = 1
        
    for k in range(1, steps + 1):
        t_start = time.time()
        
        # Normalized time (0.0 to 1.0)
        u = k / steps
        
        # Quintic profile (zero velocity and zero acceleration at start/end)
        s_u = 10 * (u**3) - 15 * (u**4) + 6 * (u**5)
        
        # Interpolate target angles
        curr_b = start_pos["b"] + db * s_u
        curr_s = start_pos["s"] + ds * s_u
        curr_e = start_pos["e"] + de * s_u
        curr_h = start_pos["h"] + dh * s_u
        
        target_angles = {
            "b": curr_b,
            "s": curr_s,
            "e": curr_e,
            "h": curr_h
        }
        
        # Calculate feedforward gravity compensation offsets
        ff = get_feedforward_offsets(target_angles)
        
        # Construct final command (target + feedforward correction with high precision)
        cmd = {
            "T": 122,
            "b": round(curr_b + ff["b"], 4),
            "s": round(curr_s + ff["s"], 4),
            "e": round(curr_e + ff["e"], 4),
            "h": round(curr_h + ff["h"], 4),
            "spd": 0,  # Execute step immediately (speed controlled by Python)
            "acc": 0   # Execute step immediately (acceleration controlled by Python)
        }
        
        send_raw_cmd(driver, cmd)
        
        # Keep fixed frequency (25Hz / 40ms)
        elapsed = time.time() - t_start
        sleep_time = max(0, dt - elapsed)
        time.sleep(sleep_time)

def play_recording(driver, filename, loop=False, speed_deg_s=30.0):
    # Enforce minimum speed limit to prevent thermal shutdown on the sideways base joint
    if speed_deg_s < 10.0:
        print(f"\n⚠️  [WARNING] Speed {speed_deg_s}°/s is below the safety threshold.")
        print("    Capping speed at 10.0°/s to prevent servo thermal shutdown.")
        speed_deg_s = 10.0

    try:
        with open(filename, 'r') as f:
            raw_waypoints = json.load(f)
    except Exception as e:
        print(f"Error reading {filename}: {e}"); return

    # Normalize all waypoints to degrees
    waypoints = []
    for wp in raw_waypoints:
        norm = normalize_waypoint(wp)
        if norm:
            waypoints.append(norm)

    if not waypoints:
        print("No valid joint waypoints found in file."); return

    driver.enable_torque()
    print(f"\n🚀 Executing {os.path.basename(filename)} ({len(waypoints)} points)...")
    print(f"   Trajectory Speed: {speed_deg_s}°/s")
    print("   Gravity Compensation: Active (Feedforward)")
    print("   (Press Ctrl+C to stop)")

    # 1. Safety: Get current physical position and transition smoothly to WP 0
    print("Syncing with current arm position...")
    curr = driver.get_xyz()
    if curr and 'b' in curr:
        start_pos = {
            "b": math.degrees(curr["b"]),
            "s": math.degrees(curr["s"]),
            "e": math.degrees(curr["e"]),
            "h": math.degrees(curr["t"])
        }
        print("Smoothly moving from current position to first waypoint...")
        stream_segment(driver, start_pos, waypoints[0], speed_deg_s=20.0)  # Safe slow transition speed
        time.sleep(0.2)

    cycle = 1
    try:
        while True:
            if loop:
                print(f"\n--- PLAYING LOOP {cycle} ---")
            
            # Follow the path smoothly
            for i in range(len(waypoints) - 1):
                sys.stdout.write(f"\rWP {i+1} -> {i+2} / {len(waypoints)} | Loop {cycle}      ")
                sys.stdout.flush()
                
                start_wp = waypoints[i]
                end_wp = waypoints[i+1]
                
                stream_segment(driver, start_wp, end_wp, speed_deg_s=speed_deg_s)
                
            if not loop:
                print("\nPlayback complete!")
                break
                
            # If looping, smoothly glide from the last point back to the first point
            sys.stdout.write(f"\rGliding back to start... | Loop {cycle}      ")
            sys.stdout.flush()
            stream_segment(driver, waypoints[-1], waypoints[0], speed_deg_s=speed_deg_s)
            time.sleep(0.2)  # Brief pause before starting next loop
            
            cycle += 1
    except KeyboardInterrupt:
        print("\n\n🛑 Playback stopped by user.")

def main():
    print("=" * 50)
    print("  🤖 RO-ARM PLAYMOTION : TRAJECTORY STREAMING")
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
            
            # 4. Speed Options (Keep interface simple matching original)
            print("\nMOTOR SPEED SETTINGS (in degrees/second):")
            print("  10  = Very Slow (Safety Minimum)")
            print("  30  = Moderate / Normal [Default]")
            print("  60  = Fast")
            print("  100 = Extremely Fast")
            speed_input = input("Enter trajectory speed [default: 30.0]: ").strip()
            speed_deg_s = float(speed_input) if speed_input else 30.0
            
            loop = input("Play continuously in a loop? (y/n) [default: n]: ").lower() == 'y'
            
            # 5. Play!
            play_recording(driver, target_file, loop, speed_deg_s)
            
        except ValueError:
            print("Please enter valid numbers.")
        except Exception as e:
            print(f"An error occurred: {e}")

    driver.disconnect()
    print("\nGoodbye.")

if __name__ == "__main__":
    main()
