# SPDX-License-Identifier: GPL-3.0-only
# fastcsv: minimal CSV row splitter (vendored copy, Skopeo demo fixture).
# Copyright (C) 2019 fastcsv contributors


def split_row(line: str, sep: str = ",") -> list[str]:
    cells, current, quoted = [], [], False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == sep and not quoted:
            cells.append("".join(current))
            current = []
        else:
            current.append(ch)
    cells.append("".join(current))
    return cells
