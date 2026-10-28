"""只提供最新已發布的iOS簽署畫面更新，不提供原始碼目錄或私鑰。"""
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath


def update_asset(root: Path, asset_path: str) -> bytes:
    root = root.resolve()
    stable = (root / "stable.json").resolve()
    if not stable.is_relative_to(root):
        raise ValueError("Invalid manifest path")
    envelope_data = stable.read_bytes()
    if len(envelope_data) > 262144:
        raise ValueError("Manifest too large")
    envelope = json.loads(envelope_data)
    manifest = json.loads(base64.b64decode(envelope["payload"], validate=True))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("revision"), int):
        raise ValueError("Invalid manifest")
    if asset_path == "stable.json":
        return envelope_data
    prefix = f"revisions/{manifest['revision']}/"
    if not asset_path.startswith(prefix):
        raise ValueError("Only current release is public")
    relative = asset_path[len(prefix):]
    path = PurePosixPath(relative)
    if not relative or "\\" in relative or path.is_absolute() or any(p.startswith(".") for p in path.parts):
        raise ValueError("Invalid asset path")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) > 128:
        raise ValueError("Invalid file list")
    metadata = next(file for file in files if file["path"] == relative)
    revision = (root / "revisions" / str(manifest["revision"])).resolve()
    target = (revision / relative).resolve()
    if not revision.is_relative_to(root) or not target.is_relative_to(revision):
        raise ValueError("Asset escaped release directory")
    data = target.read_bytes()
    if len(data) > 8 * 1024 * 1024 or len(data) != metadata["size"] or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
        raise ValueError("Asset checksum mismatch")
    return data
