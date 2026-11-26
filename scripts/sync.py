#!/usr/bin/env python3
"""Pull compose files and config from the homelab hosts into this repo, with secrets removed.

Run from the repo root:  python3 scripts/sync.py [--push]
Reads scripts/manifest.txt. Nothing is written if a possible secret is found.
"""
import re, shlex, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / 'scripts' / 'manifest.txt'

# .env keys whose values are safe to publish; every other value becomes CHANGE_ME
KEEP_KEYS = {'TZ', 'PUID', 'PGID', 'UMASK', 'LOG_LEVEL', 'COMPOSE_PROJECT_NAME'}

# lines in config files whose values are replaced
REDACT = re.compile(r'(?im)^(\s*(?:PrivateKey|PresharedKey|password|passwd|secret|token)\s*[=:]\s*).+$')

# anything matching these stops the run
SCANS = [
    ('discord webhook', re.compile(r'discord(?:app)?\.com/api/webhooks/\d+/[\w-]+')),
    ('token (JWT style)', re.compile(r'eyJ[A-Za-z0-9_-]{20,}')),
    ('base64 key (WireGuard style)', re.compile(r'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{43}=(?![A-Za-z0-9+/=])')),
    ('private key block', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('hard-coded secret', re.compile(r'(?i)(?:password|passwd|secret|token|api[_-]?key)["\']?\s*[:=]\s*["\']?(?!CHANGE_ME|<|\$\{|\$\()[^\s"\'#]{8,}')),
]

def fetch(host, path):
    if host == 'local':
        return Path(path).read_text()
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', host, 'cat', path], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'cannot read {host}:{path}: {r.stderr.strip()}')
    return r.stdout

def make_example(text):
    out = []
    for line in text.splitlines():
        m = re.match(r'^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
        if m and not line.lstrip().startswith('#'):
            key = m.group(2)
            out.append(f'{m.group(1)}{key}={m.group(3) if key in KEEP_KEYS else "CHANGE_ME"}')
        else:
            out.append(line)
    return '\n'.join(out) + '\n'

def scan(files):
    found = []
    for rel, text in files.items():
        for n, line in enumerate(text.splitlines(), 1):
            if 'sync-ok' in line:
                continue
            for name, rx in SCANS:
                if rx.search(line):
                    found.append(f'{rel}:{n}: {name}: {line.strip()[:60]}...')
    return found

def main():
    files = {}
    for raw in MANIFEST.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        kind, host, remote, dest = shlex.split(raw, comments=True)
        text = fetch(host, remote)
        if kind == 'env':
            if not dest.endswith('.env.example'):
                sys.exit(f'env entries must end in .env.example: {dest}')
            text = make_example(text)
        elif kind == 'file':
            text = REDACT.sub(lambda m: m.group(1) + 'CHANGE_ME', text)
        elif kind != 'compose':
            sys.exit(f'unknown kind {kind!r} in manifest')
        files[dest] = text

    tracked = subprocess.run(['git', '-C', str(REPO), 'ls-files'], capture_output=True, text=True).stdout.split()
    bad = [t for t in tracked if re.search(r'(^|/)\.env$|\.(pem|key)$', t)]
    if bad:
        sys.exit('secret-looking files are tracked, remove them first: ' + ', '.join(bad))

    found = scan(files)
    if found:
        print('Possible secrets found. Nothing was written.\n')
        print('\n'.join(found))
        print('\nFix the source, or add "# sync-ok" to a line that is safe, then run again.')
        sys.exit(1)

    for dest, text in files.items():
        p = REPO / dest
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    print(f'Wrote {len(files)} files.\n')
    subprocess.run(['git', '-C', str(REPO), 'status', '--short'])
    if '--push' in sys.argv:
        if input('\nCommit and push these changes? [y/N] ').lower() == 'y':
            subprocess.run(['git', '-C', str(REPO), 'add', '-A'], check=True)
            subprocess.run(['git', '-C', str(REPO), 'commit', '-m', 'Sync from homelab'], check=True)
            subprocess.run(['git', '-C', str(REPO), 'push'], check=True)
    else:
        print('\nReview with: git diff   then: git add -A && git commit -m "Sync from homelab" && git push')

if __name__ == '__main__':
    main()
