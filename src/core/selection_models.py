from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from uuid import uuid4


Point = tuple[float, float]


@dataclass(slots=True)
class RegionSelection:
    kind: str
    points: list[Point]
    id: str = field(default_factory=lambda: uuid4().hex)

    def bounds(self) -> tuple[int, int, int, int]:
        xs = [point[0] for point in self.points]
        ys = [point[1] for point in self.points]
        return (
            int(min(xs)),
            int(min(ys)),
            int(max(xs)),
            int(max(ys)),
        )

    def translated(self, dx: float, dy: float) -> "RegionSelection":
        return RegionSelection(
            id=self.id,
            kind=self.kind,
            points=[(x + dx, y + dy) for x, y in self.points],
        )

    def with_point(self, point_index: int, point: Point) -> "RegionSelection":
        updated = list(self.points)
        updated[point_index] = point
        return RegionSelection(id=self.id, kind=self.kind, points=updated)


def combined_bounds(selections: Iterable[RegionSelection]) -> tuple[int, int, int, int] | None:
    selection_list = list(selections)
    if not selection_list:
        return None

    left = min(selection.bounds()[0] for selection in selection_list)
    top = min(selection.bounds()[1] for selection in selection_list)
    right = max(selection.bounds()[2] for selection in selection_list)
    bottom = max(selection.bounds()[3] for selection in selection_list)
    return left, top, right, bottom


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    x, y = point
    inside = False
    count = len(polygon)
    if count < 3:
        return False

    for index in range(count):
        x1, y1 = polygon[index]
        x2, y2 = polygon[(index + 1) % count]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1
        )
        if intersects:
            inside = not inside
    return inside


def nearest_point_index(point: Point, points: list[Point], radius: float) -> int | None:
    px, py = point
    best_index: int | None = None
    best_distance = radius * radius
    for index, (x, y) in enumerate(points):
        distance = (x - px) ** 2 + (y - py) ** 2
        if distance <= best_distance:
            best_distance = distance
            best_index = index
    return best_index
