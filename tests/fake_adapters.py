"""Fake adapters for testing PushToTalkSession."""


class FakeIndicator:
    """Records show/hide calls for test assertions."""

    def __init__(self):
        self.calls = []
        self.closed = False

    def show(self, mode):
        self.calls.append(("show", mode))

    def hide(self):
        self.calls.append(("hide",))

    def close(self):
        self.closed = True


class FakeTranscriber:
    """Returns a canned transcript."""

    def __init__(self, text="hello world"):
        self.text = text
        self.calls = []

    def transcribe(self, audio_path, language="en"):
        self.calls.append((audio_path, language))
        return self.text


class FakeTyper:
    """Records typed text."""

    def __init__(self):
        self.texts = []

    def type(self, text):
        self.texts.append(text)
