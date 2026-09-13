"""Generate the deck's figures as SVG, straight from the committed dataset.

Screenshots of the app would be simpler, but they are raster: soft on a
projector, heavy in the repo, and impossible to annotate afterwards. These are
drawn from `data/processed/`, so a figure on a slide cannot drift away from the
numbers the product actually renders -- rebuild them and any change shows up.

    uv run python docs/deck/build_figures.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"
HERE = Path(__file__).resolve().parent
OUT = HERE / "img"
COASTLINE = HERE / "coastline.geojson"

# The app's own tokens, so the deck and the product read as one thing.
C = {
    "bg": "#0d1117",
    "surface": "#151b23",
    "border": "#2a3441",
    "border_strong": "#3a4654",
    "text": "#e6edf3",
    "dim": "#9aa7b4",
    "faint": "#6b7785",
    "accent": "#d4a05a",
    "coast": "#31404f",
    "PROTECT": "#3fb98a",
    "HOLD": "#d9a838",
    "SHRINK": "#e05c5c",
}
# Single quotes inside the stack: these land in double-quoted XML attributes,
# and a standalone .svg is parsed strictly.
MONO = "ui-monospace,'SF Mono',Menlo,monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,system-ui,sans-serif"


def extract_coastline(pbf: Path, bbox: tuple[float, float, float, float]) -> None:
    """Rebuild `coastline.geojson` from the Geofabrik extract. Run rarely.

    Floating circles on a black background do not read as a place. The
    coastline is the cheapest thing that turns them into Abu Dhabi -- and it is
    also the only basemap that survives the constraints this deck has: it must
    open with no network, so map tiles are out.

    The extract itself is gitignored (241 MB), so the simplified output is
    committed instead -- the same trade the pipeline makes for
    `zone_activity_counts.json`.

        uv run python docs/deck/build_figures.py --coastline
    """
    import osmium
    from shapely.geometry import LineString, box

    w, s_, e, n = bbox
    ways: dict[int, list[int]] = {}
    needed: set[int] = set()
    for obj in osmium.FileProcessor(pbf).with_filter(osmium.filter.KeyFilter("natural")):
        if obj.type_str() != "w" or obj.tags.get("natural") != "coastline":
            continue
        refs = [node.ref for node in obj.nodes]
        if len(refs) > 1:
            ways[obj.id] = refs
            needed.update(refs)
    print(f"    pass 1: {len(ways)} coastline ways, {len(needed)} nodes to resolve")

    # Ways carry no coordinates, so a second pass resolves just these nodes --
    # the same two-pass shape as pipeline/sourcing/extract.py, and for the same
    # reason: indexing all ~30M nodes would not fit in memory.
    loc: dict[int, tuple[float, float]] = {}
    node_only = osmium.filter.EntityFilter(osmium.osm.NODE)
    for obj in osmium.FileProcessor(pbf).with_filter(node_only):
        if obj.id in needed:
            loc[obj.id] = (obj.location.lon, obj.location.lat)

    clip = box(w, s_, e, n)
    feats = []
    for refs in ways.values():
        pts = [loc[r] for r in refs if r in loc]
        if len(pts) < 2:
            continue
        line = LineString(pts)
        if not line.intersects(clip):
            continue
        piece = line.intersection(clip)
        for geom in getattr(piece, "geoms", [piece]):
            # ~150 m tolerance and a ~1 km floor: at 60 km across a figure, finer
            # detail is invisible and a scatter of specks reads as noise.
            simp = geom.simplify(0.0014, preserve_topology=False)
            if geom.geom_type != "LineString" or len(simp.coords) < 2 or simp.length < 0.009:
                continue
            feats.append(
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[round(x, 4), round(y, 4)] for x, y in simp.coords],
                    },
                }
            )
    COASTLINE.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"    wrote {COASTLINE} ({len(feats)} lines, {COASTLINE.stat().st_size / 1024:.0f} KB)")


def load(name: str):
    return json.loads((DATA / name).read_text())


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------- the matrix
def matrix_svg() -> str:
    """The decision matrix, laid out exactly as web/src/components/Matrix.tsx.

    Same domain padding and the same sqrt area scale, so the slide and the
    Compare tab put every lounge in the same place.
    """
    branches = load("branches.json")
    th = load("model_card.json")["branch_model"]["thresholds"]

    W, H = 900, 520
    PAD = {"t": 26, "r": 30, "b": 62, "l": 78}

    def domain(values, thresholds):
        allv = list(values) + list(thresholds)
        lo, hi = min(allv), max(allv)
        margin = max((hi - lo) * 0.12, 0.02)
        return lo - margin, hi + margin

    x0, x1 = domain(
        [b["strength"]["score"] for b in branches], [th["strength_low"], th["strength_high"]]
    )
    y0, y1 = domain([b["market"]["score"] for b in branches], [th["market_low"], th["market_high"]])
    pw, ph = W - PAD["l"] - PAD["r"], H - PAD["t"] - PAD["b"]

    def X(v):
        return PAD["l"] + (v - x0) / (x1 - x0) * pw

    def Y(v):
        # SVG y grows downward, so a high market score maps to a small y.
        return PAD["t"] + (1 - (v - y0) / (y1 - y0)) * ph

    max_rev = max(b["review_count"] for b in branches)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">']
    p.append(f'<rect width="{W}" height="{H}" fill="{C["bg"]}"/>')

    # Quadrants: the PROTECT corner, and the strip that is SHRINK on strength.
    p.append(
        f'<rect x="{X(th["strength_high"]):.1f}" y="{PAD["t"]}" '
        f'width="{W - PAD["r"] - X(th["strength_high"]):.1f}" '
        f'height="{Y(th["market_high"]) - PAD["t"]:.1f}" fill="{C["PROTECT"]}" opacity=".07"/>'
    )
    p.append(
        f'<rect x="{PAD["l"]}" y="{PAD["t"]}" width="{X(th["strength_low"]) - PAD["l"]:.1f}" '
        f'height="{ph}" fill="{C["SHRINK"]}" opacity=".07"/>'
    )

    for v in (th["strength_low"], th["strength_high"]):
        p.append(
            f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{PAD["t"]}" y2="{H - PAD["b"]}" '
            f'stroke="{C["border_strong"]}" stroke-dasharray="4 3"/>'
        )
        p.append(
            f'<text x="{X(v):.1f}" y="{H - PAD["b"] + 20}" fill="{C["faint"]}" '
            f'font-family="{MONO}" font-size="14" text-anchor="middle">{v}</text>'
        )
    for v in (th["market_low"], th["market_high"]):
        p.append(
            f'<line x1="{PAD["l"]}" x2="{W - PAD["r"]}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" '
            f'stroke="{C["border_strong"]}" stroke-dasharray="4 3"/>'
        )
        p.append(
            f'<text x="{PAD["l"] - 12}" y="{Y(v) + 5:.1f}" fill="{C["faint"]}" '
            f'font-family="{MONO}" font-size="14" text-anchor="end">{v}</text>'
        )

    p.append(
        f'<line x1="{PAD["l"]}" x2="{W - PAD["r"]}" y1="{H - PAD["b"]}" y2="{H - PAD["b"]}" '
        f'stroke="{C["border_strong"]}"/>'
    )
    p.append(
        f'<line x1="{PAD["l"]}" x2="{PAD["l"]}" y1="{PAD["t"]}" y2="{H - PAD["b"]}" '
        f'stroke="{C["border_strong"]}"/>'
    )
    p.append(
        f'<text x="{W / 2}" y="{H - 14}" fill="{C["dim"]}" font-family="{SANS}" '
        f'font-size="17" text-anchor="middle">Branch strength →</text>'
    )
    p.append(
        f'<text transform="translate(24,{H / 2}) rotate(-90)" fill="{C["dim"]}" '
        f'font-family="{SANS}" font-size="17" text-anchor="middle">'
        f"Market &amp; defensibility →</text>"
    )

    p.append(
        f'<text x="{W - PAD["r"] - 10}" y="{PAD["t"] + 22}" fill="{C["PROTECT"]}" '
        f'font-family="{MONO}" font-size="14" text-anchor="end" opacity=".85">PROTECT</text>'
    )
    p.append(
        f'<text x="{PAD["l"] + 10}" y="{PAD["t"] + 22}" fill="{C["SHRINK"]}" '
        f'font-family="{MONO}" font-size="14" opacity=".85">SHRINK</text>'
    )

    hero = next(b for b in branches if b["area"] == "Ministry Area")
    # Largest first, so a small lounge is never buried under a big one.
    for b in sorted(branches, key=lambda b: -b["review_count"]):
        r = 6 + 13 * math.sqrt(b["review_count"] / max_rev)
        is_hero = b is hero
        edge = "#fff" if is_hero else C["bg"]
        p.append(
            f'<circle cx="{X(b["strength"]["score"]):.1f}" cy="{Y(b["market"]["score"]):.1f}" '
            f'r="{r:.1f}" fill="{C[b["recommendation"]]}" stroke="{edge}" '
            f'stroke-width="{3 if is_hero else 1.5}" opacity="{1 if is_hero else 0.9}"/>'
        )

    # The callout sits to the right: this lounge is near the bottom of the
    # chart, and anything below it would collide with the axis labels.
    hx, hy = X(hero["strength"]["score"]), Y(hero["market"]["score"])
    hr = 6 + 13 * math.sqrt(hero["review_count"] / max_rev)
    lx = hx + hr + 14
    p.append(
        f'<text x="{lx:.1f}" y="{hy - 2:.1f}" fill="{C["accent"]}" font-family="{SANS}" '
        f'font-size="20" font-weight="600">Ministry Area</text>'
    )
    p.append(
        f'<text x="{lx:.1f}" y="{hy + 20:.1f}" fill="{C["dim"]}" font-family="{MONO}" '
        f'font-size="15">5th of 23 · SHRINK</text>'
    )

    p.append("</svg>")
    return "\n".join(p)


# -------------------------------------------------------------- the overlap
def overlap_svg() -> str:
    """Abu Dhabi's catchments, and the ground we cover twice.

    Drawn from the same polygons the map renders, in a locally-flat planar
    frame -- at this latitude and scale the distortion is well under a pixel.
    """
    branches = {b["branch_id"]: b for b in load("branches.json")}
    catch = load("catchments.geojson")["features"]
    overlaps = load("overlaps.geojson")["features"]

    # The emirate of Abu Dhabi reaches Al Ain, 130 km inland. Including it would
    # shrink the city cluster -- the thing the figure exists to show -- to a
    # smudge, so this is the metro, not the emirate.
    emirate = [b for b in branches.values() if b["emirate"] == "Abu Dhabi"]
    mid_lon = sorted(b["lon"] for b in emirate)[len(emirate) // 2]
    mid_lat = sorted(b["lat"] for b in emirate)[len(emirate) // 2]
    ad = {
        b["branch_id"]
        for b in emirate
        if math.hypot((b["lon"] - mid_lon) * math.cos(math.radians(mid_lat)), b["lat"] - mid_lat)
        * 111
        < 40
    }
    cats = [f for f in catch if f["properties"]["branch_id"] in ad]
    ovs = [
        f
        for f in overlaps
        if f["properties"]["branch_a"] in ad and f["properties"]["branch_b"] in ad
    ]

    pts = [pt for f in cats for pt in f["geometry"]["coordinates"][0]]
    lon0 = sum(p[0] for p in pts) / len(pts)
    lat0 = sum(p[1] for p in pts) / len(pts)
    k = math.cos(math.radians(lat0))

    W, H = 900, 520
    M = 46
    TOP = 104  # room for the headline block above the map
    xs = [(p[0] - lon0) * k for p in pts]
    ys = [(p[1] - lat0) for p in pts]
    # Leave a margin wide enough for the two callout labels to sit outside the
    # catchments they point at.
    s = min((W - 2 * M - 150) / (max(xs) - min(xs)), (H - TOP - M) / (max(ys) - min(ys)))
    cx_off = W / 2 - (max(xs) + min(xs)) / 2 * s
    cy_off = (TOP + H - M) / 2 + (max(ys) + min(ys)) / 2 * s

    def P(lon, lat):
        return (cx_off + (lon - lon0) * k * s, cy_off - (lat - lat0) * s)

    def path(ring):
        d = "".join(
            ("M" if i == 0 else "L") + f"{P(*c)[0]:.1f},{P(*c)[1]:.1f}" for i, c in enumerate(ring)
        )
        return d + "Z"

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">']
    p.append(f'<rect width="{W}" height="{H}" fill="{C["bg"]}"/>')

    # The coast, underneath everything. Without it the catchments are circles
    # floating in the dark; with it they are Abu Dhabi.
    if COASTLINE.exists():
        p.append(
            f'<clipPath id="plot"><rect x="0" y="{TOP - 26}" width="{W}" '
            f'height="{H - TOP + 26}"/></clipPath>'
        )
        p.append('<g clip-path="url(#plot)">')
        for f in json.loads(COASTLINE.read_text())["features"]:
            coords = f["geometry"]["coordinates"]
            d = "".join(
                ("M" if i == 0 else "L") + f"{P(*c)[0]:.1f},{P(*c)[1]:.1f}"
                for i, c in enumerate(coords)
            )
            p.append(f'<path d="{d}" fill="none" stroke="{C["coast"]}" stroke-width="1.1"/>')
        p.append("</g>")

    for f in cats:
        rec = f["properties"]["recommendation"]
        p.append(
            f'<path d="{path(f["geometry"]["coordinates"][0])}" fill="{C[rec]}" '
            f'fill-opacity=".05" stroke="{C[rec]}" stroke-opacity=".45" '
            f'stroke-dasharray="5 4" stroke-width="1.3"/>'
        )

    hero_id = "BD16~BD23"
    hero = next(f["properties"] for f in ovs if f["properties"]["pair_id"] == hero_id)
    hero_share_a, hero_share_b = hero["share_of_a"], hero["share_of_b"]
    for f in ovs:
        is_hero = f["properties"]["pair_id"] == hero_id
        p.append(
            f'<path d="{path(f["geometry"]["coordinates"][0])}" fill="{C["SHRINK"]}" '
            f'fill-opacity="{0.42 if is_hero else 0.14}" '
            f'stroke="{C["SHRINK"] if is_hero else "none"}" '
            f'stroke-opacity=".8" stroke-width="{1.6 if is_hero else 0}"/>'
        )

    for f in cats:
        b = branches[f["properties"]["branch_id"]]
        x, y = P(b["lon"], b["lat"])
        p.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{C[b["recommendation"]]}" '
            f'stroke="{C["bg"]}" stroke-width="1.5"/>'
        )

    # Each callout points directly away from the other one, so the two labels
    # can never stack on top of each other.
    pa, pb = (
        P(branches["BD16"]["lon"], branches["BD16"]["lat"]),
        P(branches["BD23"]["lon"], branches["BD23"]["lat"]),
    )
    for bid, share, away in (("BD16", hero_share_a, pb), ("BD23", hero_share_b, pa)):
        b = branches[bid]
        x, y = P(b["lon"], b["lat"])
        dx, dy = x - away[0], y - away[1]
        n = math.hypot(dx, dy) or 1
        lx, ly = x + dx / n * 120, y + dy / n * 120
        anchor = "start" if dx >= 0 else "end"
        p.append(
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{lx:.1f}" y2="{ly:.1f}" '
            f'stroke="{C["border_strong"]}" stroke-width="1.2"/>'
        )
        p.append(
            f'<text x="{lx + (8 if dx >= 0 else -8):.1f}" y="{ly:.1f}" fill="{C["text"]}" '
            f'font-family="{SANS}" font-size="19" font-weight="600" '
            f'text-anchor="{anchor}">{esc(b["area"])}</text>'
        )
        p.append(
            f'<text x="{lx + (8 if dx >= 0 else -8):.1f}" y="{ly + 22:.1f}" '
            f'fill="{C["SHRINK"] if share > 0.3 else C["dim"]}" font-family="{MONO}" '
            f'font-size="17" text-anchor="{anchor}">gives up {share * 100:.0f}%</text>'
        )

    p.append(
        f'<text x="{M}" y="{M + 2}" fill="{C["accent"]}" font-family="{MONO}" font-size="16" '
        f'letter-spacing="1.5">ABU DHABI · {len(cats)} LOUNGES</text>'
    )
    p.append(
        f'<text x="{M}" y="{M + 36}" fill="{C["text"]}" font-family="{SANS}" font-size="28" '
        f'font-weight="600">{hero["overlap_area_km2"]:.1f} km² covered twice</text>'
    )
    p.append(
        f'<text x="{W - M}" y="{M + 36}" fill="{C["dim"]}" font-family="{SANS}" font-size="18" '
        f'text-anchor="end">{hero["centroid_distance_m"] / 1000:.1f} km apart</text>'
    )

    p.append("</svg>")
    return "\n".join(p)


def inject(deck: Path, figures: dict[str, str]) -> None:
    """Paste each figure into the deck between its markers.

    The deck is one self-contained file on purpose -- it has to open from a USB
    stick in a room with no wifi -- so the SVGs live inline rather than as
    <img> references. Writing them in from here keeps that inline copy from
    drifting away from the data it was generated from.
    """
    html = deck.read_text()
    for name, svg in figures.items():
        open_tag, close_tag = f"<!--FIG:{name}-->", f"<!--/FIG:{name}-->"
        start, end = html.index(open_tag) + len(open_tag), html.index(close_tag)
        # Drop the standalone width/height so the figure scales to its slot.
        body = svg.replace(' width="900" height="520"', "", 1)
        html = html[:start] + "\n" + body + "\n" + html[end:]
    deck.write_text(html)
    print(f"injected {len(figures)} figures into {deck}")


def main() -> None:
    if "--coastline" in sys.argv:
        from pipeline.sourcing.extract import EXTRACT_PATH

        # Padded well past the catchments so the coast runs off the figure
        # rather than stopping in mid-air at the edge.
        extract_coastline(EXTRACT_PATH, (54.18, 24.17, 54.96, 24.74))

    OUT.mkdir(parents=True, exist_ok=True)
    figures = {"matrix": matrix_svg(), "overlap": overlap_svg()}
    for name, svg in figures.items():
        (OUT / f"{name}.svg").write_text(svg)
        print(f"wrote {OUT / name}.svg ({len(svg):,} bytes)")
    inject(Path(__file__).resolve().parent / "index.html", figures)


if __name__ == "__main__":
    main()
