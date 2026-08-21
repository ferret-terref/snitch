
import os
import sys
import threading
import traceback
import winreg as reg

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

# Import FastAPI server main function
from snitch.main import main as run_server

# Global server thread
server_thread = None


def log(msg):
    print(f"[TrayLauncher] {msg}")

def start_server():
    global server_thread
    try:
        if server_thread is None:
            log("Starting FastAPI server in background thread...")
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            log("Server thread started.")
    except Exception as e:
        log(f"Error starting server: {e}\n{traceback.format_exc()}")

def stop_server(icon, item):
    log("Stopping server and exiting...")
    # No direct way to stop uvicorn from another thread; recommend closing from tray and letting process exit
    icon.stop()

def is_in_startup():
    """Check if the app is registered to run on startup."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_READ)
        try:
            reg.QueryValueEx(key, "Snitch")
            reg.CloseKey(key)
            return True
        except FileNotFoundError:
            reg.CloseKey(key)
            return False
    except Exception as e:
        log(f"Error checking startup status: {e}")
        return False

def add_to_startup():
    """Add the app to Windows startup."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
        reg.SetValueEx(key, "Snitch", 0, reg.REG_SZ, exe_path)
        reg.CloseKey(key)
        log(f"Added to startup: {exe_path}")
        return True
    except Exception as e:
        log(f"Failed to add to startup: {e}")
        return False

def remove_from_startup():
    """Remove the app from Windows startup."""
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_SET_VALUE)
        reg.DeleteValue(key, "Snitch")
        reg.CloseKey(key)
        log("Removed from startup")
        return True
    except FileNotFoundError:
        log("App was not in startup")
        return True
    except Exception as e:
        log(f"Failed to remove from startup: {e}")
        return False

def toggle_startup(icon, item):
    """Toggle the startup setting."""
    if is_in_startup():
        if remove_from_startup():
            log("Startup disabled")
    else:
        if add_to_startup():
            log("Startup enabled")
    # Update the menu to reflect the new state
    icon.update_menu()

def create_image():
    try:
        # Draw an "eyes" (👀) emoji-like icon
        image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
        dc = ImageDraw.Draw(image)
        # Draw two white eyeballs
        dc.ellipse((8, 20, 32, 52), fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        dc.ellipse((32, 20, 56, 52), fill=(255, 255, 255), outline=(0, 0, 0), width=2)
        # Draw two black pupils
        dc.ellipse((18, 36, 28, 46), fill=(0, 0, 0))
        dc.ellipse((42, 36, 52, 46), fill=(0, 0, 0))
        log("Tray icon image (eyes) created.")
        return image
    except Exception as e:
        log(f"Error creating tray icon image: {e}\n{traceback.format_exc()}")
        raise

def setup(icon):
    # No longer needed; server is started before tray icon
    pass

def main():
    log("Starting server before tray icon...")
    start_server()
    log("Starting tray icon...")
    try:
        icon = Icon(
            'FastAPI Server',
            create_image(),
            menu=Menu(
                MenuItem('Launch on Startup', toggle_startup, checked=lambda item: is_in_startup()),
                MenuItem('Stop Server and Exit', stop_server)
            )
        )
        icon.run()
        log("Tray icon should now be visible.")
    except Exception as e:
        log(f"Error running tray icon: {e}\n{traceback.format_exc()}")

if __name__ == '__main__':
    main()
