#!/usr/bin/env python3
"""Download the service icons into icons/ from homarr-labs/dashboard-icons.

The own glyph-*.svg icons are already in icons/.
Usage: python3 fetch_icons.py
"""
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
ICONS = ROOT / "icons"
# tried in order; jsDelivr is the fallback when raw GitHub refuses a file
SOURCES = [
    "https://raw.githubusercontent.com/homarr-labs/dashboard-icons/main/svg/{}.svg",
    "https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg/{}.svg",
]

# icon names used in inventory.yaml and build.py; each is the dashboard-icons file name
ICONS_USED = [
    "bazarr", "caddy", "cloudflare", "couchdb", "crafty-controller", "digital-ocean", "discord",
    "docker", "dockhand-svg", "frigate", "home-assistant", "immich", "maintainerr", "mealie",
    "openbao", "pgadmin", "plex", "postgres", "proxmox", "radarr", "raspberry-pi", "seerr",
    "semaphore", "sonarr", "tracearr", "truenas-scale", "unifi", "wireguard", "wizarr", "zigbee2mqtt",
]

# icons drawn black by default: give them a color that shows on the dark background
RECOLOR = {"docker": ('fill="#000000"', 'fill="#1d91e6"')}


def download(name, tries=3):
    """Fetch one icon from the first source that delivers it; retry with a short pause."""
    last = None
    for url in SOURCES:
        req = urllib.request.Request(url.format(name), headers={"User-Agent": "homelab-diagram/1.0"})
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return r.read().decode("utf-8")
            except Exception as e:
                last = e
                if getattr(e, "code", None) in (403, 404):
                    break
                time.sleep(2 * (attempt + 1))
    raise last


def main():
    ICONS.mkdir(exist_ok=True)
    failed = []
    for name in ICONS_USED:
        if (ICONS / f"{name}.svg").exists():
            continue
        time.sleep(0.2)
        try:
            svg = download(name)
            if name in RECOLOR:
                svg = svg.replace(*RECOLOR[name])
            (ICONS / f"{name}.svg").write_text(svg)
        except Exception as e:
            failed.append(f"{name}: {e}")
    print(f"icons in {ICONS}: {len(list(ICONS.glob('*.svg')))}")
    if failed:
        raise SystemExit("could not download:\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    main()
