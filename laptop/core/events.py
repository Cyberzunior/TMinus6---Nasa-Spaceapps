"""Thread-safe event bus. Device threads post, the main loop drains once a frame."""
import collections
import queue

Event = collections.namedtuple("Event", "kind data")


class Bus:
    def __init__(self):
        self._q = queue.Queue()

    def post(self, kind, *data):
        self._q.put(Event(kind, data))

    def drain(self, limit=500):
        out = []
        try:
            while len(out) < limit:
                out.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return out
