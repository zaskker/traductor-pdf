from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    """Representa un rectángulo geométrico axis-aligned en un espacio de coordenadas explícito por contexto."""

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        # Permitimos x0 == x1 y y0 == y1 (área cero) para geometrías degeneradas (líneas/puntos).
        # El área final para operaciones que requieran superficie positiva se validará donde corresponda.
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError(
                f"Coordenadas inválidas: x0={self.x0}, y0={self.y0}, x1={self.x1}, y1={self.y1}"
            )

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Point:
        return Point(self.x0 + self.width / 2, self.y0 + self.height / 2)

    def contains_point(self, pt: Point) -> bool:
        return self.x0 <= pt.x <= self.x1 and self.y0 <= pt.y <= self.y1

    def intersect(self, other: "Rect") -> "Rect":
        new_x0 = max(self.x0, other.x0)
        new_y0 = max(self.y0, other.y0)
        new_x1 = min(self.x1, other.x1)
        new_y1 = min(self.y1, other.y1)

        # If they don't intersect, return an empty rect at the origin or similar
        # Since Rect requires x0 <= x1, we must clamp
        if new_x0 > new_x1 or new_y0 > new_y1:
            return Rect(0, 0, 0, 0)

        return Rect(new_x0, new_y0, new_x1, new_y1)
