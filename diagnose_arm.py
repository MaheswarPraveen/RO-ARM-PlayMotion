#!/usr/bin/env python3
"""
Diagnostic v2: Uses a proper read loop with longer waits.
"""
import serial
import json
import time

PORT = '/dev/ttyUSB0'
BAUD = 115200

def send_and_dump(ser, cmd, label):
    print(f"\n{'='*50}")
    print(f"  Sending: {label}")
    print(f"  Command: {json.dumps(cmd)}")
    print(f"{'='*50}")
    
    # Flush everything
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.1)
    
    # Send command
    payload = json.dumps(cmd) + '\n'
    ser.write(payload.encode('ascii'))
    ser.flush()
    
    # Read for 3 full seconds using readline timeout
    lines_read = 0
    end_time = time.time() + 3.0
    while time.time() < end_time:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        if line:
            lines_read += 1
            print(f"  RAW [{lines_read}]: {line}")
            try:
                parsed = json.loads(line)
                print(f"  PARSED KEYS: {list(parsed.keys())}")
            except json.JSONDecodeError:
                pass
    
    if lines_read == 0:
        print("  (no response in 3 seconds)")

def main():
    print(f"Connecting to {PORT} at {BAUD} baud...")
    ser = serial.Serial(PORT, BAUD, timeout=0.5)
    time.sleep(2)
    
    # Drain any boot messages
    print("Draining boot messages for 2 seconds...")
    end_time = time.time() + 2.0
    boot_lines = 0
    while time.time() < end_time:
        line = ser.readline().decode('utf-8', errors='replace').strip()
        if line:
            boot_lines += 1
            print(f"  BOOT [{boot_lines}]: {line}")
    print(f"  ({boot_lines} boot messages)")
    
    # Test commands
    send_and_dump(ser, {"T": 210, "cmd": 0}, "DISABLE TORQUE")
    send_and_dump(ser, {"T": 105}, "XYZ FEEDBACK")
    
    print("\n\nMove the arm now (3 seconds)...")
    time.sleep(3)
    
    send_and_dump(ser, {"T": 105}, "XYZ FEEDBACK AFTER MOVE")

    ser.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
