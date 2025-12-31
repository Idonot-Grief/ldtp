"""
Fixed TCP-only File Server
- Proper cross-platform path handling
- Directory browsing & downloads
- Multi-client support
"""

import socket
import threading
import os
import json

HOST = '0.0.0.0'
PORT = 229
ROOT_DIR = 'D:\\'  # <<< CHANGE TO YOUR SHARED FOLDER >>>

def human_readable_size(size):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti']:
        if size < 1024:
            return f"{size:.1f} {unit}B"
        size /= 1024
    return f"{size:.1f} PiB"

def safe_join(base, path):
    """Join and normalize paths, prevent directory traversal."""
    full_path = os.path.normpath(os.path.join(base, path.replace('/', os.sep)))
    if not os.path.abspath(full_path).startswith(os.path.abspath(base)):
        return None
    return full_path

def get_listing(path):
    full_path = safe_join(ROOT_DIR, path)
    if not full_path:
        return {"error": "Access denied"}
    if not os.path.isdir(full_path):
        return {"error": "Path not found"}

    items = []
    try:
        for name in sorted(os.listdir(full_path)):
            item_path = os.path.join(full_path, name)
            if os.path.isdir(item_path):
                items.append({"name": name + "/", "size": "", "is_dir": True})
            else:
                items.append({
                    "name": name,
                    "size": human_readable_size(os.path.getsize(item_path)),
                    "is_dir": False
                })
    except PermissionError:
        return {"error": "Permission denied"}
    return {"listing": items}

def handle_client(conn, addr):
    print(f"Client connected: {addr}")
    try:
        while True:
            data = b''
            while not data.endswith(b'\n'):
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            try:
                cmd = json.loads(data.decode('utf-8').strip())
            except json.JSONDecodeError:
                conn.sendall(b'ERROR: Invalid JSON\n')
                continue

            if cmd['type'] == 'LIST':
                path = cmd.get('path', '/')
                response = get_listing(path)
                conn.sendall(json.dumps(response).encode('utf-8') + b'\n')

            elif cmd['type'] == 'DOWNLOAD':
                file_path = cmd.get('path', '')
                full_path = safe_join(ROOT_DIR, file_path)
                if not full_path or not os.path.isfile(full_path):
                    conn.sendall(b'ERROR: File not found or access denied\n')
                    continue

                file_size = os.path.getsize(full_path)
                conn.sendall(f'SIZE:{file_size}\n'.encode('utf-8'))

                with open(full_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        conn.sendall(chunk)
                conn.sendall(b'END\n')
    except Exception as e:
        print(f"Client {addr} error: {e}")
    finally:
        conn.close()
        print(f"Client {addr} disconnected")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"TCP-Only Server running on {HOST}:{PORT}")
        print(f"Serving directory: {ROOT_DIR}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
