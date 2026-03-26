#!/usr/bin/env python3
"""
Quick trigger test for the NPU serial TTL setup.

Sends each TTL code in sequence so you can verify that the SAGA system
and stimulator are receiving the correct signals before running the full task.

Usage:
    python test_triggers.py

The script will auto-detect serial ports, let you pick one, then cycle
through each trigger type with pauses so you can confirm reception.
"""

import time
import serial
import serial.tools.list_ports

# Must match the constants in npu_task.py
SERIAL_BAUD = 9600
TTL_STARTLE = 4
TTL_SHOCK_MARKER = 2
TTL_SHOCK_TRIGGER = 8
TTL_PULSE_DURATION = 0.01


def pulse(ser, code, label):
    """Send a single TTL pulse and print what was sent."""
    print(f"  Sending code {code} ({label})...", end=" ", flush=True)
    ser.write(bytes([code]))
    ser.flush()
    time.sleep(TTL_PULSE_DURATION)
    ser.write(bytes([0x00]))
    ser.flush()
    print("done")


def pick_port():
    """List available serial ports and let the user choose."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports detected.")
        return None

    print("Available serial ports:")
    for i, p in enumerate(ports):
        print(f"  {i + 1}) {p.device}  ({p.description})")

    while True:
        choice = input(f"\nSelect port (1-{len(ports)}), or 'q' to quit: ").strip()
        if choice.lower() == "q":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx].device
        except ValueError:
            pass
        print("Invalid selection, try again.")


def main():
    port = pick_port()
    if not port:
        return

    print(f"\nOpening {port} @ {SERIAL_BAUD} baud...")
    ser = serial.Serial(port, SERIAL_BAUD)
    ser.flush()
    print("Connected.\n")

    try:
        # -- Test 1: Startle probe TTL ---
        input("Press ENTER to send STARTLE probe (code 4 -> SAGA)...")
        pulse(ser, TTL_STARTLE, "startle -> SAGA")
        print("  -> Verify: SAGA should have received a TTL on bit 2 (code 4)\n")

        time.sleep(1)

        # -- Test 2: Shock marker TTL ---
        input("Press ENTER to send SHOCK MARKER (code 2 -> SAGA)...")
        pulse(ser, TTL_SHOCK_MARKER, "shock marker -> SAGA")
        print("  -> Verify: SAGA should have received a TTL on bit 1 (code 2)\n")

        time.sleep(1)

        # -- Test 3: Shock trigger TTL ---
        input("Press ENTER to send SHOCK TRIGGER (code 8 -> stimulator)...")
        pulse(ser, TTL_SHOCK_TRIGGER, "shock trigger -> stimulator")
        print("  -> Verify: stimulator should have received a TTL on bit 3 (code 8)\n")

        time.sleep(1)

        # -- Test 4: Full shock sequence (marker then trigger) ---
        input("Press ENTER to send FULL SHOCK SEQUENCE (code 2 then code 8)...")
        pulse(ser, TTL_SHOCK_MARKER, "shock marker -> SAGA")
        pulse(ser, TTL_SHOCK_TRIGGER, "shock trigger -> stimulator")
        print("  -> Verify: SAGA got code 2, then stimulator got code 8\n")

        time.sleep(1)

        # -- Test 5: Rapid repeat ---
        input("Press ENTER to send 5 rapid startle probes (1s apart)...")
        for i in range(5):
            print(f"  Probe {i + 1}/5")
            pulse(ser, TTL_STARTLE, "startle -> SAGA")
            if i < 4:
                time.sleep(1)
        print("  -> Verify: SAGA received 5 TTLs\n")

        print("All tests complete.")

    finally:
        ser.write(bytes([0x00]))
        ser.flush()
        ser.close()
        print("Serial port closed.")


if __name__ == "__main__":
    main()
