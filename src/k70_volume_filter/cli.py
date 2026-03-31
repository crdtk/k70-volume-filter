#!/usr/bin/env python3
"""
Filter for Corsair K70 TKL Champion volume wheel firmware bug.

The wheel sends bursts of mixed UP/DOWN events due to a firmware bug.
This filter grabs the raw input device, collects events into time-windowed
bursts, picks the majority direction, and emits clean volume events via
a virtual uinput device. All non-volume events pass through untouched.
"""

import argparse
import os
import shutil
import subprocess
import sys
import textwrap
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


SERVICE_NAME = "k70-volume-filter"
SERVICE_PATH = f"/etc/systemd/system/{SERVICE_NAME}.service"
UDEV_RULES_PATH = "/etc/udev/rules.d/99-k70-volume-filter.rules"


def _find_executable():
    path = shutil.which("k70-volume-filter")
    if path:
        return path
    return os.path.abspath(sys.argv[0])


def _generate_service(exe_path):
    return textwrap.dedent(f"""\
        [Unit]
        Description=Corsair K70 TKL Champion Volume Wheel Filter
        After=multi-user.target

        [Service]
        Type=simple
        ExecStart={exe_path}
        Restart=on-failure
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
    """)


UDEV_RULES = textwrap.dedent("""\
    # Allow k70-volume-filter to access the Corsair K70 TKL Champion input device
    SUBSYSTEM=="input", ATTRS{idVendor}=="1b1c", ATTRS{idProduct}=="1bb9", MODE="0660", TAG+="uaccess"
    # Allow uinput access for creating virtual devices
    KERNEL=="uinput", MODE="0660", TAG+="uaccess"
""")


def install_service():
    if os.geteuid() != 0:
        sys.exit("Error: install must be run as root (sudo k70-volume-filter install)")

    exe = _find_executable()
    print(f"Executable: {exe}")

    # Write service file
    with open(SERVICE_PATH, "w") as f:
        f.write(_generate_service(exe))
    print(f"Created {SERVICE_PATH}")

    # Write udev rules
    with open(UDEV_RULES_PATH, "w") as f:
        f.write(UDEV_RULES)
    print(f"Created {UDEV_RULES_PATH}")

    # Reload and enable
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["udevadm", "trigger"], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", SERVICE_NAME], check=True)
    print(f"\nService '{SERVICE_NAME}' installed and started.")
    print(f"Check status: systemctl status {SERVICE_NAME}")


def uninstall_service():
    if os.geteuid() != 0:
        sys.exit("Error: uninstall must be run as root (sudo k70-volume-filter uninstall)")

    subprocess.run(["systemctl", "disable", "--now", SERVICE_NAME], check=False)

    for path in (SERVICE_PATH, UDEV_RULES_PATH):
        if os.path.exists(path):
            os.remove(path)
            print(f"Removed {path}")

    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print(f"\nService '{SERVICE_NAME}' uninstalled.")


def main():
    parser = argparse.ArgumentParser(
        description="Filter for Corsair K70 TKL Champion volume wheel firmware bug"
    )
    sub = parser.add_subparsers(dest="command")

    # install / uninstall subcommands
    sub.add_parser("install", help="Install systemd service and udev rules")
    sub.add_parser("uninstall", help="Remove systemd service and udev rules")

    # run subcommand (default)
    run_parser = sub.add_parser("run", help="Run the filter (default)")
    run_parser.add_argument(
        "--burst-window",
        type=float,
        default=DEFAULT_BURST_WINDOW,
        help=f"Burst collection window in seconds (default: {DEFAULT_BURST_WINDOW})",
    )
    run_parser.add_argument(
        "--divisor",
        type=int,
        default=DEFAULT_DIVISOR,
        help=f"Divide total raw events by this for tick count (default: {DEFAULT_DIVISOR})",
    )
    run_parser.add_argument(
        "--max-ticks",
        type=int,
        default=DEFAULT_MAX_TICKS,
        help=f"Maximum ticks per burst (default: {DEFAULT_MAX_TICKS})",
    )
    run_parser.add_argument(
        "--device-name",
        default=DEVICE_NAME,
        help="Input device name to filter",
    )
    run_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print event details",
    )

    # Also add run args to main parser for when no subcommand is given
    parser.add_argument("--burst-window", type=float, default=DEFAULT_BURST_WINDOW)
    parser.add_argument("--divisor", type=int, default=DEFAULT_DIVISOR)
    parser.add_argument("--max-ticks", type=int, default=DEFAULT_MAX_TICKS)
    parser.add_argument("--device-name", default=DEVICE_NAME)
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.command == "install":
        install_service()
    elif args.command == "uninstall":
        uninstall_service()
    else:
        run_filter(args.burst_window, args.divisor, args.max_ticks, args.device_name, args.verbose)


if __name__ == "__main__":
    main()
