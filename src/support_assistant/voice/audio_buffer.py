from collections import deque


class AudioBuffer:
    def __init__(self, frames=10):
        self.pre_roll = deque(maxlen=frames)

    def append(self, pcm):
        self.pre_roll.append(pcm)

    def snapshot(self):
        return list(self.pre_roll)

    def clear(self):
        self.pre_roll.clear()
