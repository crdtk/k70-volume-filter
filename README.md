# k70-volume-filter

Input filter for the Corsair K70 RGB TKL Champion Series volume wheel firmware bug on Linux.

## Problem

The K70 TKL Champion (USB `1b1c:1bb9`) volume wheel sends bursts of mixed `KEY_VOLUMEUP` and `KEY_VOLUMEDOWN` events due to a firmware bug. The Linux `hid-generic` driver passes these through as-is, causing erratic volume behavior.

## Solution

This tool grabs the raw input device, collects events into time-windowed bursts, determines the intended direction by majority vote, and emits clean volume events via a virtual `uinput` device. All non-volume keyboard events pass through untouched.

## Install

```bash
uv tool install git+https://github.com/crdtk/k70-volume-filter.git
```

From source:

```bash
git clone https://github.com/crdtk/k70-volume-filter.git
cd k70-volume-filter
uv tool install -e .
```

## Usage

Make sure `ckb-next-daemon` is stopped first:

```bash
sudo systemctl stop ckb-next-daemon
```

Run the filter (requires root for input device access):

```bash
sudo k70-volume-filter
```

With verbose logging:

```bash
sudo k70-volume-filter -v
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--burst-window` | `0.1` | Burst collection window in seconds |
| `--divisor` | `3` | Divide total raw events by this for tick count |
| `--max-ticks` | `30` | Maximum ticks emitted per burst |
| `--device-name` | auto-detected | Override input device name |
| `-v, --verbose` | off | Print event details |

## Run as a systemd service

Install the service and udev rules:

```bash
sudo k70-volume-filter install
```

Check status:

```bash
systemctl status k70-volume-filter
```

Uninstall:

```bash
sudo k70-volume-filter uninstall
```

## License

MIT
