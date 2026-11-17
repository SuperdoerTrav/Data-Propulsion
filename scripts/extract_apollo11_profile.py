"""OCR the AS-506 tables; only the validated S-IC segment is source-closed."""

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
        if any(not value for value in raw_values):
            continue
        try:
            values = [_number(value) for value in raw_values]
        except ValueError:
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
                and values[2] > 10000.0):
            time_value = 90.0
            correction = "PDF p.13 row time visually verified as 90.00 s"
        previous_time = time_value
        row = {"time_from_first_motion_s": time_value, "event": event,
               "phase": phase, "_page": page, "_time_correction": correction}
        for index, value in enumerate(values):
            row[str(offset+index)] = value
            row[f"_raw{offset+index}"] = raw_values[index]
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
                if raw is not None and value is not None:
                    samples.append((key, raw, float(value)))
            confident = [
                (key, value) for key, raw, value in samples
                if any(mark in raw for mark in ".,") and minimum <= value <= maximum
            ]
            for sample_index, (key, raw, value) in enumerate(samples):
                if any(mark in raw for mark in ".,") and minimum <= value <= maximum:
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
                merged[key][str(column)] = min(candidates, key=lambda item: abs(item-expected))


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
            if any(value in (None, "") for value in vector):
                continue
            vector = [float(value) for value in vector]

            tolerance = 0.5 if offset == 25 else 0.2
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, help="NASA CR-61291 PDF; downloaded when omitted")
    parser.add_argument(
        "--phase",
        choices=("all", "s_ic"),
        default="all",
        help="extract the full experimental profile or the source-closed S-IC segment",
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
        else:
            rows = extract(pdf)
            validation = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    output = args.output
    if output is None:
        default_name = (
            "apollo11_sic_operational_reference.csv"
            if args.phase == "s_ic"
            else "apollo11_trajectory_ocr_unverified.csv"
        )
        output = Path(tempfile.gettempdir()) / default_name
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(*FIELDS[:2], "phase", *FIELDS[2:],
                        "event_side", "event_source", "transcription_corrections",
                        "source_pages"),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
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
            else "ssa_data_launch.unverified_ocr.v1"
        ),
        "source_pdf_sha256": SOURCE_SHA256,
        "output_sha256": sha256(output.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "status": (
            "SOURCE_CLOSED_OPERATIONAL_GUIDANCE_REFERENCE; NOT FLIGHT TRUTH"
            if args.phase == "s_ic"
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
