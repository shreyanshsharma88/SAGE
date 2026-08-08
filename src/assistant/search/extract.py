from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedPage:
    url: str
    title: str
    text: str


def extract_main_text(url: str, html: str) -> ExtractedPage:
    assert False, "not yet implemented — next session"
