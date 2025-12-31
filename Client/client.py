"""
Fixed TCP-only File Downloader Client
- Works with fixed server paths
- Normalized paths
- Directory browsing & downloads
"""

import socket
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import os
import threading
import time

DEFAULT_HOST = '127.0.0.1'
PORT = 229
CHUNK_SIZE = 65536

def human_readable_size(size):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti']:
        if size < 1024:
            return f"{size:.1f} {unit}B"
        size /= 1024
    return f"{size:.1f} PiB"

def human_readable_speed(bps):
    return human_readable_size(bps) + "/s"

def format_eta(seconds):
    if seconds < 0:
        return "--:--"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class Downloader:
    def __init__(self, gui, file_path, save_path):
        self.gui = gui
        self.file_path = file_path
        self.save_path = save_path
        self.cancelled = False
        self.total_size = 0
        self.downloaded = 0
        self.start_time = None

    def start(self):
        threading.Thread(target=self._download, daemon=True).start()

    def _download(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.gui.host, PORT))
            cmd = json.dumps({'type': 'DOWNLOAD', 'path': self.file_path}) + '\n'
            s.sendall(cmd.encode('utf-8'))

            # Receive header
            header = b''
            while b'\n' not in header:
                chunk = s.recv(1024)
                if not chunk:
                    raise Exception("Connection lost")
                header += chunk
            line = header.split(b'\n')[0].decode('utf-8')
            if line.startswith('ERROR'):
                messagebox.showerror("Error", line[6:])
                s.close()
                self.gui.remove_download(self.file_path)
                return
            if not line.startswith('SIZE:'):
                raise Exception("Invalid response")
            self.total_size = int(line[5:])
            self.start_time = time.time()

            with open(self.save_path, 'wb') as f:
                while not self.cancelled and self.downloaded < self.total_size:
                    chunk = s.recv(CHUNK_SIZE)
                    if not chunk:
                        break
                    if chunk.endswith(b'END\n'):
                        chunk = chunk[:-4]
                    f.write(chunk)
                    self.downloaded += len(chunk)
                    self.gui.update_progress(self.file_path,
                                             self.downloaded,
                                             self.total_size,
                                             self.start_time)
            s.close()

            if self.cancelled and os.path.exists(self.save_path):
                os.remove(self.save_path)
            else:
                self.gui.update_progress(self.file_path, self.total_size, self.total_size, self.start_time)
                messagebox.showinfo("Complete", f"Downloaded:\n{os.path.basename(self.save_path)}")
        except Exception as e:
            messagebox.showerror("Download Failed", str(e))
        finally:
            self.gui.remove_download(self.file_path)

    def cancel(self):
        self.cancelled = True

class ClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TCP File Downloader")
        self.root.configure(bg='#1e1e1e')
        self.root.geometry("900x700")

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', background='#2d2d2d', foreground='white', fieldbackground='#2d2d2d')
        style.configure('Treeview.Heading', background='#3d3d3d', foreground='white')
        style.map('Treeview', background=[('selected', '#0078d7')])

        top = tk.Frame(self.root, bg='#1e1e1e')
        top.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(top, text="Server:", bg='#1e1e1e', fg='white').pack(side=tk.LEFT)
        self.host_entry = tk.Entry(top, width=20, bg='#2d2d2d', fg='white', insertbackground='white')
        self.host_entry.insert(0, DEFAULT_HOST)
        self.host_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Connect", command=self.connect, bg='#0078d7', fg='white').pack(side=tk.LEFT)

        self.path_var = tk.StringVar(value="Path: /")
        tk.Label(self.root, textvariable=self.path_var, bg='#2d2d2d', fg='cyan', anchor='w', padx=10).pack(fill=tk.X)

        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree = ttk.Treeview(tree_frame, columns=('name', 'size'), show='headings')
        self.tree.heading('name', text='Name')
        self.tree.heading('size', text='Size')
        self.tree.column('name', width=500)
        self.tree.column('size', width=150, anchor='e')
        vbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind('<Double-1>', self.on_double_click)

        btns = tk.Frame(self.root, bg='#1e1e1e')
        btns.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btns, text="← Back", command=self.go_back, bg='#3d3d3d', fg='white').pack(side=tk.LEFT)
        self.dl_btn = tk.Button(btns, text="Download File", command=self.start_download,
                                bg='#28a745', fg='white', state=tk.DISABLED)
        self.dl_btn.pack(side=tk.LEFT, padx=10)

        dl_frame = tk.LabelFrame(self.root, text="Downloads", bg='#1e1e1e', fg='white')
        dl_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.dl_canvas = tk.Canvas(dl_frame, bg='#1e1e1e', highlightthickness=0)
        dl_scroll = ttk.Scrollbar(dl_frame, orient=tk.VERTICAL, command=self.dl_canvas.yview)
        self.dl_inner = tk.Frame(self.dl_canvas, bg='#1e1e1e')
        self.dl_canvas.create_window((0,0), window=self.dl_inner, anchor='nw')
        self.dl_canvas.configure(yscrollcommand=dl_scroll.set)
        self.dl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dl_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.dl_inner.bind("<Configure>", lambda e: self.dl_canvas.configure(scrollregion=self.dl_canvas.bbox("all")))

        self.host = DEFAULT_HOST
        self.current_path = '/'
        self.downloaders = {}
        self.progress_widgets = {}

        self.root.mainloop()

    def connect(self):
        self.host = self.host_entry.get().strip() or DEFAULT_HOST
        self.list_directory('/')

    def list_directory(self, path):
        path = path.replace('//','/').rstrip('/') + '/'
        try:
            s = socket.socket()
            s.settimeout(10)
            s.connect((self.host, PORT))
            s.sendall(json.dumps({'type': 'LIST', 'path': path}).encode('utf-8') + b'\n')
            data = b''
            while b'\n' not in data:
                chunk = s.recv(4096)
                if not chunk:
                    raise Exception("Disconnected")
                data += chunk
            resp = json.loads(data.split(b'\n')[0])
            s.close()

            if 'error' in resp:
                messagebox.showerror("Error", resp['error'])
                return

            self.current_path = path
            self.path_var.set(f"Path: {path}")
            self.tree.delete(*self.tree.get_children())
            for item in resp['listing']:
                name = item['name']
                size = item['size']
                tag = 'dir' if item['is_dir'] else 'file'
                self.tree.insert('', 'end', values=(name, size), tags=(tag,))
            self.tree.tag_configure('dir', foreground='#ffff66')
            self.tree.tag_configure('file', foreground='white')
        except Exception as e:
            messagebox.showerror("Connection Failed", str(e))

    def go_back(self):
        if self.current_path != '/':
            new_path = os.path.dirname(self.current_path.rstrip('/')) + '/'
            self.list_directory('/' if new_path == '//' else new_path)

    def on_double_click(self, event):
        item = self.tree.selection()
        if not item:
            return
        name = self.tree.item(item[0])['values'][0]
        if name.endswith('/'):
            self.list_directory(self.current_path + name.rstrip('/'))
        else:
            self.dl_btn.config(state=tk.NORMAL)

    def start_download(self):
        item = self.tree.selection()
        if not item:
            return
        name = self.tree.item(item[0])['values'][0]
        remote_path = (self.current_path + name).replace('//', '/')
        save_path = filedialog.asksaveasfilename(initialfile=name)
        if not save_path:
            return

        downloader = Downloader(self, remote_path, save_path)
        self.downloaders[remote_path] = downloader
        self.create_progress_ui(remote_path, name)
        downloader.start()
        self.dl_btn.config(state=tk.DISABLED)

    def create_progress_ui(self, remote_path, name):
        frame = tk.Frame(self.dl_inner, bg='#2d2d2d', relief='groove', bd=2)
        frame.pack(fill=tk.X, padx=5, pady=4)

        tk.Label(frame, text=name, bg='#2d2d2d', fg='white', anchor='w', font=('Segoe UI', 10, 'bold')).pack(fill=tk.X, padx=8, pady=2)

        pb = ttk.Progressbar(frame, mode='determinate')
        pb.pack(fill=tk.X, padx=8, pady=4)

        info = tk.Frame(frame, bg='#2d2d2d')
        info.pack(fill=tk.X, padx=8)
        speed_lbl = tk.Label(info, text="Speed: --", bg='#2d2d2d', fg='#00ff00', anchor='w')
        speed_lbl.pack(side=tk.LEFT)
        eta_lbl = tk.Label(info, text="ETA: --", bg='#2d2d2d', fg='#ffaa00', anchor='w')
        eta_lbl.pack(side=tk.LEFT, padx=20)
        size_lbl = tk.Label(info, text="0 / 0", bg='#2d2d2d', fg='gray', anchor='e')
        size_lbl.pack(side=tk.RIGHT)

        cancel_btn = tk.Button(frame, text="Cancel", command=lambda: self.cancel_download(remote_path),
                               bg='#c42b1c', fg='white')
        cancel_btn.pack(pady=4)

        self.progress_widgets[remote_path] = {
            'frame': frame, 'pb': pb, 'speed': speed_lbl,
            'eta': eta_lbl, 'size': size_lbl
        }

    def update_progress(self, remote_path, downloaded, total, start_time):
        if remote_path not in self.progress_widgets:
            return
        w = self.progress_widgets[remote_path]
        percent = (downloaded / total) * 100 if total > 0 else 0
        w['pb']['value'] = percent

        elapsed = time.time() - start_time
        speed = downloaded / elapsed if elapsed > 0 else 0
        w['speed'].config(text=f"Speed: {human_readable_speed(speed)}")

        remaining = total - downloaded
        eta = remaining / speed if speed > 0 else 0
        w['eta'].config(text=f"ETA: {format_eta(eta)}")

        w['size'].config(text=f"{human_readable_size(downloaded)} / {human_readable_size(total)}")

        if downloaded >= total:
            w['speed'].config(text="Speed: Complete")
            w['eta'].config(text="ETA: Done")

    def cancel_download(self, remote_path):
        if remote_path in self.downloaders:
            self.downloaders[remote_path].cancel()
        self.remove_download(remote_path)

    def remove_download(self, remote_path):
        if remote_path in self.progress_widgets:
            self.progress_widgets[remote_path]['frame'].destroy()
            del self.progress_widgets[remote_path]
        if remote_path in self.downloaders:
            del self.downloaders[remote_path]

if __name__ == "__main__":
    ClientGUI()
