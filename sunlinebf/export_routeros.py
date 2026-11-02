"""Rewrite a docker-save archive using the classic Docker archive layout.

Usage: python export_routeros.py INPUT.tar OUTPUT.tar
No extraction to the filesystem, Docker daemon, or third-party packages needed.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def convert(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output paths must differ")
    with tarfile.open(source, "r:*") as archive:
        def read(name):
            member = archive.extractfile(name)
            if member is None:
                raise ValueError(f"Missing regular file: {name}")
            return member.read()

        manifests = json.loads(read("manifest.json"))
        if len(manifests) != 1:
            raise ValueError("Export exactly one image at a time")
        manifest = manifests[0]
        config_bytes = read(manifest["Config"])
        config = json.loads(config_bytes)
        if (config.get("os"), config.get("architecture")) != ("linux", "amd64"):
            raise ValueError("Expected linux/amd64 for MikroTik CHR")
        diff_ids = config["rootfs"]["diff_ids"]
        if len(diff_ids) != len(manifest["Layers"]):
            raise ValueError("Layer count differs from image configuration")
        config_name = hashlib.sha256(config_bytes).hexdigest() + ".json"
        # Exclusive creation prevents accidentally overwriting an earlier export.
        with destination.open("xb") as stream:
            with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as output:
                def add(name, data):
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o644
                    output.addfile(info, io.BytesIO(data))

                add(config_name, config_bytes)
                layers = []
                written = set()
                for name, expected in zip(manifest["Layers"], diff_ids):
                    data = read(name)
                    if data.startswith(b"\x1f\x8b"):
                        data = gzip.decompress(data)
                    digest = hashlib.sha256(data).hexdigest()
                    if "sha256:" + digest != expected:
                        raise ValueError(f"Layer checksum mismatch: {name}")
                    target = digest + "/layer.tar"
                    if target not in written:
                        add(target, data)
                        written.add(target)
                    layers.append(target)
                add("manifest.json", json.dumps([{
                    "Config": config_name,
                    "RepoTags": manifest.get("RepoTags", []),
                    "Layers": layers,
                }], separators=(",", ":")).encode())
    print(f"Created {destination} ({destination.stat().st_size:,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    convert(args.source, args.destination)
