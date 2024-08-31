import time


def process_messages(wl):
    start = time.time()
    while time.time() < start + 1:
        wl.process_messages()
