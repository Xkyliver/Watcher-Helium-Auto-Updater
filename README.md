# Watcher: Helium Auto-Updater
   * Note: Unofficial and only for x64 Windows

## Features

* **Real-Time HUD:** Monitor download speed and estimated time of arrival (ETA) by hovering over the System Tray icon.
* **Integrity Guard:** Scans the local directory every 10 seconds. If a version installer is missing, it is immediately re-downloaded.
* **Purge Protocol:** Optional automated termination of chrome.exe(as the process name for Helium is chrome.exe) processes to ensure the installer can run and update Helium.
* **Session Chronicles:** Unique log files are generated for every session and stored in a dedicated /logs folder.
* **Background Operation:** Runs as a persistent background process in the System Tray to avoid taskbar clutter.

## Installation and Usage

1. **Download:** download the Watcher.exe from the Releases page.
2. **Setup:** Place the executable in the directory where you wish to save your Helium installers.
3. **Execution:** Run the executable. An icon will appear in your System Tray(same icon as helium).
    * You scanned the .exe file with Virustotal and a few vendors said its mailicous? It is not. when a new version is downloaded, watcher asks to kill chrome.exe(helium is chrome.exe) and run the latest installer and that triggers these false positiives

## Rate Limit Management (Required if you don't want to run into issues after a few hours)

Because this script checks for new releases every 10 minutes and every 10 seconds if the latest version is downlaoded, Github adds a rate limit. To bypass standard GitHub API rate limits we need to create a personal access token:
1. Create a file named token.txt in the same directory as the executable.
2. Paste a GitHub Personal Access Token into this file.
    * Steps to create a personal access token:
    * Create Github account
    * Open account Settings
    * In left sidebar, scroll to bottom and click on developer settings
    * in left sidebar click on personal access tokens and select token(classic)
    * create a classic token 
4. The script will automatically detect the token and apply it to all GitHub requests.

## System Tray Menu

* **Open Local Logs:** Opens the directory containing all session logs.
*  **Open Web Dashboard:** Opens a web-page contaning all the logs
* **Quit:** Terminates the watcher process.

## FAQ
* Why don't you provide a pre-made token?: I can't it's against github's rule and github will most likely revoke access so please create your own.
* How to run this 24/7?: Open task scheduler and create a basic task. Select every time I log on in triggers and choose start a program in action and select the watcher.exe
* Also, while choosing the watcher.exe there will be an option to add start-in. here, paste the path where the watcher.exe is, not the path to exe but path to the folder where it is otherwise it will fail, as to why? Because watcher.exe doesn't run as admministrator and because of this, it can't create or store files in System32, to fix that we have to add this start-in and also we don't want to store files in System32 as it all will be scattered around.
* Where is the source code, I want to check if this is malicious: Please check the Watcher.py file in the repo and if you want to directly run the .py, install all the dependencies with `pip install requests pystray Pillow psutil flask win10toast-persist` and as before, add a personal access token too in a `token.txt` file and a icon as `icon.png` . all the source code is there. To compile it into an .exe first install the builder with `pip install pyinstaller` then run `pyinstaller --noconsole --onefile --icon=icon.png --add-data "icon.png;." --name="Watcher" watcher.py` to compile.

## How does this work?

### 1. The Tri-Core Architecture
When launched, the application splits into three parallel threads to ensure zero latency:

The Sentinel: Runs the infinite loop checking for updates and file integrity.

The Architect: Hosts a local Flask web server on port 9000 to render the dashboard.

The Interface: Manages the System Tray icon and Windows context menu interactions.

### 2. The Logic Loop
GitHub Patrol (Every 10 Minutes): Igris queries the GitHub API for the "Latest Release" tag.

Rate Limit Bypass: If a token.txt file is detected, it utilizes the provided Personal Access Token to increase API limits (from 60/hr to 5000/hr).

Local Integrity Scan (Every 10 Seconds): It verifies the contents of your local directory.

If the installer corresponding to the latest known version is missing, a retrieval is triggered immediately.

This ensures that if an installer is accidentally deleted, Igris restores it instantly.

### 3. The Purge Protocol
Updating software while it is running often leads to file corruption or lock errors.

Upon securing a download, Watcher presents a Popup Prompt.

If confirmed: The script utilizes the psutil library to scan active processes.

It specifically targets chrome.exe(Helium is chrome.exe) processes.

Once the path is clear, the new installer is launched automatically and Helium is updated.

### 4. Dual-Logging System
Watcher maintains two separate archives for redundancy:

The Database (igris_v2.db): An SQLite database storing structured logs. This powers the Web Dashboard, enabling session grouping and the sidebar interface.

Physical Archives (/logs/*.txt): Raw text files generated for every session, ensuring data is accessible even without the web interface.

### 5. The Web Dashboard
Watcher hosts a lightweight, dark-themed dashboard locally at http://127.0.0.1:9000.

A shortcut file named view_logs.html is generated next to the executable; opening it redirects your browser to the local port.

Privacy: This server is bound to localhost, meaning it is inaccessible to external networks.

### 6. File Structure
Upon initialization, the tool establishes the following domain:

Watcher.exe (The core application)

igris_v2.db (The log database)

view_logs.html (Dashboard shortcut)

/logs/ (Directory containing text log archives)

token.txt (required as otherwise watcher will hit the rate limit user-created file for API tokens)
