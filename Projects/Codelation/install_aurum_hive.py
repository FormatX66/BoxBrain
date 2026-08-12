#!/usr/bin/env python3
"""Install Aurum hive as a persistent systemd worker on an authorized Linux node."""
from pathlib import Path
import os, subprocess, textwrap

ROOT = Path(__file__).resolve().parent
SERVICE = Path('/etc/systemd/system/aurum-hive.service')
UNIT = f'''[Unit]\nDescription=Aurum Hive Worker\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser={os.environ.get('SUDO_USER') or os.environ.get('USER') or 'kali'}\nWorkingDirectory={ROOT}\nExecStart=/usr/bin/python3 {ROOT / 'aurum_worker.py'}\nRestart=always\nRestartSec=2\nNoNewPrivileges=true\nPrivateTmp=true\n\n[Install]\nWantedBy=multi-user.target\n'''

if os.geteuid() != 0:
    raise SystemExit('Run with sudo: sudo python3 install_aurum_hive.py')
SERVICE.write_text(UNIT)
subprocess.run(['systemctl','daemon-reload'], check=True)
subprocess.run(['systemctl','enable','--now','aurum-hive.service'], check=True)
subprocess.run(['systemctl','is-active','--quiet','aurum-hive.service'], check=True)
print('AURUM_HIVE_SERVICE_ACTIVE')
