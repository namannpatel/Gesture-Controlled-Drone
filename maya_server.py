# start_gesture_server()

import socket
import threading
import time
import maya.cmds as cmds

try:
    from maya import utils as mutils
    HAVE_MUTILS = True
except:
    HAVE_MUTILS = False

HOST = "127.0.0.1"
PORT = 9000

DRONE = "drone_grp"

server_socket = None
running = False

motion_thread = None
motion_stop = threading.Event()
current_motion = None

# Motion speed tuning
DX = 0.10
DY = 0.10
DZ = 0.10
DELAY = 0.02

def run_on_main_thread(fn, *a, **kw):
    if HAVE_MUTILS:
        return mutils.executeInMainThreadWithResult(lambda: fn(*a, **kw))
    return fn(*a, **kw)


# Movement functions
def move_rel(dx, dy, dz):
    """Move drone relatively."""
    if cmds.objExists(DRONE):
        run_on_main_thread(cmds.move, dx, dy, dz, DRONE, r=True)


def move_abs(pos):
    """Set absolute world position."""
    if cmds.objExists(DRONE):
        run_on_main_thread(cmds.xform, DRONE, ws=True, t=pos)


# ================================================================
# Motion control
# ================================================================
def stop_motion():
    motion_stop.set()
    time.sleep(0.01)


def start_motion(direction):
    global motion_thread, current_motion

    stop_motion()
    motion_stop.clear()
    current_motion = direction

    def worker():
        while not motion_stop.is_set():

            if direction == "UP":
                move_rel(0, DY, 0)

            elif direction == "DOWN":
                move_rel(0, -DY, 0)

            elif direction == "LEFT":
                move_rel(-DX, 0, 0)

            elif direction == "RIGHT":
                move_rel(DX, 0, 0)

            elif direction == "FORWARD":
                move_rel(0, 0, -DZ)

            elif direction == "BACK":
                move_rel(0, 0, DZ)

            elif direction == "LAND":
                move_rel(0, -3 * DY, 0)

            elif direction == "RETURN_HOME":
                move_abs([0, 0, 0])

            time.sleep(DELAY)

    motion_thread = threading.Thread(target=worker)
    motion_thread.daemon = True
    motion_thread.start()


# ================================================================
# Command Handler
# ================================================================
def execute_drone_cmd(cmd):
    cmd = cmd.strip().upper()
    print("[MAYA] Received:", cmd)

    if cmd in ["UP", "DOWN", "LEFT", "RIGHT", "FORWARD", "BACK"]:
        start_motion(cmd)

    elif cmd == "STOP":
        stop_motion()

    elif cmd == "LAND":
        start_motion("LAND")
        time.sleep(0.5)
        stop_motion()

    elif cmd == "RETURN_HOME":
        start_motion("RETURN_HOME")
        time.sleep(0.7)
        stop_motion()

    else:
        print("[MAYA] Unknown command:", cmd)


# ================================================================
# Server
# ================================================================
def server_loop():
    global running
    while running:
        try:
            client, addr = server_socket.accept()
            print("[MAYA] Connected:", addr)
            with client:
                buffer = b""
                client.settimeout(1.0)
                while running:
                    try:
                        data = client.recv(1024)
                        if not data:
                            break
                        buffer += data
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            execute_drone_cmd(line.decode("utf-8"))
                    except socket.timeout:
                        continue
        except Exception as e:
            if running:
                print("[MAYA] Accept Error:", e)


def start_gesture_server(host=HOST, port=PORT):
    global server_socket, running

    if running:
        print("[MAYA] Server already running")
        return

    running = True

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((host, port))
    server_socket.listen(1)

    print(f"[MAYA] Listening on {host}:{port}")
    threading.Thread(target=server_loop, daemon=True).start()


def stop_gesture_server():
    global running
    running = False
    stop_motion()
    try:
        server_socket.close()
    except:
        pass
    print("[MAYA] Server stopped")