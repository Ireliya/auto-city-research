#!/usr/bin/env python3
"""Parse xBD/xView2 label JSON files into lightweight CSV tables.

This script uses only the Python standard library so it can run on the
remote data host without environment setup. It does not read or copy images.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


DAMAGE_SCORE = {
    "no-damage": 0.0,
    "minor-damage": 1.0 / 3.0,
    "major-damage": 2.0 / 3.0,
    "destroyed": 1.0,
    "un-classified": math.nan,
    "unknown": math.nan,
}


def parse_polygon_wkt(wkt: str) -> list[tuple[float, float]]:
    values = [float(x) for x in NUMBER_RE.findall(wkt or "")]
    points = [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    return points


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    acc = 0.0
    for idx, (x1, y1) in enumerate(points):
        x2, y2 = points[(idx + 1) % len(points)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def centroid(points: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    if not points:
        return None, None
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def bbox(points: list[tuple[float, float]]) -> tuple[float | None, float | None, float | None, float | None]:
    if not points:
        return None, None, None, None
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def stage_from_name(path: Path) -> str:
    name = path.name
    if "_pre_disaster" in name:
        return "pre"
    if "_post_disaster" in name:
        return "post"
    return "unknown"


def should_include(path: Path, stages: set[str], events: set[str] | None) -> bool:
    stage = stage_from_name(path)
    if "all" not in stages and stage not in stages:
        return False
    if events is None:
        return True
    event = path.name.split("_")[0]
    return event in events


def row_for_feature(label_path: Path, meta: dict, stage: str, lng_feature: dict, xy_feature: dict | None) -> dict:
    props = lng_feature.get("properties", {})
    uid = props.get("uid", "")
    subtype = props.get("subtype", "unknown")
    lng_points = parse_polygon_wkt(lng_feature.get("wkt", ""))
    xy_points = parse_polygon_wkt((xy_feature or {}).get("wkt", ""))
    lon, lat = centroid(lng_points)
    x, y = centroid(xy_points)
    min_lon, min_lat, max_lon, max_lat = bbox(lng_points)
    min_x, min_y, max_x, max_y = bbox(xy_points)
    area_px = polygon_area(xy_points)
    gsd = float(meta.get("gsd") or 0.0)
    area_m2 = area_px * gsd * gsd if area_px and gsd else 0.0
    score = DAMAGE_SCORE.get(subtype, math.nan)

    return {
        "label_file": label_path.name,
        "img_name": meta.get("img_name", ""),
        "stage": stage,
        "event": meta.get("disaster", ""),
        "disaster_type": meta.get("disaster_type", ""),
        "capture_date": meta.get("capture_date", ""),
        "sensor": meta.get("sensor", ""),
        "gsd": gsd,
        "width": meta.get("width", ""),
        "height": meta.get("height", ""),
        "building_uid": uid,
        "feature_type": props.get("feature_type", ""),
        "damage_subtype": subtype,
        "damage_score": score,
        "lon_centroid": lon,
        "lat_centroid": lat,
        "x_centroid": x,
        "y_centroid": y,
        "lnglat_min_lon": min_lon,
        "lnglat_min_lat": min_lat,
        "lnglat_max_lon": max_lon,
        "lnglat_max_lat": max_lat,
        "xy_min_x": min_x,
        "xy_min_y": min_y,
        "xy_max_x": max_x,
        "xy_max_y": max_y,
        "area_px": area_px,
        "area_m2_approx": area_m2,
        "has_lng_lat": bool(lng_points),
        "has_xy": bool(xy_points),
    }


def parse_labels(labels_dir: Path, out_dir: Path, stages: set[str], events: set[str] | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    building_csv = out_dir / "xbd_buildings.csv"
    label_csv = out_dir / "xbd_label_files.csv"
    event_csv = out_dir / "xbd_event_summary.csv"

    label_paths = sorted(p for p in labels_dir.glob("*.json") if should_include(p, stages, events))
    event_summary: dict[str, Counter] = defaultdict(Counter)
    label_rows = []
    building_fields: list[str] | None = None

    with building_csv.open("w", newline="", encoding="utf-8") as bf:
        writer = None
        for label_path in label_paths:
            with label_path.open(encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("metadata", {})
            stage = stage_from_name(label_path)
            features = data.get("features", {})
            lng_features = features.get("lng_lat", [])
            xy_features = features.get("xy", [])
            xy_by_uid = {
                feat.get("properties", {}).get("uid", ""): feat
                for feat in xy_features
            }

            label_rows.append({
                "label_file": label_path.name,
                "img_name": meta.get("img_name", ""),
                "stage": stage,
                "event": meta.get("disaster", ""),
                "disaster_type": meta.get("disaster_type", ""),
                "capture_date": meta.get("capture_date", ""),
                "lng_lat_features": len(lng_features),
                "xy_features": len(xy_features),
                "has_lng_lat": "lng_lat" in features,
                "has_xy": "xy" in features,
            })

            event = meta.get("disaster", "unknown")
            event_summary[event]["label_files"] += 1
            event_summary[event][f"{stage}_label_files"] += 1
            event_summary[event]["buildings"] += len(lng_features)

            for lng_feature in lng_features:
                uid = lng_feature.get("properties", {}).get("uid", "")
                xy_feature = xy_by_uid.get(uid)
                row = row_for_feature(label_path, meta, stage, lng_feature, xy_feature)
                event_summary[event][f"damage_{row['damage_subtype']}"] += 1
                if building_fields is None:
                    building_fields = list(row.keys())
                    writer = csv.DictWriter(bf, fieldnames=building_fields)
                    writer.writeheader()
                writer.writerow(row)

    label_fields = [
        "label_file",
        "img_name",
        "stage",
        "event",
        "disaster_type",
        "capture_date",
        "lng_lat_features",
        "xy_features",
        "has_lng_lat",
        "has_xy",
    ]
    with label_csv.open("w", newline="", encoding="utf-8") as lf:
        writer = csv.DictWriter(lf, fieldnames=label_fields)
        writer.writeheader()
        writer.writerows(label_rows)

    event_fields = sorted({key for counter in event_summary.values() for key in counter})
    with event_csv.open("w", newline="", encoding="utf-8") as ef:
        writer = csv.DictWriter(ef, fieldnames=["event", *event_fields])
        writer.writeheader()
        for event, counter in sorted(event_summary.items()):
            writer.writerow({"event": event, **counter})

    print(f"labels={len(label_paths)}")
    print(f"buildings_csv={building_csv}")
    print(f"label_files_csv={label_csv}")
    print(f"event_summary_csv={event_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--stages", default="post", help="Comma list: post, pre, all. Default: post")
    parser.add_argument("--events", default="", help="Optional comma-separated event names")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stages = {item.strip() for item in args.stages.split(",") if item.strip()}
    events = {item.strip() for item in args.events.split(",") if item.strip()} or None
    parse_labels(args.labels_dir, args.out_dir, stages, events)


if __name__ == "__main__":
    main()
