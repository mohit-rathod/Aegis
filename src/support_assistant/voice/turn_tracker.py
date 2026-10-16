import uuid


class TurnTracker:
    def __init__(self):
        self.generation = 0

    def interrupt(self):
        self.generation += 1
        return self.generation

    def current(self, generation):
        return generation == self.generation

    def new_id(self):
        return "voice-" + uuid.uuid4().hex
