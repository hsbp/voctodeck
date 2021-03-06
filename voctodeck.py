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
import time
import threading
from subprocess import Popen, call, check_output
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
def render_key_image(deck, btn):
    # Create new key image of the correct dimensions, black background
    image = PILHelper.create_image(deck)
    draw = ImageDraw.Draw(image)

    if btn.selected:
        draw.rectangle((0, 0, image.width - 1, image.height - 1), fill=btn.selected_color)

    label_w, label_h = draw.textsize(btn.label)
    label_pos = ((image.width - label_w) // 2, (image.height - label_h) // 2)
    draw.text(label_pos, text=btn.label, fill="white")

    return PILHelper.to_native_format(deck, image)


class Button(object):
    selected = False

    def __init__(self, label=""):
        self.label = label

    def pressed(self):
        pass


SCENE_BUTTONS = {}

class SceneButton(Button):
    selected_color = (255, 0, 0)

    def __init__(self, label, layout, inputs):
        Button.__init__(self, label)
        self.scene = (' '.join(inputs) + ' ' + layout).encode('utf-8')
        SCENE_BUTTONS[tuple([layout] + inputs)] = self

    def pressed(self):
        s.sendall(b'set_videos_and_composite ' + self.scene + b'\n')

AUDIO_BUTTONS = []


class AudioButton(Button):
    selected_color = (128, 0, 128)

    def __init__(self, label, channel):
        Button.__init__(self, label)
        self.channel = channel
        AUDIO_BUTTONS.append(self)

    def pressed(self):
        s.sendall(f'set_audio {self.channel}\n'.encode('utf-8'))


STREAM_BUTTONS = {}

class StreamButton(Button):
    selected_color = (0, 0, 255)

    def __init__(self, label, state, blank):
        Button.__init__(self, label)
        self.state = state.encode('utf-8')
        self.blank = blank
        STREAM_BUTTONS[state, blank] = self

    def pressed(self):
        s.sendall(((b'set_stream_blank ' + self.state) if self.blank else b'set_stream_live') + b'\n')


class ExecButton(Button):
    def __init__(self, label, cmd):
        Button.__init__(self, label)
        self.cmd = cmd

    def pressed(self):
        Popen(self.cmd, shell=True)

I3BUTTONS = {}

class I3workspaceButton(Button):
    selected_color = (128, 128, 0)

    def __init__(self, label, workspace):
        Button.__init__(self, label)
        self.workspace = workspace
        I3BUTTONS[workspace] = self

    def pressed(self):
        Popen(['i3-msg', 'workspace', str(self.workspace)])

UPDATE_BUTTONS = []

class ExecUpdateButton(ExecButton):
    selected_color = (0, 128, 0)

    def __init__(self, label, cmd, update):
        ExecButton.__init__(self, label, cmd)
        self.update = update
        UPDATE_BUTTONS.append(self)


BUTTONS = [
        SceneButton("PC\nFULL", "fullscreen", ["slides", "cam"]),
        SceneButton("CAM\nFULL", "fullscreen", ["cam", "slides"]),
        SceneButton("Picture\nin\nPicture", "picture_in_picture", ["slides", "cam"]),
        StreamButton("STREAM\nLIVE", "live", blank=False),
        ExecButton('WP7', 'i3-msg workspace 7'),

        AudioButton("PC\nAUDIO", "slides"),
        AudioButton("CAM\nAUDIO", "cam"),
        SceneButton("Side-by-\nside\npreview", "side_by_side_preview", ["slides", "cam"]),
        StreamButton("STREAM\nPAUSE", "pause", blank=True),
        ExecUpdateButton('YK', 'systemctl --user restart yubikey-agent', 'systemctl --user status yubikey-agent >/dev/null'),

        Button("PC\nRESTART"),
        Button("CAM\nRESTART"),
        SceneButton("Side-by-\nside\nequal", "side_by_side_equal", ["slides", "cam"]), 
        StreamButton("NO\nSTREAM", "nostream", blank=True),
        ExecUpdateButton('MIC\nMUTE', './micmute.sh', 'amixer get Digital | grep -Fq "Capture 0 ["'),
        ]

    # Creates a new key image based on the key index, style and current key state
# and updates the image on the StreamDeck.
def update_key_image(deck, key):
    # Generate the custom key with the requested image and label
    image = render_key_image(deck, BUTTONS[key])

    # Update requested key with the generated image
    deck.set_key_image(key, image)


# Prints key state change information, updates rhe key image and performs any
# associated actions when a key is pressed.
def key_change_callback(deck, key, state):
    # Print new key state
    print("Deck {} Key {} = {}".format(deck.id(), key, state), flush=True)

    if state:
        BUTTONS[key].pressed()
        

class TickThread(threading.Thread):
    def __init__(self, deck):
        threading.Thread.__init__(self)
        self.deck = deck

    def run(self):
        while True:
            needs_update = False
            for btn in UPDATE_BUTTONS:
                old = btn.selected
                btn.selected = call(btn.update, shell=True) == 0
                needs_update |= btn.selected ^ old
            if needs_update:
                deck = self.deck
                for key in range(deck.key_count()):
                    update_key_image(deck, key)
            time.sleep(0.2)


class I3Thread(threading.Thread):
    def __init__(self, deck):
        threading.Thread.__init__(self)
        self.deck = deck

    def run(self):
        last_json = None
        while True:
            needs_update = False
            workspaces = check_output(['i3-msg', '-t', 'get_workspaces'])
            if workspaces != last_json:
                for workspace in json.loads(workspaces):
                    btn = I3BUTTONS.get(workspace['num'])
                    if not btn:
                        continue
                    old = btn.selected
                    btn.selected = workspace['visible']
                    needs_update |= btn.selected ^ old
                if needs_update:
                    deck = self.deck
                    for key in range(deck.key_count()):
                        update_key_image(deck, key)
                last_json = workspaces
            time.sleep(0.2)


class VideoThread(threading.Thread):
    def __init__(self, deck):
        threading.Thread.__init__(self)
        self.deck = deck

    def run(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 5555))
        s.listen(1)
        conn, addr = s.accept()
        with conn:
            while True:
                image = PILHelper.create_image(deck)
                frame = conn.recv(11664)
                if not frame:
                    break
                video = Image.frombytes('RGB', (72,54), frame, 'raw')
                image.paste(video, (0, 0))
                deck.set_key_image(14, PILHelper.to_native_format(deck, image))



class RecvThread(threading.Thread):
    def __init__(self, deck):
        threading.Thread.__init__(self)
        self.deck = deck

    def run(self):
        while True:
            for row in s.recv(1024).decode('utf-8').strip().split('\n'):
                data = row.split(' ')
                if data[0] == 'composite_mode_and_video_status':
                    for v in SCENE_BUTTONS.values():
                        v.selected = False
                    b = SCENE_BUTTONS.get(tuple(data[1:]))
                    if b is not None:
                        b.selected = True
                elif data[0] == 'stream_status':
                    for v in STREAM_BUTTONS.values():
                        v.selected = False
                    b = STREAM_BUTTONS.get((data[-1], data[1] == 'blank'))
                    if b is not None:
                        b.selected = True
                elif data[0] == 'audio_status':
                    p = json.loads(row[13:])
                    for b in AUDIO_BUTTONS:
                        b.selected = p[b.channel] == 1
                print(repr(data))
                for key in range(deck.key_count()):
                    update_key_image(deck, key)


if __name__ == "__main__":
    streamdecks = DeviceManager().enumerate()

    print("Found {} Stream Deck(s).\n".format(len(streamdecks)))

    for deck in streamdecks:
        deck.open()
        deck.reset()

        # Set initial screen brightness to 30%
        deck.set_brightness(30)

        # Set initial key images
        for key in range(deck.key_count()):
            update_key_image(deck, key)

        # Register callback function for when a key state changes
        deck.set_key_callback(key_change_callback)
        RecvThread(deck).start()
        TickThread(deck).start()
        I3Thread(deck).start()
        VideoThread(deck).start()

        # Wait until all application threads have terminated (for this example,
        # this is when all deck handles are closed)
        for t in threading.enumerate():
            if t is threading.currentThread():
                continue

            if t.is_alive():
                t.join()
