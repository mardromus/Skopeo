"""License identification and compatibility classification (deterministic)."""

from __future__ import annotations

import re

_TEXT_FINGERPRINTS: list[tuple[str, list[str]]] = [
    ("AGPL-3.0", ["GNU AFFERO GENERAL PUBLIC LICENSE", "Version 3"]),
    ("LGPL-3.0", ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 3"]),
    ("LGPL-2.1", ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 2.1"]),
    ("GPL-3.0", ["GNU GENERAL PUBLIC LICENSE", "Version 3"]),
    ("GPL-2.0", ["GNU GENERAL PUBLIC LICENSE", "Version 2"]),
    ("MPL-2.0", ["Mozilla Public License", "2.0"]),
    ("Apache-2.0", ["Apache License", "Version 2.0"]),
    ("MIT", ["Permission is hereby granted, free of charge"]),
    ("BSD-3-Clause", ["Redistribution and use in source and binary forms", "Neither the name"]),
    ("BSD-2-Clause", ["Redistribution and use in source and binary forms"]),
    ("ISC", ["Permission to use, copy, modify, and/or distribute this software for any purpose"]),
    ("Unlicense", ["This is free and unencumbered software released into the public domain"]),
]

_ALIASES = {
    "mit": "MIT",
    "mit license": "MIT",
    "the mit license": "MIT",
    "apache": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd": "BSD",
    "bsd license": "BSD",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "new bsd license": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "isc": "ISC",
    "isc license (iscl)": "ISC",
    "mpl-2.0": "MPL-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "gpl-3.0": "GPL-3.0",
    "gpl-3.0-only": "GPL-3.0",
    "gpl-3.0-or-later": "GPL-3.0",
    "gplv3": "GPL-3.0",
    "gnu general public license v3 (gplv3)": "GPL-3.0",
    "gpl-2.0": "GPL-2.0",
    "gpl-2.0-only": "GPL-2.0",
    "gplv2": "GPL-2.0",
    "gnu general public license v2 (gplv2)": "GPL-2.0",
    "lgpl-3.0": "LGPL-3.0",
    "lgpl-2.1": "LGPL-2.1",
    "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0",
    "agpl-3.0": "AGPL-3.0",
    "agpl-3.0-only": "AGPL-3.0",
    "gnu affero general public license v3": "AGPL-3.0",
    "unlicense": "Unlicense",
    "psf": "PSF-2.0",
    "python software foundation license": "PSF-2.0",
}

_CLASS = {
    "MIT": "permissive",
    "Apache-2.0": "permissive",
    "BSD": "permissive",
    "BSD-3-Clause": "permissive",
    "BSD-2-Clause": "permissive",
    "ISC": "permissive",
    "Unlicense": "permissive",
    "PSF-2.0": "permissive",
    "MPL-2.0": "weak_copyleft",
    "LGPL-2.1": "weak_copyleft",
    "LGPL-3.0": "weak_copyleft",
    "GPL-2.0": "strong_copyleft",
    "GPL-3.0": "strong_copyleft",
    "AGPL-3.0": "network_copyleft",
}

SPDX_HEADER_RE = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.+\-() ]+)")


def identify_license_text(text: str) -> str | None:
    head = text[:6000]
    for spdx, needles in _TEXT_FINGERPRINTS:
        if all(n.lower() in head.lower() for n in needles):
            return spdx
    return None


def normalize_license(value: str | None) -> str | None:
    """Map free-form metadata ("MIT License", "Apache Software License", SPDX ids) to a canonical id."""
    if not value:
        return None
    raw = value.strip()
    key = raw.lower().rstrip(".")
    if key in _ALIASES:
        return _ALIASES[key]
    for token in re.split(r"\s+(?:OR|AND|/)\s+|\s*,\s*", raw):
        k = token.strip().lower()
        if k in _ALIASES:
            return _ALIASES[k]
    upper = raw.upper()
    for canonical in _CLASS:
        if canonical.upper() == upper or upper.startswith(canonical.upper() + "-"):
            return canonical
    return None


def normalize_expression(value: str | None) -> list[str]:
    """Return every recognised license in an expression ("Apache-2.0 OR BSD-3-Clause")."""
    if not value:
        return []
    found = []
    for token in re.split(r"\s+(?:OR|AND)\s+|\s*/\s*|\s*,\s*|[()]", value):
        norm = normalize_license(token)
        if norm and norm not in found:
            found.append(norm)
    if not found:
        norm = normalize_license(value)
        if norm:
            found.append(norm)
    return found


def classify(spdx: str | None) -> str:
    if not spdx:
        return "unknown"
    return _CLASS.get(spdx, "unknown")


def compatibility_issue(project_license: str | None, component_license: str | None) -> tuple[str, str] | None:
    """Return (severity, explanation) when ``component_license`` imposes obligations that conflict
    with the project's declared license, else None."""
    proj = classify(project_license)
    comp = classify(component_license)
    if comp == "unknown" or proj == "unknown":
        return None
    if proj == "permissive" and comp == "network_copyleft":
        return (
            "high",
            f"{component_license} (network copyleft) code inside a {project_license} project obliges source disclosure for network use",
        )
    if proj == "permissive" and comp == "strong_copyleft":
        return (
            "high",
            f"{component_license} (strong copyleft) code inside a {project_license} project forces the combined work to be distributed under {component_license}",
        )
    if proj == "permissive" and comp == "weak_copyleft":
        return "low", f"{component_license} (weak copyleft) requires modifications to that component to remain under {component_license}"
    return None
