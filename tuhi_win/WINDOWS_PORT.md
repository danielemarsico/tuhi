# Tuhi Windows Port

## Overview

This port enables Tuhi to run on Windows by replacing all Linux-specific
dependencies with cross-platform alternatives. The original Linux code is
preserved unchanged.

## Architecture

| Linux Component | Windows Replacement | File |
|---|---|---|
| BlueZ (BLE) | bleak library | `tuhi/ble_bleak.py` |
| D-Bus (IPC) | JSON-RPC over TCP | `tuhi/ipc_server.py`, `tuhi/ipc_client.py` |
| UHID (/dev/uhid) | Logging stub | `tuhi/uhid_win.py` |
| GObject/GLib | Custom signal system | `tuhi/gobject_compat.py` |
| XDG directories | %APPDATA%/tuhi | `tuhi/config_win.py` |
| pycairo (PNG) | Pillow | `tuhi/export_win.py` |
| GTK GUI | CLI interface | `tuhi_cli.py` |

## New Files

- **`tuhi/gobject_compat.py`** - Lightweight GObject replacement providing signals, properties, and timer management
- **`tuhi/ble_bleak.py`** - BLE backend using bleak (BleakDeviceManager, BleakBLEDevice, BleakCharacteristic)
- **`tuhi/uhid_win.py`** - UHID stub that logs pen events (live mode pen injection not available on Windows)
- **`tuhi/ipc_server.py`** - JSON-RPC TCP server on localhost:48150 (replaces D-Bus session bus)
- **`tuhi/ipc_client.py`** - JSON-RPC TCP client
- **`tuhi/config_win.py`** - Config using %APPDATA%/tuhi instead of XDG
- **`tuhi/drawing_win.py`** - Drawing model without gi.repository dependency
- **`tuhi/wacom_win.py`** - Wacom protocol (same logic, Windows-compatible imports)
- **`tuhi/base_win.py`** - Orchestrator using Windows backends
- **`tuhi/export_win.py`** - SVG/PNG export using svgwrite + Pillow
- **`tuhi_windows.py`** - Server entry point
- **`tuhi_cli.py`** - CLI client (list/search/listen/fetch commands)

## Installation

```
pip install -r requirements-windows.txt
```

Requirements: `bleak`, `svgwrite`, `Pillow`. Python 3.12+.

## Usage

### Start the server
```
python tuhi_windows.py
```

### Use the CLI client
```
python tuhi_cli.py list              # List registered devices
python tuhi_cli.py search            # Search for devices
python tuhi_cli.py search --register # Search and auto-register
python tuhi_cli.py listen XX:XX:...  # Listen for drawings
python tuhi_cli.py fetch XX:XX:...   # Fetch drawings
python tuhi_cli.py fetch XX:XX:... --svg  # Fetch + export SVG
```

## Data Storage

Drawings and config are stored in `%APPDATA%\tuhi\`:
```
C:\Users\<user>\AppData\Roaming\tuhi\
  XX:XX:XX:XX:XX:XX/
    settings.ini
    <timestamp>.json
    raw/log-*.yaml
  session-logs/
    tuhi-*.log
```

## Limitations

- **Live mode**: Pen data is logged but NOT injected into the system.
  Windows has no equivalent of Linux's `/dev/uhid`. A future integration
  with ViGEmBus or a custom HID minidriver could enable this.
- **No GTK GUI**: The GTK-based GUI is replaced by a CLI client. A native
  Windows GUI could be built with tkinter, Qt, or WinUI.
- **BLE stability**: bleak uses the Windows Bluetooth API, which may behave
  differently from BlueZ. Connection reliability depends on the Windows
  Bluetooth stack and driver quality.

## Compatibility

The original Linux codebase is completely untouched. All new Windows code
lives in separate files (`*_win.py`, `ble_bleak.py`, `ipc_*.py`, etc.).
