# Tuhi Windows Port

## Overview

This port enables Tuhi to run on Windows by replacing all Linux-specific
dependencies with cross-platform alternatives. The original Linux code is
preserved unchanged.

## Architecture

| Linux Component | Windows Replacement | File |
|---|---|---|
| BlueZ (BLE) | bleak library | `tuhi/ble_bleak.py` |
| D-Bus (IPC) | Direct in-process calls | `tuhi/app.py` |
| UHID (/dev/uhid) | Logging stub | `tuhi/uhid_win.py` |
| GObject/GLib | Custom signal system | `tuhi/gobject_compat.py` |
| XDG directories | %APPDATA%/tuhi | `tuhi/config_win.py` |
| pycairo (PNG) | Pillow | `tuhi/export_win.py` |
| GTK GUI | CLI interface | `tuhi_cli.py` |

## Single-Process Architecture

All components run in a single Python process.  There is no daemon and no
network socket.  The CLI creates a `TuhiApp`, calls `start()` (which spins
up a background asyncio event loop for BLE via bleak), does its work, then
calls `stop()`.

```
┌──────────────────────────────────────────────────────────────┐
│                        tuhi_cli.py                           │
│                                                              │
│  cmd_list()  cmd_search()  cmd_listen()  cmd_fetch()         │
│       │            │             │             │             │
│       └────────────┴─────────────┴─────────────┘            │
│                         TuhiApp                              │
│                         (tuhi/app.py)                        │
│                              │                               │
│                         AppDevice                            │
│                         (per device, in-process state)       │
│                              │                               │
│                         TuhiDevice                           │
│                         (tuhi/base_win.py)                   │
│                              │                               │
│                         WacomDevice                          │
│              WacomProtocolSlate / IntuosPro / Spark          │
│                              │                               │
│                         BleakDeviceManager                   │
│                         BleakBLEDevice                       │
│                         BleakCharacteristic                  │
└──────────────────────────────┬───────────────────────────────┘
                               │  BLE (bleak / Windows Bluetooth API)
                               │
                        ┌──────┴──────┐
                        │ Wacom device │
                        │  (Bamboo,   │
                        │   Slate,    │
                        │  Intuos Pro)│
                        └─────────────┘
```

### Key objects

| Class | File | Role |
|---|---|---|
| `TuhiApp` | `tuhi/app.py` | Orchestrates BLE + config; public CLI API |
| `AppDevice` | `tuhi/app.py` | Per-device in-process state (replaces IPC proxy) |
| `TuhiDevice` | `tuhi/base_win.py` | Wires BleakBLEDevice to AppDevice; drives Wacom protocol |
| `BleakDeviceManager` | `tuhi/ble_bleak.py` | BLE scanning and connection (asyncio in background thread) |
| `TuhiConfig` | `tuhi/config_win.py` | Config/drawing persistence in `%APPDATA%\tuhi` |

---

## Usage

```
python tuhi_cli.py list                        # List registered devices
python tuhi_cli.py search                      # Search for unregistered devices
python tuhi_cli.py search --register           # Search and register the first found device
python tuhi_cli.py listen XX:XX:XX:XX:XX:XX    # Listen for drawings (sync on button press)
python tuhi_cli.py fetch  XX:XX:XX:XX:XX:XX    # Export stored drawings as JSON
python tuhi_cli.py fetch  XX:XX:XX:XX:XX:XX --svg  # Export as JSON + SVG
```

---

## Step-by-Step Flows

### 1. Device Registration (first-time pairing)

```
tuhi_cli.py (TuhiApp)                        Wacom device
    │                                              │
    │  search(timeout, on_found)                   │
    │── BLE scan start ─────────────────────────>  │
    │                                              │
    │                        <─ advertisement ────│
    │                           (mfr_data len=4   │
    │                            = pairing mode)  │
    │                                              │
    │  _add_device() → TuhiDevice(REGISTER)        │
    │  on_found("Found: <addr>")                   │
    │                                              │
    │  register(address, on_button_press)          │
    │── BLE connect ────────────────────────────> │
    │                         <─ connected ───────│
    │                                              │
    │── REGISTER_PRESS_BUTTON ──────────────────> │
    │  on_button_press() → "[Press the button]"    │
    │                         <─ button press ────│
    │                                              │
    │                           determine protocol │
    │── SET_TIME / GET_TIME / GET_FIRMWARE ──────> │
    │── GET_BATTERY ────────────────────────────> │
    │                                              │
    │                           save settings.ini  │
    │── BLE disconnect ─────────────────────────> │
    │  "Registration complete."                    │
```

### 2. Fetching Drawings (listen / sync)

```
tuhi_cli.py (TuhiApp)                        Wacom device
    │                                              │
    │  start_listening(address, on_drawings)       │
    │── BLE scan start ─────────────────────────> │
    │                                              │
    │                        <─ advertisement ────│
    │                           (device in config) │
    │                                              │
    │── BLE connect ────────────────────────────> │
    │                         <─ connected ───────│
    │                                              │
    │── SET_TIME / GET_BATTERY / GET_FIRMWARE ──> │
    │── SELECT_GATT ────────────────────────────> │
    │                                              │
    │                        <─ offline pen data ─│
    │                           (stroke packets)  │
    │                                              │
    │  parse strokes → save <timestamp>.json       │
    │  on_drawings(app_dev)                        │
    │── BLE disconnect ─────────────────────────> │
```

### 3. Exporting Drawings

Drawings are read directly from disk — no BLE needed:

```python
app = TuhiApp()
app.start()
drawings = app.config.load_drawings(address)  # returns list of Drawing objects
for d in drawings:
    print(d.to_json())
app.stop()
```

---

## Data Storage

Drawings and config are stored in `%APPDATA%\tuhi\`:

```
C:\Users\<user>\AppData\Roaming\tuhi\
  F4_21_DE_4D_26_BF\          ← BT address with _ instead of :
    settings.ini               ← address, UUID, protocol, name
    <timestamp>.json           ← one file per drawing
    raw\
      log-*.yaml               ← raw BLE protocol log
  session-logs\
    tuhi-YY-MM-DD-HH-MM-SS.log
  cached_uuid.txt              ← registration UUID cache
```

---

## New Files

| File | Purpose |
|---|---|
| `tuhi/app.py` | `TuhiApp` (orchestrator) and `AppDevice` (in-process device state) |
| `tuhi/gobject_compat.py` | Lightweight GObject replacement (signals, properties, timers) |
| `tuhi/ble_bleak.py` | BLE backend using bleak (`BleakDeviceManager`, `BleakBLEDevice`, `BleakCharacteristic`) |
| `tuhi/uhid_win.py` | UHID stub — logs pen events; live mode pen injection not available on Windows |
| `tuhi/config_win.py` | Config using `%APPDATA%\tuhi` instead of XDG |
| `tuhi/drawing_win.py` | Drawing model without `gi.repository` |
| `tuhi/wacom_win.py` | Wacom protocol (same logic, Windows-compatible imports) |
| `tuhi/base_win.py` | `TuhiDevice` — wires BLE device to AppDevice and drives Wacom protocol |
| `tuhi/export_win.py` | SVG/PNG export using svgwrite + Pillow |
| `tuhi_cli.py` | CLI entry point |

## Installation

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-windows.txt
.venv\Scripts\python tuhi_cli.py list
```

Requirements: `bleak`, `svgwrite`, `Pillow`. Python 3.12+.

## Known Issues / Design Notes

### BLE connection guard (`ble_bleak.py`)
BLE advertisements arrive ~10× per second during scanning. Each `device-updated`
event triggers `_add_device` → `d.listen()` → `connect_device()`. Without a guard,
every advertisement spawned a new connection thread, each overwriting the shared
`_bleak_client` reference before the previous thread finished connecting — causing
bleak to raise *"Service Discovery has not been performed yet"*.

**Fix:** `BleakBLEDevice` now has a `_connecting` flag. `connect_device()` returns
immediately if a connection is already in progress. The `BleakClient` instance is
kept as a local variable and only written to `self._bleak_client` after service
discovery succeeds.

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
lives in separate files (`*_win.py`, `ble_bleak.py`, `app.py`, etc.).
