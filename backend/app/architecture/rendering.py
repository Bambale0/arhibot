from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import cos, radians, sin

from app.architecture.schemas import ArchitecturePackage, ExternalObjectType, Polygon2D

_LEVEL_COLORS = ("#1F7A4D", "#C45C26", "#5B3A8C", "#275D8C", "#7A4D1F")


def _pairs(polygon: Polygon2D) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    coords = [(point.x, point.y) for point in polygon.points]
    return list(zip(coords, coords[1:] + coords[:1], strict=True))


def _bounds(package: ArchitecturePackage) -> tuple[float, float, float, float]:
    points = [
        (point.x, point.y) for level in package.geometry.levels for point in level.footprint.points
    ]
    points.extend(
        (point.x, point.y)
        for item in package.geometry.external_objects
        for point in item.polygon.points
    )
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _svg_points(polygon: Polygon2D, transform) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in (transform(p.x, p.y) for p in polygon.points))


def _polygon_area(polygon: Polygon2D) -> float:
    points = [(point.x, point.y) for point in polygon.points]
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


class PlanSheetRenderer:
    """Render every level from one global XY coordinate system."""

    def render(self, package: ArchitecturePackage) -> str:
        levels = sorted(package.geometry.levels, key=lambda item: item.z)
        panel_width = 520
        panel_height = 650
        header_height = 48
        legend_height = 78
        sheet_width = panel_width * len(levels)
        sheet_height = panel_height + legend_height
        min_x, min_y, max_x, max_y = _bounds(package)
        padding_m = 2.0
        min_x -= padding_m
        min_y -= padding_m
        max_x += padding_m
        max_y += padding_m
        world_width = max(max_x - min_x, 1.0)
        world_height = max(max_y - min_y, 1.0)
        drawable_width = panel_width - 70
        drawable_height = panel_height - header_height - 70
        scale = min(drawable_width / world_width, drawable_height / world_height)

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_width}" '
            f'height="{sheet_height}" viewBox="0 0 {sheet_width} {sheet_height}" '
            'data-source="canonical-geometry">',
            '<defs><pattern id="grid" width="16" height="16" patternUnits="userSpaceOnUse">'
            '<path d="M 16 0 L 0 0 0 16" fill="none" stroke="#e8e2d9" stroke-width="0.7"/>'
            '</pattern><pattern id="poolHatch" width="8" height="8" patternUnits="userSpaceOnUse">'
            '<path d="M0 8 L8 0" stroke="#7bc7df" stroke-width="1"/></pattern>'
            '<pattern id="extHatch" width="8" height="8" patternUnits="userSpaceOnUse">'
            '<path d="M0 0 L8 8" stroke="#c9b18d" stroke-width="1"/></pattern></defs>',
            f'<rect width="{sheet_width}" height="{sheet_height}" fill="#fff"/>',
        ]

        for index, level in enumerate(levels):
            panel_x = index * panel_width
            color = _LEVEL_COLORS[index % len(_LEVEL_COLORS)]
            origin_x = panel_x + 35 + (drawable_width - world_width * scale) / 2
            origin_y = header_height + 35 + (drawable_height - world_height * scale) / 2

            def transform(
                x: float,
                y: float,
                origin_x_value: float = origin_x,
                origin_y_value: float = origin_y,
            ) -> tuple[float, float]:
                sx = origin_x_value + (x - min_x) * scale
                sy = origin_y_value + (max_y - y) * scale
                return sx, sy

            parts.extend(
                [
                    f'<rect x="{panel_x}" y="0" width="{panel_width}" '
                    f'height="{header_height}" fill="{color}"/>',
                    f'<text x="{panel_x + panel_width / 2}" y="31" text-anchor="middle" '
                    f'font-family="Arial,sans-serif" font-size="22" fill="#fff" font-weight="700">'
                    f"{escape(level.label.upper())}</text>",
                    f'<rect x="{panel_x + 1}" y="{header_height}" width="{panel_width - 2}" '
                    f'height="{panel_height - header_height}" fill="url(#grid)" stroke="#ddd"/>',
                ]
            )

            grid_step = 2.0
            first_grid_x = int(min_x // grid_step) * grid_step
            first_grid_y = int(min_y // grid_step) * grid_step
            x_value = first_grid_x
            x_index = 1
            while x_value <= max_x + 0.001:
                x, _ = transform(x_value, min_y)
                parts.append(
                    f'<line x1="{x:.1f}" y1="{origin_y:.1f}" x2="{x:.1f}" '
                    f'y2="{origin_y + world_height * scale:.1f}" stroke="#d8d1c7" '
                    'stroke-width="0.8"/>'
                )
                parts.append(
                    f'<text x="{x:.1f}" y="{origin_y - 8:.1f}" text-anchor="middle" '
                    f'font-family="Arial,sans-serif" font-size="10" fill="#555">{x_index}</text>'
                )
                x_value += grid_step
                x_index += 1

            y_value = first_grid_y
            y_index = 0
            while y_value <= max_y + 0.001:
                _, y = transform(min_x, y_value)
                parts.append(
                    f'<line x1="{origin_x:.1f}" y1="{y:.1f}" '
                    f'x2="{origin_x + world_width * scale:.1f}" y2="{y:.1f}" '
                    f'stroke="#d8d1c7" stroke-width="0.8"/>'
                )
                label = chr(ord("A") + (y_index % 26))
                parts.append(
                    f'<text x="{origin_x - 10:.1f}" y="{y + 3:.1f}" text-anchor="middle" '
                    f'font-family="Arial,sans-serif" font-size="10" fill="#555">{label}</text>'
                )
                y_value += grid_step
                y_index += 1

            for item in package.geometry.external_objects:
                belongs_here = item.level_id == level.id or (
                    item.level_id is None and index == 0 and item.z <= level.z + 0.2
                )
                if not belongs_here:
                    continue
                fill = (
                    "url(#poolHatch)" if item.type == ExternalObjectType.POOL else "url(#extHatch)"
                )
                parts.append(
                    f'<polygon points="{_svg_points(item.polygon, transform)}" fill="{fill}" '
                    'stroke="#555" stroke-width="1.5"/>'
                )
                cx = sum(point.x for point in item.polygon.points) / len(item.polygon.points)
                cy = sum(point.y for point in item.polygon.points) / len(item.polygon.points)
                tx, ty = transform(cx, cy)
                parts.append(
                    f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" '
                    f'font-family="Arial,sans-serif" font-size="11" font-weight="700" fill="#222">'
                    f"{escape(item.label.upper())}</text>"
                )

            parts.append(
                f'<polygon points="{_svg_points(level.footprint, transform)}" fill="#fffdf8" '
                'stroke="#111" stroke-width="5" stroke-linejoin="miter"/>'
            )
            for room in level.rooms:
                parts.append(
                    f'<polygon points="{_svg_points(room.polygon, transform)}" fill="#fff" '
                    'fill-opacity="0.65" '
                    'stroke="#222" stroke-width="1.5"/>'
                )
                cx = sum(point.x for point in room.polygon.points) / len(room.polygon.points)
                cy = sum(point.y for point in room.polygon.points) / len(room.polygon.points)
                tx, ty = transform(cx, cy)
                room_area = _polygon_area(room.polygon)
                parts.append(
                    f'<text x="{tx:.1f}" y="{ty - 5:.1f}" text-anchor="middle" '
                    f'font-family="Arial,sans-serif" font-size="10" font-weight="700" fill="#111">'
                    f"{escape(room.name.upper())}</text>"
                )
                parts.append(
                    f'<text x="{tx:.1f}" y="{ty + 8:.1f}" text-anchor="middle" '
                    f'font-family="Arial,sans-serif" font-size="9" fill="#333">'
                    f"{room_area:.1f} SQ M</text>"
                )

            parts.append(
                f'<text x="{panel_x + 16}" y="{panel_height - 15}" font-family="Arial,sans-serif" '
                f'font-size="10" fill="#666">Z={level.z:.2f} m · H={level.height:.2f} m</text>'
            )

        legend_y = panel_height
        parts.append(
            f'<rect x="0" y="{legend_y}" width="{sheet_width}" '
            f'height="{legend_height}" fill="#fff" stroke="#111"/>'
        )
        parts.append(
            f'<text x="{sheet_width / 2}" y="{legend_y + 23}" text-anchor="middle" '
            'font-family="Arial,sans-serif" font-size="15" fill="#111">LEVEL LEGEND</text>'
        )
        item_width = sheet_width / len(levels)
        for index, level in enumerate(levels):
            color = _LEVEL_COLORS[index % len(_LEVEL_COLORS)]
            x = index * item_width + 25
            parts.append(
                f'<rect x="{x:.1f}" y="{legend_y + 38}" width="90" height="20" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{x + 105:.1f}" y="{legend_y + 53}" font-family="Arial,sans-serif" '
                f'font-size="12" fill="#222">{escape(level.label.upper())}</text>'
            )
        parts.append("</svg>")
        return "".join(parts)


@dataclass(frozen=True)
class _Face:
    points: tuple[tuple[float, float, float], ...]
    fill: str
    stroke: str = "#3a3a3a"


class MassingRenderer:
    """Deterministic axonometric massing generated from the same level polygons."""

    def render(self, package: ArchitecturePackage) -> str:
        angle = radians(30)

        def project(x: float, y: float, z: float) -> tuple[float, float]:
            return ((x - y) * cos(angle), (x + y) * sin(angle) - z)

        faces: list[_Face] = []
        for index, level in enumerate(sorted(package.geometry.levels, key=lambda item: item.z)):
            color = _LEVEL_COLORS[index % len(_LEVEL_COLORS)]
            points = [(point.x, point.y) for point in level.footprint.points]
            top_z = level.z + level.height
            top_face = tuple((x, y, top_z) for x, y in points)
            faces.append(_Face(points=top_face, fill=color))
            for (x1, y1), (x2, y2) in _pairs(level.footprint):
                faces.append(
                    _Face(
                        points=(
                            (x1, y1, level.z),
                            (x2, y2, level.z),
                            (x2, y2, top_z),
                            (x1, y1, top_z),
                        ),
                        fill=color,
                    )
                )

        for item in package.geometry.external_objects:
            height = max(item.height, 0.05)
            fill = "#7bc7df" if item.type == ExternalObjectType.POOL else "#c7b08b"
            points = [(point.x, point.y) for point in item.polygon.points]
            faces.append(_Face(points=tuple((x, y, item.z + height) for x, y in points), fill=fill))
            if item.type != ExternalObjectType.POOL:
                for (x1, y1), (x2, y2) in _pairs(item.polygon):
                    faces.append(
                        _Face(
                            points=(
                                (x1, y1, item.z),
                                (x2, y2, item.z),
                                (x2, y2, item.z + height),
                                (x1, y1, item.z + height),
                            ),
                            fill=fill,
                        )
                    )

        projected_faces: list[tuple[float, list[tuple[float, float]], _Face]] = []
        for face in faces:
            projected = [project(*point) for point in face.points]
            depth = sum(point[1] for point in projected) / len(projected)
            projected_faces.append((depth, projected, face))
        projected_faces.sort(key=lambda item: item[0])

        projected_points = [point for _, projected, _ in projected_faces for point in projected]
        roof = package.geometry.roof
        ridge_projected: tuple[tuple[float, float], tuple[float, float]] | None = None
        if roof is not None and roof.ridge_start is not None and roof.ridge_end is not None:
            ridge_projected = (
                project(roof.ridge_start.x, roof.ridge_start.y, roof.ridge_z),
                project(roof.ridge_end.x, roof.ridge_end.y, roof.ridge_z),
            )
            projected_points.extend(ridge_projected)

        min_u = min(point[0] for point in projected_points)
        min_v = min(point[1] for point in projected_points)
        max_u = max(point[0] for point in projected_points)
        max_v = max(point[1] for point in projected_points)
        width = 960
        height = 720
        padding = 70
        scale = min(
            (width - padding * 2) / max(max_u - min_u, 1.0),
            (height - padding * 2) / max(max_v - min_v, 1.0),
        )

        def screen(point: tuple[float, float]) -> tuple[float, float]:
            return (
                padding + (point[0] - min_u) * scale,
                padding + (point[1] - min_v) * scale,
            )

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" data-source="canonical-geometry">',
            '<rect width="100%" height="100%" fill="#f7f7f5"/>',
            '<text x="35" y="42" font-family="Arial,sans-serif" font-size="20" '
            'font-weight="700" fill="#222">GEOMETRY-LOCKED MASSING</text>',
        ]
        for _, projected, face in projected_faces:
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(screen, projected))
            parts.append(
                f'<polygon points="{points}" fill="{face.fill}" fill-opacity="0.28" '
                f'stroke="{face.stroke}" stroke-width="1.5" stroke-linejoin="round"/>'
            )
        if ridge_projected is not None:
            (x1, y1), (x2, y2) = map(screen, ridge_projected)
            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                'stroke="#111" stroke-width="4"/>'
            )
        parts.append(
            '<text x="35" y="690" font-family="Arial,sans-serif" font-size="13" fill="#555">'
            "All volumes share the same world XY coordinates as the floor-plan sheet.</text>"
        )
        parts.append("</svg>")
        return "".join(parts)
