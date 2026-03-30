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

## Components

### tuhi_windows.py — Server

The server is a long-running background process. Start it once and leave
it running. It owns:

- The BLE radio (via bleak)
- The Wacom protocol state machine
- Device configuration and drawing storage
- The TCP IPC socket that CLI clients connect to

```
python tuhi_windows.py
```

### tuhi_cli.py — Client

A command-line client that connects to the running server over TCP and
issues commands. Each invocation connects, does one operation, then exits.

```
python tuhi_cli.py list                        # List registered devices
python tuhi_cli.py search                      # Search for unregistered devices
python tuhi_cli.py search --register           # Search and register the first found device
python tuhi_cli.py listen XX:XX:XX:XX:XX:XX    # Listen for drawings (sync on button press)
python tuhi_cli.py fetch  XX:XX:XX:XX:XX:XX    # Download stored drawings as JSON
python tuhi_cli.py fetch  XX:XX:XX:XX:XX:XX --svg  # Download and export as SVG
```

---

## Communication Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        tuhi_cli.py                          │
│                      (CLI client)                           │
│                                                             │
│  cmd_search()   cmd_listen()   cmd_fetch()   cmd_list()     │
│       │               │             │             │         │
│       └───────────────┴─────────────┴─────────────┘         │
│                       TuhiIPCClientManager                   │
│                       TuhiIPCClientDevice                    │
└───────────────────────────┬─────────────────────────────────┘
                            │  JSON-RPC over TCP (127.0.0.1:48150)
                            │  Requests:  {"method": "...", "id": N, "args": {...}}
                            │  Responses: {"id": N, "result": ...}
                            │  Events:    {"event": "...", "data": {...}}
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                      tuhi_windows.py                        │
│                        (Server)                             │
│                                                             │
│                      TuhiIPCServer                          │
│                      TuhiIPCDevice (per device)             │
│                            │                                │
│                      TuhiKeeperManager                      │
│                      TuhiDevice (per device)                │
│                            │                                │
│                      WacomDevice                            │
│              WacomProtocolSlate / IntuosPro / Spark         │
│                            │                                │
│                      BleakDeviceManager                     │
│                      BleakBLEDevice                         │
│                      BleakCharacteristic                    │
└───────────────────────────┬─────────────────────────────────┘
                            │  BLE (bleak / Windows Bluetooth API)
                            │
                     ┌──────┴──────┐
                     │ Wacom device │
                     │  (Bamboo,   │
                     │   Slate,    │
                     │  Intuos Pro)│
                     └─────────────┘
```

---

## Step-by-Step Flows

### 1. Device Registration (first-time pairing)

```
tuhi_cli.py                     tuhi_windows.py              Wacom device
    │                                  │                           │
    │── StartSearch ─────────────────>│                           │
    │                                  │── BLE scan start ──────>│
    │                                  │                           │
    │                                  │<─ advertisement data ────│
    │                                  │   (mfr_data len=4        │
    │                                  │    = pairing mode)       │
    │                                  │                           │
    │                                  │  create TuhiDevice        │
    │                                  │  (mode=REGISTER)         │
    │                                  │                           │
    │<── event: unregistered_device ──│                           │
    │    (with device properties)      │                           │
    │                                  │                           │
    │  [user sees "Found: <addr>"]     │                           │
    │                                  │                           │
    │── Device.Register ─────────────>│                           │
    │── StopSearch ──────────────────>│                           │
    │                                  │── BLE connect ─────────>│
    │                                  │<─ connected ─────────────│
    │                                  │                           │
    │                                  │── REGISTER_PRESS_BUTTON─>│
    │                                  │                           │
    │<── event: ButtonPressRequired ──│  [user presses button]    │
    │                                  │<─ button confirmation ───│
    │                                  │                           │
    │                                  │  determine protocol       │
    │                                  │  (SLATE / INTUOS_PRO)    │
    │                                  │                           │
    │                                  │── SET_TIME ─────────────>│
    │                                  │── GET_TIME ─────────────>│
    │                                  │── GET_FIRMWARE ─────────>│
    │                                  │── GET_BATTERY ──────────>│
    │                                  │                           │
    │                                  │  save settings.ini        │
    │                                  │  (address, uuid,          │
    │                                  │   protocol)              │
    │                                  │── BLE disconnect ───────>│
    │                                  │                           │
    │  [30s wait in CLI]               │                           │
    │  "Registration complete"         │                           │
```

### 2. Fetching Drawings (listen / sync)

```
tuhi_cli.py                     tuhi_windows.py              Wacom device
    │                                  │                           │
    │── Device.StartListening ───────>│                           │
    │                                  │── BLE scan start ──────>│
    │                                  │                           │
    │                                  │<─ advertisement data ────│
    │                                  │  (device known in config)│
    │                                  │                           │
    │                                  │── BLE connect ─────────>│
    │                                  │<─ connected ─────────────│
    │                                  │                           │
    │                                  │── SET_TIME ─────────────>│
    │                                  │── GET_BATTERY ──────────>│
    │                                  │── GET_FIRMWARE ─────────>│
    │                                  │── SELECT_GATT ──────────>│
    │                                  │                           │
    │                                  │<─ offline pen data ──────│
    │                                  │   (stroke packets)       │
    │                                  │                           │
    │                                  │  parse strokes            │
    │                                  │  save <timestamp>.json   │
    │                                  │                           │
    │<── event: device_property       │                           │
    │    changed (drawings_available) │                           │
    │                                  │── BLE disconnect ───────>│
    │                                  │                           │
    │── Device.StopListening ────────>│                           │
```

### 3. Fetching JSON Data

```
tuhi_cli.py                     tuhi_windows.py
    │                                  │
    │── Device.GetJSONData ──────────>│
    │   {timestamp: N}                 │  read <timestamp>.json
    │<── {json: "..."}  ─────────────│  from %APPDATA%\tuhi\
    │                                  │  <addr>\<N>.json
    │  save drawing_<N>.json locally  │
    │  [optionally convert to SVG]    │
```

---

## IPC Protocol Reference

All messages are newline-delimited JSON over a TCP connection to `127.0.0.1:48150`.

### Client → Server (Requests)

| Method | Args | Description |
|---|---|---|
| `GetDevices` | — | List registered device IDs |
| `GetAllDevices` | — | List all devices with full properties |
| `GetManagerProperties` | — | Searching state, device list, JSON versions |
| `StartSearch` | — | Start BLE scanning for unregistered devices |
| `StopSearch` | — | Stop BLE scanning |
| `Device.Register` | `device_id` | Begin registration for a found device |
| `Device.StartListening` | `device_id` | Connect and retrieve stored drawings |
| `Device.StopListening` | `device_id` | Disconnect from device |
| `Device.GetJSONData` | `device_id`, `timestamp`, `file_version` | Get a drawing as JSON |
| `Device.GetProperties` | `device_id` | Get device metadata |

### Server → Client (Events)

| Event | Data | Description |
|---|---|---|
| `unregistered_device` | full device properties | New unregistered device detected during scan |
| `search_stopped` | `status` | BLE scan has ended |
| `manager_property_changed` | `property`, `value` | Searching state or device list changed |
| `device_property_changed` | `device_id`, `property`, `value` | Per-device property update (battery, listening, etc.) |
| `device_signal` | `device_id`, `signal`, `args` | Per-device signal (ButtonPressRequired, etc.) |

---

## Data Storage

Drawings and config are stored in `%APPDATA%\tuhi\`:

```
C:\Users\<user>\AppData\Roaming\tuhi\
  F4_21_DE_4D_26_BF\          ← BT address with _ instead of :
    settings.ini               ← address, UUID, protocol
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
| `tuhi/gobject_compat.py` | Lightweight GObject replacement (signals, properties, timers) |
| `tuhi/ble_bleak.py` | BLE backend using bleak (`BleakDeviceManager`, `BleakBLEDevice`, `BleakCharacteristic`) |
| `tuhi/uhid_win.py` | UHID stub — logs pen events; live mode pen injection not available on Windows |
| `tuhi/ipc_server.py` | JSON-RPC TCP server on `localhost:48150` |
| `tuhi/ipc_client.py` | JSON-RPC TCP client |
| `tuhi/config_win.py` | Config using `%APPDATA%\tuhi` instead of XDG |
| `tuhi/drawing_win.py` | Drawing model without `gi.repository` |
| `tuhi/wacom_win.py` | Wacom protocol (same logic, Windows-compatible imports) |
| `tuhi/base_win.py` | Orchestrator wiring all Windows backends together |
| `tuhi/export_win.py` | SVG/PNG export using svgwrite + Pillow |
| `tuhi_windows.py` | Server entry point |
| `tuhi_cli.py` | CLI client |

## Installation

```
pip install -r requirements-windows.txt
```

Requirements: `bleak`, `svgwrite`, `Pillow`. Python 3.12+.

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
