import json
import subprocess
import sys
import time
import threading
import argparse

import websocket


PING_INTERVAL = 10

DEFAULT_DELAY = 10

HOST = "localhost:3000"


def run(delay=DEFAULT_DELAY, command_args=None):
    if command_args is None:
        raise ValueError('`command_args` list is required')

    ws = websocket.create_connection(f"ws://{HOST}/api/ws", timeout=1)

    def send_json(d, msg=None):
        try:
            ws.send(json.dumps(d))
        except BrokenPipeError as e:
            if msg:
                print(f"{msg}: {e}")
            else:
                print(f"Error... Websocket was closed unexpectedly: {e}")
            exit(1)

    # Ping mindlessly to keep connection valid for long-running subprocesses.
    # If the main connection dies it'll be from a broken pipe/websocket
    command_done = False
    mutex = threading.Lock()
    def ping():
        while True:
            send_json({'ping': 'ping'}, "Ping Error... Unable to send ping")
            t = time.time()
            while (time.time() - t) < PING_INTERVAL:
                time.sleep(1)
                mutex.acquire()
                if command_done:
                    mutex.release()
                    return
                mutex.release()



    send_json({'initialize': True})
    msg = ws.recv()
    data = json.loads(msg)
    stream_id = data.get('stream_id')
    if not stream_id:
        print(f"Error initiating stream: {data}")
        return

    print(f"Page: http://{HOST}/{stream_id}")

    th = threading.Thread(target=ping)
    th.start()

    time.sleep(delay)

    with subprocess.Popen(command_args, stdout=subprocess.PIPE) as proc:
        for line in iter(proc.stdout.readline, ''):
            line = line.decode('utf8')
            sys.stdout.write(line)
            sys.stdout.flush()
            if not line:
                break
            send_json({'payload': line})

    mutex.acquire()
    command_done = True
    mutex.release()

    ws.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            formatter_class=argparse.RawTextHelpFormatter,
            description=
'''
James K. <james.kominick@gmail.com>
Pipe stdout to the webs
'''
        )
    parser.add_argument(
            '-d', '--delay',
            dest='delay',
            type=int,
            nargs=1,
            help='Set the delay in seconds to wait before running',
            required=False,
        )
    opts, remaining = parser.parse_known_args()

    delay = opts.delay[0] if opts.delay else DEFAULT_DELAY
    run(delay=delay, command_args=remaining)

