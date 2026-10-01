#!/usr/bin/env python3
# THE LICENSED WORK IS PROVIDED UNDER THE TERMS OF THE ADAPTIVE PUBLIC LICENSE
# ("LICENSE") AS FIRST COMPLETED BY: Guillermo Adrián Molina. ANY USE, PUBLIC
# DISPLAY, PUBLIC PERFORMANCE, REPRODUCTION OR DISTRIBUTION OF, OR PREPARATION OF
# DERIVATIVE WORKS BASED ON, THE LICENSED WORK CONSTITUTES RECIPIENT'S ACCEPTANCE
# OF THIS LICENSE AND ITS TERMS, WHETHER OR NOT SUCH RECIPIENT READS THE TERMS OF
# THE LICENSE. "LICENSED WORK" AND "RECIPIENT" ARE DEFINED IN THE LICENSE. A COPY
# OF THE LICENSE IS LOCATED IN THE TEXT FILE ENTITLED "LICENSE.TXT" ACCOMPANYING
# THE CONTENTS OF THIS FILE. IF A COPY OF THE LICENSE DOES NOT ACCOMPANY THIS
# FILE, A COPY OF THE LICENSE MAY ALSO BE OBTAINED AT THE FOLLOWING WEB SITE:
# https://github.com/guillermomolina/protos-benchmarks
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

TRUFFLE = Path(__file__).resolve().parent
CATALOG = TRUFFLE / "workloads" / "catalog.json"
LANGUAGES = ("protos", "js", "python")


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict[str, object]]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))

    if data.get("schema") != 1:
        raise RuntimeError("unsupported workload catalog schema")

    raw = data.get("workloads")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError("workload catalog must contain workloads")

    result: dict[str, dict[str, object]] = {}
    truffle_root = TRUFFLE.resolve()

    for entry in raw:
        if not isinstance(entry, dict):
            raise RuntimeError("workload entry must be an object")

        name = entry.get("id")
        expected = entry.get("expected")
        sources = entry.get("sources")

        if not isinstance(name, str) or not name:
            raise RuntimeError("workload id must be a non-empty string")

        if name in result:
            raise RuntimeError(f"duplicate workload id: {name}")

        if not isinstance(expected, str) or not expected:
            raise RuntimeError(
                f"{name}: expected result must be a non-empty string"
            )

        if not isinstance(sources, dict):
            raise RuntimeError(f"{name}: sources must be an object")

        resolved: dict[str, Path] = {}

        for language in LANGUAGES:
            relative = sources.get(language)

            if not isinstance(relative, str) or not relative:
                raise RuntimeError(
                    f"{name}: missing source for {language}"
                )

            path = (TRUFFLE / relative).resolve()

            try:
                path.relative_to(truffle_root)
            except ValueError as exc:
                raise RuntimeError(
                    f"{name}/{language} escapes truffle root: {path}"
                ) from exc

            if not path.is_file():
                raise RuntimeError(
                    f"{name}/{language} source missing: {path}"
                )

            resolved[language] = path

        result[name] = {
            "expected": expected,
            "sources": resolved,
        }

    return result


def workload_ids() -> tuple[str, ...]:
    return tuple(catalog())


def select_workloads(selector: str) -> tuple[str, ...]:
    available = workload_ids()

    if selector == "all":
        return available

    if selector not in catalog():
        raise ValueError(
            "unknown workload "
            f"{selector!r}; expected all or one of "
            + ", ".join(available)
        )

    return (selector,)


def source_for(workload: str, language: str) -> Path:
    if language not in LANGUAGES:
        raise ValueError(
            f"unknown language {language!r}; expected "
            + ", ".join(LANGUAGES)
        )

    item = catalog().get(workload)

    if item is None:
        raise ValueError(f"unknown workload: {workload}")

    return item["sources"][language]


def expected_result(workload: str) -> str:
    item = catalog().get(workload)

    if item is None:
        raise ValueError(f"unknown workload: {workload}")

    return str(item["expected"])


def cases_for_selection(
    selector: str,
) -> tuple[tuple[str, str, Path], ...]:
    return tuple(
        (
            language,
            workload,
            source_for(workload, language),
        )
        for workload in select_workloads(selector)
        for language in LANGUAGES
    )


def protos_workloads_for_selection(
    selector: str,
) -> tuple[tuple[str, Path], ...]:
    return tuple(
        (workload, source_for(workload, "protos"))
        for workload in select_workloads(selector)
    )
