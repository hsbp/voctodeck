#!/usr/bin/env python3

#         Python Stream Deck Library
#      Released under the MIT license
#
#   dean [at] fourwalledcubicle [dot] com
#         www.fourwalledcubicle.com
#

# Example script showing basic library usage - updating key images with new
# tiles generated at runtime, and responding to button state change events.

import os
import threading
from PIL import Image, ImageDraw, ImageFont
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper

import socket
import json

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('localhost', 9999))
s.sendall(b'get_composite_mode_and_video_status\nget_stream_status\nget_audio\n')

# Generates a custom tile with run-time generated text and custom image via the
# PIL module.
def render_key_image(deck, font_filename, label_text, name):
    # Create new key image of the correct dimensions, black background
    image = PILHelper.create_image(deck)
    draw = ImageDraw.Draw(image)

    if name == active_scene:
        draw.rectangle((0, 0, image.width - 1, image.height - 1), fill=(255, 0, 0))
    elif name.startswith('stream-') and name[7:] == stream:
        draw.rectangle((0, 0, image.width - 1, image.height - 1), fill=(0, 0, 255))
    elif name == audio:
        draw.rectangle((0, 0, image.width - 1, image.height - 1), fill=(128, 0, 128))

    # Load a custom TrueType font and use it to overlay the key index, draw key
    # label onto the image
    font = ImageFont.truetype(font_filename, 14)
    label_w, label_h = draw.textsize(label_text, font=font)
    label_pos = ((image.width - label_w) // 2, (image.height - label_h) // 2)
    draw.text(label_pos, text=label_text, font=font, fill="white")

    return PILHelper.to_native_format(deck, image)


active_scene = None
stream = None
audio = None


# Returns styling information for a key based on its position and state.
def get_key_style(deck, key, state):
    # Last button in the example application is the exit button
    exit_key_index = deck.key_count() - 1
    font = "Roboto-Regular.ttf"

    if key == exit_key_index:
        name = "exit"
        label = "Bye" if state else "Exit"
    elif key == 0:
        name = "pc-full"
        label = "PC\nFULL"
    elif key == 1:
        name = "cam-full"
        label = "CAM\nFULL"
    elif key == 2:
        name = "pip"
        label = "Picture\nin\nPicture"
    elif key == 3:
        name = "stream-live"
        label = "STREAM\nLIVE"
    elif key == 5:
        name = "pc-audio"
        label = "PC\nAUDIO"
    elif key == 6:
        name = "cam-audio"
        label = "CAM\nAUDIO"
    elif key == 7:
        name = "sbsp"
        label = "Side-by-\nside\npreview"
    elif key == 8:
        name = "stream-blank-pause"
        label = "STREAM\nPAUSE"
    elif key == 10:
        name = "pc-restart"
        label = "PC\nRESTART"
    elif key == 11:
        name = "cam-restart"
        label = "CAM\nRESTART"
    elif key == 12:
        name = "sbse"
        label = "Side-by-\nside\nequal"
    elif key == 13:
        name = "stream-blank-nostream"
        label = "NO\nSTREAM"
    else:
        name = "emoji"
        label = ''

    return {
            "name": name,
            "font": os.path.join(os.path.dirname(__file__), "Assets", font),
            "label": label
            }


    # Creates a new key image based on the key index, style and current key state
# and updates the image on the StreamDeck.
def update_key_image(deck, key, state):
    # Determine what label to use on the generated key
    key_style = get_key_style(deck, key, state)

    # Generate the custom key with the requested image and label
    image = render_key_image(deck, key_style["font"], key_style["label"], key_style["name"])

    # Update requested key with the generated image
    deck.set_key_image(key, image)


# Prints key state change information, updates rhe key image and performs any
# associated actions when a key is pressed.
def key_change_callback(deck, key, state):
    # Print new key state
    print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)

    # Update the key image based on the new key state
    update_key_image(deck, key, state)

    # Check if the key is changing to the pressed state
    if state:
        key_style = get_key_style(deck, key, state)

        # When an exit button is pressed, close the application
        if key_style["name"] == "exit":
            # Reset deck, clearing all button images
            deck.reset()

            # Close deck handle, terminating internal worker threads
            deck.close()
            s.close()
        elif key_style["name"] == "pc-full":
            s.sendall(b'set_videos_and_composite slides * fullscreen\n')
        elif key_style["name"] == "cam-full":
            s.sendall(b'set_videos_and_composite cam * fullscreen\n')
        elif key_style["name"] == "pip":
            s.sendall(b'set_videos_and_composite slides cam picture_in_picture\n')
        elif key_style["name"] == "sbsp":
            s.sendall(b'set_videos_and_composite slides cam side_by_side_preview\n')
        elif key_style["name"] == "sbse":
            s.sendall(b'set_videos_and_composite slides cam side_by_side_equal\n')
        elif key_style["name"].startswith('stream-'):
            parts = key_style["name"].split('-')
            if parts[1] == 'blank':
                s.sendall(('set_stream_blank ' + parts[2] + '\n').encode('utf-8'))
            else:
                s.sendall(b'set_stream_live\n')
        elif key_style["name"] == "pc-audio":
            s.sendall(b'set_audio slides\n')
        elif key_style["name"] == "cam-audio":
            s.sendall(b'set_audio cam\n')
        

class RecvThread(threading.Thread):
    def __init__(self, deck):
        threading.Thread.__init__(self)
        self.deck = deck

    def run(self):
        global active_scene, stream, audio
        while True:
            for row in s.recv(1024).decode('utf-8').strip().split('\n'):
                data = row.split(' ')
                if data[0] == 'composite_mode_and_video_status':
                    if data[1] == 'fullscreen':
                        if data[2] == 'slides':
                            active_scene = 'pc-full'
                        elif data[2] == 'cam':
                            active_scene = 'cam-full'
                    elif data[1] == 'picture_in_picture':
                        if data[2] == 'slides':
                            active_scene = 'pip'
                        else:
                            active_scene = None
                    elif data[1] == 'side_by_side_preview':
                        if data[2] == 'slides':
                            active_scene = 'sbsp'
                        else:
                            active_scene = None
                    elif data[1] == 'side_by_side_equal':
                        if data[2] == 'slides':
                            active_scene = 'sbse'
                        else:
                            active_scene = None
                    else:
                        active_scene = None
                elif data[0] == 'stream_status':
                    stream = '-'.join(data[1:])
                elif data[0] == 'audio_status':
                    p = json.loads(row[13:])
                    if p['cam'] == 1:
                        audio = 'cam-audio'
                    elif p['slides'] == 1:
                        audio = 'pc-audio'
                    else:
                        audio = None
                print(repr(data))
                for key in range(deck.key_count()):
                    update_key_image(deck, key, False)


if __name__ == "__main__":
    streamdecks = DeviceManager().enumerate()

    print("Found {} Stream Deck(s).\n".format(len(streamdecks)))

    for index, deck in enumerate(streamdecks):
        deck.open()
        deck.reset()

        # Set initial screen brightness to 30%
        deck.set_brightness(30)

        # Set initial key images
        for key in range(deck.key_count()):
            update_key_image(deck, key, False)

        # Register callback function for when a key state changes
        deck.set_key_callback(key_change_callback)
        RecvThread(deck).start()

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed)
        for t in threading.enumerate():
            if t is threading.currentThread():
                continue

            if t.is_alive():
                t.join()
