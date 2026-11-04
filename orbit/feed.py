"""Build Orbit's contract-v2 feed (tic-feed/2, GeoJSON) from normalized GCAT and Maneuver Compare snapshot."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "doctrine" / "kit" / "python"))
from tic_doctrine import CONTRACT, confidence, likelihood  # noqa: E402

SITE = "https://orbit.theintelligence.company"
METHOD = "orbit-1.0"
LANGUAGE_KEY = "https://github.com/metacog-osint/tic-doctrine/blob/main/docs/language-key.md"

SRC_GCAT = {
    "id": "gcat-mcdowell",
    "publisher": "Jonathan McDowell (GCAT)",
    "title": "General Catalog of Artificial Space Objects (satcat.tsv / active.tsv)",
    "url": "https://planet4589.org/space/gcat/",
    "licence": "CC BY 4.0",
    "grade": "A1",
    "independence_group": "gcat",
    "source_type": "registry",
    "descriptor": "Daily satellite catalog with Soviet (SU) vs Russian (RU) owner-code hygiene and unnumbered object tracking.",
}

SRC_CELESTRAK = {
    "id": "celestrak-gp",
    "publisher": "CelesTrak / USSF 18 SDS",
    "title": "GP Orbital Element Sets",
    "url": "https://celestrak.org/NORAD/elements/",
    "licence": "Public orbital element data",
    "grade": "A1",
    "independence_group": "ussf-18sds",
    "source_type": "telemetry",
    "descriptor": "Consecutive SGP4 general perturbations element sets for Maneuver Compare delta-v analysis.",
}


def _plus_hours(iso_utc: str, hours: int) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return (dt + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conf(ind_lines: int, cov: float, alt_rej: int) -> dict:
    return confidence.fields(confidence.Evidence(
        independent_lines=max(1, ind_lines),
        contradicted=False,
        coverage_fraction=cov,
        grades=["A1"],
        alternatives_rejected=alt_rej,
        method_scored=False,
        assumption_status="holds",
        ease_of_faking="low",
        horizon_days=0.0,
    ))


def build_feed(snapshot: dict) -> dict:
    """Build a contract-v2 GeoJSON FeatureCollection from Orbit's normalized snapshot."""
    generated = snapshot["generated_at"]
    valid_until = _plus_hours(generated, 24)
    detections = snapshot.get("maneuvers", [])
    health_flags = snapshot.get("source_health_flags", [])
    catalog_objects = snapshot.get("catalog", {}).get("objects", [])

    features = []

    # 1. Maneuver Compare detections (OR-WP-1)
    for m in detections:
        is_warn = m["tier"] == "warning"
        cov = 0.50 if m["tle_gap_hours"] >= 48.0 else 0.90
        conf = _conf(2, cov, 1 if is_warn else 0)
        prob = m["calibrated_confidence"]
        props = {
            "contract": CONTRACT,
            "id": f"orbit:maneuver:{m['jcat'].lower()}:{m['epoch_after'][:13]}",
            "program": "orbit",
            "title": (
                f"{m['name']} (NORAD {m['norad']}, {m['owner']}): {m['maneuver_type']} maneuver "
                f"Δv={m['delta_v_ms']} m/s ({m['orbit_class']})"
            ),
            "summary": m["summary"],
            "kind": "assessment" if is_warn else "observation",
            "tier": "warning" if is_warn else "routine",
            "status": "actual",
            "msg_type": "new",
            "human_review": "sampled" if is_warn else "none",
            "us_person_data": "none",
            "status_class": "assessed" if is_warn else "reported",
            "product_category": "warning" if is_warn else "current",
            "data_as_of": m["epoch_after"],
            "published_at": generated,
            "valid_until": valid_until,
            "countries": [m["country"]],
            "pmesii_pt": ["military", "infrastructure"],
            "ascope": ["capabilities"],
            "ie_aspect": ["physical", "informational"],
            "ncf": ["provide_satellite_access", "provide_pnt"],
            "requirement_ids": ["OR-PIR-1", "OR-EEI-1"],
            "method_version": METHOD,
            "coverage_fraction": cov,
            "precision_class": "point",
            "measures": {
                "delta_v_ms": m["delta_v_ms"],
                "delta_a_km": m["delta_a_km"],
                "delta_inc_deg": m["delta_inc_deg"],
                "tle_gap_hours": m["tle_gap_hours"],
            },
            "visual": {"type": "table", "url": f"{SITE}/#{m['jcat']}"},
            "sources": [
                {**SRC_CELESTRAK, "accessed_at": generated},
                {**SRC_GCAT, "accessed_at": generated},
            ],
        }
        if is_warn:
            props.update({
                "change_from_prior": "new",
                "change_reason": f"Detected {m['maneuver_type']} burn (Δv={m['delta_v_ms']} m/s) between consecutive GP epochs.",
                "warning_problem_id": "OR-WP-1",
                "indicator_id": "OR-IND-1",
                "hypothesis_id": "OR-H-1A",
                "direction": "supports",
                "indicator_state": "present",
                "probability": prob,
                "likelihood_term": likelihood.term_for(prob)["id"],
                **conf,
                "alternatives": [
                    {
                        "hypothesis": "Deliberate orbital re-phasing, ground-track retargeting, or co-orbital approach",
                        "tell_apart": "Sustained closing drift rate toward another active payload or repeat ground-track lock.",
                    },
                    {
                        "hypothesis": "Routine constellation slot maintenance or debris-avoidance burn",
                        "tell_apart": "Return to nominal orbital slot without proximity approach or subsatellite release.",
                    },
                ],
            })
        geom = {"type": "Point", "coordinates": [m["subpoint_lon"], m["subpoint_lat"]]}
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # 2. Subsatellite deployments from GCAT catalog diff (OR-IND-2)
    for obj in catalog_objects:
        if not obj.get("is_subsatellite_deployment"):
            continue
        conf = _conf(2, 0.85, 1)
        prob = 0.85
        props = {
            "contract": CONTRACT,
            "id": f"orbit:subsat:{obj['jcat'].lower()}:{obj['launch_date']}",
            "program": "orbit",
            "title": f"Subsatellite deployment cataloged: {obj['name']} (from {obj.get('parent_object') or 'host'}, {obj['owner_clean']})",
            "summary": (
                f"GCAT cataloged {obj['name']} ({obj['jcat']}, NORAD {obj['norad'] or 'unnumbered'}, owner {obj['owner_clean']}) "
                f"separating from host {obj.get('parent_object') or 'payload'} in {obj['orbit_class']}."
            ),
            "kind": "assessment",
            "tier": "warning",
            "status": "actual",
            "msg_type": "new",
            "human_review": "sampled",
            "us_person_data": "none",
            "status_class": "assessed",
            "product_category": "warning",
            "data_as_of": f"{obj['launch_date']}T00:00:00Z",
            "published_at": generated,
            "valid_until": valid_until,
            "change_from_prior": "new",
            "change_reason": f"Newly cataloged subsatellite {obj['name']} ({obj['jcat']}) separating from host {obj.get('parent_object') or 'payload'}.",
            "countries": [obj["country"]],
            "pmesii_pt": ["military"],
            "ascope": ["capabilities"],
            "ie_aspect": ["physical"],
            "ncf": ["provide_satellite_access"],
            "requirement_ids": ["OR-PIR-2"],
            "warning_problem_id": "OR-WP-1",
            "indicator_id": "OR-IND-2",
            "hypothesis_id": "OR-H-1A",
            "direction": "supports",
            "indicator_state": "present",
            "method_version": METHOD,
            "coverage_fraction": 0.85,
            "probability": prob,
            "likelihood_term": likelihood.term_for(prob)["id"],
            **conf,
            "alternatives": [
                {
                    "hypothesis": "Co-orbital inspector subsatellite or calibration target release",
                    "tell_apart": "Independent station-keeping or bidirectional proximity maneuvers relative to the host.",
                },
                {
                    "hypothesis": "Passive debris fragment or adapter separation",
                    "tell_apart": "High area-to-mass ballistic decay without thruster burns.",
                },
            ],
            "precision_class": "point",
            "visual": {"type": "table", "url": f"{SITE}/#{obj['jcat']}"},
            "sources": [{**SRC_GCAT, "accessed_at": generated}],
        }
        geom = {"type": "Point", "coordinates": [obj["subpoint_lon"], obj["subpoint_lat"]]}
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    # 3. Source Health flags: TLE gaps >= 48 hours (OR-IND-4)
    for hf in health_flags:
        props = {
            "contract": CONTRACT,
            "id": f"orbit:gap:{hf['jcat'].lower()}:{hf['last_epoch'][:10]}",
            "program": "orbit",
            "title": f"TLE tracking gap ({hf['max_tle_gap_hours']} h): {hf['name']} (NORAD {hf['norad']})",
            "summary": hf["summary"],
            "kind": "observation",
            "tier": "anomaly",
            "baseline_ref": "celestrak-gp-48h-max-epoch-cadence",
            "status": "actual",
            "msg_type": "new",
            "human_review": "none",
            "us_person_data": "none",
            "status_class": "reported",
            "product_category": "current",
            "data_as_of": hf["last_epoch"],
            "published_at": generated,
            "valid_until": valid_until,
            "countries": [hf["country"]],
            "pmesii_pt": ["military"],
            "ascope": ["capabilities"],
            "ie_aspect": ["informational"],
            "ncf": ["provide_satellite_access"],
            "requirement_ids": ["OR-EEI-2"],
            "indicator_id": "OR-IND-4",
            "hypothesis_id": "OR-H-1C",
            "direction": "supports",
            "indicator_state": "present",
            "method_version": METHOD,
            "coverage_fraction": 0.45,
            "precision_class": "point",
            "measures": {"tle_gap_hours": hf["max_tle_gap_hours"]},
            "visual": {"type": "table", "url": f"{SITE}/#{hf['jcat']}"},
            "sources": [{**SRC_CELESTRAK, "accessed_at": generated}],
        }
        geom = {"type": "Point", "coordinates": [hf["subpoint_lon"], hf["subpoint_lat"]]}
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    return {
        "type": "FeatureCollection",
        "contract": CONTRACT,
        "program": "orbit",
        "generated_at": generated,
        "licence": "CC BY 4.0 (GCAT); Public orbital element data (CelesTrak / 18 SDS); Orbit code MIT",
        "attribution": "Orbit, The Intelligence Company (GCAT, CelesTrak / 18 SDS)",
        "language_key": LANGUAGE_KEY,
        "features": features,
    }
