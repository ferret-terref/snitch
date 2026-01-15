
import os
import sys
import threading
import traceback

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
                MenuItem('Stop Server and Exit', stop_server)
            )
        )
        icon.run()
        log("Tray icon should now be visible.")
    except Exception as e:
        log(f"Error running tray icon: {e}\n{traceback.format_exc()}")

if __name__ == '__main__':
    main()
