"""
monitor.py
----------
This file reads the real stats of the computer running the app
(CPU, RAM, disk, network, temperature) using the psutil library.

Everything here is just a thin wrapper around psutil so the rest
of the app doesn't have to deal with it directly.
"""

import psutil
import platform
import socket
import time


def get_system_info():
    """Basic info about this machine that doesn't change much."""
    return {
        "hostname": socket.gethostname(),
        "os_info": f"{platform.system()} {platform.release()}",
        "cpu_count": psutil.cpu_count(),
        "uptime": format_uptime(get_uptime_seconds()),
    }


def get_uptime_seconds():
    return int(time.time() - psutil.boot_time())


def format_uptime(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_temperature():
    """Try to read CPU temperature. Not all machines support this."""
    try:
        temps = psutil.sensors_temperatures()
        for name in ("coretemp", "cpu_thermal", "k10temp"):
            if name in temps and temps[name]:
                return round(temps[name][0].current, 1)
        if temps:
            first_key = list(temps.keys())[0]
            if temps[first_key]:
                return round(temps[first_key][0].current, 1)
    except Exception:
        pass
    return None


def get_current_metrics():
    """
    Grab a fresh snapshot of CPU / RAM / disk / network right now.
    This is called every few seconds by the dashboard.
    """
    disk_path = "C:\\" if platform.system() == "Windows" else "/"
    disk = psutil.disk_usage(disk_path)
    mem = psutil.virtual_memory()
    net = psutil.net_io_counters()

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "ram_percent": mem.percent,
        "ram_used_mb": round(mem.used / (1024 * 1024)),
        "ram_total_mb": round(mem.total / (1024 * 1024)),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "net_sent_mb": round(net.bytes_sent / (1024 * 1024), 1),
        "net_recv_mb": round(net.bytes_recv / (1024 * 1024), 1),
        "temperature": get_temperature(),
    }


def ping_host(ip_address):
    """
    Check if a server is reachable by pinging it.
    Returns True if it replied, False otherwise.
    """
    import subprocess
    param = "-n" if platform.system() == "Windows" else "-c"
    try:
        result = subprocess.run(
            ["ping", param, "1", "-W", "2", ip_address]
            if platform.system() != "Windows"
            else ["ping", param, "1", ip_address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False
