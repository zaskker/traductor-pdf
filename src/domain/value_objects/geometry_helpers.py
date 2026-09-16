from src.domain.value_objects.geometry import Rect


def move_rect(rect: Rect, dx: float, dy: float) -> Rect:
    return Rect(rect.x0 + dx, rect.y0 + dy, rect.x1 + dx, rect.y1 + dy)


def clamp_move(rect: Rect, bounds: Rect) -> Rect:
    """Clamps a rect within bounds, preserving its width and height when possible."""
    w = min(rect.width, bounds.width)
    h = min(rect.height, bounds.height)

    x0 = max(bounds.x0, min(rect.x0, bounds.x1 - w))
    y0 = max(bounds.y0, min(rect.y0, bounds.y1 - h))

    return Rect(x0, y0, x0 + w, y0 + h)


def resize_rect(rect: Rect, handle: str, dx: float, dy: float, min_size: float = 1.0) -> Rect:
    """
    Resizes a rect by moving one of its corners by (dx, dy).
    Enforces a minimum size and prevents negative dimensions.
    """
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1

    if handle == "TL":
        x0 = min(x0 + dx, x1 - min_size)
        y0 = min(y0 + dy, y1 - min_size)
    elif handle == "TR":
        x1 = max(x1 + dx, x0 + min_size)
        y0 = min(y0 + dy, y1 - min_size)
    elif handle == "BL":
        x0 = min(x0 + dx, x1 - min_size)
        y1 = max(y1 + dy, y0 + min_size)
    elif handle == "BR":
        x1 = max(x1 + dx, x0 + min_size)
        y1 = max(y1 + dy, y0 + min_size)

    return Rect(x0, y0, x1, y1)


def clamp_resize(rect: Rect, bounds: Rect) -> Rect:
    """Clamps a rect within bounds without preserving size (just intersections)."""
    return rect.intersect(bounds)
