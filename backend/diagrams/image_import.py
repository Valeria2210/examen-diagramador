"""Extraccion determinista de diagramas UML desde imagenes.

El modulo usa OpenCV para localizar cajas y lineas, y Tesseract para leer el
texto. No llama a ningun servicio de IA generativa.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np
import pytesseract
from PIL import Image
from decouple import config


@dataclass(frozen=True)
class DetectedBox:
    x: int
    y: int
    width: int
    height: int
    text: str

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def configure_tesseract() -> None:
    """Configura Tesseract desde variable de entorno o rutas habituales de Windows."""
    configured = config("TESSERACT_CMD", default="").strip()
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
        return

    if os.name == "nt":
        candidates = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        )
        for candidate in candidates:
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                return


def _clean_text(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r", "")).strip()


def _unique_boxes(boxes: Iterable[DetectedBox]) -> list[DetectedBox]:
    result: list[DetectedBox] = []
    for box in sorted(boxes, key=lambda item: item.width * item.height, reverse=True):
        duplicate = False
        for current in result:
            contained = (
                box.x >= current.x - 5
                and box.y >= current.y - 5
                and box.x + box.width <= current.x + current.width + 5
                and box.y + box.height <= current.y + current.height + 5
            )
            if contained:
                duplicate = True
                break
            intersection_x = max(0, min(box.x + box.width, current.x + current.width) - max(box.x, current.x))
            intersection_y = max(0, min(box.y + box.height, current.y + current.height) - max(box.y, current.y))
            intersection = intersection_x * intersection_y
            smaller = min(box.width * box.height, current.width * current.height)
            if smaller and intersection / smaller > 0.75:
                duplicate = True
                break
        if not duplicate:
            result.append(box)
    return sorted(result, key=lambda item: (item.y, item.x))


def _find_box_candidates(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = gray.shape[0] * gray.shape[1]
    candidates: list[tuple[int, int, int, int]] = []

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        x, y, width, height = cv2.boundingRect(polygon)
        area = width * height
        ratio = width / max(height, 1)
        if len(polygon) != 4 or area < image_area * 0.002 or area > image_area * 0.85:
            continue
        if width < 80 or height < 45 or ratio < 0.35 or ratio > 8:
            continue
        candidates.append((x, y, width, height))
    return _merge_compartment_candidates(candidates)


def _merge_compartment_candidates(candidates: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Une los tres rectángulos horizontales que forman una caja UML."""
    unique = list(dict.fromkeys(candidates))
    groups: list[list[tuple[int, int, int, int]]] = []
    for candidate in sorted(unique, key=lambda item: (item[0], item[1])):
        x, y, width, height = candidate
        matching_group = None
        for group in groups:
            group_x = group[0][0]
            group_width = group[0][2]
            same_column = abs(x - group_x) <= 18 and abs(width - group_width) <= 30
            last = max(group, key=lambda item: item[1] + item[3])
            close_vertical = y - (last[1] + last[3]) <= 25
            if same_column and close_vertical:
                matching_group = group
                break
        if matching_group is None:
            groups.append([candidate])
        else:
            matching_group.append(candidate)

    merged = []
    for group in groups:
        if len(group) < 2:
            merged.extend(group)
            continue
        left = min(item[0] for item in group)
        top = min(item[1] for item in group)
        right = max(item[0] + item[2] for item in group)
        bottom = max(item[1] + item[3] for item in group)
        merged.append((left, top, right - left, bottom - top))
    return merged


def _ocr_box(image: np.ndarray, bounds: tuple[int, int, int, int]) -> str:
    x, y, width, height = bounds
    padding = max(2, int(min(width, height) * 0.02))
    crop = image[max(0, y + padding):y + height - padding, max(0, x + padding):x + width - padding]
    scale = 2 if max(crop.shape[:2]) < 1200 else 1
    if scale > 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    try:
        text = pytesseract.image_to_string(crop, config="--psm 6", lang=config("TESSERACT_LANG", default="eng"))
    except pytesseract.TesseractNotFoundError:
        return ""
    return "\n".join(line for line in (_clean_text(item) for item in text.splitlines()) if line)


def _split_class_text(text: str) -> dict:
    lines = [line for line in (_clean_text(item) for item in text.splitlines()) if line]
    if not lines:
        return {"name": "Clase", "kind": "CLASS", "attributes": [], "methods": []}

    name = lines[0].strip("| ") or "Clase"
    attributes = []
    methods = []
    for line in lines[1:]:
        line = line.strip("| ")
        if not line or set(line) <= {"-", "_", "="}:
            continue
        if "(" in line and ")" in line:
            match = re.match(r"([+#~-]?)\s*([\wáéíóúñÁÉÍÓÚÑ]+)\s*\((.*?)\)\s*(?::\s*([\w.<>\[\]]+))?", line)
            if match:
                parameters = []
                for raw_parameter in filter(None, (item.strip() for item in match.group(3).split(","))):
                    if ":" in raw_parameter:
                        parameter_name, parameter_type = (part.strip() for part in raw_parameter.split(":", 1))
                    elif " " in raw_parameter:
                        parameter_type, parameter_name = raw_parameter.rsplit(None, 1)
                    else:
                        parameter_name, parameter_type = raw_parameter, "String"
                    parameters.append(f"{parameter_name}: {parameter_type}")
                methods.append({
                    "name": match.group(2),
                    "returnType": match.group(4) or "void",
                    "visibility": _visibility(match.group(1)),
                    "parameters": parameters,
                })
                continue
        match = re.match(r"([+#~-]?)\s*([\wáéíóúñÁÉÍÓÚÑ]+)\s*(?::|\s+)\s*([\w.<>\[\]]+)", line)
        if match:
            attributes.append({
                "name": match.group(2),
                "type": match.group(3),
                "visibility": _visibility(match.group(1)),
            })
    return {"name": name, "kind": "CLASS", "attributes": attributes, "methods": methods}


def _visibility(symbol: str) -> str:
    return {"+": "PUBLIC", "-": "PRIVATE", "#": "PROTECTED", "~": "PACKAGE"}.get(symbol, "PRIVATE")


def _line_touches_box(point: tuple[int, int], box: DetectedBox, margin: int = 35) -> bool:
    px, py = point
    return box.x - margin <= px <= box.x + box.width + margin and box.y - margin <= py <= box.y + box.height + margin


def _box_distance(point: tuple[int, int], box: DetectedBox) -> float:
    px, py = point
    dx = max(box.x - px, 0, px - (box.x + box.width))
    dy = max(box.y - py, 0, py - (box.y + box.height))
    return float((dx * dx + dy * dy) ** 0.5)


def _nearby_line_segments(edges: np.ndarray) -> list[tuple[int, int, int, int]]:
    minimum = max(25, min(edges.shape) // 14)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(18, min(edges.shape) // 18),
        minLineLength=minimum,
        maxLineGap=max(12, minimum // 3),
    )
    if lines is None:
        return []
    return [tuple(map(int, line)) for line in lines[:, 0]]


def _endpoint_box(point: tuple[int, int], boxes: list[DetectedBox], excluded: int | None = None) -> int | None:
    candidates = [
        (distance, index)
        for index, box in enumerate(boxes)
        if index != excluded and (distance := _box_distance(point, box)) <= 48
    ]
    return min(candidates)[1] if candidates else None


def _crop_near(point: tuple[int, int], image: np.ndarray, radius: int = 24) -> np.ndarray:
    x, y = point
    left = max(0, x - radius)
    top = max(0, y - radius)
    right = min(image.shape[1], x + radius + 1)
    bottom = min(image.shape[0], y + radius + 1)
    return image[top:bottom, left:right]


def _has_diamond(image: np.ndarray, point: tuple[int, int]) -> bool:
    crop = _crop_near(point, image, 28)
    if crop.size == 0:
        return False
    threshold = cv2.threshold(crop, 180, 255, cv2.THRESH_BINARY_INV)[1]
    contours, _ = cv2.findContours(threshold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 8 or area > 500:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.12 * perimeter, True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            width, height = cv2.boundingRect(polygon)[2:]
            if 0.45 <= width / max(height, 1) <= 2.2:
                return True
    return False


def _has_arrowhead(image: np.ndarray, point: tuple[int, int]) -> bool:
    crop = _crop_near(point, image, 30)
    if crop.size == 0:
        return False
    edges = cv2.Canny(crop, 60, 180)
    lines = _nearby_line_segments(edges)
    if len(lines) < 2:
        return False
    vectors = []
    for x1, y1, x2, y2 in lines:
        vectors.append(np.array([x2 - x1, y2 - y1], dtype=float))
    for first in vectors:
        for second in vectors:
            first_norm = np.linalg.norm(first)
            second_norm = np.linalg.norm(second)
            if first_norm == 0 or second_norm == 0:
                continue
            cosine = np.clip(np.dot(first, second) / (first_norm * second_norm), -1, 1)
            angle = np.degrees(np.arccos(cosine))
            if 20 <= angle <= 75:
                return True
    return False


def _read_multiplicity(image: np.ndarray, point: tuple[int, int]) -> str:
    crop = _crop_near(point, image, 42)
    if crop.size == 0:
        return "1"
    scale = 2 if max(crop.shape) < 100 else 1
    if scale > 1:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    crop = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    try:
        raw = pytesseract.image_to_string(crop, config="--psm 7 -c tessedit_char_whitelist=0123456789*.-", lang=config("TESSERACT_LANG", default="eng"))
    except pytesseract.TesseractNotFoundError:
        return "1"
    value = re.sub(r"[^0-9.*-]", "", raw).strip(".")
    return value or "1"


def _relation_type(image: np.ndarray, source_point: tuple[int, int], target_point: tuple[int, int]) -> str:
    if _has_diamond(image, source_point) or _has_diamond(image, target_point):
        return "COMPOSITION" if np.mean(_crop_near(source_point if _has_diamond(image, source_point) else target_point, image, 12)) < 120 else "AGGREGATION"
    if _has_arrowhead(image, target_point):
        return "INHERITANCE"
    return "ASSOCIATION"


def _detect_relations(image: np.ndarray, boxes: list[DetectedBox]) -> list[dict]:
    if len(boxes) < 2:
        return []
    normalized = cv2.normalize(image, None, 0, 255, cv2.NORM_MINMAX)
    edges = cv2.Canny(cv2.GaussianBlur(normalized, (3, 3), 0), 45, 135)
    candidates: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for x1, y1, x2, y2 in _nearby_line_segments(edges):
        first = _endpoint_box((x1, y1), boxes)
        second = _endpoint_box((x2, y2), boxes, first)
        if first is None or second is None or first == second:
            first = _endpoint_box((x2, y2), boxes)
            second = _endpoint_box((x1, y1), boxes, first)
        if first is None or second is None or first == second:
            continue
        pair = tuple(sorted((first, second)))
        length = int(np.hypot(x2 - x1, y2 - y1))
        previous = candidates.get(pair)
        if previous is None or length > int(np.hypot(previous[2] - previous[0], previous[3] - previous[1])):
            candidates[pair] = (x1, y1, x2, y2)

    relations = []
    for first, second in sorted(candidates):
        x1, y1, x2, y2 = candidates[(first, second)]
        first_point, second_point = (x1, y1), (x2, y2)
        if _box_distance(first_point, boxes[first]) > _box_distance(second_point, boxes[first]):
            first_point, second_point = second_point, first_point
        # El extremo UML se representa en target; el orden espacial de las cajas
        # no determina la dirección de una herencia o una composición.
        first_diamond = _has_diamond(image, first_point)
        second_diamond = _has_diamond(image, second_point)
        reverse = first_diamond and not second_diamond
        if not first_diamond and not second_diamond:
            reverse = _has_arrowhead(image, first_point) and not _has_arrowhead(image, second_point)
        if reverse:
            first, second = second, first
            first_point, second_point = second_point, first_point
        relation_type = _relation_type(image, first_point, second_point)
        relations.append({
            "from": boxes[first].text,
            "to": boxes[second].text,
            "type": relation_type,
            "sourceMultiplicity": _read_multiplicity(image, first_point),
            "targetMultiplicity": _read_multiplicity(image, second_point),
            "label": "",
        })
    return relations


def image_to_spec(image_bytes: bytes) -> dict:
    """Convierte una imagen UML en el contrato {classes, relations} del frontend."""
    configure_tesseract()
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("El archivo no es una imagen válida.")

    boxes: list[DetectedBox] = []
    ocr_cache: dict[tuple[int, int, int, int], dict] = {}
    for index, bounds in enumerate(_find_box_candidates(image), start=1):
        text = _ocr_box(image, bounds)
        parsed = _split_class_text(text)
        name = parsed["name"] if parsed["name"] != "Clase" and len(parsed["name"]) >= 2 else f"Clase{index}"
        parsed["name"] = name
        ocr_cache[bounds] = parsed
        boxes.append(DetectedBox(*bounds, text=name))

    boxes = _unique_boxes(boxes)
    classes = []
    for box in boxes:
        bounds = (box.x, box.y, box.width, box.height)
        parsed = ocr_cache.get(bounds) or _split_class_text(_ocr_box(image, bounds))
        parsed["pos_x"] = float(box.x)
        parsed["pos_y"] = float(box.y)
        classes.append(parsed)

    relations = _detect_relations(image, boxes)
    names = {item["name"] for item in classes}
    relations = [relation for relation in relations if relation["from"] in names and relation["to"] in names]
    if not classes:
        raise ValueError("No se detectaron cajas UML. Usa una imagen nítida con los rectángulos completos.")
    return {"classes": classes, "relations": relations}


# Mantiene Image como dependencia efectiva y permite validar formatos comunes antes de OpenCV.
def validate_image_bytes(image_bytes: bytes) -> None:
    with Image.open(__import__("io").BytesIO(image_bytes)) as image:
        image.verify()
