![tuhi-logo](data/org.freedesktop.Tuhi.svg)

Tuhi
=====

Tuhi is a GTK application that connects to and fetches the data from the
Wacom ink range (Spark, Slate, Folio, Intuos Paper, ...). Users can save the
data as SVGs.

Tuhi is the Māori word for "to draw".

Supported Platforms
-------------------

**Tuhi is a Linux-only application.** It depends on several Linux-specific
technologies that have no equivalents on Windows or macOS:

| Dependency      | Purpose                                  | Why Linux-only                           |
|-----------------|------------------------------------------|------------------------------------------|
| **BlueZ**       | Bluetooth Low Energy communication       | Linux Bluetooth stack; Windows uses a different API |
| **D-Bus**       | IPC between tuhi-server, tuhi-gui, and BlueZ | freedesktop.org standard; not available on Windows |
| **UHID**        | Live pen input via `/dev/uhid`           | Linux kernel subsystem                   |
| **GTK 3 / GLib**| GUI and main loop                        | GNOME ecosystem; tightly coupled to D-Bus |
| **XDG directories** | Config and data storage (`~/.local/share/tuhi/`) | POSIX standard paths              |

**Windows is not supported.** The codebase contains no platform abstractions,
no Windows Bluetooth API integration, and no conditional imports. Running on
Windows (including WSL) is not possible without fundamental architectural
changes to replace BlueZ, D-Bus, and UHID with cross-platform alternatives.

Supported Devices
-----------------

Devices tested and known to be supported:

* Bamboo Spark
* Bamboo Slate
* Bamboo Folio (A4 — uses the Slate protocol, dimensions read dynamically)
* Intuos Pro Paper

Building Tuhi (Linux)
---------------------

Tuhi requires **Python v3.12 or above** and the following dependencies:

* **PyGObject** 3.30+
* **svgwrite**
* **xdg** (pyxdg)
* **cairo** (via PyGObject introspection)

### Installing dependencies

On Debian/Ubuntu:

```
 $> sudo apt install python3-dev python3-gi python3-cairo \
        python3-xdg python3-svgwrite meson ninja-build \
        libglib2.0-dev gettext
```

On Fedora:

```
 $> sudo dnf install python3-devel python3-gobject python3-cairo \
        python3-pyxdg python3-svgwrite meson ninja-build \
        glib2-devel gettext
```

On Arch Linux:

```
 $> sudo pacman -S python-gobject python-cairo python-xdg \
        python-svgwrite meson ninja gettext
```

### Build from source (development)

```
 $> git clone http://github.com/tuhiproject/tuhi
 $> cd tuhi
 $> meson setup builddir
 $> ninja -C builddir
 $> ./builddir/tuhi.devel
```

The `tuhi.devel` script runs directly from the build tree without installing.

### Running tests

```
 $> ninja -C builddir test
```

This runs flake8 linting and pytest unit tests.

Running Tuhi (Linux)
--------------------

Tuhi requires a running Bluetooth daemon (BlueZ) and D-Bus session bus.
Most Linux desktop environments provide both by default.

### From the build tree (development)

```
 $> ./builddir/tuhi.devel
```

### After system-wide install

```
 $> tuhi
```

The `tuhi` launcher starts both the background daemon (`tuhi-server`) and
the GTK GUI (`tuhi-gui`). Make sure your Wacom device is registered first
(see "Registering devices" below).

Debugging Tuhi (Linux)
----------------------

### Verbose logging

Pass `-v` or `--verbose` to enable DEBUG-level console output:

```
 $> ./builddir/tuhi.devel --verbose
```

### Session logs

Every run writes a detailed log to:

```
~/.local/share/tuhi/session-logs/tuhi-YY-MM-DD-HH:MM:SS.log
```

These logs contain DEBUG-level output regardless of the `-v` flag.

### Raw BLE communication logs

Per-device BLE traffic is recorded in:

```
~/.local/share/tuhi/<BT_ADDRESS>/raw/log-*.yaml
```

These are useful for diagnosing protocol-level issues.

### Peek mode

Download only the first drawing without deleting it from the device:

```
 $> ./builddir/tuhi.devel --peek
```

### Custom config directory

Use `--config-dir` to override the default data/config location:

```
 $> ./builddir/tuhi.devel --config-dir /tmp/tuhi-debug
```

### Debugging tools

| Tool                          | Purpose                                         |
|-------------------------------|--------------------------------------------------|
| `tools/kete.py`               | Interactive CLI for direct device communication  |
| `tools/tuhi-live.py`          | Stream live pen input in real-time               |
| `tools/parse_log.py`          | Parse btsnoop Bluetooth capture files            |
| `tools/raw-log-converter.py`  | Convert raw BLE communication logs               |
| `tools/exporter.py`           | Export drawings from stored JSON                 |

### Named loggers

The codebase uses fine-grained loggers you can filter on:
`tuhi`, `tuhi.protocol`, `tuhi.ble`, `tuhi.wacom`, `tuhi.config`,
`tuhi.dbusserver`, `tuhi.drawing`, `tuhi.dbusclient`.

### Debugging with bluetoothctl

For low-level Bluetooth troubleshooting, use `bluetoothctl` to inspect
the BLE connection independently of Tuhi:

```
 $> bluetoothctl
 [bluetooth]# scan on
 [bluetooth]# connect <BT_ADDRESS>
```

See "Device notes" at the end of this file for device-specific tips.

Deploying Tuhi (Linux)
----------------------

### System-wide install (Meson)

```
 $> git clone http://github.com/tuhiproject/tuhi
 $> cd tuhi
 $> meson setup builddir
 $> ninja -C builddir install
```

Run Tuhi with:

```
 $> tuhi
```

This installs the `tuhi`, `tuhi-gui`, and `tuhi-server` executables, the
desktop file (`org.freedesktop.Tuhi.desktop`), and appdata to the standard
freedesktop.org locations.

### Flatpak

```
 $> git clone http://github.com/tuhiproject/tuhi
 $> cd tuhi
 $> flatpak-builder flatpak_builddir org.freedesktop.Tuhi.json --install --user --force-clean
 $> flatpak run org.freedesktop.Tuhi
```

Note that Flatpak's containers use different XDG directories. This affects
Tuhi being able to remember devices and the data storage. Switching between
the Flatpak and a normal installation requires re-registering the device and
previously downloaded drawings may become inaccessible.

### Arch Linux

Available via AUR: [tuhi-git](https://aur.archlinux.org/packages/tuhi-git/)

Bamboo Folio Support
--------------------

The Bamboo Folio is the A4-sized sibling of the Bamboo Slate. It uses the
same **SLATE** protocol and is fully supported by Tuhi.

### Connection Protocol

The Bamboo Folio communicates over **Bluetooth Low Energy (BLE)** using the
**Nordic UART Service (NUS)**. The full connection flow is:

1. **Discovery** — Tuhi scans for BLE advertisements matching Wacom company
   IDs (`0x4755`, `0x4157`, `0x424d`).
2. **GATT connection** — Tuhi connects to the device's GATT server and
   subscribes to the Nordic UART RX characteristic
   (`6e400003-b5a3-f393-e0a9-e50e24dcca9e`) for incoming data. Outgoing
   commands are written to the TX characteristic
   (`6e400002-b5a3-f393-e0a9-e50e24dcca9e`).
3. **Protocol detection** — If the device exposes the System Event
   Notification GATT characteristic, Tuhi selects the SLATE protocol;
   otherwise it falls back to SPARK.
4. **Authentication** — Tuhi authenticates using a UUID that was assigned
   during the initial registration (6-second button hold). Without this UUID,
   the device will not respond.
5. **Dimension query** — Unlike the Spark (which uses hardcoded dimensions),
   the Folio's dimensions (~297 × 210 mm for A4) are read dynamically at
   connection time via `GET_WIDTH`, `GET_HEIGHT`, and `GET_POINT_SIZE` protocol
   messages. This allows Tuhi to adapt automatically to the device's actual
   drawing area.
6. **Data transfer** — Binary stroke data is downloaded over Nordic UART,
   parsed into `Drawing` / `Stroke` / `Point` objects, and saved as JSON.

The protocol implementation lives in `tuhi/wacom.py` (`WacomProtocolSlate`
class, which inherits from `WacomProtocolSpark`) and `tuhi/protocol.py` (70+
opcodes per protocol version).

### SLATE Protocol Details

| Property       | Value                        |
|----------------|------------------------------|
| Pressure       | 11-bit (0–2047)              |
| Point size     | 10 µm (read from device)     |
| Dimensions     | Read dynamically from device |
| Orientation    | Portrait                     |
| Base class     | `WacomProtocolSpark`         |

Registration and usage are identical to the Bamboo Slate (see
"Registering devices" below).

Cross-Currency Support
----------------------

**Note:** Tuhi is a drawing/ink application for Wacom SmartPad devices. It does
not include any cross-currency or financial functionality. If you are looking
for currency conversion or multi-currency features, those are outside the scope
of this project.

Architecture
------------

Tuhi is split into a background daemon (`tuhi-server`) that manages Bluetooth
communication, and a GTK GUI (`tuhi-gui`) that talks to the daemon over DBus.
The launcher script (`tuhi`) starts both.

### Module Overview

```
tuhi/
├── base.py          Orchestrator — bridges BlueZ, config, and DBus
├── ble.py           BlueZ / D-Bus wrappers for BLE GATT communication
├── wacom.py         Wacom device logic & protocol class hierarchy
├── protocol.py      BLE protocol messages (70+ opcodes per protocol version)
├── config.py        Per-device config & drawing storage (~/.local/share/tuhi/)
├── drawing.py       Data model: Drawing → Stroke → Point
├── dbusserver.py    DBus service (org.freedesktop.tuhi1)
├── dbusclient.py    DBus client used by the GUI
├── export.py        SVG and PNG export (pressure-sensitive stroke widths)
├── uhid.py          Kernel UHID device for live pen input
└── util.py          Small helpers
```

### Communication Stack

```
  GTK GUI  (tuhi-gui)
     │  DBus (org.freedesktop.tuhi1)
     ▼
  Tuhi Daemon  (tuhi-server / base.py)
     │
     ▼
  WacomDevice  (wacom.py  — one per tablet, runs in its own thread)
     │
     ▼
  WacomProtocol{Spark,Slate,IntuosPro}  (wacom.py + protocol.py)
     │  Nordic UART Service over BLE GATT
     ▼
  BlueZDevice / BlueZDeviceManager  (ble.py)
     │  D-Bus  →  BlueZ 5
     ▼
  Linux Bluetooth (HCI)
```

### Protocol Versions

The three protocol families form an inheritance chain:

| Protocol    | Devices                | Pressure | Point Size | Dimensions (default) |
|-------------|------------------------|----------|------------|----------------------|
| SPARK       | Bamboo Spark           | 10-bit   | 10 µm      | 210 × 148 mm         |
| SLATE       | Bamboo Slate / Folio   | 11-bit   | 10 µm      | read from device     |
| INTUOS_PRO  | Intuos Pro Paper       | 13-bit   | 5 µm       | 448 × 296 mm         |

Protocol detection is automatic: if the device exposes the System Event
Notification GATT characteristic it uses SLATE (or INTUOS_PRO); otherwise it
uses SPARK.

### Device Modes

| Mode      | Trigger                         | What happens                                    |
|-----------|----------------------------------|-------------------------------------------------|
| Register  | Hold button 6 s (blue LED blinks) | Tuhi assigns a UUID; device stores it in firmware |
| Listen    | Short button press               | Tuhi connects, downloads stored drawings, deletes them from device |
| Live      | Started via DBus method          | Pen data streamed in real-time to a UHID kernel device |

### Data Flow (Listen / Offline)

1. User draws on paper, pen strokes are stored in device memory.
2. User presses the device button → device advertises via BLE.
3. Tuhi detects the advertisement (Wacom company IDs `0x4755`, `0x4157`,
   `0x424d`), connects, authenticates with the stored UUID.
4. Tuhi downloads binary stroke data over Nordic UART, parses it into
   `Drawing` / `Stroke` / `Point` objects.
5. Drawings are saved as JSON in `~/.local/share/tuhi/<BT_ADDRESS>/`.
6. The GUI retrieves drawings over DBus and can export to SVG or PNG.

### Data Storage

```
~/.local/share/tuhi/
└── <BT_ADDRESS>/
    ├── settings.ini          Device UUID + protocol version
    ├── <timestamp>.json      Drawing data (strokes, points, pressure)
    └── raw/
        └── log-*.yaml        BLE communication logs (for debugging)
```

License
-------

Tuhi is licensed under the GPLv2 or later.

Registering devices
-------------------

For a device to work with Tuhi, it must be registered first. This is
achieved by holiding the device button for 6 or more seconds until the blue
LED starts blinking. Only in that mode can Tuhi detect it during
`Searching` and register it.

Registration sends a randomly generated UUID to the device. Subsequent
connections must use that UUID as identifier for the tablet device to
respond. Without knowing that UUID, other applications cannot connect.

A device can only be registered with one application at a time. Thus, when a
device is registered with Tuhi, other applications (e.g. Wacom Inkspace)
cannot not connect to the device anymore. Likewise, when registered with
another application, Tuhi cannot connect.

To make the tablet connect again, simply re-register with the respective
application or Tuhi, whichever desired.

This is not registering the device with some cloud service, vendor, or
other networked service. It is a communication between Tuhi and the firmware
on the device only. It is merely a process of "your ID is now $foo" followed
by "hi $foo, I want to connect".

The word "register" was chosen because "pairing" is already in use by
Bluetooth.

Device notes
============

When following any device notes below, replace the example bluetooth
addresses with your device's bluetooth address.

Bamboo Spark
------------

The Bluetooth connection on the Bamboo Spark behaves differently depending
on whether there are drawings pending or not. Generally, if no drawings are
pending, it is harder to connect to the device. Save yourself the pain and
make sure you have drawings pending while debugging.

### If the device has no drawings available:

* start `bluetoothctl`, commands below are to be issued in its interactive shell
* enable discovery mode (`scan on`)
* hold the Bamboo Spark button until the blue light is flashing
* You should see the device itself show up, but none of its services
  ```
  [NEW] Device E2:43:03:67:0E:01 Bamboo Spark
  ```
* While the LED is still flashing, `connect E2:43:03:67:0E:01`
  ```
  Attempting to connect to E2:43:03:67:0E:01
  [CHG] Device E2:43:03:67:0E:01 Connected: yes
  ... lots of services being resolved
  [CHG] Device E2:43:03:67:0E:01 ServicesResolved: yes
  [CHG] Device E2:43:03:67:0E:01 ServicesResolved: no
  [CHG] Device E2:43:03:67:0E:01 Connected: no
  ```
  Note how the device disconnects again at the end. Doesn't matter, now you
  have the services cached.
* Don't forget to eventually turn disable discovery mode off (`scan off`)

Now you have the device cached in bluez and you can work with that data.
However, you **cannot connect to the device while it has no drawings
pending**. Running `connect` and pressing the Bamboo Spark button shortly
does nothing.

### If the device has drawings available:

* start `bluetoothctl`, commands below are to be issued in its interactive shell
* enable discovery mode (`scan on`)
* press the Bamboo Spark button shortly
* You should see the device itself show up, but none of its services
  ```
  [NEW] Device E2:43:03:67:0E:01 Bamboo Spark
  ```
* `connect E2:43:03:67:0E:01`, then press the Bamboo Spark button
  ```
  Attempting to connect to E2:43:03:67:0E:01
  [CHG] Device E2:43:03:67:0E:01 Connected: yes
  ... lots of services being resolved
  [CHG] Device E2:43:03:67:0E:01 ServicesResolved: yes
  [CHG] Device E2:43:03:67:0E:01 ServicesResolved: no
  [CHG] Device E2:43:03:67:0E:01 Connected: no
  ```
  Note how the device disconnects again at the end. Doesn't matter, now you
  have the services cached.
* `connect E2:43:03:67:0E:01`, then press the Bamboo Spark button re-connects to the device
  The device will disconnect after approximately 10s. You need to start
  issuing the commands to talk to the controller before that happens.
* Don't forget to eventually turn disable discovery mode off (`scan off`)

You **must** run `connect` before pressing the button. Just pressing the
button does nothing unless bluez is trying to connect to the device.

**Warning**: A successful communication with the controller deletes the
drawings from the controller, so you may not be able to re-connect.
