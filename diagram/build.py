#!/usr/bin/env python3
"""Render the homelab diagram from inventory.yaml.

Usage: python3 build.py [--inventory FILE] → out/homelab.svg + out/homelab.png
Content comes from inventory.yaml; the layout (positions of every box and line) is
hand-placed in this file. Line width encodes link speed (SPEED_W); trunks are drawn
as a light cable with a dark core. Based on Goblinmine/homelab-diagram (MIT).
"""
import base64
import html
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
if "--inventory" in sys.argv:
    _i = sys.argv.index("--inventory") + 1
    if _i >= len(sys.argv) or sys.argv[_i].startswith("--"):
        raise SystemExit("--inventory needs a file")
    INV_FILE = pathlib.Path(sys.argv[_i])
else:
    INV_FILE = ROOT / "inventory.yaml"
INV = yaml.safe_load(INV_FILE.read_text())
ICONS = ROOT / "icons"
OUT = ROOT / "out"

UNREDACTED = not INV["redact"]["domain"]
RED = INV["redact"]
DOMAIN = INV["meta"]["domain"]
SHOWN_DOMAIN = DOMAIN if (UNREDACTED or not RED["domain"]) else RED["domain_placeholder"]

W, H = 2400, 0      # H is set at the end from the content (see "canvas height")

# ---------------------------------------------------------------- palette
BG = "#0b0f15"
GRID = "#151c26"
PANEL = "#111821"
PANEL2 = "#161f2b"
CHIP = "#19222e"
BORDER = "#253042"
TEXT = "#e6edf3"
MUTED = "#8d9aab"
FAINT = "#5d6a7c"
TRUNK = "#d5dde6"
TRUNK_BORDER = "#3a475a"   # border for devices on a tagged trunk (not in a single VLAN)
LINK = "#79c0ff"
DISK = "#1d2734"
DISK_EDGE = "#5a6b82"
PROTO = {"TCP": "#79c0ff", "UDP": "#39c5cf"}
UNKNOWN = "#6b7a90"   # a used port whose VLANs aren't known
SPEED_W = {"10G": 9.5, "2.5G": 3.8, "1G": 2.4, "100M": 1.4}   # access-line widths
VLAN = {v["key"]: v for v in INV["vlans"]}
C = {k: v["color"] for k, v in VLAN.items()}
SANS = "Fira Sans"
MONO = "Fira Code"


def trunk_w(speed):
    return SPEED_W[speed] + 3.4


def sub(s):
    """Fill {domain} placeholders and apply redaction."""
    s = str(s).replace("{domain}", SHOWN_DOMAIN)
    if not UNREDACTED and RED["domain"]:
        s = s.replace(DOMAIN, SHOWN_DOMAIN)
    return s


def esc(s):
    return html.escape(sub(s), quote=True)


def tw(s, size, mono=False):
    """Rough text width for layout decisions."""
    return len(sub(s)) * size * (0.6 if mono else 0.53)


def _font_file(pattern):
    """Path of an installed font via fontconfig (fc-match), or None."""
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


try:
    from PIL import ImageFont
    _FONTS = {700: _font_file("Fira Sans:bold"), 600: _font_file("Fira Sans:semibold"),
              400: _font_file("Fira Sans:regular")}
    if not all(_FONTS.values()):
        raise RuntimeError("Fira Sans not found")
    _FCACHE = {}

    def measure(s, size, weight=700):
        key = (weight, size)
        if key not in _FCACHE:
            _FCACHE[key] = ImageFont.truetype(_FONTS[weight], size=size * 8)
        return _FCACHE[key].getlength(s) / 8
except Exception:          # no Pillow / font file: rough estimate
    def measure(s, size, weight=700):
        return tw_title(s, size)


def tw_title(s, size):
    """Width estimate for bold title text (capitals are wider than lowercase)."""
    return sum(0.68 if c.isupper() else 0.58 if c.isdigit() else 0.5 for c in s) * size


def fqdn(h):
    return f"{h}.{SHOWN_DOMAIN}"


class SVG:
    def __init__(self):
        self.p = []
        self._icon_cache = {}

    def add(self, s):
        self.p.append(s)

    def rect(self, x, y, w, h, rx=10, fill=PANEL, stroke=BORDER, sw=1.2, op=1, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{op}"{d}/>')

    def text(self, x, y, s, size=14, fill=TEXT, weight=400, anchor="start", mono=False, ls=0, op=1):
        fam = MONO if mono else SANS
        lsa = f' letter-spacing="{ls}"' if ls else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-size="{size}" fill="{fill}" '
                 f'font-weight="{weight}" text-anchor="{anchor}" opacity="{op}"{lsa}>{esc(s)}</text>')

    def icon(self, name, x, y, size):
        if name not in self._icon_cache:
            f = ICONS / f"{name}.svg"
            if not f.exists():
                raise SystemExit(f"missing icon '{name}' – run: python3 fetch_icons.py")
            self._icon_cache[name] = base64.b64encode(f.read_bytes()).decode()
        self.add(f'<image x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" '
                 f'href="data:image/svg+xml;base64,{self._icon_cache[name]}"/>')

    def line(self, pts, color, sw=3, dash=None, r=10, op=1, cap="round"):
        self.add(f'<path d="{rounded(pts, r)}" fill="none" stroke="{color}" stroke-width="{sw}" '
                 f'stroke-linecap="{cap}" stroke-linejoin="round" opacity="{op}"'
                 + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")

    def trunk(self, pts, r=12, sw=7):
        """Tagged trunk: light cable with a dark core."""
        self.line(pts, TRUNK, sw=sw, r=r)
        self.line(pts, BG, sw=sw - 4.4, r=r)

    def arrow(self, pts, color=MUTED, sw=1.8, dash=None, r=8):
        """Line with an arrowhead at the last point."""
        self.line(pts, color, sw, dash=dash, r=r)
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        ln = max(abs(dx), abs(dy)) or 1
        ux, uy = dx / ln, dy / ln
        a, b = 8, 4.5
        p1 = (x1 - ux * a - uy * b, y1 - uy * a + ux * b)
        p2 = (x1 - ux * a + uy * b, y1 - uy * a - ux * b)
        self.add(f'<path d="M{x1},{y1} L{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f} Z" fill="{color}"/>')

    def pill(self, x, y, s, color, size=12, fill=None, mono=False, anchor="start", h=None, pad=8, tcolor=None, weight=600):
        w = tw(s, size, mono) + pad * 2
        h = h or size + 10
        if anchor == "middle":
            x -= w / 2
        elif anchor == "end":
            x -= w
        self.rect(x, y, w, h, rx=h / 2, fill=fill or color + "22", stroke=color + "88", sw=1)
        self.text(x + w / 2, y + h / 2 + size * 0.36, s, size, tcolor or color, weight, "middle", mono)
        return w

    def label(self, x, y, s, color=MUTED, size=12, anchor="middle", mono=False, bg=BG):
        """Text on a line, with a background knock-out."""
        w = tw(s, size, mono) + 12
        bx = x - w / 2 if anchor == "middle" else (x if anchor == "start" else x - w)
        self.rect(bx, y - size - 2, w, size + 9, rx=5, fill=bg, stroke=bg, sw=0)
        self.text(bx + w / 2, y + 1, s, size, color, 500, "middle", mono)

    def render(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                + "".join(self.p) + "</svg>")


def rounded(pts, r):
    """Orthogonal polyline with rounded corners."""
    if len(pts) == 2:
        return f"M{pts[0][0]},{pts[0][1]} L{pts[1][0]},{pts[1][1]}"
    d = f"M{pts[0][0]},{pts[0][1]}"
    for i in range(1, len(pts) - 1):
        (x0, y0), (x1, y1), (x2, y2) = pts[i - 1], pts[i], pts[i + 1]
        l1 = max(abs(x1 - x0), abs(y1 - y0))
        l2 = max(abs(x2 - x1), abs(y2 - y1))
        rr = min(r, l1 / 2, l2 / 2)
        ax = x1 - (x1 - x0) / l1 * rr if l1 else x1
        ay = y1 - (y1 - y0) / l1 * rr if l1 else y1
        bx = x1 + (x2 - x1) / l2 * rr if l2 else x1
        by = y1 + (y2 - y1) / l2 * rr if l2 else y1
        d += f" L{ax:.1f},{ay:.1f} Q{x1},{y1} {bx:.1f},{by:.1f}"
    d += f" L{pts[-1][0]},{pts[-1][1]}"
    return d


S = SVG()


# ---------------------------------------------------------------- shared pieces
def hostname(g):
    """(text, color) for the text after the IP on a card's address line."""
    if g.get("host"):
        return fqdn(g["host"]), LINK
    if g.get("internal"):
        return g["internal"], None
    return None, None


def addr(x, y, ip, g, color, size=12):
    """Address line under a card's name (like the switch): IP · hostname, in the VLAN color
    (a public Traefik hostname is blue)."""
    S.text(x, y, ip, size, color, 500, mono=True)
    name, ncol = hostname(g)
    if name:
        cw_ = size * 0.6                      # Fira Code advance width
        dx = x + len(ip) * cw_ + cw_ * 0.6
        S.text(dx, y, "·", size, MUTED, 400, mono=True)
        S.text(dx + cw_ * 1.6, y, name, size, ncol or color, 400, mono=True, op=1 if ncol else 0.85)


def card(x, y, w, h, color=None, title=None, icons=None, sub_=None, isz=34, tsize=19):
    """Panel with a colored left accent, icons, title and subtitle."""
    S.rect(x, y, w, h, rx=14, fill=PANEL, stroke=(color + "aa") if color else BORDER, sw=1.6)
    if color:
        S.add(f'<rect x="{x+1}" y="{y+14}" width="4" height="{h-28}" rx="2" fill="{color}"/>')
    ix = x + 18
    for ic in icons or []:
        S.icon(ic, ix, y + 16, isz)
        ix += isz + 6
    tx_ = ix + 4 if icons else x + 18
    if title:
        S.text(tx_, y + 16 + isz * 0.5 - (2 if sub_ else -6), title, tsize, TEXT, 600)
    if sub_:
        S.text(tx_, y + 16 + isz * 0.5 + 17, sub_, 13, MUTED, 400)
    return tx_


HWC = "#c08a5c"   # "physical hardware" accent (same tan as the HARDWARE labels)


def hw_bar(x, y, h):
    """Left accent bar = this card is a physical box / hardware part."""
    S.add(f'<rect x="{x+1}" y="{y+12}" width="4" height="{h-24}" rx="2" fill="{HWC}"/>')


TAB = 34   # height of the folder tab on physical-device cards


def tab_width(g):
    """Tab fits 'name · type' (name 20px bold, type 14px semibold), measured from the font."""
    return 16 + measure(g["name"], 20, 700) + 7 + measure("·", 20, 700) + 7 + measure(g["type"], 14, 600) + 18


def folder(x, y, w, h, tab_w, fill, stroke, sw):
    """Card body at (x, y, w, h) with a folder tab on its top-left edge, tab_w wide and TAB high."""
    t = y - TAB
    r, rt, sl = 12, 9, 16
    d = (f"M{x},{y+h-r} L{x},{t+rt} Q{x},{t} {x+rt},{t} L{x+tab_w-sl:.1f},{t} "
         f"C{x+tab_w-sl/3:.1f},{t} {x+tab_w-sl/3:.1f},{y} {x+tab_w+sl/2:.1f},{y} "
         f"L{x+w-r},{y} Q{x+w},{y} {x+w},{y+r} L{x+w},{y+h-r} Q{x+w},{y+h} {x+w-r},{y+h} "
         f"L{x+r},{y+h} Q{x},{y+h} {x},{y+h-r} Z")
    S.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def device_card(x, y, w, h, icons, g, color, fill=PANEL, stroke=None, sw=1.6):
    """Physical device: folder tab 'name · type'; body = icon, full device name, IP · hostname, OS."""
    folder(x, y, w, h, tab_width(g), fill, stroke or color + "aa", sw)
    S.add(f'<text x="{x+16}" y="{y-10}" font-family="{SANS}" fill="{TEXT}">'
          f'<tspan font-size="20" font-weight="700">{esc(g["name"])}</tspan>'
          f'<tspan dx="7" font-size="20" font-weight="700" fill-opacity="0.6">·</tspan>'
          f'<tspan dx="7" font-size="14" font-weight="600">{esc(g["type"])}</tspan></text>')
    ix = x + 14
    for ic in icons:                      # icon spans the three body lines (full name … OS)
        S.icon(ic, ix, y + 15, 54)
        ix += 58
    tx_ = ix + 8
    dy = 0 if g.get("os") else 8          # no OS line → center the two lines on the icon
    S.text(tx_, y + 28 + dy, g.get("model") or "custom build", 14, TEXT if g.get("model") else MUTED, 500)
    addr(tx_, y + 48 + dy, g["ip"], g, color)
    if g.get("os"):
        S.text(tx_, y + 66, g["os"], 12, MUTED, 400)
    if g.get("config"):                   # optional 4th line: how the device is set up
        S.text(tx_, y + 84, g["config"], 12, FAINT, 400)


def jack(x, y, w, h, fill, stroke, sfp=False, dash=None):
    S.rect(x, y, w, h, rx=5, fill=fill, stroke=stroke, sw=1.4, dash=dash)
    if sfp:
        S.rect(x + 8, y + 9, w - 16, h - 18, rx=2, fill="#0b0f15", stroke="none", sw=0)
    else:
        S.add(f'<path d="M{x+10},{y+h-8} v-14 h6 v-5 h{w-32} v5 h6 v14 z" fill="#0b0f15"/>')


def ticks(cx, y, untagged=None, tagged=(), up=False):
    """VLAN indicator bars for a port: tall = untagged, short = tagged. up=True grows upwards."""
    vk = ([untagged] if untagged else []) + list(tagged)
    x0 = cx - (len(vk) * 7) / 2
    for j, k in enumerate(vk):
        hh = 8 if k == untagged else 5
        yy = y - hh if up else y
        S.add(f'<rect x="{x0 + j*7:.1f}" y="{yy}" width="5" height="{hh}" rx="1" fill="{C[k]}"/>')


def vlan_tag(vkey):
    v = VLAN[vkey]
    return f"{v['tag']} · {v['name']}" if v["tag"].startswith("VLAN") else v["name"]


# ---------------------------------------------------------------- background + header
S.add(f'<defs><pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
      f'<circle cx="1.5" cy="1.5" r="1.3" fill="{GRID}"/></pattern></defs>')
BG_IDX = len(S.p)
S.add("")   # background + dot grid: drawn at the end, once the canvas height is known
S.add("")

meta = INV["meta"]
S.text(40, 86, meta["title"], 46, TEXT, 700, ls=-0.5)
S.text(W - 40, 74, meta["subtitle"], 19, TEXT, 600, "end")
S.text(W - 40, 100, meta["date"], 16, MUTED, 400, "end")

PLANNED_DASH = "7 5"


def speed_tag(x, y, txt, color, anchor="start"):
    """Small speed label where a cable enters a device."""
    S.label(x, y, txt, color, 11, anchor=anchor, mono=True)


def planned_pill(x, y, anchor="end"):
    S.pill(x, y, "planned", MUTED, 10, mono=True, h=17, pad=5, anchor=anchor)


# ================================================================ left column: networks
vx, vy, vw = 40, 150, 500
vh = 70 + len(INV["vlans"]) * 60
S.rect(vx, vy, vw, vh, rx=14, fill=PANEL, stroke=BORDER, sw=1.4)
S.text(vx + 20, vy + 36, "Networks", 19, TEXT, 600)
for i, v in enumerate(INV["vlans"]):
    y = vy + 56 + i * 60
    S.rect(vx + 14, y, vw - 28, 52, rx=9, fill=CHIP, stroke=v["color"] + "55", sw=1)
    S.add(f'<rect x="{vx+14}" y="{y}" width="6" height="52" rx="3" fill="{v["color"]}"/>')
    S.text(vx + 32, y + 22, v["tag"], 13, v["color"], 600, mono=True)
    S.text(vx + 128, y + 22, v["name"], 15.5, TEXT, 600)
    S.text(vx + vw - 28, y + 22, v["subnet"], 13.5, TEXT, 500, "end", mono=True)
    S.text(vx + 32, y + 42, v["note"], 12, MUTED, 400)

# ================================================================ internet, cloud services, PON stick
CX = 1160
cy0 = 172
blobs = [(-95, 18, 42), (-45, -8, 56), (25, -18, 62), (90, 6, 48), (130, 26, 30), (-130, 30, 28)]
for dx, dy, r in blobs:
    S.add(f'<circle cx="{CX+dx}" cy="{cy0+dy}" r="{r+2.5}" fill="#3a4a60"/>')
S.add(f'<rect x="{CX-150}" y="{cy0+12}" width="300" height="46" rx="23" fill="#3a4a60"/>')
for dx, dy, r in blobs:
    S.add(f'<circle cx="{CX+dx}" cy="{cy0+dy}" r="{r}" fill="#1a2433"/>')
S.add(f'<rect x="{CX-147.5}" y="{cy0+14.5}" width="295" height="41" rx="20.5" fill="#1a2433"/>')
S.text(CX, cy0 + 14, "Internet", 26, TEXT, 600, "middle")
S.text(CX, cy0 + 40, "Frontier fiber", 13, MUTED, 400, "middle")

rw = INV["remote"]
rx_, ry_ = 590, 150
S.line([(rx_ + 290, ry_ + 42), (CX - 140, ry_ + 42)], C["vpn"], 1.8, dash="2 5", r=0)
S.rect(rx_, ry_, 290, 84, rx=12, fill=PANEL, stroke=C["vpn"] + "aa", sw=1.6)
S.icon("wireguard", rx_ + 16, ry_ + 22, 38)
S.text(rx_ + 66, ry_ + 38, rw["name"], 18, TEXT, 600)
S.text(rx_ + 66, ry_ + 60, rw["note"], 13, MUTED, 400)

RCX, RCW = 1790, 570                       # right column
csy = 146
for i, cs in enumerate(INV["cloud_services"]):
    y = csy + i * 54
    S.rect(RCX, y, RCW, 44, rx=10, fill=PANEL2, stroke=BORDER)
    S.icon(cs["icon"], RCX + 10, y + 9, 26)
    S.text(RCX + 46, y + 20, cs["name"], 14, TEXT, 600)
    S.text(RCX + 46, y + 36, cs["note"], 12, MUTED, 400)
    sy = cy0 - 8 + i * 22
    S.line([(CX + 150, sy), (RCX - 40, sy), (RCX - 40, y + 22), (RCX, y + 22)], FAINT, 1.6, dash="2 5", r=8)

pon = INV["pon"]
py0 = 262
S.line([(CX, cy0 + 58), (CX, py0)], C["wan"], SPEED_W["2.5G"])
S.rect(CX - 190, py0, 380, 62, rx=12, fill=PANEL, stroke=C["wan"] + "aa", sw=1.6)
S.icon("glyph-fiber", CX - 176, py0 + 15, 32)
S.text(CX - 134, py0 + 26, f"{pon['name']} · {pon['type']}", 16, TEXT, 600)
S.text(CX - 134, py0 + 46, pon["model"], 12.5, MUTED, 400)

# ================================================================ UDM Pro
udm = INV["udm"]
ox, oy, ow, oh = 570, 410, 1190, 318
device_card(ox, oy, ow, oh, ["unifi"], udm, C["1"], stroke=TRUNK_BORDER)
S.text(ox + 20, oy + 100, "PORTS", 11.5, HWC, 700, ls=1.4)
S.text(ox + 300, oy + 100, "SERVICES", 11.5, HWC, 700, ls=1.4)
for i, hwi in enumerate(udm["hw"]):
    x, y = ox + 16, oy + 110 + i * 64
    S.rect(x, y, 264, 58, rx=11, fill="#151d29", stroke="#2e3a4c", sw=1.2)
    hw_bar(x, y, 58)
    S.icon(hwi["icon"], x + 12, y + 15, 28)
    S.text(x + 50, y + 17, hwi["label"], 10, HWC, 700, ls=1.3)
    S.text(x + 50, y + 35, hwi["value"], 15.5, TEXT, 700)
    S.text(x + 50, y + 50, hwi["sub"], 10.5, MUTED, 400)
sw_, sh_ = 284, 50
for i, sv in enumerate(udm["services"]):
    col, row = i % 3, i // 3
    x = ox + 298 + col * (sw_ + 9)
    y = oy + 110 + row * (sh_ + 8)
    S.rect(x, y, sw_, sh_, rx=9, fill=CHIP, stroke=BORDER, sw=1)
    S.icon(sv["icon"], x + 9, y + 12, 26)
    S.text(x + 44, y + 22, sv["name"], 14, TEXT, 600)
    S.text(x + 44, y + 39, sv["note"], 11.5, MUTED, 400)
assert ox + 298 + 3 * (sw_ + 9) - 9 <= ox + ow - 14, "UDM services run past the card"

S.line([(CX, py0 + 62), (CX, oy + 14)], C["wan"], SPEED_W["2.5G"])
jack(CX - 30, oy + 14, 60, 36, C["wan"] + "55", C["wan"], sfp=True)
S.text(CX + 40, oy + 30, "SFP+ 11", 11, MUTED, 500, mono=True)
S.text(CX + 40, oy + 45, "WAN 192.168.11.2", 11, C["wan"], 500, mono=True)
speed_tag(CX + 8, py0 + 62 + (oy + 14 - py0 - 62) / 2 + 5, "fiber", C["wan"])

# ================================================================ core switch
swc = INV["switch"]
bx, by, bw, bh = 570, 830, 1190, 112
SB = by + bh
device_card(bx, by, bw, bh, ["unifi"], swc, C["1"], fill="#141b25", stroke=TRUNK_BORDER)
PX0 = bx + 300
PORTS = {}


def core_port_x(i):
    """Center x of core switch port i: three ports, a gap, the 41-48 block, then SFP+ 49-52."""
    n_rj = sum(1 for p in swc["ports"] if not p.get("sfp"))
    if i < n_rj:
        return PX0 + 24 + i * 52 + (24 if i >= 3 else 0)
    return PX0 + 24 + (n_rj - 1) * 52 + 24 + 53 + (i - n_rj) * 66


def draw_ports(ports, xfun, y, bottom, label_y):
    out = {}
    for i, p in enumerate(ports):
        sfp = p.get("sfp")
        w = 60 if sfp else 48
        cx = xfun(i)
        unt, tagged = p.get("untagged"), p.get("tagged", [])
        if p["to"] == "free":
            fill, stroke = "#1b222c", "#3a475a"
        elif not unt and not tagged:
            fill, stroke = UNKNOWN + "44", UNKNOWN
        elif unt and not tagged:
            fill, stroke = C[unt] + "55", C[unt]
        else:
            fill, stroke = "#2a3443", TRUNK
        jack(cx - w / 2, y, w, 36, fill, stroke, sfp, dash="4 3" if p.get("planned") else None)
        S.text(cx, y - 7, p["name"], 11, MUTED, 500, "middle", mono=True)
        if p["to"] != "free":
            ticks(cx, y + 41, unt, tagged)
        S.text(cx, label_y, p["to"], 10.5, FAINT if p["to"] == "free" else MUTED, 500, "middle")
        out[(p["name"], p["to"])] = cx
    return out


PORTS = draw_ports(swc["ports"], core_port_x, by + 30, SB, SB - 9)
S.text(core_port_x(2) + 24 + 12, by + 52, "⋯", 14, FAINT, 600, "middle")
assert core_port_x(len(swc["ports"]) - 1) + 40 <= bx + bw, "core switch ports run past the card"
S.text(bx + bw - 14, by - 10, "network rack · only ports in use shown", 11.5, FAINT, 500, "end")

# UDM SFP+ 10 ↔ switch port 49
up_x = PORTS[("49", "UDM")]
S.trunk([(up_x, by + 30), (up_x, oy + oh - 20)], sw=trunk_w("10G"))
jack(up_x - 30, oy + oh - 46, 60, 36, "#2a3443", TRUNK, sfp=True)
S.text(up_x - 40, oy + oh - 22, "SFP+ 10", 11, MUTED, 500, "end", mono=True)
speed_tag(up_x + 10, (oy + oh + by) / 2 + 4, "10G", TRUNK)

# ================================================================ device row
DY = 1090
dev = INV["devices"]
BOX = {"zigbee": (40, 262, 86), "unvr": (322, 262, 86), "desk": (604, 360, 86), "ap": (984, 486, 124)}


def device(key):
    x, w, h = BOX[key]
    d = dev[key]
    col = C[d["vlan"]]
    device_card(x, DY, w, h, d["icons"], d, col, stroke=TRUNK_BORDER if d.get("trunk") else None)
    return x, w, h


for k in BOX:
    device(k)

x, w, h = BOX["ap"]
ss = INV["ssid"]
S.add(f'<circle cx="{x+24}" cy="{DY+99}" r="4" fill="{TRUNK}"/>')
S.text(x + 36, DY + 103, ss["name"], 13, TEXT, 600)
S.text(x + 120, DY + 103, "PPSK", 11, TRUNK, 700, mono=True)
for j, k in enumerate(ss["vlans"]):
    S.add(f'<circle cx="{x + 166 + j*13}" cy="{DY+99}" r="4.5" fill="{C[k]}"/>')
S.text(x + 166 + len(ss["vlans"]) * 13 + 6, DY + 103, ss["note"], 11.5, MUTED, 400)


def entry(key, extra=0):
    """x where a cable enters a device card from above: right of the folder tab."""
    return BOX[key][0] + tab_width(dev[key]) + 30 + extra


links = [  # (port key, device, entry x, horizontal y, color, width, tag)
    (("1", "Zigbee"), "zigbee", entry("zigbee"), SB + 20, C["50"], SPEED_W["100M"], "PoE"),
    (("?", "UNVR"), "unvr", entry("unvr"), SB + 36, C["1"], SPEED_W["1G"], None),
    (("41", "Desk PC"), "desk", entry("desk"), SB + 52, C["10"], SPEED_W["1G"], None),
    (("42", "Desk sw"), "desk", entry("desk", 52), SB + 68, UNKNOWN, SPEED_W["1G"], None),
]
for pk, key, ex, hy, col, wdt, tag in links:
    px = PORTS[pk]
    dash = PLANNED_DASH if dev[key].get("planned") else None
    S.line([(px, SB), (px, hy), (ex, hy), (ex, DY)], col, wdt, dash=dash)
    if tag:
        speed_tag(ex + 6, DY - 9, tag, col)
for pk in (("45", "AP back"), ("47", "AP front")):
    px = PORTS[pk]
    S.trunk([(px, SB), (px, DY)], sw=trunk_w("1G"))
    speed_tag(px + 8, DY - 9, "PoE", TRUNK)

# ================================================================ right column: how the internet gets in
iy_ = csy + len(INV["cloud_services"]) * 54 + 12
rows = INV["ingress"]
RH = 104
ih_ = 66 + len(rows) * RH
S.rect(RCX, iy_, RCW, ih_, rx=14, fill=PANEL, stroke=BORDER, sw=1.4)
S.text(RCX + 20, iy_ + 34, "How the internet gets in", 19, TEXT, 600)
S.text(RCX + 20, iy_ + 54, "only two ports are forwarded at home; everything else comes in outbound", 12.5, MUTED, 400)
AG = 26
for r_i, row in enumerate(rows):
    y = iy_ + 70 + r_i * RH
    S.text(RCX + 20, y + 12, row["name"].upper(), 11.5, HWC, 700, ls=1.4)
    n = len(row["steps"])
    nw = (RCW - 40 - (n - 1) * AG) / n
    for k, st in enumerate(row["steps"]):
        nx = RCX + 20 + k * (nw + AG)
        S.rect(nx, y + 22, nw, 46, rx=8, fill=CHIP, stroke=BORDER, sw=1)
        S.icon(st["icon"], nx + 9, y + 34, 22)
        S.text(nx + 38, y + 41 if st.get("sub") else y + 49, st["name"], 13, TEXT, 600)
        if st.get("sub"):
            S.text(nx + 38, y + 58, st["sub"], 10.5, FAINT, 500, mono=True)
        if k:
            S.arrow([(nx - AG + 4, y + 45), (nx - 4, y + 45)])
    S.text(RCX + 20, y + 86, row["note"], 11.5, MUTED, 400)

# ================================================================ legend (right column)
LG_ROWS = ["trunk", "access", "unknown", "wan", "net", "planned", "speed", "ticks", "docker"]
lgx, lgy, lgw = RCX, iy_ + ih_ + 16, RCW
LR = 27
lgh = 52 + len(LG_ROWS) * LR + 8
S.rect(lgx, lgy, lgw, lgh, rx=14, fill=PANEL, stroke=BORDER, sw=1.4)
S.text(lgx + 20, lgy + 36, "Legend", 19, TEXT, 600)
SX, TX = lgx + 22, lgx + 162
for i, k in enumerate(LG_ROWS):
    y = lgy + 66 + i * LR
    t = None
    if k == "trunk":
        S.trunk([(SX, y), (SX + 50, y)], sw=trunk_w("2.5G"), r=0); t = "802.1Q trunk (tagged VLANs)"
    elif k == "access":
        for jj, c in enumerate(["1", "10", "30", "50"]):
            S.line([(SX + jj * 13, y), (SX + jj * 13 + 9, y)], C[c], 3.6, r=0, cap="butt")
        t = "access port, colored by VLAN"
    elif k == "unknown":
        S.line([(SX, y), (SX + 50, y)], UNKNOWN, 3, r=0); t = "in use, VLAN not in the notes"
    elif k == "wan":
        S.line([(SX, y), (SX + 50, y)], C["wan"], 3, r=0); t = "WAN (fiber to Frontier)"
    elif k == "net":
        S.line([(SX, y), (SX + 50, y)], MUTED, 1.8, dash="2 5", r=0); t = "over the internet (not a cable)"
    elif k == "planned":
        S.rect(SX, y - 8, 50, 16, rx=4, fill="none", stroke=MUTED, sw=1.3, dash="5 4"); t = "planned, not built yet"
    elif k == "speed":
        S.text(SX, y + 4.5, "line width = speed", 12.5, MUTED, 400)
        x0 = TX
        for lbl in ("10G", "2.5G", "1G", "100M"):
            S.line([(x0, y), (x0 + 26, y)], C["10"], SPEED_W[lbl], r=0, cap="butt")
            S.text(x0 + 32, y + 4.5, lbl, 12, TEXT, 500, mono=True)
            x0 += 32 + tw(lbl, 12, True) + 20
    elif k == "ticks":
        for jj, c in enumerate(["1", "10", "30"]):
            S.add(f'<rect x="{SX + jj*7}" y="{y-5 if jj == 0 else y-2}" width="5" height="{8 if jj == 0 else 5}" rx="1" fill="{C[c]}"/>')
        t = "port VLANs (tall = untagged)"
    elif k == "docker":
        S.add(f'<circle cx="{SX+12}" cy="{y}" r="11" fill="{PANEL}" stroke="#2f6fb0" stroke-width="1.2"/>')
        S.icon("docker", SX + 4, y - 8, 16)
        t = "Docker VM, one row per app"
    if t:
        S.text(TX, y + 4.5, t, 13, MUTED, 400)
LEG_BOTTOM = lgy + lgh

# ================================================================ main rack switch
s2 = INV["switch2"]
P25, P26 = PORTS[("51", "LACP")], PORTS[("52", "LACP")]
s2x = P25 - 30 - 20 - tab_width(s2)          # folder tab ends left of the LACP cables
s2y, s2w, s2h = max(LEG_BOTTOM + 60, DY + BOX["ap"][2] + 70), 0, 104
s2w = W - 40 - s2x
S2B = s2y + s2h
folder(s2x, s2y, s2w, s2h, tab_width(s2), "#141b25", TRUNK_BORDER, 1.6)
S.add(f'<text x="{s2x+16}" y="{s2y-10}" font-family="{SANS}" fill="{TEXT}">'
      f'<tspan font-size="20" font-weight="700">{esc(s2["name"])}</tspan>'
      f'<tspan dx="7" font-size="20" font-weight="700" fill-opacity="0.6">·</tspan>'
      f'<tspan dx="7" font-size="14" font-weight="600">{esc(s2["type"])}</tspan></text>')
S2X = [P25, P26, P26 + 64, P26 + 116]
PORTS2 = draw_ports(s2["ports"], lambda i: S2X[i], s2y + 26, S2B, S2B - 9)
tx2 = S2X[-1] + 50
S.icon("unifi", tx2, s2y + 20, 46)
S.text(tx2 + 58, s2y + 38, s2["model"], 14, TEXT, 500)
S.text(tx2 + 58, s2y + 58, "main rack · Elizabeth's office", 12, MUTED, 400)
S.text(tx2 + 58, s2y + 76, "LACP 2× 10G fiber, runs 1 + 2", 12, FAINT, 400)

for px in (P25, P26):
    S.trunk([(px, SB), (px, s2y + 26)], sw=trunk_w("10G"))
lx, ly = (P25 + P26) / 2, (SB + s2y) / 2
S.add(f'<ellipse cx="{lx}" cy="{ly}" rx="52" ry="12" fill="none" stroke="{TRUNK}" stroke-width="1.4" stroke-dasharray="3 3"/>')
S.label(lx + 60, ly + 4, "LACP · 20G", TRUNK, 11, anchor="start", mono=True)

# ================================================================ jupiter
J = INV["jupiter"]
tx0, ty0, tw0 = 40, S2B + 90, W - 80
GY = 92
HWW = 270
TH_, TG_ = 58, 6
ZH = 22 + len(J["hw"]) * (TH_ + TG_) + 4
th0 = GY + ZH + 22
device_card(tx0, ty0, tw0, th0, ["proxmox"], J, C["1"], fill="#0f151e", stroke=TRUNK_BORDER, sw=2)

# cables into jupiter
fx = PORTS[("50", "jupiter")]
FJ = s2x - 30                               # fiber to jupiter runs left of the main rack switch
S.trunk([(fx, SB), (fx, s2y - TAB - 24), (FJ, s2y - TAB - 24), (FJ, ty0)], sw=trunk_w("10G"))
speed_tag(FJ - 10, ty0 - 9, "10G fiber · primary", TRUNK, anchor="end")
bmc_x, nic0_x = PORTS2[("23", "BMC")], PORTS2[("24", "jupiter")]
S.line([(bmc_x, S2B), (bmc_x, ty0)], C["1"], SPEED_W["1G"])
S.trunk([(nic0_x, S2B), (nic0_x, ty0)], sw=trunk_w("1G"))
speed_tag(bmc_x - 8, ty0 - 9, "BMC", C["1"], anchor="end")
speed_tag(nic0_x + 8, ty0 - 9, "1G · backup", TRUNK)

hwx = tx0 + 20
hy0 = ty0 + GY
S.text(hwx + 2, hy0 + 12, "HARDWARE", 11.5, HWC, 700, ls=1.4)
for i, hwi in enumerate(J["hw"]):
    x, y = hwx, hy0 + 22 + i * (TH_ + TG_)
    S.rect(x, y, HWW, TH_, rx=11, fill="#151d29", stroke="#2e3a4c", sw=1.2)
    hw_bar(x, y, TH_)
    S.icon(hwi["icon"], x + 12, y + 15, 28)
    S.text(x + 50, y + 17, hwi["label"], 10, HWC, 700, ls=1.3)
    vs = min(15.5, 15.5 * (HWW - 62) / measure(hwi["value"], 15.5, 700))
    S.text(x + 50, y + 35, hwi["value"], round(vs, 2), TEXT, 700)
    ss_ = min(10.5, 10.5 * (HWW - 60) / max(tw(hwi["sub"], 10.5), 1))
    S.text(x + 50, y + 50, hwi["sub"], round(ss_, 2), MUTED, 400)

# ---- column 2: TrueNAS and the multi-network guests
gx, gw = hwx + HWW + 20, 440
gy = hy0 + 22


def guest_card(g, x, y, w, h):
    col = C[g["vlan"]]
    S.rect(x, y, w, h, rx=12, fill=PANEL, stroke=col + "99", sw=1.5)
    S.icon(g["icon"], x + 16, y + 14, 34)
    S.text(x + 60, y + 32, g["name"], 17, TEXT, 600)
    S.text(x + 60 + measure(g["name"], 17, 600) + 10, y + 32, g["role"], 13, MUTED, 500)
    S.text(x + w - 14, y + 30, g["id"], 12, FAINT, 500, "end", mono=True)
    S.text(x + 60, y + 52, g["ip"], 12, col, 500, mono=True)
    S.text(x + 60, y + 70, g["note"], 12, MUTED, 400)


tn = J["truenas"]
tnh = 84 + len(tn["pools"]) * 52 + 30
guest_card(tn, gx, gy, gw, tnh)
for i, pl in enumerate(tn["pools"]):
    y = gy + 84 + i * 52
    S.rect(gx + 14, y, gw - 28, 46, rx=9, fill=CHIP, stroke=BORDER, sw=1)
    S.icon("glyph-hdd", gx + 24, y + 11, 24)
    S.text(gx + 58, y + 20, pl["name"], 14, TEXT, 700, mono=True)
    S.text(gx + 58, y + 37, pl["holds"], 11.5, MUTED, 400)
S.text(gx + 18, gy + tnh - 12, tn["shares"], 11.5, MUTED, 400)
cy_ = gy + tnh + 14
for g in J["cards"]:
    guest_card(g, gx, cy_, gw, 84)
    cy_ += 98
assert cy_ - 14 <= hy0 + ZH + 6, "jupiter column 2 too tall"

# ---- VLAN zones
CH, CG = 64, 7
cgap = 14


def docker_badge(x, y):
    S.add(f'<circle cx="{x}" cy="{y}" r="12" fill="{PANEL}" stroke="#2f6fb0" stroke-width="1.2"/>')
    S.icon("docker", x - 8.5, y - 8.5, 17)


def chip_ids(g, x, y, w, zone):
    S.text(x + w - 12, y + 21, f"{g.get('kind', 'CT')} {g['id']}", 12, FAINT, 500, "end", mono=True)
    S.text(x + w - 12, y + 37, g["ip"], 11, C[zone], 500, "end", mono=True)
    if g.get("planned"):
        planned_pill(x + w - 12, y + CH - 24)


def chip(g, x, y, w, zone):
    dash = "5 4" if g.get("planned") else None
    if g.get("apps"):
        h = 46 + len(g["apps"]) * 21 + 8
        S.rect(x, y, w, h, rx=9, fill=CHIP, stroke=BORDER, sw=1, dash=dash)
        S.text(x + 14, y + 22, g["name"], 14.5, TEXT, 600)
        S.text(x + 14, y + 38, g.get("note", ""), 11.5, MUTED, 400)
        chip_ids(g, x, y, w, zone)
        for k, a in enumerate(g["apps"]):
            ry = y + 50 + k * 21
            S.icon(a["icon"], x + 14, ry, 17)
            S.text(x + 38, ry + 13, a["name"], 12.5, TEXT, 600)
            if a.get("note"):
                S.text(x + 130, ry + 13, a["note"], 11.5, MUTED, 400)
        if g.get("docker"):
            docker_badge(x + 2, y + 2)
        return h
    S.rect(x, y, w, CH, rx=9, fill=CHIP, stroke=BORDER if not dash else MUTED, sw=1, dash=dash)
    S.icon(g["icons"][0], x + 12, y + 16, 32)
    S.text(x + 54, y + 27, g["name"], 14.5, TEXT, 600)
    S.text(x + 54, y + 45, g.get("note", ""), 11.5, MUTED, 400)
    chip_ids(g, x, y, w, zone)
    return CH


zx = gx + gw + 20
zend = tx0 + tw0 - 20
zone_w = {"30": 3, "40": 1}
ncols = sum(len(z["columns"]) for z in J["zones"])
colw = (zend - zx - 32 * len(J["zones"]) - cgap * (ncols - len(J["zones"])) - 20 * (len(J["zones"]) - 1)) / ncols
zy = hy0
for z in J["zones"]:
    nc = len(z["columns"])
    zw = 32 + nc * colw + (nc - 1) * cgap
    col = C[z["vlan"]]
    S.rect(zx, zy, zw, ZH, rx=14, fill=col + "0d", stroke=col + "88", sw=1.5)
    S.pill(zx + zw - 14, zy + 16, vlan_tag(z["vlan"]), col, 10.5, mono=True, h=19, pad=6, anchor="end")
    S.text(zx + 18, zy + 31, z["note"], 12.5, MUTED, 400)
    for ci, groups in enumerate(z["columns"]):
        x = zx + 16 + ci * (colw + cgap)
        y = zy + 56
        for grp in groups:
            S.text(x + 2, y + 12, grp["name"].upper(), 11.5, HWC, 700, ls=1.4)
            y += 22
            for g in grp["guests"]:
                y += chip(g, x, y, colw, z["vlan"]) + CG
            y += 14
        assert y <= zy + ZH + 6, f"zone {z['vlan']} column {ci} too tall"
    zx += zw + 20

# ================================================================ saturn (planned)
SA = INV["saturn"]
sx0, sy0, sw0 = 40, ty0 + th0 + 34 + 40, W - 80
sh0 = GY + 22 + 3 * (CH + CG) + 16
folder(sx0, sy0, sw0, sh0, tab_width(SA), "#0f151e", MUTED + "aa", 1.6)
# dashed outline on top of the solid one marks the whole host as planned
t = sy0 - TAB
S.rect(sx0 - 5, t - 5, sw0 + 10, sh0 + TAB + 10, rx=16, fill="none", stroke=MUTED, sw=1.2, dash="6 6")
S.add(f'<text x="{sx0+16}" y="{sy0-10}" font-family="{SANS}" fill="{TEXT}">'
      f'<tspan font-size="20" font-weight="700">{esc(SA["name"])}</tspan>'
      f'<tspan dx="7" font-size="20" font-weight="700" fill-opacity="0.6">·</tspan>'
      f'<tspan dx="7" font-size="14" font-weight="600">{esc(SA["type"])}</tspan></text>')
S.icon("proxmox", sx0 + 14, sy0 + 15, 54)
S.text(sx0 + 80, sy0 + 28, SA["model"], 14, TEXT, 500)
S.text(sx0 + 80, sy0 + 48, SA["ip"], 12, C["1"], 500, mono=True)
S.text(sx0 + 80, sy0 + 66, SA["os"], 12, MUTED, 400)
planned_pill(sx0 + sw0 - 14, sy0 + 14)

shy = sy0 + GY
S.text(sx0 + 22, shy + 12, "HARDWARE", 11.5, HWC, 700, ls=1.4)
for i, hwi in enumerate(SA["hw"]):
    c, r = i % 3, i // 3
    x, y = sx0 + 20 + c * (HWW + 10), shy + 22 + r * (TH_ + TG_)
    S.rect(x, y, HWW, TH_, rx=11, fill="#151d29", stroke="#2e3a4c", sw=1.2, dash="5 4")
    hw_bar(x, y, TH_)
    S.icon(hwi["icon"], x + 12, y + 15, 28)
    S.text(x + 50, y + 17, hwi["label"], 10, HWC, 700, ls=1.3)
    S.text(x + 50, y + 35, hwi["value"], 15.5, TEXT, 700)
    S.text(x + 50, y + 50, hwi["sub"], 10.5, MUTED, 400)

gx2 = sx0 + 20 + 3 * (HWW + 10) + 20
S.text(gx2 + 2, shy + 12, "GUESTS THAT MOVE HERE, AND NEW ONES", 11.5, HWC, 700, ls=1.4)
items = SA["guests"] + SA["extra"]
NC2 = 4
cw2 = (sx0 + sw0 - 20 - gx2 - (NC2 - 1) * cgap) / NC2
for i, g in enumerate(items):
    c, r = i % NC2, i // NC2
    x, y = gx2 + c * (cw2 + cgap), shy + 22 + r * (CH + CG)
    S.rect(x, y, cw2, CH, rx=9, fill=CHIP, stroke=MUTED, sw=1, dash="5 4")
    S.icon(g["icon"], x + 12, y + 16, 32)
    S.text(x + 54, y + 27, g["name"], 14.5, TEXT, 600)
    S.text(x + 54, y + 45, g["note"], 11.5, MUTED, 400)
    if g.get("was"):
        S.text(x + cw2 - 12, y + 21, f"was {g['was']}", 11, FAINT, 500, "end", mono=True)
    elif g.get("new"):
        S.text(x + cw2 - 12, y + 21, "new", 11, FAINT, 500, "end", mono=True)
assert shy + 22 + ((len(items) - 1) // NC2 + 1) * (CH + CG) <= sy0 + sh0 + 4, "saturn guests too tall"

# ---------------------------------------------------------------- canvas height
H = int(sy0 + sh0 + 40)
S.rect(0, 0, W, H, rx=0, fill=BG, stroke=BG, sw=0)
S.rect(0, 0, W, H, rx=0, fill="url(#dots)", stroke="none", sw=0)
dots = S.p.pop()
S.p[BG_IDX], S.p[BG_IDX + 1] = S.p.pop(), dots

OUT.mkdir(exist_ok=True)
svg_path = OUT / "homelab.svg"
svg_path.write_text(S.render())
png_path = OUT / "homelab.png"
subprocess.run(["rsvg-convert", "-z", "1.6", "-o", str(png_path), str(svg_path)], check=True)
print(svg_path, png_path)
