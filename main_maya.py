#!/usr/bin/venv python3
# python3 -m venv venv
# source venv/bin/activate

"""
Webcam -> gesture detector -> Maya TCP commands.
Make sure Maya server is running inside Maya via: start_gesture_server().
"""

import socket
import time
import cv2
import argparse
from collections import deque
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gestures.gesture_recognition import GestureRecognition, GestureBuffer
from gestures.maya_gesture_controller import MayaGestureController
from utils import CvFpsCalc

LABEL_TO_CMD = {
    "Up": "UP",
    "Down": "DOWN",
    "Back": "BACK",
    "Forward": "FORWARD",
    "OK": "LAND",
    "Stop": "STOP",
    "Left": "LEFT",
    "Right": "RIGHT",
    "Victory": "RETURN_HOME",
}


class StableDebouncer:
    def __init__(self, buffer_len=6, min_interval_s=0.5):
        self.buf = GestureBuffer(buffer_len)
        self.last_sent = None
        self.last_time = 0
        self.min_interval_s = min_interval_s

    def add_and_get(self, gesture_id):
        self.buf.add_gesture(gesture_id)
        gid = self.buf.get_gesture()
        if gid is None:
            return None

        now = time.time()
        if gid != self.last_sent or (now - self.last_time) > self.min_interval_s:
            self.last_sent = gid
            self.last_time = now
            return gid
        return None


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--device", type=int, default=0)
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--min_detection_confidence", type=float, default=0.5)
    p.add_argument("--min_tracking_confidence", type=float, default=0.5)
    p.add_argument("--buffer_len", type=int, default=6)
    return p.parse_args()


def main():
    args = parse_args()

    maya = MayaGestureController(host=args.host, port=args.port)

    gesture_detector = GestureRecognition(
        use_static_image_mode=False,
        min_detection_confidence=args.min_detection_confidence,
        min_tracking_confidence=args.min_tracking_confidence,
        history_length=16
    )

    deb = StableDebouncer(buffer_len=args.buffer_len, min_interval_s=0.35)

    cap = cv2.VideoCapture(args.device, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not cap.isOpened():
        print("ERROR: camera open failed — try another --device")
        return

    fps = CvFpsCalc(buffer_len=10)

    mode = 0         # 0 = normal, 1 = logging key points
    number = -1      # class id for logging (0-9), -1 = none
    last_stable = None

    print("Running Maya gesture client. Press ESC to exit.")
    print("Press 'n' to toggle Logging Key Point mode. While logging: press 0-9 to set class. 'c' cancels logging.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera error")
            break

        fps_val = fps.get()

        # pass current logging mode & number into recognition so samples are saved when mode==1
        debug_img, gesture_id = gesture_detector.recognize(frame, number=number, mode=mode)

        send_id = deb.add_and_get(gesture_id)
        if send_id is not None:
            label = gesture_detector.gesture_id_to_label(send_id)
            cmd = LABEL_TO_CMD.get(label)
            if cmd:
                print(f"[SEND] id={send_id} label='{label}'  ->  {cmd}")
                maya.send(cmd)
            else:
                print(f"[IGNORE] unmapped label: {label}")

        # overlay mode/fps/number using repository's draw_info
        try:
            debug_img = gesture_detector.draw_info(debug_img, fps_val, mode, number)
        except Exception:
            # fallback if draw_info fails
            try:
                cv2.putText(debug_img, f"FPS:{int(fps_val)}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            except Exception:
                pass

        # small overlay for detected label
        try:
            overlay = gesture_detector.gesture_id_to_label(gesture_id) or "-"
        except Exception:
            overlay = str(gesture_id)

        cv2.putText(debug_img, f"Detected: {overlay}", (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

        cv2.imshow("Gestures -> Maya", debug_img)

        key = cv2.waitKey(1) & 0xFF

        if key == 27:  # ESC
            break
        if key == ord('n'):
            mode = 1 if mode == 0 else 0
            if mode == 1:
                print("[MODE] Logging Key Point ON")
            else:
                print("[MODE] Logging Key Point OFF")
                number = -1
        if key == ord('c'):
            mode = 0
            number = -1
            print("[MODE] Logging Key Point OFF (cancelled)")
        # set number 0..9 while logging
        if mode == 1 and key in [ord(str(i)) for i in range(10)]:
            number = int(chr(key))
            print(f"[LOGGING] Selected class {number}")

    try:
        maya.send("LAND")
    except Exception:
        pass
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()