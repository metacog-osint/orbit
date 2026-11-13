"""Maneuver Compare engine from the 1 Nov 2026 seed build. NOT RUN by tools/orbit.py (13 Nov 2026 review).

Kept for reference only. Why it is not live:
  - It differences two consecutive element sets and calls anything at or above 0.35 m/s a manoeuvre. In low
    orbit, drag and ordinary element-set fit noise move mean motion by more than that between sets, so on live
    data it would report false manoeuvres.
  - "calibrated_confidence" is a fixed formula, not a calibration against known manoeuvres.
  - Its inputs were made up. A real history needs Space-Track GP history (terms reported to bar publishing
    derived analysis; not yet read) or an archive Orbit builds itself from a source it may republish.
The plan's first step is to run maneuver-detect (MIT, astro-tools) on SJ-21 and BeiDou-2 G2 (January 2022)
locally and judge whether it is believable. See doctrine/method.md.
"""
from __future__ import annotations

import math
from datetime import datetime

MU_EARTH_KM3_S2 = 398600.4418

MEANING_SENTENCES = {
    "in-track": (
        "Hypothesis: An in-track burn alters semi-major axis and orbital period, which usually indicates "
        "along-track re-phasing, ground-track repeat timing adjustment, or closing/opening distance to a co-orbital object."
    ),
    "cross-track": (
        "Hypothesis: A cross-track out-of-plane burn alters inclination or right ascension of the ascending node (RAAN), "
        "which usually indicates orbital plane realignment, sun-synchronous local-time-of-ascending-node maintenance, or plane matching."
    ),
    "radial": (
        "Hypothesis: A radial or eccentricity-shaping burn alters perigee/apogee geometry without a large period shift, "
        "which usually indicates perigee height maintenance or close-proximity circumnavigation."
    ),
}


def _semi_major_axis_km(mean_motion_rev_day: float) -> float:
    n_rad_s = (mean_motion_rev_day * 2.0 * math.pi) / 86400.0
    return (MU_EARTH_KM3_S2 / (n_rad_s ** 2)) ** (1.0 / 3.0)


def _orbital_speed_ms(a_km: float) -> float:
    return math.sqrt(MU_EARTH_KM3_S2 / a_km) * 1000.0


def evaluate_tle_history(watched_histories: list[dict], siblings_map: dict[str, list[str]] | None = None) -> dict:
    """Compare consecutive TLE epochs for each watched satellite to detect maneuvers and flag >=48h TLE gaps."""
    siblings_map = siblings_map or {}
    detections = []
    source_health_flags = []

    for sat in watched_histories:
        jcat = sat["jcat"]
        norad = sat.get("norad") or "UNNUMBERED"
        name = sat["name"]
        owner = sat.get("owner_clean") or sat.get("owner") or "RU"
        country = sat.get("country") or ("RU" if owner in ("RU", "SU") else owner)
        orbit_class = sat.get("orbit_class") or "LEO"
        launch_desig = sat.get("launch_designator") or ""
        days_since_launch = int(sat.get("days_since_launch", 120))
        is_sibling_dispersion = bool(launch_desig in siblings_map and days_since_launch <= 30)
        epochs = sat.get("epochs") or []

        max_gap_h = 0.0
        for i in range(1, len(epochs)):
            prev, curr = epochs[i - 1], epochs[i]
            t0 = datetime.fromisoformat(prev["epoch"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(curr["epoch"].replace("Z", "+00:00"))
            gap_h = round((t1 - t0).total_seconds() / 3600.0, 2)
            if gap_h > max_gap_h:
                max_gap_h = gap_h

            a0 = _semi_major_axis_km(float(prev["mean_motion"]))
            a1 = _semi_major_axis_km(float(curr["mean_motion"]))
            v_ms = _orbital_speed_ms((a0 + a1) / 2.0)

            da_km = a1 - a0
            di_deg = float(curr["inclination_deg"]) - float(prev["inclination_deg"])
            de = float(curr["eccentricity"]) - float(prev["eccentricity"])

            dv_intrack = abs(0.5 * v_ms * (da_km / a0))
            dv_crosstrack = abs(2.0 * v_ms * math.sin(math.radians(abs(di_deg)) / 2.0))
            dv_radial = abs(0.5 * v_ms * abs(de))

            components = [
                ("in-track", dv_intrack),
                ("cross-track", dv_crosstrack),
                ("radial", dv_radial),
            ]
            mtype, peak_dv = max(components, key=lambda x: x[1])
            total_dv = round(math.sqrt(dv_intrack ** 2 + dv_crosstrack ** 2 + dv_radial ** 2), 2)

            if total_dv < 0.35:
                continue

            # Calibrated confidence (degraded if a >=48h TLE gap spans the detection window)
            raw_conf = min(0.96, round(0.55 + min(0.40, total_dv / 8.0), 2))
            if gap_h >= 48.0:
                raw_conf = min(raw_conf, 0.45)

            routine_sk = bool(sat.get("routine_station_keeping", False)) or (orbit_class == "GEO" and total_dv < 1.2) or is_sibling_dispersion
            tier = "warning" if (total_dv >= 1.5 and raw_conf >= 0.75 and not routine_sk) else "routine"

            detections.append({
                "id": f"maneuver-{jcat.lower()}-{curr['epoch'][:13]}",
                "jcat": jcat,
                "norad": norad,
                "name": name,
                "owner": owner,
                "country": country,
                "orbit_class": orbit_class,
                "epoch_before": prev["epoch"],
                "epoch_after": curr["epoch"],
                "tle_gap_hours": gap_h,
                "maneuver_type": mtype,
                "delta_v_ms": total_dv,
                "delta_a_km": round(da_km, 3),
                "delta_inc_deg": round(di_deg, 4),
                "calibrated_confidence": raw_conf,
                "routine_station_keeping": routine_sk,
                "is_sibling_dispersion": is_sibling_dispersion,
                "tier": tier,
                "meaning_sentence": MEANING_SENTENCES[mtype],
                "subpoint_lat": float(curr.get("subpoint_lat", sat.get("subpoint_lat", 0.0))),
                "subpoint_lon": float(curr.get("subpoint_lon", sat.get("subpoint_lon", 0.0))),
                "summary": (
                    f"{name} (NORAD {norad}, {owner}, {orbit_class}): {mtype} maneuver of {total_dv} m/s "
                    f"(Δa={round(da_km, 2)} km, Δi={round(di_deg, 4)}°) detected between {prev['epoch'][:16]}Z and "
                    f"{curr['epoch'][:16]}Z (confidence {round(raw_conf * 100)}%). {MEANING_SENTENCES[mtype]}"
                ),
            })

        if max_gap_h >= 48.0:
            source_health_flags.append({
                "jcat": jcat,
                "norad": norad,
                "name": name,
                "owner": owner,
                "country": country,
                "orbit_class": orbit_class,
                "max_tle_gap_hours": max_gap_h,
                "last_epoch": epochs[-1]["epoch"] if epochs else "unknown",
                "subpoint_lat": float(sat.get("subpoint_lat", 0.0)),
                "subpoint_lon": float(sat.get("subpoint_lon", 0.0)),
                "summary": (
                    f"Source health flag: {name} (NORAD {norad}, {owner}) had a {max_gap_h} h TLE tracking gap "
                    f"(>=48 h threshold); an untracked window looks identical to zero maneuvers."
                ),
            })

    detections.sort(key=lambda d: (d["tier"] != "warning", -d["delta_v_ms"], d["jcat"]))
    return {"detections": detections, "source_health_flags": source_health_flags}
