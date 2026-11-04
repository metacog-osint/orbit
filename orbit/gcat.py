"""GCAT catalog snapshot parser, owner-code hygiene, unnumbered object tracker, and launch-sibling grouping."""
from __future__ import annotations

OWNER_COUNTRY_MAP = {
    "US": "US",
    "RU": "RU",
    "SU": "RU",  # Historical Soviet Union tracked separately in owner_clean="SU", mapped to ISO "RU" only for GeoJSON country array when needed
    "CN": "CN",
    "PRC": "CN",
    "FR": "FR",
    "JP": "JP",
    "IN": "IN",
    "IL": "IL",
    "IR": "IR",
    "KP": "KP",
    "UK": "GB",
    "GB": "GB",
    "DE": "DE",
}


def normalize_gcat_catalog(records: list[dict]) -> dict:
    """Apply GCAT owner-code hygiene, detect unnumbered active objects, flag duplicate NORAD claims, and group launch siblings."""
    by_norad: dict[str, list[dict]] = {}
    by_launch: dict[str, list[str]] = {}
    unnumbered_active = []
    soviet_count = 0
    russian_count = 0
    normalized = []

    for rec in records:
        jcat = rec.get("jcat") or rec.get("id") or "S00000"
        norad = str(rec["norad"]).strip() if rec.get("norad") not in (None, "", "-") else None
        raw_celestrak_owner = (rec.get("celestrak_owner") or "CIS").upper()
        gcat_state = (rec.get("gcat_state") or rec.get("owner") or raw_celestrak_owner).upper()

        # Owner-code hygiene: never leave 'CIS' undifferentiated when GCAT provides SU vs RU
        if gcat_state == "SU":
            soviet_count += 1
            owner_clean = "SU"
            iso_cc = "RU"
        elif gcat_state in ("RU", "RUS"):
            russian_count += 1
            owner_clean = "RU"
            iso_cc = "RU"
        else:
            owner_clean = gcat_state
            iso_cc = OWNER_COUNTRY_MAP.get(gcat_state, "US" if len(gcat_state) != 2 else gcat_state)

        status = (rec.get("status") or "O").upper()
        is_active = status in ("O", "AO", "ACTIVE", "IN ORBIT")
        launch_desig = rec.get("launch_designator") or (rec.get("piece") or "")[:8]
        if launch_desig:
            by_launch.setdefault(launch_desig, []).append(jcat)
        if norad:
            by_norad.setdefault(norad, []).append(jcat)
        elif is_active:
            unnumbered_active.append({
                "jcat": jcat,
                "name": rec.get("name") or jcat,
                "owner": owner_clean,
                "country": iso_cc,
                "orbit_class": rec.get("orbit_class") or "LEO",
                "launch_date": rec.get("launch_date") or "2026-10-15",
            })

        item = {
            "jcat": jcat,
            "norad": norad,
            "name": rec.get("name") or jcat,
            "celestrak_owner": raw_celestrak_owner,
            "owner_clean": owner_clean,
            "country": iso_cc,
            "orbit_class": rec.get("orbit_class") or "LEO",
            "launch_designator": launch_desig,
            "launch_date": rec.get("launch_date") or "2026-01-01",
            "is_active": is_active,
            "is_subsatellite_deployment": bool(rec.get("is_subsatellite_deployment", False)),
            "parent_object": rec.get("parent_object"),
            "subpoint_lat": float(rec.get("subpoint_lat", 0.0)),
            "subpoint_lon": float(rec.get("subpoint_lon", 0.0)),
        }
        normalized.append(item)

    duplicate_norads = {n: jcats for n, jcats in by_norad.items() if len(jcats) > 1}
    siblings_by_launch = {ld: jcats for ld, jcats in by_launch.items() if len(jcats) > 1}

    for item in normalized:
        ld = item["launch_designator"]
        sibs = [j for j in siblings_by_launch.get(ld, []) if j != item["jcat"]]
        item["siblings"] = sibs
        item["has_duplicate_norad"] = bool(item["norad"] and item["norad"] in duplicate_norads)

    return {
        "objects": normalized,
        "hygiene_summary": {
            "total_watched": len(normalized),
            "soviet_su_separated": soviet_count,
            "russian_ru_separated": russian_count,
            "unnumbered_active_count": len(unnumbered_active),
            "duplicate_norad_claims": duplicate_norads,
            "multi_sibling_launches": siblings_by_launch,
        },
        "unnumbered_active": unnumbered_active,
    }
