#!/usr/bin/env python3
"""
Standalone check of the NI USB-6501 on macOS, before wiring it into npu_task.py.

Runs in stages so you can see exactly where things break:
  1. libusb backend is loadable by PyUSB
  2. The USB-6501 is visible on the USB bus
  3. The ni-usb-6501 driver can connect and configure the port as output
  4. Read-back: writing a value to the port and reading it back matches
  5. Line scan: pulse each line of the port one at a time (watch SAGA / stimulator)
  6. Task codes: pulse the codes npu_task.py uses

Setup:
    brew install libusb
    pip install pyusb ni-usb-6501

Usage:
    python test_usb6501.py
"""

import sys
import time

# Must match the constants in npu_task.py
TTL_STARTLE = 4
TTL_SHOCK_MARKER = 2
TTL_SHOCK_TRIGGER = 8          # MATLAB_mn_stim.m: 8 fires the stimulator
TTL_PULSE_DURATION = 0.01

NI_VENDOR_ID = 0x3923
NI_6501_PRODUCT_ID = 0x718A
# MATLAB_mn_stim.m drives 'Dev2/Port1/Line0:7', so the splitter is wired to port 1.
# Override on the command line, e.g. `python test_usb6501.py 0`.
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1


def stage(n, msg):
    print(f"\n[{n}] {msg}")


def fail(msg):
    print(f"  FAILED: {msg}")
    sys.exit(1)


def pulse(dev, code, label):
    """Set port 0 to `code`, hold, then reset to 0. Reports write latency."""
    print(f"  Sending code {code:>3d} ({label})...", end=" ", flush=True)
    t0 = time.perf_counter()
    dev.write_port(PORT, code)
    t1 = time.perf_counter()
    time.sleep(TTL_PULSE_DURATION)
    dev.write_port(PORT, 0)
    print(f"done (write took {(t1 - t0) * 1000:.1f} ms)")


def main():
    # -- 1. libusb backend ---
    stage(1, "Checking PyUSB + libusb backend...")
    try:
        import usb.core
        import usb.backend.libusb1
    except ImportError:
        fail("pyusb not installed. Run: pip install pyusb")
    backend = usb.backend.libusb1.get_backend()
    if backend is None:
        fail("libusb not found. Run: brew install libusb\n"
             "  (On Apple Silicon, if it still fails, try:\n"
             "   export DYLD_LIBRARY_PATH=/opt/homebrew/lib)")
    print("  OK: libusb backend loaded")

    # -- 2. Device on the bus ---
    stage(2, "Looking for NI USB-6501 on the USB bus...")
    raw = usb.core.find(idVendor=NI_VENDOR_ID, idProduct=NI_6501_PRODUCT_ID,
                        backend=backend)
    if raw is None:
        ni = list(usb.core.find(find_all=True, idVendor=NI_VENDOR_ID, backend=backend))
        if ni:
            ids = ", ".join(f"0x{d.idProduct:04x}" for d in ni)
            fail(f"found NI device(s) with product ID {ids}, expected 0x718a")
        fail("not found. Check the cable/adapter and that it shows in System Information > USB")
    print(f"  OK: found device (bus {raw.bus}, address {raw.address})")

    # -- 3. Driver connect + configure ---
    stage(3, "Connecting with ni-usb-6501 driver...")
    try:
        import ni_usb_6501.driver as ni_driver
    except ImportError:
        fail("ni-usb-6501 not installed. Run: pip install ni-usb-6501")
    ni_driver.time = time  # driver's retry path uses `time` without importing it
    try:
        dev = ni_driver.NIUSB6501()
        modes = [0x00, 0x00, 0x00]
        modes[PORT] = 0xFF  # selected port all outputs, others inputs
        dev.set_io_mode(*modes)
        dev.write_port(PORT, 0)
    except Exception as e:
        fail(f"{type(e).__name__}: {e}\n"
             "  If this is an access/permission error, try running once with sudo\n"
             "  to confirm, then let me know.")
    print(f"  OK: connected, port {PORT} set to output, all lines low")

    try:
        # -- 4. Read-back ---
        stage(4, f"Write/read-back test on port {PORT} (no pulses, lines go high briefly)...")
        mismatches = 0
        for val in (0x00, 0x55, 0xAA, 0x00):
            dev.write_port(PORT, val)
            got = dev.read_port(PORT)
            ok = got == val
            mismatches += not ok
            print(f"  wrote 0x{val:02X}, read 0x{got:02X}  {'OK' if ok else 'MISMATCH'}")
        if mismatches:
            print("  Note: read-back mismatch doesn't necessarily mean writes fail; "
                  "continue and watch the hardware.")
        dev.write_port(PORT, 0)

        # -- 5. Line scan ---
        stage(5, "Line scan: one line at a time. Watch SAGA and the stimulator.")
        print("  (Turn the stimulator output DOWN / disconnect the participant first!)")
        for line in range(8):
            code = 1 << line
            input(f"\n  ENTER to pulse P{PORT}.{line} (code {code})...")
            pulse(dev, code, f"P{PORT}.{line}")
            print("  -> Which device saw it: SAGA, stimulator, or neither?")

        # -- 6. Task codes ---
        stage(6, "Pulsing the codes npu_task.py uses...")
        input(f"\n  ENTER to send STARTLE (code {TTL_STARTLE} -> SAGA)...")
        pulse(dev, TTL_STARTLE, "startle -> SAGA")
        input(f"\n  ENTER to send SHOCK MARKER + TRIGGER "
              f"(code {TTL_SHOCK_MARKER} then {TTL_SHOCK_TRIGGER})...")
        pulse(dev, TTL_SHOCK_MARKER, "shock marker -> SAGA")
        pulse(dev, TTL_SHOCK_TRIGGER, "shock trigger -> stimulator")

        input("\n  ENTER to send 5 startle pulses, 1 s apart...")
        for i in range(5):
            pulse(dev, TTL_STARTLE, f"startle {i + 1}/5")
            if i < 4:
                time.sleep(1)

        print("\nAll tests complete.")

    finally:
        try:
            dev.write_port(PORT, 0)
            dev.release_interface()
        except Exception:
            pass
        print("Lines reset to 0, device released.")


if __name__ == "__main__":
    main()
