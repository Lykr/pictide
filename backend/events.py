"""Bounded lifecycle notifications; no worker or polling loop of its own."""
import asyncio

_STOP = object()


class EventHub:
    def __init__(self):
        self.revision = 0
        self.subscribers = set()
        self.closed = False

    def publish(self, topic):
        if self.closed:
            return
        self.revision += 1
        event = {"revision": self.revision, "topic": topic}
        for queue in tuple(self.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    def close(self):
        self.closed = True
        for queue in tuple(self.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(_STOP)

    async def stream(self):
        if self.closed:
            return
        queue = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        queue.put_nowait({"revision": self.revision, "topic": "ready"})
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20)
                    if event is _STOP:
                        return
                    yield event
                except asyncio.TimeoutError:
                    yield None
        finally:
            self.subscribers.discard(queue)
