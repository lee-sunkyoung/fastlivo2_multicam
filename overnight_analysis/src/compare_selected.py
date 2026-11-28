#!/usr/bin/env python3

import csv
import sys
from pathlib import Path


def read_rows(path: Path):
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        fieldnames = [name.strip() for name in reader.fieldnames]
        if fieldnames[:2] != ["cam", "capture_time"]:
            raise ValueError(f"CSV header must begin with 'cam,capture_time': {path}")

        rows = []
        for row in reader:
            cam = row.get("cam", "")
            capture_time = row.get("capture_time", "")
            if cam == "" and capture_time == "":
                continue
            rows.append((int(cam), float(capture_time)))
        return rows


def format_row(label, row_idx, row):
    if row is None:
        return f"{label}[{row_idx}] = <missing>"
    return f"{label}[{row_idx}] = (cam={row[0]}, capture_time={row[1]:.6f})"


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {Path(sys.argv[0]).name} <csv1> <csv2>", file=sys.stderr)
        return 2

    path_a = Path(sys.argv[1])
    path_b = Path(sys.argv[2])

    try:
        rows_a = read_rows(path_a)
        rows_b = read_rows(path_b)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    count_a = len(rows_a)
    count_b = len(rows_b)
    print(f"{path_a.name}: {count_a} rows")
    print(f"{path_b.name}: {count_b} rows")
    print(f"Total count match: {count_a == count_b}")

    limit = min(count_a, count_b)
    first_diff = None
    for i in range(limit):
        if rows_a[i] != rows_b[i]:
            first_diff = i
            break

    if first_diff is None:
        if count_a != count_b:
            first_diff = limit
        else:
            print("No differences found.")
            return 0

    start = max(0, first_diff - 5)
    end = min(max(count_a, count_b), first_diff + 6)

    print(f"First difference at row {first_diff}")
    print("--- context ---")
    for idx in range(start, end):
        left = rows_a[idx] if idx < count_a else None
        right = rows_b[idx] if idx < count_b else None
        left_text = format_row("A", idx, left)
        right_text = format_row("B", idx, right)
        marker = " <diff>" if idx == first_diff else ""
        print(f"{left_text}{marker}")
        print(f"{right_text}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
