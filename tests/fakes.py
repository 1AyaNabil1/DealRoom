"""Test doubles. FakeLLM stands in for Gemini so tests never touch the network."""
import time


class FakeLLM:
    """Replays scripted replies. An exception in the script is raised instead."""

    name = "fake-model"

    def __init__(self, *replies, delay_s: float = 0.0):
        self.replies = list(replies)
        self.delay_s = delay_s
        self.prompts: list[str] = []
        self.json_flags: list[bool] = []

    def generate(self, prompt: str, *, json_output: bool = False) -> str:
        self.prompts.append(prompt)
        self.json_flags.append(json_output)
        if self.delay_s:
            time.sleep(self.delay_s)
        # The last reply repeats once the script runs out.
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, BaseException):
            raise reply
        return reply

    @property
    def calls(self) -> int:
        return len(self.prompts)
