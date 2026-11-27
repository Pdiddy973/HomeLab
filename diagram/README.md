# Homelab diagram

Renders one big picture of the lab (network, switches, jupiter and its guests, saturn as planned) from `inventory.yaml` into `out/homelab.png` and `out/homelab.svg`. The layout code comes from [Goblinmine/homelab-diagram](https://github.com/Goblinmine/homelab-diagram) (MIT, see `LICENSE`), with the layout rewritten for this lab.

## Run it

Needs Python 3.11+ with PyYAML and Pillow, `rsvg-convert` (librsvg), and the Fira Sans and Fira Code fonts.

```bash
pip install pyyaml pillow           # or: apt install python3-yaml python3-pil
apt install librsvg2-bin fonts-firacode   # Fira Sans: install from github.com/mozilla/Fira
python3 fetch_icons.py              # once: service icons from dashboard-icons
python3 build.py                    # → out/homelab.png + out/homelab.svg
```

Copy `out/homelab.png` to the vault as `01 Overview/Attachments/homelab-diagram.png`.

## Change it

- Text, IPs, guests, ports and VLAN colors: edit `inventory.yaml` and run `build.py` again.
- A new guest: add a chip under the right zone and group in `jupiter.zones` (or `saturn.guests`).
- A new icon: add its [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) name to `ICONS_USED` in `fetch_icons.py`, or use one of the `glyph-*` icons.
- Positions of boxes and cables are hand-placed in `build.py`. If a column runs out of room an `assert` names it.
