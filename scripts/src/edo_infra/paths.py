"""Filesystem layout of the infrastructure checkout (single source of defaults)."""

from __future__ import annotations

from pathlib import Path

#: ``.../infrastructure/scripts`` — this package's project directory
SCRIPTS_DIR = Path(__file__).resolve().parents[2]
#: ``.../infrastructure/scripts/src`` — where the ``edo_infra`` package lives
PACKAGE_SRC = SCRIPTS_DIR / "src"
#: ``.../infrastructure``
INFRA_DIR = SCRIPTS_DIR.parent
#: ``...`` — the edo root (infrastructure is a submodule of it)
EDO_ROOT = INFRA_DIR.parent

#: default RDMO instance directory
DEFAULT_RDMO_APP = INFRA_DIR / "Servers" / "rdmo-app"
#: default directory for RDMO project XML fixtures
DEFAULT_XML_DIR = INFRA_DIR / "fixtures" / "rdmo"
#: default maDMP exporter package directory
DEFAULT_EXPORTER = EDO_ROOT / "components" / "socket-rdmo" / "madmp-exporter"
