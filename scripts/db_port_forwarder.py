"""
scripts/db_port_forwarder.py
----------------------------
Lightweight TCP forwarder listening on 127.0.0.1:5433 and forwarding to 127.0.0.1:5432.
Allows isolated test database traffic (database: campus_ai_test, schema: test_schema)
to connect via standard port 5433 without requiring Windows admin elevation.
"""

import socket
import sys
import threading


def forward(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(8192)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


def handle_client(client_socket: socket.socket) -> None:
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.connect(("127.0.0.1", 5432))
        t1 = threading.Thread(target=forward, args=(client_socket, server_socket), daemon=True)
        t2 = threading.Thread(target=forward, args=(server_socket, client_socket), daemon=True)
        t1.start()
        t2.start()
    except Exception as exc:
        print(f"[proxy] Failed to connect to target 5432: {exc}", file=sys.stderr)
        try:
            client_socket.close()
        except Exception:
            pass


def main() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", 5433))
    except Exception as exc:
        print(f"[proxy] Could not bind to 127.0.0.1:5433: {exc}", file=sys.stderr)
        sys.exit(1)

    server.listen(128)
    print("[proxy] Active: listening on 127.0.0.1:5433 -> forwarding to 127.0.0.1:5432", flush=True)

    while True:
        try:
            client_sock, _ = server.accept()
            threading.Thread(target=handle_client, args=(client_sock,), daemon=True).start()
        except Exception as exc:
            print(f"[proxy] Accept error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
