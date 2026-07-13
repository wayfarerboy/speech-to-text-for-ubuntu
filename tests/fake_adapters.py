"""Fake adapters for testing PushToTalkSession."""


class FakeIndicator:
    """Records show/hide calls for test assertions."""

    def __init__(self, pid=12345):
        self.calls = []
        self._pid = pid

    @property
    def pid(self):
        return self._pid

    def show(self, mode):
        self.calls.append(("show", mode))

    def hide(self):
        self.calls.append(("hide",))


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
