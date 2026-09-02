from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .definitions import DefinitionDecodeError, decode_definition_parts

_PAGE_RE = re.compile(r"^definition/pages/([^/]+)/page\.json$", re.IGNORECASE)
_VISUAL_RE = re.compile(r"^definition/pages/([^/]+)/visuals/([^/]+)/visual\.json$", re.IGNORECASE)


class PbirInspectionError(RuntimeError):
    """La definición PBIR no puede analizarse de forma determinística."""


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True)
class VisualGeometry:
    name: str
    folder: str
    visual_type: str | None
    rect: Rect
    z: float | None
    tab_order: float | None
    parent_group_name: str | None
    is_group: bool
    is_hidden: bool


def load_local_pbir_parts(
    project_path: Path,
    *,
    report_name: str | None = None,
    max_total_bytes: int = 25_000_000,
) -> tuple[str, dict[str, bytes]]:
    """Carga partes PBIR desde un proyecto PBIP local sin devolver rutas absolutas."""

    if not project_path.is_dir():
        raise ValueError(f"No existe el directorio del proyecto: {project_path}")

    report_dirs = sorted(path for path in project_path.glob("*.Report") if path.is_dir())
    if report_name:
        report_dirs = [path for path in report_dirs if path.name == report_name or path.stem == report_name]
    if not report_dirs:
        raise PbirInspectionError("No se encontró un directorio *.Report compatible.")
    if len(report_dirs) > 1:
        raise PbirInspectionError("Hay múltiples reportes; especifica report_name para seleccionar uno.")

    report_dir = report_dirs[0]
    definition_dir = report_dir / "definition"
    if not definition_dir.is_dir():
        raise PbirInspectionError("El reporte no contiene un directorio definition PBIR.")

    parts: dict[str, bytes] = {}
    total_bytes = 0
    for path in sorted(definition_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise PbirInspectionError(f"No fue posible leer una parte PBIR: {path.name}.") from exc
        total_bytes += len(payload)
        if total_bytes > max_total_bytes:
            raise PbirInspectionError("La definición PBIR local excede el límite seguro de 25 MB.")
        relative = path.relative_to(report_dir).as_posix()
        parts[relative] = payload

    return report_dir.name, parts


def inspect_pbir_definition(
    response: dict[str, Any],
    *,
    page: str | None = None,
    alignment_tolerance: float = 3.0,
    overlap_min_area: float = 1.0,
    include_visuals: bool = False,
    max_findings: int = 100,
) -> dict[str, Any]:
    """Inspecciona una respuesta Fabric getDefinition en formato PBIR."""

    definition_format, parts = decode_definition_parts(response)
    if definition_format not in {None, "PBIR"}:
        raise PbirInspectionError("Canvas Inspector requiere una definición PBIR.")
    return inspect_pbir_parts(
        parts,
        page=page,
        alignment_tolerance=alignment_tolerance,
        overlap_min_area=overlap_min_area,
        include_visuals=include_visuals,
        max_findings=max_findings,
    )


def inspect_pbir_parts(
    parts: dict[str, bytes],
    *,
    page: str | None = None,
    alignment_tolerance: float = 3.0,
    overlap_min_area: float = 1.0,
    include_visuals: bool = False,
    max_findings: int = 100,
) -> dict[str, Any]:
    """Analiza páginas y geometría de visuales PBIR desde partes ya decodificadas."""

    if alignment_tolerance < 0 or alignment_tolerance > 50:
        raise ValueError("alignment_tolerance debe estar entre 0 y 50.")
    if overlap_min_area < 0:
        raise ValueError("overlap_min_area no puede ser negativo.")
    if max_findings < 1 or max_findings > 1000:
        raise ValueError("max_findings debe estar entre 1 y 1000.")

    normalized = {path.replace("\\", "/").lstrip("/"): content for path, content in parts.items()}
    page_docs: dict[str, dict[str, Any]] = {}
    visual_docs: dict[str, list[tuple[str, dict[str, Any]]]] = {}

    for path, payload in normalized.items():
        page_match = _PAGE_RE.match(path)
        visual_match = _VISUAL_RE.match(path)
        if not page_match and not visual_match:
            continue
        data = _decode_json(payload, path)
        if page_match:
            page_docs[page_match.group(1)] = data
        else:
            assert visual_match is not None
            visual_docs.setdefault(visual_match.group(1), []).append((visual_match.group(2), data))

    if not page_docs:
        raise PbirInspectionError("No se encontraron archivos definition/pages/*/page.json en PBIR.")

    selected_keys = _select_pages(page_docs, page)
    pages: list[dict[str, Any]] = []
    total_visuals = 0
    total_overlaps = 0
    total_bounds = 0
    total_alignment_drift = 0
    findings_truncated = False

    for page_key in selected_keys:
        page_doc = page_docs[page_key]
        visuals = [
            _parse_visual(folder, doc)
            for folder, doc in sorted(visual_docs.get(page_key, []), key=lambda item: item[0])
        ]
        page_result = _inspect_page(
            page_key,
            page_doc,
            visuals,
            alignment_tolerance=alignment_tolerance,
            overlap_min_area=overlap_min_area,
            include_visuals=include_visuals,
            max_findings=max_findings,
        )
        pages.append(page_result)
        total_visuals += page_result["visual_count"]
        total_overlaps += page_result["overlap_count"]
        total_bounds += page_result["bounds_issue_count"]
        total_alignment_drift += page_result["alignment_drift_count"]
        findings_truncated = findings_truncated or page_result["findings_truncated"]

    return {
        "format": "PBIR",
        "page_filter": page,
        "page_count": len(pages),
        "visual_count": total_visuals,
        "overlap_count": total_overlaps,
        "bounds_issue_count": total_bounds,
        "alignment_drift_count": total_alignment_drift,
        "findings_truncated": findings_truncated,
        "pages": pages,
        "status": "REVIEW" if total_overlaps or total_bounds or total_alignment_drift else "PASS",
    }


def _decode_json(payload: bytes, path: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8-sig")
        data = json.loads(text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise PbirInspectionError(f"JSON PBIR inválido en '{path}'.") from exc
    if not isinstance(data, dict):
        raise PbirInspectionError(f"Se esperaba un objeto JSON en '{path}'.")
    return data


def _select_pages(page_docs: dict[str, dict[str, Any]], selector: str | None) -> list[str]:
    if selector is None:
        return sorted(page_docs)
    normalized = selector.casefold()
    matches = [
        key
        for key, doc in page_docs.items()
        if key.casefold() == normalized
        or str(doc.get("name") or "").casefold() == normalized
        or str(doc.get("displayName") or "").casefold() == normalized
    ]
    if not matches:
        raise PbirInspectionError(f"No se encontró la página solicitada: {selector}.")
    if len(matches) > 1:
        raise PbirInspectionError(f"La página solicitada es ambigua: {selector}.")
    return matches


def _parse_visual(folder: str, doc: dict[str, Any]) -> VisualGeometry:
    position = doc.get("position")
    if not isinstance(position, dict):
        raise PbirInspectionError(f"El visual '{folder}' no contiene position válido.")

    try:
        rect = Rect(
            x=float(position["x"]),
            y=float(position["y"]),
            width=float(position["width"]),
            height=float(position["height"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PbirInspectionError(f"El visual '{folder}' tiene geometría inválida.") from exc

    visual_config = doc.get("visual") if isinstance(doc.get("visual"), dict) else {}
    visual_type = str(visual_config.get("visualType")) if visual_config.get("visualType") else None
    name = str(doc.get("name") or folder)
    return VisualGeometry(
        name=name,
        folder=folder,
        visual_type=visual_type,
        rect=rect,
        z=_optional_number(position.get("z")),
        tab_order=_optional_number(position.get("tabOrder")),
        parent_group_name=str(doc.get("parentGroupName")) if doc.get("parentGroupName") else None,
        is_group=isinstance(doc.get("visualGroup"), dict),
        is_hidden=bool(doc.get("isHidden", False)),
    )


def _inspect_page(
    page_key: str,
    page_doc: dict[str, Any],
    visuals: list[VisualGeometry],
    *,
    alignment_tolerance: float,
    overlap_min_area: float,
    include_visuals: bool,
    max_findings: int,
) -> dict[str, Any]:
    width = _optional_number(page_doc.get("width"))
    height = _optional_number(page_doc.get("height"))

    bounds = _detect_bounds(visuals, width, height)
    overlaps = _detect_overlaps(visuals, overlap_min_area)
    alignment_drift = _detect_alignment_drift(visuals, alignment_tolerance)
    tab_order_duplicates = _duplicate_tab_orders(visuals)
    spacing = _spacing_summary(visuals)

    all_findings: list[dict[str, Any]] = []
    all_findings.extend(bounds)
    all_findings.extend(overlaps)
    all_findings.extend(alignment_drift)
    all_findings.extend(tab_order_duplicates)
    findings_truncated = len(all_findings) > max_findings
    findings = all_findings[:max_findings]

    result: dict[str, Any] = {
        "page_key": page_key,
        "name": page_doc.get("name"),
        "display_name": page_doc.get("displayName"),
        "display_option": page_doc.get("displayOption"),
        "width": width,
        "height": height,
        "visual_count": len(visuals),
        "hidden_visual_count": sum(1 for visual in visuals if visual.is_hidden),
        "group_count": sum(1 for visual in visuals if visual.is_group),
        "bounds_issue_count": len(bounds),
        "overlap_count": len(overlaps),
        "alignment_drift_count": len(alignment_drift),
        "duplicate_tab_order_count": len(tab_order_duplicates),
        "spacing": spacing,
        "findings": findings,
        "findings_truncated": findings_truncated,
    }
    if include_visuals:
        result["visuals"] = [_visual_dict(visual) for visual in visuals]
    return result


def _detect_bounds(
    visuals: list[VisualGeometry],
    page_width: float | None,
    page_height: float | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for visual in visuals:
        rect = visual.rect
        reasons: list[str] = []
        if rect.width <= 0 or rect.height <= 0:
            reasons.append("NON_POSITIVE_SIZE")
        if rect.x < 0 or rect.y < 0:
            reasons.append("NEGATIVE_POSITION")
        if page_width is not None and rect.right > page_width:
            reasons.append("EXCEEDS_PAGE_WIDTH")
        if page_height is not None and rect.bottom > page_height:
            reasons.append("EXCEEDS_PAGE_HEIGHT")
        if reasons:
            findings.append(
                {
                    "kind": "BOUNDS",
                    "severity": "HIGH",
                    "visual": visual.name,
                    "reasons": reasons,
                    "rect": _rect_dict(rect),
                }
            )
    return findings


def _detect_overlaps(visuals: list[VisualGeometry], min_area: float) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, left in enumerate(visuals):
        for right in visuals[index + 1 :]:
            area = _intersection_area(left.rect, right.rect)
            if area <= min_area:
                continue
            relation = _overlap_relation(left, right)
            if relation == "GROUP_CONTAINMENT":
                continue
            min_visual_area = min(left.rect.width * left.rect.height, right.rect.width * right.rect.height)
            ratio = area / min_visual_area if min_visual_area > 0 else 1.0
            findings.append(
                {
                    "kind": "OVERLAP",
                    "severity": "MEDIUM" if relation == "SAME_GROUP" else "HIGH",
                    "visual_a": left.name,
                    "visual_b": right.name,
                    "intersection_area": round(area, 3),
                    "smaller_visual_covered_ratio": round(ratio, 4),
                    "relation": relation,
                }
            )
    return findings


def _overlap_relation(left: VisualGeometry, right: VisualGeometry) -> str:
    if left.name == right.parent_group_name or right.name == left.parent_group_name:
        return "GROUP_CONTAINMENT"
    if left.parent_group_name and left.parent_group_name == right.parent_group_name:
        return "SAME_GROUP"
    if left.is_group or right.is_group:
        return "GROUP_LAYERING"
    return "UNRELATED"


def _detect_alignment_drift(
    visuals: list[VisualGeometry],
    tolerance: float,
) -> list[dict[str, Any]]:
    if tolerance <= 0:
        return []
    findings: list[dict[str, Any]] = []
    attributes = {
        "left": lambda visual: visual.rect.x,
        "top": lambda visual: visual.rect.y,
        "right": lambda visual: visual.rect.right,
        "bottom": lambda visual: visual.rect.bottom,
        "center_x": lambda visual: visual.rect.center_x,
        "center_y": lambda visual: visual.rect.center_y,
    }
    for index, left in enumerate(visuals):
        for right in visuals[index + 1 :]:
            for edge, getter in attributes.items():
                delta = abs(getter(left) - getter(right))
                if 0 < delta <= tolerance:
                    findings.append(
                        {
                            "kind": "ALIGNMENT_DRIFT",
                            "severity": "LOW",
                            "visual_a": left.name,
                            "visual_b": right.name,
                            "edge": edge,
                            "delta": round(delta, 3),
                        }
                    )
    return findings


def _duplicate_tab_orders(visuals: list[VisualGeometry]) -> list[dict[str, Any]]:
    by_order: dict[float, list[str]] = {}
    for visual in visuals:
        if visual.tab_order is not None:
            by_order.setdefault(visual.tab_order, []).append(visual.name)
    return [
        {
            "kind": "DUPLICATE_TAB_ORDER",
            "severity": "MEDIUM",
            "tab_order": order,
            "visuals": names,
        }
        for order, names in sorted(by_order.items())
        if len(names) > 1
    ]


def _spacing_summary(visuals: list[VisualGeometry]) -> dict[str, Any]:
    horizontal: list[float] = []
    vertical: list[float] = []
    for index, left in enumerate(visuals):
        for right in visuals[index + 1 :]:
            vertical_overlap = min(left.rect.bottom, right.rect.bottom) - max(left.rect.y, right.rect.y)
            horizontal_overlap = min(left.rect.right, right.rect.right) - max(left.rect.x, right.rect.x)

            if vertical_overlap > 0:
                if left.rect.right <= right.rect.x:
                    horizontal.append(right.rect.x - left.rect.right)
                elif right.rect.right <= left.rect.x:
                    horizontal.append(left.rect.x - right.rect.right)
            if horizontal_overlap > 0:
                if left.rect.bottom <= right.rect.y:
                    vertical.append(right.rect.y - left.rect.bottom)
                elif right.rect.bottom <= left.rect.y:
                    vertical.append(left.rect.y - right.rect.bottom)

    return {
        "horizontal_gap_count": len(horizontal),
        "vertical_gap_count": len(vertical),
        "common_horizontal_gaps": _common_gaps(horizontal),
        "common_vertical_gaps": _common_gaps(vertical),
    }


def _common_gaps(values: list[float], limit: int = 8) -> list[dict[str, Any]]:
    rounded = Counter(round(value, 1) for value in values if value >= 0)
    return [
        {"gap": gap, "count": count}
        for gap, count in sorted(rounded.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _intersection_area(left: Rect, right: Rect) -> float:
    width = min(left.right, right.right) - max(left.x, right.x)
    height = min(left.bottom, right.bottom) - max(left.y, right.y)
    return max(0.0, width) * max(0.0, height)


def _visual_dict(visual: VisualGeometry) -> dict[str, Any]:
    return {
        "name": visual.name,
        "folder": visual.folder,
        "visual_type": visual.visual_type,
        "position": _rect_dict(visual.rect),
        "z": visual.z,
        "tab_order": visual.tab_order,
        "parent_group_name": visual.parent_group_name,
        "is_group": visual.is_group,
        "is_hidden": visual.is_hidden,
    }


def _rect_dict(rect: Rect) -> dict[str, float]:
    return {
        "x": rect.x,
        "y": rect.y,
        "width": rect.width,
        "height": rect.height,
        "right": rect.right,
        "bottom": rect.bottom,
    }


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PbirInspectionError("Se encontró un valor numérico PBIR inválido.") from exc
