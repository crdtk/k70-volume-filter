#!/usr/bin/env python3
"""
Filter for Corsair K70 TKL Champion volume wheel firmware bug.

The wheel sends bursts of mixed UP/DOWN events due to a firmware bug.
This filter grabs the raw input device, collects events into time-windowed
bursts, picks the majority direction, and emits clean volume events via
a virtual uinput device. All non-volume events pass through untouched.
"""

import argparse
import sys
import threading
import evdev
from evdev import UInput, ecodes

DEVICE_NAME = "Corsair CORSAIR K70 RGB TKL CHAMPION SERIES Optical Mechanical Gaming Keyboard"
VOLUME_UP = ecodes.KEY_VOLUMEUP
VOLUME_DOWN = ecodes.KEY_VOLUMEDOWN

DEFAULT_BURST_WINDOW = 0.1
DEFAULT_DIVISOR = 3
DEFAULT_MAX_TICKS = 30


def find_device(device_name):
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        if dev.name == device_name:
            return dev
    return None


def run_filter(burst_window, divisor, max_ticks, device_name, verbose):
    dev = find_device(device_name)
    if not dev:
        print(f"Device not found: {device_name}", file=sys.stderr)
        sys.exit(1)

    print(f"Found: {dev.path} - {dev.name}")

    cap = dev.capabilities(verbose=False)
    cap.pop(ecodes.EV_SYN, None)

    ui = UInput(cap, name="K70 Filtered", vendor=0x1b1c, product=0x1bb9)
    print(f"Virtual device: {ui.device.path}")

    dev.grab()
    print("Filtering volume events. Press Ctrl+C to stop.\n")

    lock = threading.Lock()
    up_count = 0
    down_count = 0
    last_direction = None
    timer = None

    def flush():
        nonlocal up_count, down_count, last_direction
        with lock:
            u, d = up_count, down_count
            up_count = 0
            down_count = 0

        if u == 0 and d == 0:
            return

        if u > d:
            real_code = VOLUME_UP
            real_dir = "UP"
        elif d > u:
            real_code = VOLUME_DOWN
            real_dir = "DOWN"
        elif last_direction is not None:
            real_code = VOLUME_UP if last_direction == "UP" else VOLUME_DOWN
            real_dir = last_direction
        else:
            return

        last_direction = real_dir

        total = u + d
        ticks = max(1, total // divisor)
        ticks = min(ticks, max_ticks)
        for _ in range(ticks):
            ui.write(ecodes.EV_KEY, real_code, 1)
            ui.syn()
            ui.write(ecodes.EV_KEY, real_code, 0)
            ui.syn()

        if verbose:
            noise = min(u, d)
            ratio = f"{max(u,d)}:{min(u,d)}" if min(u, d) > 0 else "clean"
            print(
                f"  VOL {real_dir:4s} | ticks={ticks:2d} | "
                f"raw: up={u:3d} down={d:3d} total={total:3d} | "
                f"noise={noise:3d} ratio={ratio}"
            )

    try:
        for event in dev.read_loop():
            if event.type != ecodes.EV_KEY or event.code not in (VOLUME_UP, VOLUME_DOWN):
                ui.write_event(event)
                ui.syn()
                continue

            if event.value != 1:
                continue

            with lock:
                if event.code == VOLUME_UP:
                    up_count += 1
                else:
                    down_count += 1

                if timer is not None:
                    timer.cancel()
                timer = threading.Timer(burst_window, flush)
                timer.daemon = True
                timer.start()

    except KeyboardInterrupt:
        if timer is not None:
            timer.cancel()
        flush()
        print("\nStopped.")
    finally:
        dev.ungrab()
        ui.close()


def main():
    parser = argparse.ArgumentParser(
        description="Filter for Corsair K70 TKL Champion volume wheel firmware bug"
    )
    parser.add_argument(
        "--burst-window",
        type=float,
        default=DEFAULT_BURST_WINDOW,
        help=f"Burst collection window in seconds (default: {DEFAULT_BURST_WINDOW})",
    )
    parser.add_argument(
        "--divisor",
        type=int,
        default=DEFAULT_DIVISOR,
        help=f"Divide total raw events by this for tick count (default: {DEFAULT_DIVISOR})",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=DEFAULT_MAX_TICKS,
        help=f"Maximum ticks per burst (default: {DEFAULT_MAX_TICKS})",
    )
    parser.add_argument(
        "--device-name",
        default=DEVICE_NAME,
        help="Input device name to filter",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print event details",
    )
    args = parser.parse_args()

    run_filter(args.burst_window, args.divisor, args.max_ticks, args.device_name, args.verbose)


if __name__ == "__main__":
    main()
