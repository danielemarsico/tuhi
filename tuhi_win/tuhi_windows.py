#!/usr/bin/env python3
#
#  Tuhi for Windows - Entry point
#
#  Starts the Tuhi server daemon using Windows-compatible backends:
#    - bleak for BLE (instead of BlueZ)
#    - JSON-RPC TCP server for IPC (instead of D-Bus)
#    - UHID stub for live mode (instead of /dev/uhid)
#    - %APPDATA%/tuhi for config (instead of XDG)
#
#  Usage:
#    python tuhi_windows.py [-v] [--config-dir PATH] [--peek]
#

import sys

if sys.version_info < (3, 12):
    sys.exit('Python 3.12 or later required')

from tuhi.base_win import main

if __name__ == '__main__':
    main(sys.argv + ['--verbose'])
