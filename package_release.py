"""Build the public client bundle and matching registry metadata for one version."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import tomllib
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

version = json.loads(Path("manifest.json").read_text())["version"]
if (sys.argv[1:] != ["v" + version]
        or tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"] != version):
    raise SystemExit("Tag, manifest and project versions must match")
output = Path("dist")
output.mkdir(exist_ok=True)
bundle = output / "neuraliquid.mcpb"
with ZipFile(bundle, "w") as archive:
    for name in ("manifest.json", "pyproject.toml", "neuraliquid_mcp.py", "README.md"):
        info = ZipInfo(name)
        info.compress_type = ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, Path(name).read_bytes())
repository = "https://github.com/Marcolist/neuraliquid-mcp"
package = {"registryType": "mcpb", "identifier": f"{repository}/releases/download/v{version}/{bundle.name}",
           "fileSha256": sha256(bundle.read_bytes()).hexdigest(), "transport": {"type": "stdio"}}
metadata = {"$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
            "name": "io.github.Marcolist/neuraliquid-mcp", "title": "NeuraLiquid Signals by FutureCast",
            "description": "Inspect an x402 watchlist offer, check feed freshness and read an existing crypto signal pass.",
            "version": version, "repository": {"url": repository, "source": "github"}, "packages": [package]}
(output / "server.json").write_text(json.dumps(metadata, indent=2) + "\n")
