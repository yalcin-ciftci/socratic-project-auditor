"""Resolve contracts in a checkout, legacy integration, or installed wheel."""
from importlib.resources import files
from pathlib import Path


def resolve_specs(root: Path | None = None) -> Path:
    if root is not None:
        for candidate in (Path(root) / 'specs', Path(root) /
                          '🛠️ 600-Arsenal/Ajanlar/proje-denetleyici-ve-ogrenim-sorgulayicisi'):
            if (candidate / 'CONTRACT.md').is_file():
                return candidate
    return Path(str(files('project_auditor_runtime.specs')))
