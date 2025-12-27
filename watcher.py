import requests
import os
import time
import threading
import sys
import pystray
from PIL import Image
import urllib3
import ctypes
import subprocess
import psutil
import sqlite3
import webbrowser
import platform
from datetime import datetime
from flask import Flask, render_template_string, request
from win10toast_persist import ToastNotifier

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
REPO = "imputnet/helium-windows"
GITHUB_CHECK_INTERVAL = 600
LOCAL_CHECK_INTERVAL = 10
TARGET_DIR = os.getcwd()
VERSION_FILE = os.path.join(TARGET_DIR, "last_version.txt")
TOKEN_FILE = os.path.join(TARGET_DIR, "token.txt")
DB_FILE = os.path.join(TARGET_DIR, "watcher_v2.db")
REDIRECT_FILE = os.path.join(TARGET_DIR, "view_logs.html")
WEB_PORT = 9000

# --- Auto-Detect Architecture ---
def get_target_arch_string():
    """Detects system architecture to decide which installer to hunt."""
    arch = platform.machine().lower()
    if "arm" in arch or "aarch64" in arch:
        return "arm64-installer.exe"
    return "x64-installer.exe"

SEARCH_STR = get_target_arch_string()

# --- Physical Log Setup ---
LOGS_DIR = os.path.join(TARGET_DIR, "logs")
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Generate Session Identifiers
SESSION_ID = datetime.now().strftime("%b %d • %H:%M")
SESSION_FILENAME = datetime.now().strftime("watcher_%Y-%m-%d_%H-%M.txt")
TXT_LOG_PATH = os.path.join(LOGS_DIR, SESSION_FILENAME)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

ICON_PATH = resource_path("icon.png")

# --- Globals ---
status_text = f"Watcher: Checking for new releases({SEARCH_STR.split('-')[0]})"
icon = None
toaster = ToastNotifier()
app = Flask(__name__)

# --- Database & Logging ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY, session_id TEXT, date TEXT, time TEXT, level TEXT, message TEXT)''')
    conn.commit()
    conn.close()

def log_event(level, message):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    
    # DB Write
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO logs (session_id, date, time, level, message) VALUES (?, ?, ?, ?, ?)",
                  (SESSION_ID, date_str, time_str, level, message))
        conn.commit()
        conn.close()
    except: pass

    # Txt Write
    try:
        with open(TXT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{date_str} {time_str}] [{level}] {message}\n")
    except: pass

# --- Web Interface ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Watcher Chronicles</title>
    <style>
        :root { --sidebar-width: 280px; --accent: #9b59b6; --bg: #121212; --panel: #1e1e1e; --text: #e0e0e0; }
        body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; height: 100vh; display: flex; overflow: hidden; }
        
        .sidebar { width: var(--sidebar-width); background: #000; border-right: 1px solid #333; display: flex; flex-direction: column; height: 100%; box-shadow: 2px 0 10px rgba(0,0,0,0.5); }
        .sidebar-header { padding: 20px; border-bottom: 2px solid var(--accent); text-align: center; background: #0a0a0a; }
        .sidebar-header h1 { margin: 0; font-size: 1.2em; letter-spacing: 2px; color: var(--accent); text-transform: uppercase; }
        .session-list { flex-grow: 1; overflow-y: auto; list-style: none; padding: 0; margin: 0; }
        .session-item { padding: 15px 20px; border-bottom: 1px solid #222; cursor: pointer; transition: all 0.2s; display: flex; justify-content: space-between; align-items: center; }
        .session-item:hover { background: #1a1a1a; padding-left: 25px; }
        .session-item.active { background: var(--accent); color: #fff; border-left: 4px solid #fff; }
        .session-item .date { font-weight: bold; font-size: 0.95em; }
        .session-item .count { font-size: 0.8em; opacity: 0.7; background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 4px; }
        
        .main { flex-grow: 1; display: flex; flex-direction: column; height: 100%; background: var(--panel); position: relative; }
        .log-container { flex-grow: 1; overflow-y: auto; padding: 0; scroll-behavior: smooth; }
        .log-header { padding: 15px 25px; background: #252525; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }
        .log-header h2 { margin: 0; font-size: 1.1em; color: #fff; }
        .refresh-btn { background: transparent; border: 1px solid var(--accent); color: var(--accent); padding: 5px 15px; cursor: pointer; border-radius: 4px; transition: 0.3s; }
        .refresh-btn:hover { background: var(--accent); color: #fff; }

        .entry { display: flex; padding: 10px 20px; border-bottom: 1px solid #2a2a2a; font-family: 'Consolas', monospace; font-size: 0.9em; align-items: flex-start; }
        .entry:hover { background: #2a2a2a; }
        .entry .time { color: #666; width: 80px; min-width: 80px; margin-right: 15px; }
        .entry .lvl { padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 0.8em; margin-right: 15px; min-width: 60px; text-align: center; }
        .entry .msg { color: #ddd; word-break: break-word; line-height: 1.4; }

        .INFO { background: rgba(52, 152, 219, 0.15); color: #3498db; }
        .SUCCESS { background: rgba(46, 204, 113, 0.15); color: #2ecc71; }
        .WARNING { background: rgba(241, 196, 15, 0.15); color: #f1c40f; }
        .ERROR { background: rgba(231, 76, 60, 0.15); color: #e74c3c; }
        .PURGE { background: rgba(155, 89, 182, 0.15); color: #d8bfd8; }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #000; }
        ::-webkit-scrollbar-thumb { background: #444; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <h1>Watcher Logs</h1>
        </div>
        <ul class="session-list">
            {% for sess in sessions %}
                <li class="session-item {% if sess[0] == current_session %}active{% endif %}" onclick="window.location.href='/?session={{ sess[0] }}'">
                    <span class="date">{{ sess[0] }}</span>
                    <span class="count">{{ sess[1] }} Events</span>
                </li>
            {% endfor %}
        </ul>
    </div>
    
    <div class="main">
        <div class="log-header">
            <h2>Session: {{ current_session }}</h2>
            <button class="refresh-btn" onclick="location.reload()">Refresh Data</button>
        </div>
        <div class="log-container" id="logBox">
            {% for entry in logs %}
                <div class="entry">
                    <div class="time">{{ entry[3] }}</div>
                    <div class="lvl {{ entry[4] }}">{{ entry[4] }}</div>
                    <div class="msg">{{ entry[5] }}</div>
                </div>
            {% endfor %}
        </div>
    </div>
    <script>
        var logBox = document.getElementById("logBox");
        logBox.scrollTop = logBox.scrollHeight;
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT session_id, COUNT(*) FROM logs GROUP BY session_id ORDER BY id DESC")
        sessions = c.fetchall()
        selected_session = request.args.get('session')
        if not selected_session and sessions:
            selected_session = sessions[0][0]
        logs = []
        if selected_session:
            c.execute("SELECT * FROM logs WHERE session_id=? ORDER BY id ASC", (selected_session,))
            logs = c.fetchall()
        conn.close()
        return render_template_string(HTML_TEMPLATE, sessions=sessions, logs=logs, current_session=selected_session)
    except Exception as e:
        return f"Error reading chronicles: {e}"

def run_web_server():
    with open(REDIRECT_FILE, 'w') as f:
        f.write(f'<meta http-equiv="refresh" content="0; url=http://127.0.0.1:{WEB_PORT}" />')
    cli = sys.modules['flask.cli']
    cli.show_server_banner = lambda *x: None
    app.run(port=WEB_PORT, use_reloader=False)

# --- Watcher Logic ---

def send_alert(title, message):
    def _toast():
        try:
            toaster.show_toast(title, message, icon_path=ICON_PATH if os.path.exists(ICON_PATH) else None, duration=5)
        except: pass
    threading.Thread(target=_toast, daemon=True).start()

def format_speed(bps):
    if bps > 1024 * 1024: return f"{bps / (1024 * 1024):.1f} MB/s"
    return f"{bps / 1024:.1f} KB/s"

def format_time(s):
    if s < 0: return "--:--"
    m, s = divmod(int(s), 60)
    return f"{m:02d}:{s:02d}"

def kill_processes():
    targets = ["chrome.exe", "Helium", "helium"]
    log_event("PURGE", f"Purging processes: {targets}")
    count = 0
    for proc in psutil.process_iter(['name']):
        try:
            p_name = proc.info['name']
            if any(t.lower() in p_name.lower() for t in targets):
                proc.kill()
                count += 1
        except: pass
    log_event("PURGE", f"Eliminated {count} active processes.")

def prompt_install(filepath):
    msg = "Helium download complete.\n\nRun installer now?\n\nWARNING: This will kill Chrome & Helium."
    res = ctypes.windll.user32.MessageBoxW(0, msg, "Watcher Decree", 0x04 | 0x30 | 0x40000)
    if res == 6: 
        kill_processes()
        log_event("SUCCESS", f"Launching installer: {filepath}")
        subprocess.Popen([filepath], shell=True)

def get_token():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f: return f.read().strip()
        except: pass
    return None

def download_file(url, filename, version):
    global status_text
    filepath = os.path.join(TARGET_DIR, filename)
    log_event("INFO", f"Starting download: {filename}")
    send_alert("Retrieval Started", f"Downloading Helium {version}...")
    
    try:
        start = time.time()
        last_upd = time.time()
        response = requests.get(url, stream=True, timeout=60, verify=False)
        total = int(response.headers.get('content-length', 0))
        dl = 0
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=16384):
                if chunk:
                    f.write(chunk)
                    dl += len(chunk)
                    now = time.time()
                    if now - last_upd > 1.0:
                        speed = dl / (now - start)
                        eta = (total - dl) / speed if speed > 0 else 0
                        pct = int((dl / total) * 100) if total > 0 else 0
                        status_text = f"{version} ({pct}%) | {format_speed(speed)} | ETA {format_time(eta)}"
                        if icon: icon.title = status_text
                        last_upd = now

        status_text = f"Watcher: Checking for new releases ({SEARCH_STR.split('-')[0]})"
        if icon: icon.title = status_text
        log_event("SUCCESS", f"Download secured: {filename}")
        send_alert("Success", f"Helium {version} Ready.")
        threading.Thread(target=prompt_install, args=(filepath,), daemon=True).start()
        return True
    except Exception as e:
        log_event("ERROR", f"Download failed: {str(e)}")
        status_text = "Watcher: Error"
        if icon: icon.title = status_text
        return False

def monitor_logic():
    log_event("INFO", f"Watcher Session Initialized ({SESSION_ID}). Target: {SEARCH_STR}")
    last_check = 0
    cached_v, cached_n, cached_u = None, None, None
    
    while True:
        try:
            curr = time.time()
            # GitHub Check
            if (cached_v is None) or (curr - last_check > GITHUB_CHECK_INTERVAL):
                log_event("INFO", "Scanning GitHub...")
                url = f"https://api.github.com/repos/{REPO}/releases/latest"
                head = {'User-Agent': 'Watcher'}
                tk = get_token()
                if tk: head['Authorization'] = f'token {tk}'
                r = requests.get(url, headers=head, timeout=15, verify=False)
                if r.status_code == 200:
                    d = r.json()
                    # THIS IS THE CRITICAL CHANGE: Uses SEARCH_STR variable
                    ast = next((a for a in d.get('assets', []) if SEARCH_STR in a['name']), None)
                    if ast:
                        cached_v, cached_n, cached_u = d['tag_name'], ast['name'], ast['browser_download_url']
                        last_check = curr
                        log_event("INFO", f"Latest Intel: {cached_v} (Asset: {cached_n})")
                    else:
                        log_event("WARNING", f"Version found {d['tag_name']}, but no asset matched '{SEARCH_STR}'")
                elif r.status_code == 403:
                    log_event("WARNING", "Rate Limit Hit. Cooling down.")
                    time.sleep(300)
            
            # Local Check
            if cached_v:
                t_path = os.path.join(TARGET_DIR, cached_n)
                local_v = None
                if os.path.exists(VERSION_FILE):
                    with open(VERSION_FILE, 'r') as f: local_v = f.read().strip()
                
                if not os.path.exists(t_path) or local_v != cached_v:
                    log_event("WARNING", f"Mismatch detected. Local: {local_v} vs Remote: {cached_v}")
                    if download_file(cached_u, cached_n, cached_v):
                        with open(VERSION_FILE, 'w') as f: f.write(cached_v)
        except Exception as e:
            log_event("ERROR", f"Logic Loop Error: {e}")
        time.sleep(LOCAL_CHECK_INTERVAL)

def open_logs_page():
    if os.path.exists(REDIRECT_FILE): os.startfile(REDIRECT_FILE)
    else: webbrowser.open(f"http://127.0.0.1:{WEB_PORT}")

def open_local_logs_folder():
    if os.path.exists(LOGS_DIR):
        os.startfile(LOGS_DIR)

def on_quit(icon, item):
    log_event("INFO", "Session Ended.")
    icon.stop()
    os._exit(0)

def setup_tray():
    global icon
    img_path = resource_path("icon.png")
    img = Image.open(img_path) if os.path.exists(img_path) else Image.new('RGB', (64, 64), (128, 0, 128))
    
    menu = pystray.Menu(
        pystray.MenuItem("Open Web Dashboard", open_logs_page),
        pystray.MenuItem("Open Local Logs", open_local_logs_folder),
        pystray.MenuItem("Quit", on_quit)
    )
    
    icon = pystray.Icon("Watcher", img, title=status_text, menu=menu)
    icon.run()

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_web_server, daemon=True).start()
    threading.Thread(target=monitor_logic, daemon=True).start()
    setup_tray()
