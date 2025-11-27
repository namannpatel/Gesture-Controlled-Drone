# gestures/maya_gesture_controller.py
import socket
import threading
import time

class MayaGestureController:
    def __init__(self, host="127.0.0.1", port=9000, reconnect=True):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()
        self.reconnect = reconnect
        self._connect()

    def _connect(self):
        try:
            with self.lock:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(3.0)
                self.sock.connect((self.host, self.port))
                self.sock.settimeout(None)
                print(f"[MayaClient] Connected to {self.host}:{self.port}")
        except Exception as e:
            print(f"[MayaClient] Connection failed: {e}")
            self.sock = None

    def send(self, msg):
        """
        Send a newline-terminated command. Retries once on failure.
        """
        if msg is None:
            return False
        data = (msg + "\n").encode("utf-8")
        try:
            if not self.sock and self.reconnect:
                self._connect()
            if not self.sock:
                print("[MayaClient] No connection.")
                return False
            with self.lock:
                self.sock.sendall(data)
            return True
        except Exception as e:
            print(f"[MayaClient] Send error: {e}")
            try:
                # try reconnect once
                if self.reconnect:
                    self._connect()
                    if self.sock:
                        with self.lock:
                            self.sock.sendall(data)
                        return True
            except Exception:
                pass
            self.sock = None
            return False

    def close(self):
        try:
            with self.lock:
                if self.sock:
                    self.sock.close()
                    self.sock = None
        except Exception:
            pass