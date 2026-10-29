"""Start BillBuddy so that phones in the same Wi-Fi can open it.

Usage: python -m billbuddy.serve

Only use this in a network you trust (e.g. at home): everyone in the same
Wi-Fi could open the app, and there is no login yet.
"""

import socket

import uvicorn

PORT = 8000


def local_ip() -> str:
    """The address of this computer in the local network."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # Sends no data; it only asks the system which network it would use
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> None:
    print(f"\n  On your phone (same Wi-Fi) open:  http://{local_ip()}:{PORT}\n")
    uvicorn.run("billbuddy.api.main:app", host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
