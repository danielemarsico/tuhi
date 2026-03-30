#!/usr/bin/env python3
#
#  Tuhi CLI client for Windows.
#  Connects to the Tuhi IPC server and provides device management
#  via command-line (replaces tuhi-gui which requires GTK).
#
#  Usage:
#    python tuhi_cli.py list         - List registered devices
#    python tuhi_cli.py search       - Search for unregistered devices
#    python tuhi_cli.py listen ADDR  - Start listening on a device
#    python tuhi_cli.py fetch ADDR   - Fetch and export drawings
#

import argparse
import json
import sys
import time

from tuhi.ipc_client import TuhiIPCClientManager, IPCError


def cmd_list(args):
    """List registered devices."""
    try:
        mgr = TuhiIPCClientManager()
    except Exception as e:
        print(f'Error: Cannot connect to Tuhi server: {e}')
        print('Make sure tuhi_windows.py is running.')
        return 1

    if not mgr.devices:
        print('No registered devices.')
        return 0

    for dev in mgr.devices:
        print(f'  {dev.address}  {dev.name}')
        print(f'    Battery: {dev.battery_percent}%')
        dims = dev.dimensions
        if dims and dims != (0, 0):
            print(f'    Dimensions: {dims[0]/1000:.0f}x{dims[1]/1000:.0f} mm')
        drawings = dev.drawings_available or []
        print(f'    Drawings: {len(drawings)}')
    return 0


def cmd_search(args):
    """Search for unregistered devices."""
    try:
        mgr = TuhiIPCClientManager()
    except Exception as e:
        print(f'Error: Cannot connect to Tuhi server: {e}')
        return 1

    print('Searching for devices... (press Ctrl+C to stop)')
    print('Put your device in pairing mode (hold button for 6 seconds)')

    found = []

    def on_unregistered(manager, device):
        found.append(device)
        print(f'  Found: {device.address} - {device.name}')

    mgr.connect('unregistered-device', on_unregistered)
    mgr.start_search()

    try:
        timeout = args.timeout or 30
        for i in range(timeout):
            time.sleep(1)
            if found:
                break
    except KeyboardInterrupt:
        pass
    finally:
        mgr.stop_search()

    if not found:
        print('No devices found.')
        return 1

    if args.register:
        dev = found[0]
        print(f'\nRegistering {dev.address}...')
        print('Press the button on your device when prompted.')
        dev.register()
        time.sleep(5)
        print('Registration complete (check server log for details).')

    return 0


def cmd_listen(args):
    """Start listening for drawings from a device."""
    try:
        mgr = TuhiIPCClientManager()
    except Exception as e:
        print(f'Error: Cannot connect to Tuhi server: {e}')
        return 1

    addr = args.address.upper()
    try:
        dev = mgr[addr]
    except KeyError:
        print(f'Error: Device {addr} not found. Use "list" to see registered devices.')
        return 1

    print(f'Listening on {dev.name} ({addr})...')
    print('Press the button on your device to sync drawings.')

    def on_drawings(device, pspec):
        drawings = device.drawings_available or []
        print(f'  Drawings available: {len(drawings)}')
        for ts in drawings:
            t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
            print(f'    {ts} ({t})')

    dev.connect('notify::drawings-available', on_drawings)
    dev.start_listening()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        dev.stop_listening()
        print('\nStopped listening.')

    return 0


def cmd_fetch(args):
    """Fetch drawings from a device and export."""
    try:
        mgr = TuhiIPCClientManager()
    except Exception as e:
        print(f'Error: Cannot connect to Tuhi server: {e}')
        return 1

    addr = args.address.upper()
    try:
        dev = mgr[addr]
    except KeyError:
        print(f'Error: Device {addr} not found.')
        return 1

    drawings = dev.drawings_available or []
    if not drawings:
        print('No drawings available.')
        return 0

    print(f'Found {len(drawings)} drawing(s):')
    for ts in drawings:
        t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
        json_data = dev.json(ts)
        if json_data:
            outfile = f'drawing_{ts}.json'
            with open(outfile, 'w') as f:
                f.write(json_data)
            print(f'  Saved: {outfile} ({t})')

            # Export to SVG if requested
            if args.svg:
                try:
                    from tuhi.export_win import JsonSvg
                    parsed = json.loads(json_data)
                    svg_file = f'drawing_{ts}.svg'
                    JsonSvg(parsed, args.orientation or 'landscape', svg_file)
                    print(f'  SVG:   {svg_file}')
                except Exception as e:
                    print(f'  SVG export failed: {e}')

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Tuhi CLI client for Windows')
    sub = parser.add_subparsers(dest='command')

    # list
    sub.add_parser('list', help='List registered devices')

    # search
    sp = sub.add_parser('search', help='Search for unregistered devices')
    sp.add_argument('--register', action='store_true',
                    help='Automatically register the first found device')
    sp.add_argument('--timeout', type=int, default=30,
                    help='Search timeout in seconds (default: 30)')

    # listen
    sp = sub.add_parser('listen', help='Listen for drawings from a device')
    sp.add_argument('address', help='Bluetooth address (XX:XX:XX:XX:XX:XX)')

    # fetch
    sp = sub.add_parser('fetch', help='Fetch and export drawings')
    sp.add_argument('address', help='Bluetooth address (XX:XX:XX:XX:XX:XX)')
    sp.add_argument('--svg', action='store_true', help='Export as SVG')
    sp.add_argument('--orientation', choices=['landscape', 'portrait',
                    'reverse-landscape', 'reverse-portrait'],
                    default='landscape', help='Drawing orientation')

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    commands = {
        'list': cmd_list,
        'search': cmd_search,
        'listen': cmd_listen,
        'fetch': cmd_fetch,
    }

    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
