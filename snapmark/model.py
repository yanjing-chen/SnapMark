"""Annotation data model with no GTK dependency (unit-testable)."""
from dataclasses import dataclass, field
from math import hypot


@dataclass
class Mark:
    tool: str
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = '#e82c20'
    width: float = 4.0
    fill: bool = False
    opacity: float = 0.25
    text: str = ''
    points: list[tuple[float, float]] = field(default_factory=list)

    def is_meaningful(self) -> bool:
        if self.tool == 'text':
            return bool(self.text.strip())
        if self.tool == 'pen':
            return len(self.points) > 1
        return hypot(self.x2 - self.x1, self.y2 - self.y1) >= 2.0


class History:
    def __init__(self) -> None:
        self.marks: list[Mark] = []
        self.redo_stack: list[Mark] = []

    def push(self, mark: Mark) -> bool:
        if not mark.is_meaningful():
            return False
        self.marks.append(mark)
        self.redo_stack.clear()
        return True

    def undo(self) -> bool:
        if not self.marks:
            return False
        self.redo_stack.append(self.marks.pop())
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.marks.append(self.redo_stack.pop())
        return True


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def fit_zoom(width: int, height: int, available_width: int, available_height: int) -> float:
    if min(width, height, available_width, available_height) <= 0:
        return 1.0
    return min(1.0, available_width / width, available_height / height)
