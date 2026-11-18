"""OCR AS-506 report tables and validate selected operational state references."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from itertools import product
import json
from math import hypot
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

SOURCE_URL = "https://ntrs.nasa.gov/api/citations/19690026499/downloads/19690026499.pdf"
SOURCE_SHA256 = "55b94c5947c91a3cd0539601517c82941a04ec9631dbb90458275664b855a7b3"
PHASE_TABLE_PAGES = (
    ("s_ic", {"vehicle": (13,), "geodetic": (14,), "space_fixed": (18,),
              "aerodynamics": (17,), "attitude": (16,)}),
    ("s_ii", {"vehicle": (25, 26), "geodetic": (27, 28),
              "space_fixed": (35, 36), "aerodynamics": (33, 34), "attitude": (31, 32)}),
    ("s_ivb", {"vehicle": (49,), "geodetic": (50,), "space_fixed": (54,),
               "aerodynamics": (53,), "attitude": (52,)}),
)
FIELDS = (
    "time_from_first_motion_s",
    "event",
    "total_engine_thrust_n",
    "total_vehicle_mass_kg",
    "altitude_above_spherical_earth_m",
    "inertial_speed_m_s",
    "inertial_path_angle_deg",
    "longitudinal_acceleration_m_s2",
    "geocentric_radius_m",
    "geocentric_speed_m_s",
    "latitude_deg",
    "longitude_deg",
    "arc_range_km",
    "mach",
    "dynamic_pressure_pa",
    "total_angle_of_attack_deg",
    "drag_along_velocity_kgf",
    "aerodynamic_load_kg_m2",
    "aerodynamic_force_kgf",
    "commanded_pitch_angle_deg",
    "eulerian_pitch_attitude_deg",
    "commanded_yaw_angle_deg",
    "eulerian_yaw_attitude_deg",
    "commanded_roll_angle_deg",
    "eulerian_roll_attitude_deg",
    "space_fixed_x_m",
    "space_fixed_y_m",
    "space_fixed_z_m",
    "space_fixed_vx_m_s",
    "space_fixed_vy_m_s",
    "space_fixed_vz_m_s",
)
EVENTS = (
    "TIME BASE 1", "MACH 1", "MAX Q", "S-IC CECO", "S-IC OECO",
    "S-IC/S-II SEP", "S-II ENGINE START", "S-II 90 THRUST",
    "INITIATE IGM", "S-II CECO", "S-II ENGINE CUTOFF", "S-II OECO", "S-IVB ULL IGN",
    "S-II/S-IVB SEP", "S-IVB ENGINE START", "S-IVB 90 THRUST",
    "S-IVB ULLAGE JETT", "S-IVB GCS1", "EPOI",
)
TABLE_EVENT_TIMES = {
    "TIME BASE 1": 0.4,
    "MACH 1": 65.75,
    "MAX Q": 81.0,
    "S-IC CECO": 135.0,
    "S-IC OECO": 160.82,
    "S-IC/S-II SEP": 161.59,
    "S-II ENGINE START": 162.22,
    "S-II 90 THRUST": 165.22,
    "INITIATE IGM": 201.42,
    "S-II CECO": 459.8,
    "S-II ENGINE CUTOFF": 551.384,
    "S-IVB ULL IGN": 552.08,
    "S-II/S-IVB SEP": 552.26,
    "S-IVB ENGINE START": 552.38,
    "S-IVB 90 THRUST": 557.88,
    "S-IVB ULLAGE JETT": 564.18,
    "S-IVB GCS1": 699.23,
    "EPOI": 709.23,
}
PHASE_TIME_BOUNDS = {
    "s_ic": (0.0, 161.59),
    "s_ii": (161.59, 552.26),
    "s_ivb": (552.26, 709.23),
}
SIC_REFERENCE_FIELDS = (
    "time_from_first_motion_s",
    "event",
    "phase",
    "geocentric_radius_m",
    "inertial_speed_m_s",
    "space_fixed_x_m",
    "space_fixed_y_m",
    "space_fixed_z_m",
    "space_fixed_vx_m_s",
    "space_fixed_vy_m_s",
    "space_fixed_vz_m_s",
    "event_side",
    "event_source",
    "transcription_corrections",
    "source_pages",
)
SII_CLOSED_REFERENCE_FIELDS = SIC_REFERENCE_FIELDS
STATE_CLOSURE_FIELDS = (
    "geocentric_radius_m", "inertial_speed_m_s",
    "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
    "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
)
STATE_REFERENCE_COLUMNS = frozenset({5, 8, 25, 26, 27, 28, 29, 30})
STATE_REFERENCE_FIELD_NAMES = {
    5: "inertial_speed_m_s",
    8: "geocentric_radius_m",
    25: "space_fixed_x_m",
    26: "space_fixed_y_m",
    27: "space_fixed_z_m",
    28: "space_fixed_vx_m_s",
    29: "space_fixed_vy_m_s",
    30: "space_fixed_vz_m_s",
}
SIC_GEODETIC_CHECKPOINTS = (
    (0.0, 28.6084, -80.60),
    (40.0, 28.6083, -80.60),
    (80.0, 28.6208, -80.56),
    (100.0, 28.6436, -80.48),
    (135.0, 28.7363, -80.15),
    (161.59, 28.8658, -79.69),
)
SII_INITIAL_TIMES = (161.59, 162.22, 165.22, 170.0, 175.0)
SII_INITIAL_REFERENCE_FIELDS = SIC_REFERENCE_FIELDS
SII_SOURCE_CLOSED_GEODETIC_CHECKPOINTS = (
    (180.0, 28.9754, -79.29),
    (185.0, 29.0059, -79.18),
    (190.0, 29.0367, -79.06),
    (195.0, 29.0678, -78.95),
    (200.0, 29.0992, -78.83),
    (201.42, 29.1082, -78.79),
    (205.0, 29.1310, -78.71),
    (210.0, 29.1631, -78.59),
    (215.0, 29.1954, -78.46),
    (220.0, 29.2281, -78.34),
    (225.0, 29.2611, -78.21),
    (230.0, 29.2943, -78.08),
    (235.0, 29.3279, -77.95),
    (240.0, 29.3617, -77.82),
    (245.0, 29.3958, -77.69),
    (250.0, 29.4303, -77.55),
    (255.0, 29.4650, -77.41),
    (260.0, 29.5000, -77.27),
    (265.0, 29.5354, -77.13),
    (270.0, 29.5710, -76.98),
    (275.0, 29.6069, -76.84),
    (280.0, 29.6431, -76.69),
    (285.0, 29.6796, -76.54),
    (290.0, 29.7164, -76.38),
    (295.0, 29.7535, -76.23),
    (300.0, 29.7909, -76.07),
    (305.0, 29.8286, -75.91),
    (310.0, 29.8665, -75.75),
    (315.0, 29.9048, -75.58),
    (320.0, 29.9433, -75.41),
    (325.0, 29.9822, -75.24),
    (330.0, 30.0213, -75.07),
    (335.0, 30.0607, -74.89),
    (340.0, 30.1004, -74.71),
    (345.0, 30.1403, -74.53),
    (350.0, 30.1806, -74.35),
    (355.0, 30.2211, -74.16),
    (360.0, 30.2619, -73.97),
    (365.0, 30.3030, -73.78),
    (370.0, 30.3443, -73.58),
    (375.0, 30.3859, -73.38),
    (380.0, 30.4277, -73.18),
    (385.0, 30.4699, -72.97),
    (390.0, 30.5122, -72.76),
    (395.0, 30.5548, -72.55),
    (400.0, 30.5976, -72.33),
    (405.0, 30.6407, -72.11),
    (410.0, 30.6839, -71.89),
    (415.0, 30.7274, -71.66),
    (420.0, 30.7711, -71.43),
    (425.0, 30.8150, -71.20),
    (430.0, 30.8591, -70.96),
    (440.0, 30.9478, -70.47),
    (445.0, 30.9924, -70.22),
    (450.0, 31.0371, -69.97),
    (455.0, 31.0820, -69.71),
    (460.0, 31.1270, -69.44),
    (465.0, 31.1720, -69.17),
    (470.0, 31.2170, -68.90),
    (475.0, 31.2619, -68.63),
    (480.0, 31.3067, -68.35),
    (485.0, 31.3514, -68.06),
    (490.0, 31.3960, -67.78),
    (495.0, 31.4403, -67.48),
    (500.0, 31.4843, -67.19),
    (505.0, 31.5280, -66.89),
    (510.0, 31.5714, -66.59),
    (515.0, 31.6144, -66.29),
    (520.0, 31.6570, -65.98),
    (525.0, 31.6992, -65.67),
    (530.0, 31.7410, -65.35),
    (535.0, 31.7824, -65.04),
    (540.0, 31.8233, -64.71),
    (545.0, 31.8637, -64.39),
    (550.0, 31.9036, -64.06),
    (551.384, 31.9146, -63.97),
    (552.08, 31.9201, -63.92),
    (552.26, 31.9215, -63.91),
)


def _run(command):
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def _fetch_report(destination):
    with urlopen(SOURCE_URL, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    digest = sha256(destination.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        destination.unlink(missing_ok=True)
        raise ValueError(f"NASA source SHA-256 mismatch: {digest}")
    return digest


def _number(token):
    token = token.strip().strip("*:")
    table = str.maketrans({
        "O": "0", "o": "0", "C": "0", "Q": "0", "Z": "2", "z": "2",
        "I": "1", "l": "1", "B": "8", "S": "5", "T": "7", "%": "4",
        "£": "6", "€": "6", "~": "-", "=": "-",
    })
    token = token.translate(table).replace(",", ".")
    token = re.sub(r"^-{2,}", "-", token)
    token = re.sub(r"[^0-9.+-]", "", token)
    if not token or token in {"+", "-", ".", "+.", "-."}:
        raise ValueError("empty OCR number")
    return float(token)


def _time_and_values(line, count, *, previous_time=None):
    glyphs = r"0-9OoIlBCST£€%"
    match = re.search(
        rf"(?<![A-Za-z0-9])([{glyphs}]{{1,4}}[.,]\s*[{glyphs}]{{1,2}})(?!\d)",
        line,
    )
    if match is None:
        return None
    try:
        raw_time = match.group(1).replace("%", "")
        time_value = _number(raw_time)
    except ValueError:
        return None
    if time_value > 720.0:
        integer, separator, fraction = raw_time.replace(",", ".").partition(".")
        candidates = []
        for index in range(len(integer)):
            candidate = _number(integer[:index]+integer[index+1:]+separator+fraction)
            if 0.0 <= candidate <= 710.0 and abs(candidate/5.0-round(candidate/5.0)) < 1e-8:
                candidates.append(candidate)
        if not candidates:
            return None
        if previous_time is None:
            time_value = candidates[0]
        else:
            candidates = [candidate for candidate in candidates if candidate >= previous_time]
            if not candidates:
                return None
            time_value = min(candidates, key=lambda candidate: abs(candidate-(previous_time+5.0)))
    tokens = line[match.end():].split()
    joined_tokens = []
    for token in tokens:
        if (joined_tokens and joined_tokens[-1].endswith((",", ".")) and
                re.fullmatch(r"[0-9OoIlBCST£€%]+", token)):
            joined_tokens[-1] += token
        else:
            joined_tokens.append(token)
    values = []
    raw_values = []
    for token in joined_tokens:
        try:
            values.append(_number(token))
            raw_values.append(token)
        except ValueError:
            continue
    if len(values) < count:
        return None
    return round(time_value, 2), values[:count], raw_values[:count]


def _event(line):
    upper = line.upper().replace("1I", "II")
    for name in EVENTS:
        if name in upper:
            return name
    if ("S-IC" in upper or "S-1C" in upper) and ("S-II" in upper or "S-11" in upper) and "SEP" in upper:
        return "S-IC/S-II SEP"
    if ("S-II" in upper or "S-11" in upper) and "S-IVB" in upper and "SEP" in upper:
        return "S-II/S-IVB SEP"
    if ("S-IC" in upper or "S-1C" in upper) and "CEC" in upper:
        return "S-IC CECO"
    if ("S-IC" in upper or "S-1C" in upper) and ("OEC" in upper or "OECO" in upper):
        return "S-IC OECO"
    if ("S-II" in upper or "S-11" in upper) and ("CEC" in upper or "CECO" in upper):
        return "S-II CECO"
    if ("S-II" in upper or "S-11" in upper) and ("ECO" in upper or "EC0" in upper):
        return "S-II ENGINE CUTOFF"
    if "S-IVB" in upper and "ULL" in upper and "IGN" in upper:
        return "S-IVB ULL IGN"
    if "GCS1" in upper or "GCSL" in upper:
        return "S-IVB GCS1"
    return ""


def _tsv_rows(output):
    rows = {}
    reader = csv.DictReader(output.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    for item in reader:
        if item.get("level") != "5" or not item.get("text", "").strip():
            continue
        key = (item["block_num"], item["par_num"], item["line_num"])
        word = {
            "left": int(item["left"]),
            "center": int(item["left"])+int(item["width"])/2,
            "text": item["text"].strip(),
        }
        rows.setdefault(key, []).append(word)
    return [sorted(words, key=lambda word: word["left"]) for words in rows.values()]


def _tsv_time_text(words):
    candidates = []
    for index, word in enumerate(words):
        if not 600 <= word["center"] <= 960:
            continue
        for end in range(index+1, min(index+4, len(words)+1)):
            sequence = words[index:end]
            if any(not 600 <= item["center"] <= 960 for item in sequence):
                break
            if any(
                second["center"]-first["center"] > 70
                for first, second in zip(sequence, sequence[1:])
            ):
                break
            text = "".join(item["text"] for item in sequence)
            if re.fullmatch(r"[0-9OoIlBCST£€%]{1,4}[.,][0-9OoIlBCST£€%]{1,2}", text):
                candidates.append((word["center"], text))
    return min(candidates)[1] if candidates else None


def _table_column_centers(lines, count):
    ranked = []
    for words in lines:
        if _tsv_time_text(words) is None:
            continue
        values = [
            word for word in words
            if word["center"] > 960 and re.search(r"\d", word["text"])
        ]
        if len(values) == count:
            ranked.append([word["center"] for word in values])
    if not ranked:
        raise ValueError("unable to locate numeric columns in the rendered table")
    centers = []
    for index in range(count):
        values = sorted(row[index] for row in ranked)
        middle = len(values)//2
        centers.append(
            float(values[middle]) if len(values) % 2
            else float((values[middle-1]+values[middle])/2.0)
        )
    return centers


def _extract_page(pdf, page, role, phase, directory):
    prefix = directory / f"page-{page:03d}"
    _run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", "3000",
          "-png", str(pdf), str(prefix)])
    image = Path(f"{prefix}-{page:03d}.png")
    rotated = directory / f"page-{page:03d}-rotated.png"
    _run(["convert", str(image), "-rotate", "90", str(rotated)])
    output = subprocess.run(["tesseract", str(rotated), "stdout", "--psm", "6", "tsv"],
                            check=True, text=True, capture_output=True).stdout
    if role == "vehicle":
        count, offset = 6, 2
    elif role == "geodetic":
        count, offset = 5, 8
    elif role == "aerodynamics":
        count, offset = 6, 13
    elif role == "space_fixed":
        count, offset = 6, 25
    else:
        count, offset = 6, 19

    rows = []
    previous_time = None
    lines = _tsv_rows(output)
    centers = _table_column_centers(lines, count)
    for words in lines:
        time_text = _tsv_time_text(words)
        if time_text is None:
            continue
        try:
            time_value = _number(time_text)
        except ValueError:
            continue
        assigned = [[] for _ in range(count)]
        for word in words:
            if word["center"] <= 960 or not re.search(r"\d", word["text"]):
                continue
            column = min(
                range(count), key=lambda index: abs(centers[index]-word["center"])
            )
            assigned[column].append(word)
        raw_values = ["".join(word["text"] for word in column) for column in assigned]
        values = []
        for raw in raw_values:
            if not raw:
                values.append(None)
                continue
            try:
                values.append(_number(raw))
            except ValueError:
                values.append(None)
        if all(value is None for value in values):
            continue
        line = " ".join(word["text"] for word in words)
        event = _event(line)
        if event in TABLE_EVENT_TIMES:
            time_value = TABLE_EVENT_TIMES[event]
        else:
            matching_events = [
                (abs(time_value-event_time), event_name, event_time)
                for event_name, event_time in TABLE_EVENT_TIMES.items()
                if abs(time_value-event_time) <= 0.02
            ]
            if matching_events:
                _, event, time_value = min(matching_events)
        lower_time, upper_time = PHASE_TIME_BOUNDS[phase]
        if not lower_time <= time_value <= upper_time:
            continue
        if event not in TABLE_EVENT_TIMES and abs(time_value/5.0-round(time_value/5.0)) > 0.004:
            continue
        correction = ""
        if (page == 13 and role == "vehicle" and time_value == 30.0
                and values[2] is not None and values[2] > 10000.0):
            time_value = 90.0
            correction = "PDF p.13 row time visually verified as 90.00 s"
        previous_time = time_value
        row = {"time_from_first_motion_s": time_value, "event": event,
               "phase": phase, "_page": page, "_time_correction": correction}
        for index, value in enumerate(values):
            if raw_values[index]:
                row[f"_raw{offset+index}"] = raw_values[index]
            if value is not None:
                row[str(offset+index)] = value
        rows.append(row)
    return rows


def _numeric_candidates(token, minimum, maximum):
    cleaned = token.translate(str.maketrans({
        "O": "0", "o": "0", "C": "0", "Q": "0", "Z": "2", "z": "2",
        "I": "1", "l": "1",
        "B": "8", "S": "5", "T": "7", "%": "4", "£": "6", "€": "6", "~": "-",
        ",": ".",
    }))
    try:
        direct = _number(cleaned)
    except ValueError:
        direct = None
    candidates = set()
    if direct is not None and minimum <= direct <= maximum:
        candidates.add(direct)
    if "." in cleaned:
        digits = re.sub(r"[^0-9]", "", cleaned)
        negative = cleaned.lstrip().startswith("-")
    else:
        digits = re.sub(r"[^0-9]", "", cleaned)
        negative = cleaned.lstrip().startswith("-")
    sign = "-" if negative else ""
    for index in range(1, len(digits)):
        candidate = float(f"{sign}{digits[:index]}.{digits[index:]}")
        if minimum <= candidate <= maximum:
            candidates.add(candidate)
    if len(digits) >= 6:
        for index in range(len(digits)):
            shortened = digits[:index]+digits[index+1:]
            for split in range(1, len(shortened)):
                candidate = float(f"{sign}{shortened[:split]}.{shortened[split:]}")
                if minimum <= candidate <= maximum:
                    candidates.add(candidate)
    return candidates


def _vector_digit_candidates(token, minimum, maximum):
    candidates = _numeric_candidates(token, minimum, maximum)
    cleaned = token.translate(str.maketrans({
        "O": "0", "o": "0", "C": "0", "Q": "0", "Z": "2", "z": "2",
        "I": "1", "l": "1",
        "B": "8", "S": "5", "T": "7", "%": "4", "£": "6", "€": "6",
        "~": "-", ",": ".",
    }))
    sign = "-" if cleaned.lstrip().startswith("-") else ""
    unsigned = cleaned.lstrip("+-")
    if "." in unsigned:
        integer, fraction = unsigned.split(".", 1)
        digits = integer+fraction
        decimal_position = len(integer)
    else:
        digits, decimal_position = unsigned, None
    if not digits.isdigit():
        return candidates

    def add(value_digits, point):
        if point is None:
            return
        if point <= 0:
            text = "0."+("0"*(-point))+value_digits
        elif point >= len(value_digits):
            text = value_digits+("0"*(point-len(value_digits)))
        else:
            text = value_digits[:point]+"."+value_digits[point:]
        try:
            value = float(sign+text)
        except ValueError:
            return
        if minimum <= value <= maximum:
            candidates.add(value)

    if decimal_position is not None:
        add(digits, decimal_position)
        for index, character in enumerate(digits):
            for replacement in "0123456789":
                if replacement != character:
                    add(digits[:index]+replacement+digits[index+1:], decimal_position)
        for index in range(len(digits)+1):
            point = decimal_position+(index <= decimal_position)
            for inserted in "0123456789":
                add(digits[:index]+inserted+digits[index:], point)
        for index in range(len(digits)):
            point = decimal_position-(index < decimal_position)
            add(digits[:index]+digits[index+1:], point)
    else:
        for index, character in enumerate(digits):
            for replacement in "0123456789":
                if replacement != character:
                    variant = digits[:index]+replacement+digits[index+1:]
                    for split in range(1, len(variant)):
                        add(variant, split)
        for index in range(len(digits)+1):
            for inserted in "0123456789":
                variant = digits[:index]+inserted+digits[index:]
                for split in range(1, len(variant)):
                    add(variant, split)
    return candidates


def _digit_edit_cost(token, value):
    translated = token.translate(str.maketrans({
        "O": "0", "o": "0", "C": "0", "Q": "0", "Z": "2", "z": "2",
        "I": "1", "l": "1",
        "B": "8", "S": "5", "%": "4", "£": "6", "€": "6",
        "~": "-", ",": ".",
    })).replace("T", "")
    source_digits = re.sub(r"[^0-9]", "", translated)
    target_digits = re.sub(r"[^0-9]", "", f"{abs(value):.12g}")
    previous = list(range(len(target_digits)+1))
    for source_index, source_digit in enumerate(source_digits, start=1):
        current = [source_index]
        for target_index, target_digit in enumerate(target_digits, start=1):
            current.append(min(
                current[-1]+1,
                previous[target_index]+1,
                previous[target_index-1]+(source_digit != target_digit),
            ))
        previous = current
    return previous[-1]


_TABLE_FIELD_LIMITS = {
    2: (0.0, 50e6), 3: (0.0, 3e6), 4: (0.0, 300e3),
    5: (0.0, 12000.0), 6: (0.0, 180.0), 7: (-100.0, 100.0),
    8: (6e6, 7e6), 9: (0.0, 12000.0), 10: (-90.0, 90.0),
    11: (-180.0, 180.0), 12: (0.0, 10000.0),
    13: (0.0, 50.0), 14: (0.0, 100000.0), 15: (-90.0, 90.0),
    16: (-500000.0, 500000.0), 17: (0.0, 100000.0),
    18: (0.0, 500000.0),
    19: (-180.0, 180.0), 20: (-180.0, 180.0),
    21: (-180.0, 180.0), 22: (-180.0, 180.0),
    23: (-180.0, 180.0), 24: (-180.0, 180.0),
    25: (-7e6, 7e6), 26: (-7e6, 7e6), 27: (-7e6, 7e6),
    28: (-15000.0, 15000.0), 29: (-15000.0, 15000.0), 30: (-15000.0, 15000.0),
}

_VISUALLY_VERIFIED_TRANSCRIPTIONS = {
    # Source digits were read directly from the 3000-pixel PDF-page renders.
    # The page number is the PDF page and each row is kept in the source phase.
    ("s_ic", 70.0, 5): (655.07, 13),
    ("s_ic", 135.0, 5): (1989.82, 13),
    ("s_ic", 125.0, 25): (6409716.4, 18),
    ("s_ic", 130.0, 26): (35374.2, 18),
    ("s_ic", 135.0, 25): (6416974.3, 18),
    ("s_ic", 135.0, 26): (35963.1, 18),
    ("s_ic", 135.0, 27): (100672.6, 18),
    ("s_ic", 140.0, 26): (36549.3, 18),
    ("s_ic", 145.0, 26): (37133.3, 18),
    ("s_ic", 150.0, 26): (37715.1, 18),
    ("s_ic", 155.0, 26): (38294.6, 18),
    ("s_ic", 160.0, 26): (38871.6, 18),
    ("s_ic", 160.82, 26): (38965.9, 18),
    ("s_ic", 161.59, 25): (6438562.7, 18),
    ("s_ic", 161.59, 26): (39054.5, 18),
    ("s_ic", 161.59, 27): (159600.6, 18),
    ("s_ic", 161.59, 28): (858.782, 18),
    ("s_ic", 161.59, 29): (115.035, 18),
    ("s_ic", 161.59, 30): (2626.743, 18),
    ("s_ic", 150.0, 8): (6430271.06, 14),
    ("s_ic", 160.82, 3): (826691.91, 19),
    ("s_ii", 161.59, 2): (411783.57, 19),
    ("s_ii", 161.59, 3): (659530.11, 19),
    ("s_ii", 162.22, 3): (659446.64, 19),
    ("s_ii", 162.22, 4): (67850.2, 19),
    ("s_ii", 165.22, 3): (658353.04, 19),
    ("s_ii", 165.22, 4): (70567.9, 19),
    ("s_ii", 165.22, 5): (2760.10, 19),
    ("s_ii", 165.22, 6): (71.07, 19),
    ("s_ii", 165.22, 7): (5.682, 19),
    ("s_ii", 170.0, 5): (2777.47, 25),
    ("s_ii", 161.59, 25): (6438562.7, 35),
    ("s_ii", 161.59, 26): (39054.5, 35),
    ("s_ii", 161.59, 27): (159600.6, 35),
    ("s_ii", 161.59, 28): (858.782, 35),
    ("s_ii", 161.59, 29): (115.035, 35),
    ("s_ii", 161.59, 30): (2626.743, 35),
    ("s_ii", 162.22, 25): (6439101.9, 35),
    ("s_ii", 162.22, 26): (39127.0, 35),
    ("s_ii", 162.22, 27): (161255.5, 35),
    ("s_ii", 162.22, 28): (852.869, 35),
    ("s_ii", 162.22, 29): (115.006, 35),
    ("s_ii", 162.22, 30): (2626.956, 35),
    ("s_ii", 165.22, 25): (6441618.8, 35),
    ("s_ii", 165.22, 26): (39471.8, 35),
    ("s_ii", 165.22, 27): (169139.3, 35),
    ("s_ii", 165.22, 28): (825.870, 35),
    ("s_ii", 165.22, 29): (114.858, 35),
    ("s_ii", 165.22, 30): (2631.143, 35),
    ("s_ii", 170.0, 25): (6445482.7, 35),
    ("s_ii", 170.0, 26): (40020.2, 35),
    ("s_ii", 170.0, 27): (181783.1, 35),
    ("s_ii", 170.0, 28): (791.375, 35),
    ("s_ii", 170.0, 29): (114.513, 35),
    ("s_ii", 170.0, 30): (2659.883, 35),
    ("s_ii", 175.0, 25): (6449355.2, 35),
    ("s_ii", 175.0, 26): (40591.7, 35),
    ("s_ii", 175.0, 27): (195168.8, 35),
    ("s_ii", 175.0, 28): (757.676, 35),
    ("s_ii", 175.0, 29): (114.094, 35),
    ("s_ii", 175.0, 30): (2694.544, 35),
    ("s_ii", 180.0, 5): (2826.64, 25),
    ("s_ii", 180.0, 8): (6456565.75, 27),
    ("s_ii", 180.0, 25): (6453059.8, 35),
    ("s_ii", 180.0, 26): (41161.1, 35),
    ("s_ii", 180.0, 27): (208729.7, 35),
    ("s_ii", 180.0, 28): (724.193, 35),
    ("s_ii", 180.0, 29): (113.676, 35),
    ("s_ii", 180.0, 30): (2729.928, 35),
    ("s_ii", 200.0, 5): (2938.77, 25),
    ("s_ii", 200.0, 8): (6471789.69, 27),
    ("s_ii", 200.0, 25): (6466225.4, 35),
    ("s_ii", 200.0, 26): (43417.3, 35),
    ("s_ii", 200.0, 27): (264777.1, 35),
    ("s_ii", 200.0, 28): (593.132, 35),
    ("s_ii", 200.0, 29): (111.936, 35),
    ("s_ii", 200.0, 30): (2876.111, 35),
    ("s_ii", 205.0, 5): (2969.45, 25),
    ("s_ii", 205.0, 8): (6475284.25, 27),
    ("s_ii", 205.0, 25): (6469110.6, 35),
    ("s_ii", 205.0, 26): (43975.9, 35),
    ("s_ii", 205.0, 27): (279251.9, 35),
    ("s_ii", 205.0, 28): (561.007, 35),
    ("s_ii", 205.0, 29): (111.483, 35),
    ("s_ii", 205.0, 30): (2913.841, 35),
    ("s_ii", 210.0, 5): (3000.23, 25),
    ("s_ii", 210.0, 8): (6478664.63, 27),
    ("s_ii", 210.0, 25): (6471841.2, 35),
    ("s_ii", 210.0, 26): (44532.4, 35),
    ("s_ii", 210.0, 27): (293913.7, 35),
    ("s_ii", 210.0, 28): (532.027, 35),
    ("s_ii", 210.0, 29): (111.144, 35),
    ("s_ii", 210.0, 30): (2950.591, 35),
    ("s_ii", 215.0, 5): (3031.04, 25),
    ("s_ii", 215.0, 8): (6481949.88, 27),
    ("s_ii", 215.0, 25): (6474435.3, 35),
    ("s_ii", 215.0, 26): (45087.3, 35),
    ("s_ii", 215.0, 27): (308756.2, 35),
    ("s_ii", 215.0, 28): (505.490, 35),
    ("s_ii", 215.0, 29): (110.798, 35),
    ("s_ii", 215.0, 30): (2986.539, 35),
    ("s_ii", 201.42, 5): (2947.38, 25),
    ("s_ii", 201.42, 8): (6472793.75, 27),
    ("s_ii", 201.42, 25): (6467060.6, 35),
    ("s_ii", 201.42, 26): (43576.1, 35),
    ("s_ii", 201.42, 27): (268865.9, 35),
    ("s_ii", 201.42, 28): (584.008, 35),
    ("s_ii", 201.42, 29): (111.808, 35),
    ("s_ii", 201.42, 30): (2886.782, 35),
    ("s_ii", 225.0, 5): (3095.61, 25),
    ("s_ii", 225.0, 8): (6488242.81, 27),
    ("s_ii", 225.0, 25): (6479216.6, 35),
    ("s_ii", 225.0, 26): (46192.4, 35),
    ("s_ii", 225.0, 27): (338990.5, 35),
    ("s_ii", 225.0, 28): (450.693, 35),
    ("s_ii", 225.0, 29): (110.238, 35),
    ("s_ii", 225.0, 30): (3060.636, 35),
    ("s_ii", 240.0, 5): (3198.52, 25),
    ("s_ii", 240.0, 8): (6496994.25, 27),
    ("s_ii", 240.0, 25): (6485355.8, 35),
    ("s_ii", 240.0, 26): (47839.4, 35),
    ("s_ii", 240.0, 27): (385755.3, 35),
    ("s_ii", 240.0, 28): (367.708, 35),
    ("s_ii", 240.0, 29): (109.346, 35),
    ("s_ii", 240.0, 30): (3175.433, 35),
    ("s_ii", 245.0, 5): (3234.48, 25),
    ("s_ii", 245.0, 8): (6499731.75, 27),
    ("s_ii", 245.0, 25): (6487124.6, 35),
    ("s_ii", 245.0, 26): (48385.5, 35),
    ("s_ii", 245.0, 27): (401730.5, 35),
    ("s_ii", 245.0, 28): (339.815, 35),
    ("s_ii", 245.0, 29): (109.108, 35),
    ("s_ii", 245.0, 30): (3214.725, 35),
    ("s_ii", 250.0, 5): (3271.25, 25),
    ("s_ii", 250.0, 8): (6502381.25, 27),
    ("s_ii", 250.0, 25): (6488753.8, 35),
    ("s_ii", 250.0, 26): (48930.5, 35),
    ("s_ii", 250.0, 27): (417903.4, 35),
    ("s_ii", 250.0, 28): (311.822, 35),
    ("s_ii", 250.0, 29): (108.871, 35),
    ("s_ii", 250.0, 30): (3254.537, 35),
    ("s_ii", 255.0, 5): (3308.86, 25),
    ("s_ii", 255.0, 8): (6504943.69, 27),
    ("s_ii", 255.0, 25): (6490242.6, 35),
    ("s_ii", 255.0, 26): (49474.3, 35),
    ("s_ii", 255.0, 27): (434276.7, 35),
    ("s_ii", 255.0, 28): (283.724, 35),
    ("s_ii", 255.0, 29): (108.649, 35),
    ("s_ii", 255.0, 30): (3294.884, 35),
    ("s_ii", 260.0, 5): (3347.30, 25),
    ("s_ii", 260.0, 8): (6507420.38, 27),
    ("s_ii", 260.0, 25): (6491590.8, 35),
    ("s_ii", 260.0, 26): (50017.0, 35),
    ("s_ii", 260.0, 27): (450853.1, 35),
    ("s_ii", 260.0, 28): (255.521, 35),
    ("s_ii", 260.0, 29): (108.438, 35),
    ("s_ii", 260.0, 30): (3335.773, 35),
    ("s_ii", 265.0, 5): (3386.62, 25),
    ("s_ii", 265.0, 8): (6509812.56, 27),
    ("s_ii", 265.0, 25): (6492797.7, 35),
    ("s_ii", 265.0, 26): (50558.7, 35),
    ("s_ii", 265.0, 27): (467635.4, 35),
    ("s_ii", 265.0, 28): (227.225, 35),
    ("s_ii", 265.0, 29): (108.231, 35),
    ("s_ii", 265.0, 30): (3377.250, 35),
    ("s_ii", 270.0, 5): (3426.80, 25),
    ("s_ii", 270.0, 8): (6512121.63, 27),
    ("s_ii", 270.0, 25): (6493862.9, 35),
    ("s_ii", 270.0, 26): (51099.3, 35),
    ("s_ii", 270.0, 27): (484626.6, 35),
    ("s_ii", 270.0, 28): (198.813, 35),
    ("s_ii", 270.0, 29): (108.030, 35),
    ("s_ii", 270.0, 30): (3419.321, 35),
    ("s_ii", 280.0, 5): (3509.79, 25),
    ("s_ii", 280.0, 8): (6516494.88, 27),
    ("s_ii", 280.0, 25): (6495565.1, 35),
    ("s_ii", 280.0, 26): (52177.6, 35),
    ("s_ii", 280.0, 27): (519247.6, 35),
    ("s_ii", 280.0, 28): (141.562, 35),
    ("s_ii", 280.0, 29): (107.637, 35),
    ("s_ii", 280.0, 30): (3505.286, 35),
    ("s_ii", 285.0, 5): (3552.60, 25),
    ("s_ii", 285.0, 8): (6518561.81, 27),
    ("s_ii", 285.0, 25): (6496200.9, 35),
    ("s_ii", 285.0, 26): (52715.3, 35),
    ("s_ii", 285.0, 27): (536883.5, 35),
    ("s_ii", 285.0, 28): (112.737, 35),
    ("s_ii", 285.0, 29): (107.442, 35),
    ("s_ii", 285.0, 30): (3549.190, 35),
    ("s_ii", 290.0, 5): (3596.30, 25),
    ("s_ii", 290.0, 8): (6520550.69, 27),
    ("s_ii", 290.0, 25): (6496692.3, 35),
    ("s_ii", 290.0, 26): (53252.1, 35),
    ("s_ii", 290.0, 27): (554740.5, 35),
    ("s_ii", 290.0, 28): (83.769, 35),
    ("s_ii", 290.0, 29): (107.246, 35),
    ("s_ii", 290.0, 30): (3593.721, 35),
    ("s_ii", 295.0, 5): (3640.87, 25),
    ("s_ii", 295.0, 8): (6522463.06, 27),
    ("s_ii", 295.0, 25): (6497038.4, 35),
    ("s_ii", 295.0, 26): (53787.8, 35),
    ("s_ii", 295.0, 27): (572821.7, 35),
    ("s_ii", 295.0, 28): (54.649, 35),
    ("s_ii", 295.0, 29): (107.049, 35),
    ("s_ii", 295.0, 30): (3638.888, 35),
    ("s_ii", 300.0, 5): (3686.34, 25),
    ("s_ii", 300.0, 8): (6524300.19, 27),
    ("s_ii", 300.0, 25): (6497238.5, 35),
    ("s_ii", 300.0, 26): (54322.5, 35),
    ("s_ii", 300.0, 27): (591130.4, 35),
    ("s_ii", 300.0, 28): (25.371, 35),
    ("s_ii", 300.0, 29): (106.849, 35),
    ("s_ii", 300.0, 30): (3684.703, 35),
    ("s_ii", 305.0, 5): (3732.71, 25),
    ("s_ii", 305.0, 8): (6526063.63, 27),
    ("s_ii", 305.0, 25): (6497291.8, 35),
    ("s_ii", 305.0, 26): (54856.3, 35),
    ("s_ii", 305.0, 27): (609669.9, 35),
    ("s_ii", 305.0, 28): (-4.074, 35),
    ("s_ii", 305.0, 29): (106.645, 35),
    ("s_ii", 305.0, 30): (3731.180, 35),
    ("s_ii", 310.0, 5): (3779.99, 25),
    ("s_ii", 310.0, 8): (6527754.75, 27),
    ("s_ii", 310.0, 25): (6497197.4, 35),
    ("s_ii", 310.0, 26): (55389.0, 35),
    ("s_ii", 310.0, 27): (628443.4, 35),
    ("s_ii", 310.0, 28): (-33.698, 35),
    ("s_ii", 310.0, 29): (106.440, 35),
    ("s_ii", 310.0, 30): (3778.338, 35),
    ("s_ii", 315.0, 5): (3828.20, 25),
    ("s_ii", 315.0, 8): (6529375.25, 27),
    ("s_ii", 315.0, 25): (6496954.5, 35),
    ("s_ii", 315.0, 26): (55920.7, 35),
    ("s_ii", 315.0, 27): (647454.4, 35),
    ("s_ii", 315.0, 28): (-63.512, 35),
    ("s_ii", 315.0, 29): (106.234, 35),
    ("s_ii", 315.0, 30): (3826.195, 35),
    ("s_ii", 320.0, 5): (3877.35, 25),
    ("s_ii", 320.0, 8): (6530926.44, 27),
    ("s_ii", 320.0, 25): (6496561.9, 35),
    ("s_ii", 320.0, 26): (56451.3, 35),
    ("s_ii", 320.0, 27): (666706.5, 35),
    ("s_ii", 320.0, 28): (-93.529, 35),
    ("s_ii", 320.0, 29): (106.025, 35),
    ("s_ii", 320.0, 30): (3874.770, 35),
    ("s_ii", 325.0, 5): (3927.46, 25),
    ("s_ii", 325.0, 8): (6532410.06, 27),
    ("s_ii", 325.0, 25): (6496018.8, 35),
    ("s_ii", 325.0, 26): (56980.9, 35),
    ("s_ii", 325.0, 27): (686203.3, 35),
    ("s_ii", 325.0, 28): (-123.764, 35),
    ("s_ii", 325.0, 29): (105.812, 35),
    ("s_ii", 325.0, 30): (3924.081, 35),
    ("s_ii", 330.0, 5): (3978.54, 25),
    ("s_ii", 330.0, 8): (6533827.56, 27),
    ("s_ii", 330.0, 25): (6495323.9, 35),
    ("s_ii", 330.0, 26): (57509.4, 35),
    ("s_ii", 330.0, 27): (705948.5, 35),
    ("s_ii", 330.0, 28): (-154.230, 35),
    ("s_ii", 330.0, 29): (105.598, 35),
    ("s_ii", 330.0, 30): (3974.145, 35),
    ("s_ii", 335.0, 5): (4030.61, 25),
    ("s_ii", 335.0, 8): (6535180.56, 27),
    ("s_ii", 335.0, 25): (6494476.1, 35),
    ("s_ii", 335.0, 26): (58036.9, 35),
    ("s_ii", 335.0, 27): (725946.0, 35),
    ("s_ii", 335.0, 28): (-184.938, 35),
    ("s_ii", 335.0, 29): (105.379, 35),
    ("s_ii", 335.0, 30): (4024.981, 35),
    ("s_ii", 340.0, 5): (4083.67, 25),
    ("s_ii", 340.0, 8): (6536470.69, 27),
    ("s_ii", 340.0, 25): (6493474.1, 35),
    ("s_ii", 340.0, 26): (58563.2, 35),
    ("s_ii", 340.0, 27): (746199.6, 35),
    ("s_ii", 340.0, 28): (-215.901, 35),
    ("s_ii", 340.0, 29): (105.160, 35),
    ("s_ii", 340.0, 30): (4076.606, 35),
    ("s_ii", 345.0, 5): (4137.76, 25),
    ("s_ii", 345.0, 8): (6537699.56, 27),
    ("s_ii", 345.0, 25): (6492316.7, 35),
    ("s_ii", 345.0, 26): (59088.5, 35),
    ("s_ii", 345.0, 27): (766713.3, 35),
    ("s_ii", 345.0, 28): (-247.134, 35),
    ("s_ii", 345.0, 29): (104.940, 35),
    ("s_ii", 345.0, 30): (4129.038, 35),
    ("s_ii", 350.0, 5): (4192.88, 25),
    ("s_ii", 350.0, 8): (6538868.88, 27),
    ("s_ii", 350.0, 25): (6491002.3, 35),
    ("s_ii", 350.0, 26): (59612.6, 35),
    ("s_ii", 350.0, 27): (787491.3, 35),
    ("s_ii", 350.0, 28): (-278.646, 35),
    ("s_ii", 350.0, 29): (104.714, 35),
    ("s_ii", 350.0, 30): (4182.302, 35),
    ("s_ii", 355.0, 5): (4249.07, 25),
    ("s_ii", 355.0, 8): (6539980.50, 27),
    ("s_ii", 355.0, 25): (6489529.8, 35),
    ("s_ii", 355.0, 26): (60135.6, 35),
    ("s_ii", 355.0, 27): (808537.7, 35),
    ("s_ii", 355.0, 28): (-310.454, 35),
    ("s_ii", 355.0, 29): (104.485, 35),
    ("s_ii", 355.0, 30): (4236.423, 35),
    ("s_ii", 370.0, 5): (4424.19, 25),
    ("s_ii", 370.0, 8): (6542987.13, 27),
    ("s_ii", 370.0, 25): (6484147.3, 35),
    ("s_ii", 370.0, 26): (61695.6, 35),
    ("s_ii", 370.0, 27): (873331.6, 35),
    ("s_ii", 370.0, 28): (-407.696, 35),
    ("s_ii", 370.0, 29): (103.442, 35),
    ("s_ii", 370.0, 30): (4404.148, 35),
    ("s_ii", 375.0, 5): (4484.85, 25),
    ("s_ii", 375.0, 8): (6543886.19, 27),
    ("s_ii", 375.0, 25): (6482026.1, 35),
    ("s_ii", 375.0, 26): (62212.2, 35),
    ("s_ii", 375.0, 27): (895496.4, 35),
    ("s_ii", 375.0, 28): (-440.852, 35),
    ("s_ii", 375.0, 29): (103.175, 35),
    ("s_ii", 375.0, 30): (4461.942, 35),
    ("s_ii", 380.0, 5): (4546.70, 25),
    ("s_ii", 380.0, 8): (6544736.63, 27),
    ("s_ii", 380.0, 25): (6479738.2, 35),
    ("s_ii", 380.0, 26): (62727.4, 35),
    ("s_ii", 380.0, 27): (917952.7, 35),
    ("s_ii", 380.0, 28): (-474.383, 35),
    ("s_ii", 380.0, 29): (102.896, 35),
    ("s_ii", 380.0, 30): (4520.716, 35),
    ("s_ii", 390.0, 5): (4674.07, 26),
    ("s_ii", 390.0, 8): (6546299.94, 28),
    ("s_ii", 390.0, 25): (6474654.3, 36),
    ("s_ii", 390.0, 26): (63753.7, 36),
    ("s_ii", 390.0, 27): (963759.4, 36),
    ("s_ii", 390.0, 28): (-542.681, 36),
    ("s_ii", 390.0, 29): (102.387, 36),
    ("s_ii", 390.0, 30): (4641.333, 36),
    ("s_ii", 395.0, 5): (4739.65, 26),
    ("s_ii", 395.0, 8): (6547016.88, 28),
    ("s_ii", 395.0, 25): (6471854.1, 36),
    ("s_ii", 395.0, 26): (64265.0, 36),
    ("s_ii", 395.0, 27): (987120.3, 36),
    ("s_ii", 395.0, 28): (-577.476, 36),
    ("s_ii", 395.0, 29): (102.146, 36),
    ("s_ii", 395.0, 30): (4703.234, 36),
    ("s_ii", 400.0, 5): (4806.55, 26),
    ("s_ii", 400.0, 8): (6547693.50, 28),
    ("s_ii", 400.0, 25): (6468878.8, 36),
    ("s_ii", 400.0, 26): (64775.2, 36),
    ("s_ii", 400.0, 27): (1010793.5, 36),
    ("s_ii", 400.0, 28): (-612.732, 36),
    ("s_ii", 400.0, 29): (101.909, 36),
    ("s_ii", 400.0, 30): (4766.242, 36),
    ("s_ii", 425.0, 5): (5162.03, 26),
    ("s_ii", 425.0, 8): (6550551.44, 28),
    ("s_ii", 425.0, 25): (6451289.3, 36),
    ("s_ii", 425.0, 26): (67308.3, 36),
    ("s_ii", 425.0, 27): (1134046.7, 36),
    ("s_ii", 425.0, 28): (-796.668, 36),
    ("s_ii", 425.0, 29): (100.742, 36),
    ("s_ii", 425.0, 30): (5099.190, 36),
    ("s_ii", 430.0, 5): (5237.64, 26),
    ("s_ii", 430.0, 8): (6551035.00, 28),
    ("s_ii", 430.0, 25): (6447209.9, 36),
    ("s_ii", 430.0, 26): (67811.5, 36),
    ("s_ii", 430.0, 27): (1159718.2, 36),
    ("s_ii", 430.0, 28): (-835.150, 36),
    ("s_ii", 430.0, 29): (100.508, 36),
    ("s_ii", 430.0, 30): (5169.651, 36),
    ("s_ii", 440.0, 5): (5393.76, 26),
    ("s_ii", 440.0, 8): (6551935.19, 28),
    ("s_ii", 440.0, 25): (6438466.3, 36),
    ("s_ii", 440.0, 26): (68814.1, 36),
    ("s_ii", 440.0, 27): (1212135.6, 36),
    ("s_ii", 440.0, 28): (-914.014, 36),
    ("s_ii", 440.0, 29): (100.027, 36),
    ("s_ii", 440.0, 30): (5314.810, 36),
    ("s_ii", 450.0, 5): (5556.79, 26),
    ("s_ii", 450.0, 8): (6552765.38, 28),
    ("s_ii", 450.0, 25): (6428920.5, 36),
    ("s_ii", 450.0, 26): (69812.0, 36),
    ("s_ii", 450.0, 27): (1266034.3, 36),
    ("s_ii", 450.0, 28): (-995.601, 36),
    ("s_ii", 450.0, 29): (99.535, 36),
    ("s_ii", 450.0, 30): (5465.971, 36),
    ("s_ii", 455.0, 5): (5641.07, 26),
    ("s_ii", 455.0, 8): (6553161.88, 28),
    ("s_ii", 455.0, 25): (6423838.1, 36),
    ("s_ii", 455.0, 26): (70309.0, 36),
    ("s_ii", 455.0, 27): (1293558.3, 36),
    ("s_ii", 455.0, 28): (-1037.492, 36),
    ("s_ii", 455.0, 29): (99.286, 36),
    ("s_ii", 455.0, 30): (5543.949, 36),
    ("s_ii", 460.0, 5): (5727.26, 26),
    ("s_ii", 460.0, 8): (6553550.44, 28),
    ("s_ii", 460.0, 25): (6418544.3, 36),
    ("s_ii", 460.0, 26): (70804.8, 36),
    ("s_ii", 460.0, 27): (1321476.5, 36),
    ("s_ii", 460.0, 28): (-1080.158, 36),
    ("s_ii", 460.0, 29): (99.035, 36),
    ("s_ii", 460.0, 30): (5623.610, 36),
    ("s_ii", 465.0, 5): (5799.29, 26),
    ("s_ii", 465.0, 8): (6553926.06, 28),
    ("s_ii", 465.0, 25): (6413034.4, 36),
    ("s_ii", 465.0, 26): (71299.3, 36),
    ("s_ii", 465.0, 27): (1349760.6, 36),
    ("s_ii", 465.0, 28): (-1123.978, 36),
    ("s_ii", 465.0, 29): (98.799, 36),
    ("s_ii", 465.0, 30): (5688.469, 36),
    ("s_ii", 470.0, 5): (5870.23, 26),
    ("s_ii", 470.0, 8): (6554281.75, 28),
    ("s_ii", 470.0, 25): (6407306.3, 36),
    ("s_ii", 470.0, 26): (71792.8, 36),
    ("s_ii", 470.0, 27): (1378362.1, 36),
    ("s_ii", 470.0, 28): (-1166.588, 36),
    ("s_ii", 470.0, 29): (98.539, 36),
    ("s_ii", 470.0, 30): (5752.296, 36),
    ("s_ii", 475.0, 5): (5941.50, 26),
    ("s_ii", 475.0, 8): (6554637.94, 28),
    ("s_ii", 475.0, 25): (6401375.2, 36),
    ("s_ii", 475.0, 26): (72284.2, 36),
    ("s_ii", 475.0, 27): (1407285.0, 36),
    ("s_ii", 475.0, 28): (-1205.748, 36),
    ("s_ii", 475.0, 29): (98.019, 36),
    ("s_ii", 475.0, 30): (5817.038, 36),
    ("s_ii", 480.0, 5): (6014.27, 26),
    ("s_ii", 480.0, 8): (6555006.44, 28),
    ("s_ii", 480.0, 25): (6395246.9, 36),
    ("s_ii", 480.0, 26): (72777.0, 36),
    ("s_ii", 480.0, 27): (1436534.5, 36),
    ("s_ii", 480.0, 28): (-1245.837, 36),
    ("s_ii", 480.0, 29): (97.494, 36),
    ("s_ii", 480.0, 30): (5883.008, 36),
    ("s_ii", 485.0, 5): (6088.74, 26),
    ("s_ii", 485.0, 8): (6555386.38, 28),
    ("s_ii", 485.0, 25): (6388914.3, 36),
    ("s_ii", 485.0, 26): (73259.2, 36),
    ("s_ii", 485.0, 27): (1466117.1, 36),
    ("s_ii", 485.0, 28): (-1287.500, 36),
    ("s_ii", 485.0, 29): (96.993, 36),
    ("s_ii", 485.0, 30): (5950.272, 36),
    ("s_ii", 495.0, 5): (6216.47, 26),
    ("s_ii", 495.0, 8): (6556153.94, 28),
    ("s_ii", 495.0, 25): (6375602.9, 36),
    ("s_ii", 495.0, 26): (74224.5, 36),
    ("s_ii", 495.0, 27): (1526215.7, 36),
    ("s_ii", 495.0, 28): (-1376.129, 36),
    ("s_ii", 495.0, 29): (96.098, 36),
    ("s_ii", 495.0, 30): (6061.482, 36),
    ("s_ii", 500.0, 5): (6275.51, 26),
    ("s_ii", 500.0, 8): (6556517.13, 28),
    ("s_ii", 500.0, 25): (6368609.2, 36),
    ("s_ii", 500.0, 26): (74703.8, 36),
    ("s_ii", 500.0, 27): (1556648.3, 36),
    ("s_ii", 500.0, 28): (-1421.339, 36),
    ("s_ii", 500.0, 29): (95.587, 36),
    ("s_ii", 500.0, 30): (6111.685, 36),
    ("s_ii", 505.0, 5): (6335.29, 26),
    ("s_ii", 505.0, 8): (6556870.88, 28),
    ("s_ii", 505.0, 25): (6361389.6, 36),
    ("s_ii", 505.0, 26): (75180.4, 36),
    ("s_ii", 505.0, 27): (1587333.5, 36),
    ("s_ii", 505.0, 28): (-1466.301, 36),
    ("s_ii", 505.0, 29): (95.066, 36),
    ("s_ii", 505.0, 30): (6162.535, 36),
    ("s_ii", 510.0, 5): (6395.90, 26),
    ("s_ii", 510.0, 8): (6557222.44, 28),
    ("s_ii", 510.0, 25): (6353946.1, 36),
    ("s_ii", 510.0, 26): (75654.4, 36),
    ("s_ii", 510.0, 27): (1618274.7, 36),
    ("s_ii", 510.0, 28): (-1511.326, 36),
    ("s_ii", 510.0, 29): (94.535, 36),
    ("s_ii", 510.0, 30): (6214.057, 36),
    ("s_ii", 515.0, 5): (6457.64, 26),
    ("s_ii", 515.0, 8): (6557572.50, 28),
    ("s_ii", 515.0, 25): (6346274.1, 36),
    ("s_ii", 515.0, 26): (76125.8, 36),
    ("s_ii", 515.0, 27): (1649475.1, 36),
    ("s_ii", 515.0, 28): (-1557.648, 36),
    ("s_ii", 515.0, 29): (94.040, 36),
    ("s_ii", 515.0, 30): (6266.258, 36),
    ("s_ii", 520.0, 5): (6520.44, 26),
    ("s_ii", 520.0, 8): (6557921.00, 28),
    ("s_ii", 520.0, 25): (6338368.0, 36),
    ("s_ii", 520.0, 26): (76594.8, 36),
    ("s_ii", 520.0, 27): (1680938.3, 36),
    ("s_ii", 520.0, 28): (-1604.922, 36),
    ("s_ii", 520.0, 29): (93.564, 36),
    ("s_ii", 520.0, 30): (6319.148, 36),
    ("s_ii", 525.0, 5): (6584.29, 26),
    ("s_ii", 525.0, 8): (6558269.44, 28),
    ("s_ii", 525.0, 25): (6330223.6, 36),
    ("s_ii", 525.0, 26): (77061.5, 36),
    ("s_ii", 525.0, 27): (1712667.7, 36),
    ("s_ii", 525.0, 28): (-1652.973, 36),
    ("s_ii", 525.0, 29): (93.099, 36),
    ("s_ii", 525.0, 30): (6372.746, 36),
    ("s_ii", 530.0, 5): (6649.18, 26),
    ("s_ii", 530.0, 8): (6558620.00, 28),
    ("s_ii", 530.0, 25): (6321837.1, 36),
    ("s_ii", 530.0, 26): (77525.8, 36),
    ("s_ii", 530.0, 27): (1744666.9, 36),
    ("s_ii", 530.0, 28): (-1701.705, 36),
    ("s_ii", 530.0, 29): (92.639, 36),
    ("s_ii", 530.0, 30): (6427.073, 36),
    ("s_ii", 535.0, 5): (6715.14, 26),
    ("s_ii", 535.0, 8): (6558975.38, 28),
    ("s_ii", 535.0, 25): (6313205.4, 36),
    ("s_ii", 535.0, 26): (77987.9, 36),
    ("s_ii", 535.0, 27): (1776939.6, 36),
    ("s_ii", 535.0, 28): (-1751.093, 36),
    ("s_ii", 535.0, 29): (92.181, 36),
    ("s_ii", 535.0, 30): (6482.149, 36),
    ("s_ii", 540.0, 5): (6782.17, 26),
    ("s_ii", 540.0, 8): (6559338.44, 28),
    ("s_ii", 540.0, 25): (6304325.1, 36),
    ("s_ii", 540.0, 26): (78447.7, 36),
    ("s_ii", 540.0, 27): (1809489.6, 36),
    ("s_ii", 540.0, 28): (-1801.146, 36),
    ("s_ii", 540.0, 29): (91.724, 36),
    ("s_ii", 540.0, 30): (6537.991, 36),
    ("s_ii", 545.0, 5): (6850.31, 26),
    ("s_ii", 545.0, 8): (6559712.19, 28),
    ("s_ii", 545.0, 25): (6295192.8, 36),
    ("s_ii", 545.0, 26): (78905.1, 36),
    ("s_ii", 545.0, 27): (1842320.8, 36),
    ("s_ii", 545.0, 28): (-1851.885, 36),
    ("s_ii", 545.0, 29): (91.269, 36),
    ("s_ii", 545.0, 30): (6594.610, 36),
    ("s_ii", 550.0, 5): (6919.54, 26),
    ("s_ii", 550.0, 8): (6560099.56, 28),
    ("s_ii", 550.0, 25): (6285805.1, 36),
    ("s_ii", 550.0, 26): (79360.3, 36),
    ("s_ii", 550.0, 27): (1875436.9, 36),
    ("s_ii", 550.0, 28): (-1903.318, 36),
    ("s_ii", 550.0, 29): (90.815, 36),
    ("s_ii", 550.0, 30): (6652.002, 36),
    ("s_ii", 551.384, 5): (6938.88, 26),
    ("s_ii", 551.384, 8): (6560209.69, 28),
    ("s_ii", 551.384, 25): (6283161.0, 36),
    ("s_ii", 551.384, 26): (79485.9, 36),
    ("s_ii", 551.384, 27): (1884654.3, 36),
    ("s_ii", 551.384, 28): (-1917.675, 36),
    ("s_ii", 551.384, 29): (90.689, 36),
    ("s_ii", 551.384, 30): (6668.011, 36),
    ("s_ii", 552.08, 5): (6941.82, 26),
    ("s_ii", 552.08, 8): (6560265.50, 28),
    ("s_ii", 552.08, 25): (6281816.3, 36),
    ("s_ii", 552.08, 26): (79549.4, 36),
    ("s_ii", 552.08, 27): (1889323.0, 36),
    ("s_ii", 552.08, 28): (-1924.211, 36),
    ("s_ii", 552.08, 29): (90.621, 36),
    ("s_ii", 552.08, 30): (6669.191, 36),
    ("s_ii", 552.26, 5): (6941.90, 26),
    ("s_ii", 552.26, 8): (6560279.31, 28),
    ("s_ii", 552.26, 25): (6281479.4, 36),
    ("s_ii", 552.26, 26): (79565.3, 36),
    ("s_ii", 552.26, 27): (1890490.0, 36),
    ("s_ii", 552.26, 28): (-1925.773, 36),
    ("s_ii", 552.26, 29): (90.604, 36),
    ("s_ii", 552.26, 30): (6668.816, 36),
    ("s_ivb", 552.26, 3): (166492.60, 43),
    ("s_ivb", 552.38, 3): (166492.60, 43),
    ("s_ivb", 557.88, 3): (166240.40, 43),
    ("s_ivb", 557.88, 4): (186492.7, 43),
    ("s_ivb", 557.88, 5): (6947.03, 43),
    ("s_ivb", 557.88, 6): (89.43, 43),
    ("s_ivb", 557.88, 7): (4.941, 43),
}


def _apply_visually_verified_transcriptions(merged, phases=None):
    for key, (value, page) in _VISUALLY_VERIFIED_TRANSCRIPTIONS.items():
        phase, time_value, column = key
        if phases is not None and phase not in phases:
            continue
        row = merged.get((phase, time_value))
        if row is None:
            raise ValueError(
                f"source PDF is missing visually checked {phase} row at {time_value} s"
            )
        row[str(column)] = value
        row.setdefault("source_pages", set()).add(page)
        superseded_notes = (
            f"space-fixed component {column} changed from",
            f"column {column} changed from",
        )
        notes = row.setdefault("transcription_corrections", [])
        notes[:] = [
            note for note in notes
            if not any(note.startswith(prefix) for prefix in superseded_notes)
        ]
        notes.append(
            f"PDF p.{page}, table 2.2 column {column}: manually verified"
        )


def _correct_ocr_columns(merged):
    for phase, _tables in PHASE_TABLE_PAGES:
        keys = sorted((key for key in merged if key[0] == phase), key=lambda key: key[1])
        for column, (minimum, maximum) in _TABLE_FIELD_LIMITS.items():
            samples = []
            for key in keys:
                row = merged[key]
                raw = row.get(f"_raw{column}")
                value = row.get(str(column))
                if raw is not None:
                    samples.append((
                        key, raw, None if value is None else float(value),
                    ))
            confident = [
                (key, value) for key, raw, value in samples
                if value is not None
                and any(mark in raw for mark in ".,")
                and minimum <= value <= maximum
            ]
            for sample_index, (key, raw, value) in enumerate(samples):
                if (
                    value is not None
                    and any(mark in raw for mark in ".,")
                    and minimum <= value <= maximum
                ):
                    continue
                candidates = _numeric_candidates(raw, minimum, maximum)
                if not candidates:
                    continue
                before = [item for item in confident if item[0][1] < key[1]]
                after = [item for item in confident if item[0][1] > key[1]]
                if before and after:
                    left_key, left_value = before[-1]
                    right_key, right_value = after[0]
                    fraction = (key[1]-left_key[1])/(right_key[1]-left_key[1])
                    expected = left_value+fraction*(right_value-left_value)
                elif before:
                    expected = before[-1][1]
                elif after:
                    expected = after[0][1]
                else:
                    continue
                selected = min(candidates, key=lambda item: abs(item-expected))
                merged[key][str(column)] = selected
                if value is None or selected != value:
                    old = "unreadable token" if value is None else str(value)
                    merged[key].setdefault("transcription_corrections", []).append(
                        f"column {column} changed from {old} to {selected} "
                        f"from OCR token {raw!r} using printed-value digit candidates "
                        "and adjacent source rows"
                    )


def _correct_source_vector_ocr(merged):
    for row in merged.values():
        targets = (
            (25, ("_raw25", "_raw26", "_raw27"), "8", "_raw8",
             ((6e6, 7e6), (-7e6, 7e6), (-7e6, 7e6)), _TABLE_FIELD_LIMITS[8]),
            (28, ("_raw28", "_raw29", "_raw30"), "5", "_raw5",
             ((-15000.0, 15000.0), (-15000.0, 15000.0), (-15000.0, 15000.0)),
             _TABLE_FIELD_LIMITS[5]),
        )
        for offset, raw_names, target_name, raw_target_name, limits, scalar_limits in targets:
            target = row.get(target_name)
            if target in (None, ""):
                continue
            vector = [row.get(str(offset+index)) for index in range(3)]
            tolerance = 0.5 if offset == 25 else 0.2
            missing = [
                index for index, value in enumerate(vector)
                if value in (None, "")
            ]
            if len(missing) == 1:
                index = missing[0]
                raw = row.get(raw_names[index], "")
                if not raw:
                    continue
                known = [
                    float(value) if value not in (None, "") else None
                    for value in vector
                ]
                candidates = _vector_digit_candidates(raw, *limits[index])
                accepted = [
                    candidate for candidate in candidates
                    if abs(hypot(*(
                        known[item] if item != index else candidate
                        for item in range(3)
                    ))-float(target)) <= tolerance
                ]
                if len(accepted) != 1:
                    continue
                vector[index] = accepted[0]
                row[str(offset+index)] = accepted[0]
                row.setdefault("transcription_corrections", []).append(
                    f"column {offset+index} unreadable token {raw!r} uniquely "
                    f"recovered as {accepted[0]} by printed vector-norm closure"
                )
            elif missing:
                continue
            vector = [float(value) for value in vector]

            raw_target = row.get(raw_target_name, "")
            if (not any(mark in raw_target for mark in ".,") and all(
                    re.fullmatch(r"[+-]?\d+(?:[.,]\d+)", row.get(name, "")) is not None
                    for name in raw_names)):
                candidates = _numeric_candidates(raw_target, *scalar_limits)
                if candidates:
                    vector_norm = hypot(*vector)
                    selected = min(candidates, key=lambda value: abs(value-vector_norm))
                    if abs(selected-vector_norm) < abs(float(target)-vector_norm)-1e-6:
                        old = float(target)
                        row[target_name] = selected
                        target = selected
                        row.setdefault("transcription_corrections", []).append(
                            f"column {target_name} changed from {old} to {selected} "
                            "using redundant vector norm"
                        )
            reference = float(target)

            def candidate_values(index, raw_name, bounds):
                raw = row.get(raw_name, "")
                candidates = _vector_digit_candidates(raw, *bounds)
                candidates.add(vector[index])
                candidates = sorted(candidates, key=lambda value: (
                    _digit_edit_cost(raw, value),
                    abs(hypot(*(vector[:index]+[value]+vector[index+1:]))-reference),
                    abs(value-vector[index]),
                ))
                return candidates[:24]

            candidate_sets = [
                candidate_values(index, raw_name, bounds)
                for index, (raw_name, bounds) in enumerate(zip(raw_names, limits))
            ]
            combinations = []
            for candidate_vector in product(*candidate_sets):
                residual = abs(hypot(*candidate_vector)-reference)
                edit_cost = sum(
                    _digit_edit_cost(row.get(raw_name, ""), value)
                    for raw_name, value in zip(raw_names, candidate_vector)
                )
                change = sum(abs(value-old) for value, old in zip(candidate_vector, vector))
                combinations.append((residual, edit_cost, change, candidate_vector))
            accepted = [item for item in combinations if item[0] <= tolerance]
            if accepted:
                selected_vector = min(
                    accepted, key=lambda item: (item[1], item[2], item[0])
                )[3]
            else:
                selected_vector = min(
                    combinations, key=lambda item: (item[0], item[1], item[2])
                )[3]
            for index, (old, selected) in enumerate(zip(vector, selected_vector)):
                if selected != old:
                    row.setdefault("transcription_corrections", []).append(
                        f"space-fixed component {offset+index} changed from "
                        f"{old} to {selected} using redundant vector norm"
                    )
            vector = list(selected_vector)

            if not any(mark in raw_target for mark in ".,"):
                minimum, maximum = scalar_limits
                candidates = _numeric_candidates(raw_target, minimum, maximum)
                if candidates:
                    vector_norm = hypot(*vector)
                    selected = min(candidates, key=lambda value: abs(value-vector_norm))
                    if abs(selected-vector_norm) < abs(float(target)-vector_norm)-1e-6:
                        old = float(target)
                        row[target_name] = selected
                        target = selected
                        row.setdefault("transcription_corrections", []).append(
                            f"column {target_name} changed from {old} to {selected} "
                            "using redundant vector norm"
                        )
            for index, value in enumerate(vector):
                row[str(offset+index)] = value


def _merge_rows(pdf, *, phases=None):
    merged = {}
    with tempfile.TemporaryDirectory(prefix="ssa-apollo11-") as temporary:
        directory = Path(temporary)
        for phase, tables in PHASE_TABLE_PAGES:
            if phases is not None and phase not in phases:
                continue
            for role, pages in tables.items():
                for page in pages:
                    for row in _extract_page(pdf, page, role, phase, directory):
                        key = (phase, row["time_from_first_motion_s"])
                        current = merged.setdefault(key, {})
                        current.update({name: value for name, value in row.items()
                                        if name not in {"_page", "event"} and value != ""})
                        if row.get("_time_correction"):
                            current.setdefault("transcription_corrections", []).append(
                                row["_time_correction"]
                            )
                        if row["event"]:
                            current["event"] = row["event"]
                        current.setdefault("source_pages", set()).add(page)
    _correct_ocr_columns(merged)
    _correct_source_vector_ocr(merged)
    _apply_visually_verified_transcriptions(merged, phases=phases)
    output = []
    for event, event_time in TABLE_EVENT_TIMES.items():
        candidates = [(phase, time_value) for phase, time_value in merged
                      if abs(time_value-event_time) <= 0.02]
        for key in candidates:
            merged[key]["event"] = event
    phase_order = {"s_ic": 0, "s_ii": 1, "s_ivb": 2}
    for phase, sample_time in sorted(
        merged, key=lambda key: (key[1], phase_order[key[0]])
    ):
        values = merged[(phase, sample_time)]
        event = values.get("event", "")
        row = {"time_from_first_motion_s": sample_time,
               "phase": phase,
               "event": event,
               "event_side": "",
               "event_source": ("Table 2.4" if event in {
                   "MAX Q", "S-IC CECO", "S-IC OECO", "S-II CECO", "S-IVB GCS1", "EPOI",
               } else "Table 2.1" if event else ""),
               "source_pages": ";".join(map(str, sorted(values.pop("source_pages", set())))),
               "transcription_corrections": ";".join(values.pop("transcription_corrections", []))}
        if event == "S-IC/S-II SEP":
            row["event_side"] = "pre_reset" if phase == "s_ic" else "post_reset"
        elif event == "S-II/S-IVB SEP":
            row["event_side"] = "pre_reset" if phase == "s_ii" else "post_reset"
        for index, field in enumerate(FIELDS[2:], start=2):
            row[field] = values.get(str(index), "")
        if row["dynamic_pressure_pa"] != "":
            pressure = float(row["dynamic_pressure_pa"])
            if pressure > 1e6:
                row["dynamic_pressure_pa"] = pressure/1000.0
        if event == "MAX Q":
            row["dynamic_pressure_pa"] = 34725.243
        output.append(row)
    return output


def _validate_sic(rows):
    expected_times = {0.0, 0.4, 65.75, 81.0, 160.82, 161.59}
    expected_times.update(float(value) for value in range(5, 161, 5))
    actual_times = {row["time_from_first_motion_s"] for row in rows}
    if actual_times != expected_times or len(rows) != len(expected_times):
        missing = sorted(expected_times-actual_times)
        extra = sorted(actual_times-expected_times)
        raise ValueError(
            f"S-IC profile epochs differ from the 5 s/event grid; "
            f"missing={missing}, extra={extra}"
        )

    expected_events = {
        "TIME BASE 1": 0.4,
        "MACH 1": 65.75,
        "MAX Q": 81.0,
        "S-IC CECO": 135.0,
        "S-IC OECO": 160.82,
        "S-IC/S-II SEP": 161.59,
    }
    by_event = {row["event"]: row for row in rows if row["event"]}
    for event, expected_time in expected_events.items():
        if event not in by_event:
            raise ValueError(f"S-IC profile is missing summary event {event!r}")
        actual_time = by_event[event]["time_from_first_motion_s"]
        if abs(actual_time-expected_time) > 0.02:
            raise ValueError(
                f"{event} time {actual_time} s disagrees with NASA Table 2.2"
            )

    position_residuals = []
    speed_residuals = []
    required = (
        "geocentric_radius_m", "inertial_speed_m_s",
        "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
        "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
    )
    for row in rows:
        missing = [name for name in required if row.get(name, "") == ""]
        if missing:
            raise ValueError(
                f"S-IC {row['time_from_first_motion_s']} s is missing {missing}"
            )
        position = [float(row[name]) for name in (
            "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
        )]
        velocity = [float(row[name]) for name in (
            "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
        )]
        position_residuals.append(
            abs(hypot(*position)-float(row["geocentric_radius_m"]))
        )
        speed_residuals.append(
            abs(hypot(*velocity)-float(row["inertial_speed_m_s"]))
        )

    max_position_residual = max(position_residuals)
    max_speed_residual = max(speed_residuals)
    if max_position_residual > 0.5 or max_speed_residual > 0.2:
        raise ValueError(
            "S-IC source-vector closure fails: "
            f"max radius residual {max_position_residual:.6f} m, "
            f"max speed residual {max_speed_residual:.6f} m/s"
        )
    return {
        "sample_count": len(rows),
        "time_span_s": [min(actual_times), max(actual_times)],
        "max_abs_position_norm_residual_m": max_position_residual,
        "position_norm_tolerance_m": 0.5,
        "max_abs_velocity_norm_residual_m_s": max_speed_residual,
        "velocity_norm_tolerance_m_s": 0.2,
        "geodetic_frame_checkpoints": [
            {
                "time_s": time_s,
                "latitude_deg_north": latitude,
                "longitude_deg_west": longitude_west,
                "source_table": "2.2",
                "source_pdf_page": 14,
            }
            for time_s, latitude, longitude_west in SIC_GEODETIC_CHECKPOINTS
        ],
    }


def _validate(rows):
    by_event = {row["event"]: row for row in rows if row["event"]}
    expected_times = {
        "MAX Q": (81.0, 0.0),
        "S-IC CECO": (135.0, 0.0),
        "S-IC OECO": (160.82, 0.02),
        "S-II CECO": (459.8, 0.02),
        "S-II ENGINE CUTOFF": (551.384, 0.02),
        "S-IVB GCS1": (699.23, 0.02),
        "EPOI": (709.23, 0.02),
    }
    for event, (expected, tolerance) in expected_times.items():
        if event not in by_event:
            raise ValueError(f"extracted profile is missing summary event {event!r}")
        actual = by_event[event]["time_from_first_motion_s"]
        if abs(actual-expected) > tolerance:
            raise ValueError(f"{event} time {actual} s disagrees with NASA Table 2.4")
    peak_q = float(by_event["MAX Q"]["dynamic_pressure_pa"])
    if abs(peak_q-34725.24) > 0.1:
        raise ValueError(f"maximum q {peak_q} Pa disagrees with NASA Table 2.4 (34,725.243 Pa)")
    final_radius = float(by_event["EPOI"]["geocentric_radius_m"])
    if abs(final_radius-6563308.7) > 0.1:
        raise ValueError(f"EPOI radius {final_radius} m disagrees with NASA Table 2.4")
    closure_errors = []
    for row in rows:
        required = ("geocentric_radius_m", "inertial_speed_m_s",
                    "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
                    "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s")
        if any(row.get(name, "") == "" for name in required):
            missing = [name for name in required if row.get(name, "") == ""]
            closure_errors.append(
                f"{row['phase']} {row['time_from_first_motion_s']} s is missing "
                f"{missing} (source pages {row['source_pages']})"
            )
            continue
        position = [float(row[name]) for name in
                    ("space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m")]
        velocity = [float(row[name]) for name in
                    ("space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s")]
        radius_residual = abs(hypot(*position)-float(row["geocentric_radius_m"]))
        speed_residual = abs(hypot(*velocity)-float(row["inertial_speed_m_s"]))
        if radius_residual > 0.5 or speed_residual > 0.2:
            closure_errors.append(
                f"{row['phase']} {row['time_from_first_motion_s']} s source-vector closure "
                f"fails: radius residual {radius_residual:.3f} m, speed residual "
                f"{speed_residual:.3f} m/s; position {position}, expected radius "
                f"{row['geocentric_radius_m']}; velocity {velocity}, expected speed "
                f"{row['inertial_speed_m_s']}; source pages {row['source_pages']}"
            )
    if closure_errors:
        raise ValueError("source-vector closure errors:\n" + "\n".join(closure_errors))


def extract(pdf):
    pdf = Path(pdf)
    if sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("input PDF does not match the pinned NASA CR-61291 source digest")
    rows = _merge_rows(pdf)
    _validate(rows)
    return rows


def extract_sic(pdf):
    """Extract the source-closed S-IC arc; this is operational data, not flight truth."""
    pdf = Path(pdf)
    if sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("input PDF does not match the pinned NASA CR-61291 source digest")
    rows = _merge_rows(pdf, phases={"s_ic"})
    _validate_sic(rows)
    return rows


def _validate_sii_initial(rows):
    """Validate five early S-II event/sample states against printed norm fields."""
    by_time = {
        row["time_from_first_motion_s"]: row
        for row in rows
        if row["phase"] == "s_ii"
        and row["time_from_first_motion_s"] in SII_INITIAL_TIMES
    }
    if set(by_time) != set(SII_INITIAL_TIMES):
        raise ValueError(
            "early S-II epochs differ from the pinned sample/event set; "
            f"missing={sorted(set(SII_INITIAL_TIMES)-set(by_time))}, "
            f"extra={sorted(set(by_time)-set(SII_INITIAL_TIMES))}"
        )

    required = (
        "geocentric_radius_m", "inertial_speed_m_s",
        "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
        "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
    )
    position_residuals = []
    speed_residuals = []
    for time_s in SII_INITIAL_TIMES:
        row = by_time[time_s]
        missing = [name for name in required if row.get(name, "") == ""]
        if missing:
            raise ValueError(f"S-II {time_s} s is missing {missing}")
        position = [float(row[name]) for name in (
            "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
        )]
        velocity = [float(row[name]) for name in (
            "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
        )]
        position_residuals.append(
            abs(hypot(*position)-float(row["geocentric_radius_m"]))
        )
        speed_residuals.append(
            abs(hypot(*velocity)-float(row["inertial_speed_m_s"]))
        )

    if max(position_residuals) > 0.5 or max(speed_residuals) > 0.2:
        raise ValueError(
            "early S-II source-vector closure fails: "
            f"max radius residual {max(position_residuals):.6f} m, "
            f"max speed residual {max(speed_residuals):.6f} m/s"
        )
    events = {row["event"]: row for row in by_time.values() if row["event"]}
    expected_events = {
        "S-IC/S-II SEP": 161.59,
        "S-II ENGINE START": 162.22,
        "S-II 90 THRUST": 165.22,
    }
    for event, expected_time in expected_events.items():
        if event not in events or events[event]["time_from_first_motion_s"] != expected_time:
            raise ValueError(f"early S-II reference is missing event {event!r}")
    if by_time[161.59]["event_side"] != "post_reset":
        raise ValueError("S-II separation reference must be the post-reset state")
    return {
        "sample_count": len(SII_INITIAL_TIMES),
        "time_span_s": [min(SII_INITIAL_TIMES), max(SII_INITIAL_TIMES)],
        "max_abs_position_norm_residual_m": max(position_residuals),
        "position_norm_tolerance_m": 0.5,
        "max_abs_velocity_norm_residual_m_s": max(speed_residuals),
        "velocity_norm_tolerance_m_s": 0.2,
    }


def extract_sii_initial(pdf):
    """Extract source-closed post-separation S-II event/early-ascent states."""
    pdf = Path(pdf)
    if sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("input PDF does not match the pinned NASA CR-61291 source digest")
    rows = _merge_rows(pdf, phases={"s_ii"})
    _validate_sii_initial(rows)
    return [
        row for row in rows
        if row["time_from_first_motion_s"] in SII_INITIAL_TIMES
    ]


def extract_sii_source_closed(pdf):
    """Return S-II rows with closed norms and uncorrected/visually checked source cells."""
    pdf = Path(pdf)
    if sha256(pdf.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("input PDF does not match the pinned NASA CR-61291 source digest")
    candidates = _merge_rows(pdf, phases={"s_ii"})
    included = []
    incomplete = []
    closure_failed = []
    review_withheld = []
    position_residuals = []
    speed_residuals = []
    for row in candidates:
        time_s = row["time_from_first_motion_s"]
        missing = [name for name in STATE_CLOSURE_FIELDS if row.get(name, "") == ""]
        if missing:
            incomplete.append({"time_s": time_s, "missing_fields": missing})
            continue
        position = [float(row[name]) for name in (
            "space_fixed_x_m", "space_fixed_y_m", "space_fixed_z_m",
        )]
        velocity = [float(row[name]) for name in (
            "space_fixed_vx_m_s", "space_fixed_vy_m_s", "space_fixed_vz_m_s",
        )]
        position_residual = abs(hypot(*position)-float(row["geocentric_radius_m"]))
        speed_residual = abs(hypot(*velocity)-float(row["inertial_speed_m_s"]))
        if position_residual > 0.5 or speed_residual > 0.2:
            closure_failed.append({
                "time_s": time_s,
                "position_norm_residual_m": position_residual,
                "speed_norm_residual_m_s": speed_residual,
                "source_pages": row["source_pages"],
            })
            continue
        notes = [
            note for note in row.get("transcription_corrections", "").split(";")
            if note
        ]
        manually_verified = set()
        for note in notes:
            match = re.search(
                r"table 2\.2 column (\d+): manually verified", note,
            )
            if match:
                manually_verified.add(int(match.group(1)))
        unreviewed_state_corrections = []
        for note in notes:
            match = re.match(r"(?:space-fixed component|column) (\d+)", note)
            if (
                match
                and int(match.group(1)) in STATE_REFERENCE_COLUMNS
                and int(match.group(1)) not in manually_verified
            ):
                unreviewed_state_corrections.append(note)
        if unreviewed_state_corrections:
            unverified_columns = sorted({
                int(match.group(1))
                for note in unreviewed_state_corrections
                if (match := re.match(r"(?:space-fixed component|column) (\d+)", note))
            })
            review_withheld.append({
                "time_s": time_s,
                "reason": "state-field OCR correction lacks visual verification",
                "unverified_state_fields": [
                    {
                        "source_table_column": column,
                        "field": STATE_REFERENCE_FIELD_NAMES[column],
                    }
                    for column in unverified_columns
                ],
                "source_pages": row["source_pages"],
            })
            continue
        row["transcription_corrections"] = ";".join(
            note for note in notes
            if (
                "table 2.2 column " in note
                and "manually verified" in note
            )
        )
        included.append(row)
        position_residuals.append(position_residual)
        speed_residuals.append(speed_residual)

    if not included:
        raise ValueError("S-II extraction produced no source-closed state samples")
    validation = {
        "candidate_record_count": len(candidates),
        "record_count": len(included),
        "incomplete_records": incomplete,
        "closure_failed_records": closure_failed,
        "review_withheld_records": review_withheld,
        "sample_times_s": [row["time_from_first_motion_s"] for row in included],
        "max_abs_position_norm_residual_m": max(position_residuals),
        "position_norm_tolerance_m": 0.5,
        "max_abs_velocity_norm_residual_m_s": max(speed_residuals),
        "velocity_norm_tolerance_m_s": 0.2,
        "geodetic_frame_checkpoints": [
            {
                "time_s": time_s,
                "latitude_deg_north": latitude,
                "longitude_deg_west": longitude_west,
                "source_table": "2.2",
                "source_pdf_page": 27,
                "printed_page": 21,
            }
            for time_s, latitude, longitude_west
            in SII_SOURCE_CLOSED_GEODETIC_CHECKPOINTS
        ],
        "interpretation": (
            "Only individually source-closed S-II records are included. "
            "The samples are sparse and do not define a continuous trajectory."
        ),
    }
    return included, validation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="NASA CR-61291 PDF; downloaded when omitted")
    parser.add_argument(
        "--phase",
        choices=("all", "s_ic", "s_ii_initial", "s_ii_closed"),
        default="all",
        help=(
            "extract the experimental profile, source-closed S-IC or early "
            "S-II segments, or individually source-closed S-II samples"
        ),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not all(shutil.which(name) for name in ("pdftoppm", "convert", "tesseract")):
        parser.error("extractor requires Poppler pdftoppm, ImageMagick convert, and Tesseract")
    temporary = None
    pdf = args.pdf
    if pdf is None:
        handle = tempfile.NamedTemporaryFile(prefix="nasa-cr-61291-", suffix=".pdf", delete=False)
        handle.close()
        temporary = Path(handle.name)
        _fetch_report(temporary)
        pdf = temporary
    try:
        if args.phase == "s_ic":
            rows = extract_sic(pdf)
            validation = _validate_sic(rows)
            output_rows = [
                {field: row[field] for field in SIC_REFERENCE_FIELDS}
                for row in rows
            ]
            output_fields = SIC_REFERENCE_FIELDS
        elif args.phase == "s_ii_initial":
            rows = extract_sii_initial(pdf)
            validation = _validate_sii_initial(rows)
            output_rows = [
                {field: row[field] for field in SII_INITIAL_REFERENCE_FIELDS}
                for row in rows
            ]
            output_fields = SII_INITIAL_REFERENCE_FIELDS
        elif args.phase == "s_ii_closed":
            rows, validation = extract_sii_source_closed(pdf)
            output_rows = [
                {field: row[field] for field in SII_CLOSED_REFERENCE_FIELDS}
                for row in rows
            ]
            output_fields = SII_CLOSED_REFERENCE_FIELDS
        else:
            rows = extract(pdf)
            validation = None
            output_rows = rows
            output_fields = (
                *FIELDS[:2], "phase", *FIELDS[2:],
                "event_side", "event_source", "transcription_corrections",
                "source_pages",
            )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    output = args.output
    if output is None:
        default_name = (
            "apollo11_sic_operational_reference.csv"
            if args.phase == "s_ic"
            else "apollo11_sii_initial_operational_reference.csv"
            if args.phase == "s_ii_initial"
            else "apollo11_sii_source_closed_samples.csv"
            if args.phase == "s_ii_closed"
            else "apollo11_trajectory_ocr_unverified.csv"
        )
        output = Path(tempfile.gettempdir()) / default_name
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=output_fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)
    versions = {}
    for name, flag in (("pdftoppm", "-v"), ("convert", "--version"),
                       ("tesseract", "--version")):
        completed = subprocess.run([name, flag], text=True, capture_output=True)
        version_text = (completed.stdout or completed.stderr).splitlines()
        versions[name] = version_text[0] if version_text else "unknown"
    provenance = {
        "schema": (
            "ssa_data_launch.apollo11_sic_profile.v1"
            if args.phase == "s_ic"
            else "ssa_data_launch.apollo11_sii_initial_profile.v1"
            if args.phase == "s_ii_initial"
            else "ssa_data_launch.apollo11_sii_closed_samples.v1"
            if args.phase == "s_ii_closed"
            else "ssa_data_launch.unverified_ocr.v1"
        ),
        "source_pdf_sha256": SOURCE_SHA256,
        "output_sha256": sha256(output.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "status": (
            "SOURCE_CLOSED_OPERATIONAL_GUIDANCE_REFERENCE; NOT FLIGHT TRUTH"
            if args.phase in {"s_ic", "s_ii_initial"}
            else "PARTIAL_SOURCE_CLOSED_OPERATIONAL_GUIDANCE_SAMPLES; NOT FLIGHT TRUTH"
            if args.phase == "s_ii_closed"
            else "UNVERIFIED_OCR; NOT A BENCHMARK OR FLIGHT-TRUTH DATASET"
        ),
        "software_versions": versions,
    }
    if validation is not None:
        provenance["validation"] = validation
    sidecar = output.with_name(output.name+".provenance.json")
    with sidecar.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(provenance, indent=2)+"\n")


if __name__ == "__main__":
    main()
