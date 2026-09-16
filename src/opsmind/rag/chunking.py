"""Deterministic small chunks; preserve headings and original line locations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    text: str
    heading: str
    line: int


def split_document(text: str, size: int = 100) -> list[Chunk]:
    if not 40 <= size <= 400:
        raise ValueError("Chunk size must be between 40 and 400.")
    chunks = []
    heading = "正文"
    buffer = ""
    start = 1
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            if buffer:
                chunks.append(Chunk(buffer, heading, start))
                buffer = ""
            if line.startswith("#"):
                heading = line.lstrip("# ")[:100]
            continue
        while line:
            if not buffer:
                start = number
            room = size - len(buffer)
            buffer += line[:room]
            line = line[room:]
            if len(buffer) == size:
                chunks.append(Chunk(buffer, heading, start))
                buffer = ""
        if buffer and len(buffer) < size:
            buffer += "\n"
    if buffer.strip():
        chunks.append(Chunk(buffer.strip(), heading, start))
    return chunks
