import time

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem


def create_image():
    image = Image.new('RGB', (64, 64), (255, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse((8, 8, 56, 56), fill=(255, 255, 0))
    return image

def on_exit(icon, item):
    icon.stop()

icon = Icon(
    'TestTray',
    create_image(),
    menu=Menu(MenuItem('Exit', on_exit))
)

icon.run()
