![tuhi-logo](data/org.freedesktop.Tuhi.svg)

Tuhi
=====

Tuhi is a GTK application that connects to and fetches the data from the
Wacom ink range (Spark, Slate, Folio, Intuos Paper, ...). Users can save the
data as SVGs.

Tuhi is the Māori word for "to draw".

Supported Devices
-----------------

Devices tested and known to be supported:

* Bamboo Spark
* Bamboo Slate
* Bamboo Folio (A4 — uses the Slate protocol, dimensions read dynamically)
* Intuos Pro Paper

Building Tuhi
-------------

To build and run Tuhi from the repository directly:

```
 $> git clone http://github.com/tuhiproject/tuhi
 $> cd tuhi
 $> meson setup builddir
 $> ninja -C builddir
 $> ./builddir/tuhi.devel
```

Tuhi requires Python v3.6 or above.

Installing Tuhi
---------------

To install and run Tuhi:

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

Tuhi requires Python v3.6 or above.

Flatpak
-------

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

Bamboo Folio Support
--------------------

The Bamboo Folio is the A4-sized sibling of the Bamboo Slate. It uses the
same **SLATE** protocol and is fully supported by Tuhi. The device dimensions
(~297 × 210 mm for A4) are read dynamically from the device at connection time
via the `GET_WIDTH` and `GET_HEIGHT` protocol messages, so no special
configuration is needed — Tuhi adapts automatically.

Registration and usage are identical to the Bamboo Slate (see
"Registering devices" below).

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

Packages
--------

Arch Linux: [tuhi-git](https://aur.archlinux.org/packages/tuhi-git/)

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
