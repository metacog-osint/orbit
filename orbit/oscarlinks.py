"""TIC's hand-reviewed WMO OSCAR/Space link file, `orbit/data/catalog/oscar-links.yml` (18 Nov 2026).

17 Nov 2026: OSCAR carries no NORAD number and no COSPAR ID, so it joins the catalog only through a
hand-reviewed slug-to-NORAD file, each entry with its evidence, reviewed by diff; a script may propose candidates;
nothing joins until a person has reviewed the entry. The 414 operational satellites first.

One entry per OSCAR satellite (its `slug`, which OSCAR's API and page URLs use):
  - `norad`: the one object it is, or `members`: the objects of an OSCAR entry that stands for several (CYGNSS's
    eight, MMS's four);
  - `relation`: `same` (the satellite itself) or `hosted` (an instrument or payload on another object: ISS
    instruments on 25544, TEMPO on Intelsat 40e);
  - `proposal`: how the entry was found: `single-fit` (the only payload whose launch date and orbit fit OSCAR's),
    `one-of-n` (several fit; chosen by the evidence lines, a name among them), `by-hand`;
  - `oscar_id`, `read` (the OSCAR read the evidence comes from), `evidence` (a list), `proposed_by`, `proposed`;
  - `reviewed_by` and `reviewed`: set only by the person who reviewed the entry. **Only reviewed entries join.**
An entry is never edited to change its number: a wrong one gets `withdrawn: <date>` and `reason` and stays.

The file uses the alias file's YAML subset (orbit/aliases.py parse).
"""
from __future__ import annotations

import re
from pathlib import Path

from .aliases import AliasError, _check_date, parse

PATH = Path(__file__).resolve().parent / "data" / "catalog" / "oscar-links.yml"
KEYS = {"slug", "norad", "members", "relation", "proposal", "oscar_id", "acronym", "read", "evidence",
        "proposed_by", "proposed", "reviewed_by", "reviewed", "withdrawn", "reason", "note"}
NEED = ("slug", "relation", "proposal", "read", "evidence", "proposed_by", "proposed")
RELATIONS = ("same", "hosted")
PROPOSALS = ("single-fit", "one-of-n", "by-hand")


class LinkError(AliasError):
    pass


def validate(entries: list[dict]) -> list[dict]:
    """Checks every entry and returns the live ones (withdrawn left out), reviewed or not. Raises LinkError on the
    first problem, naming the entry's line."""
    live, slugs, numbers = [], {}, {}
    for e in entries:
        where = f"oscar-links.yml line {e.get('line')}"
        extra = set(e) - KEYS - {"line"}
        if extra:
            raise LinkError(f"{where}: unknown keys {sorted(extra)}")
        missing = [k for k in NEED if k not in e]
        if missing:
            raise LinkError(f"{where}: missing {missing}")
        if not (isinstance(e["slug"], str) and re.fullmatch(r"[A-Za-z0-9_\-]+", e["slug"])):
            raise LinkError(f"{where}: slug must be OSCAR's slug")
        if ("norad" in e) == ("members" in e):
            raise LinkError(f"{where}: give exactly one of norad or members")
        nums = [e["norad"]] if "norad" in e else e["members"]
        if not (isinstance(nums, list) and nums and all(isinstance(x, int) and x > 0 for x in nums)):
            raise LinkError(f"{where}: norad and members must be NORAD numbers")
        if "members" in e and len(set(nums)) != len(nums):
            raise LinkError(f"{where}: a member is listed twice")
        if e["relation"] not in RELATIONS:
            raise LinkError(f"{where}: relation must be one of {RELATIONS}")
        if e["proposal"] not in PROPOSALS:
            raise LinkError(f"{where}: proposal must be one of {PROPOSALS}")
        ev = e["evidence"]
        if not (isinstance(ev, list) and ev and all(isinstance(x, str) and x.strip() for x in ev)):
            raise LinkError(f"{where}: evidence must be a list of at least one statement")
        for k in ("read", "proposed", "reviewed", "withdrawn"):
            try:
                _check_date(e, k, where)
            except AliasError as exc:
                raise LinkError(str(exc)) from None
        if ("reviewed" in e) != ("reviewed_by" in e):
            raise LinkError(f"{where}: reviewed and reviewed_by go together")
        if "reviewed_by" in e and not (isinstance(e["reviewed_by"], str) and e["reviewed_by"].strip()):
            raise LinkError(f"{where}: reviewed_by must name the person")
        if "withdrawn" in e:
            if not e.get("reason"):
                raise LinkError(f"{where}: a withdrawn entry needs a reason")
            continue
        if e["slug"] in slugs:
            raise LinkError(f"{where}: slug {e['slug']} already linked at line {slugs[e['slug']]}")
        slugs[e["slug"]] = e.get("line")
        if e["relation"] == "same":
            for n in nums:
                if n in numbers:
                    raise LinkError(f"{where}: {n} is already the satellite of line {numbers[n]}")
                numbers[n] = e.get("line")
        live.append(e)
    return live


def load(path: Path | str | None = None) -> list[dict]:
    p = Path(path) if path else PATH
    if not p.exists():
        return []
    return validate(parse(p.read_text(encoding="utf-8")))


def reviewed(entries: list[dict]) -> list[dict]:
    """The entries that may join: reviewed by a person."""
    return [e for e in entries if e.get("reviewed_by")]


def numbers(e: dict) -> list[int]:
    return [e["norad"]] if "norad" in e else list(e["members"])


# --- writing proposals ---------------------------------------------------------------------------------------------

def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def entry_text(slug: str, nums: list[int], relation: str, proposal: str, oscar_id, acronym: str, read: str,
               evidence: list[str], proposed: str, proposed_by: str = "oscar-propose") -> str:
    """One unreviewed entry in the file's YAML subset."""
    lines = [f"- slug: {slug}"]
    lines.append(f"  norad: {nums[0]}" if len(nums) == 1 else f"  members: [{', '.join(map(str, nums))}]")
    lines += [f"  relation: {relation}", f"  proposal: {proposal}"]
    if oscar_id is not None:
        lines.append(f"  oscar_id: {oscar_id}")
    lines.append(f"  acronym: {_q(acronym)}")
    lines.append(f"  read: {read}")
    lines.append("  evidence:")
    lines += [f"    - {_q(x)}" for x in evidence]
    lines += [f"  proposed_by: {proposed_by}", f"  proposed: {proposed}"]
    return "\n".join(lines) + "\n"
