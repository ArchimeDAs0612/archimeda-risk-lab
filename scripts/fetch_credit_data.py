"""Download the pinned UCI 350 CSV; no authentication, raw-data redistribution or extraction.

Dataset: I-Cheng Yeh, Default of Credit Card Clients, UCI (2009),
https://doi.org/10.24432/C55S3H ; CC BY 4.0, not the Lab's MIT license.
"""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import HTTPSHandler, HTTPRedirectHandler, build_opener
from urllib.parse import urlparse


URL = 'https://archive.ics.uci.edu/static/public/350/data.csv'
EXPECTED = '45bcf4df62ff2e237a74eb155cabfb4bbbc171219a0637daef44fdad07503dd0'


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != 'https' or parsed.hostname != 'archive.ics.uci.edu' or any([parsed.username, parsed.password]):
            raise ValueError('unexpected redirect origin')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(destination):
    target = Path(destination).expanduser().resolve()
    root = Path.cwd().resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError('download destination must be inside the selected workspace')
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() == EXPECTED:
            return 'VERIFIED_EXISTING'
        raise ValueError('existing file differs; preserve it and choose another path')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.uci350-', dir=target.parent)
    try:
        opener = build_opener(HTTPSHandler(), SameOriginRedirect())
        total = 0; checksum = hashlib.sha256()
        with os.fdopen(fd, 'wb') as sink, opener.open(URL, timeout=30) as response:
            for chunk in iter(lambda: response.read(65536), b''):
                total += len(chunk)
                if total > 8_000_000:
                    raise ValueError('unexpected source size')
                checksum.update(chunk); sink.write(chunk)
        if checksum.hexdigest() != EXPECTED:
            raise ValueError('upstream checksum changed; review instead of silently adopting')
        # Exclusive target creation prevents replacing a different concurrently created file.
        os.link(name, target)
        return 'DOWNLOADED_VERIFIED'
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    print(fetch(parser.parse_args().out))
