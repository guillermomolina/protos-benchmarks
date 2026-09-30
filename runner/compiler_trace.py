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

"""Pure Truffle/Graal compiler-trace record splitting and event parsing.

No I/O and no Docker: everything here maps raw diagnostic text to ordered records so that every
derived summary is reproducible from the retained raw log alone. The grammar handled here is the
one observed in the retained GraalVM 25.4.4.1.1 `engine.TraceCompilation` /
`TraceCompilationDetails` / `CompilationFailureAction=Print` / `compiler.TraceInlining` output
(results/upstream003-platform-comparison/diagnostic/logs) and the `compiler.TracePerformanceWarnings`
output retained by PERF003-A:

    [engine] opt queued engine=2  id=149   Root@4ae9cfc1   |Tier 1|Count/Thres ...|UTC ...|Src n/a
    [engine] opt start  engine=2  id=149   Root@4ae9cfc1   |Tier 1|Priority ...|UTC ...|Src n/a
    [engine] opt done   engine=2  id=149   Root@4ae9cfc1   |Tier 1|Time ...|CompId 2585   |UTC ...
    [engine] opt failed engine=2  id=150   Root@6326d182   |Tier 1|Time ...|Reason: <multi-line>
    [engine] opt fail     Root@6326d182                    |AST      2   (failure detail, multi-line)
    [engine] opt unque. engine=2  id=153   Root@52b56a3e   |Tier 1|...|Reason Stale compilation task
    [engine] opt deopt  engine=2  id=149   Root@4ae9cfc1   |Invalidated  true|...|Reason uncommon trap

A record starts at a line beginning with a recognised prefix; every other line is a continuation of
the current record. Nothing is discarded: unrecognised lines are kept as records of kind OTHER or as
continuation text, and an `opt` line whose verb is not known yields kind OPT_UNKNOWN so the caller can
fail closed instead of silently ignoring a lifecycle event it does not understand.
"""

from __future__ import annotations

import re
from typing import Any

MARKER_PREFIX = "PERF010A_HOTROOT_MARK "

# Record kinds.
OPT_QUEUED = "OPT_QUEUED"
OPT_START = "OPT_START"
OPT_DONE = "OPT_DONE"
OPT_FAILED = "OPT_FAILED"
OPT_FAIL_DETAIL = "OPT_FAIL_DETAIL"
OPT_DEQUEUED = "OPT_DEQUEUED"
OPT_DEOPT = "OPT_DEOPT"
OPT_INVALIDATED = "OPT_INVALIDATED"
OPT_UNKNOWN = "OPT_UNKNOWN"
OPT_UNPARSED = "OPT_UNPARSED"
INLINE_START = "INLINE_START"
INLINE_DONE = "INLINE_DONE"
INLINE_DECISION = "INLINE_DECISION"
PERF_WARN = "PERF_WARN"
DUMP_FILE = "DUMP_FILE"
DUMP_DIR = "DUMP_DIR"
ENGINE_WARNING = "ENGINE_WARNING"
ENGINE_OTHER = "ENGINE_OTHER"
JVM_WARNING = "JVM_WARNING"
MARK = "MARK"
OTHER = "OTHER"

LIFECYCLE_KINDS = frozenset(
    {
        OPT_QUEUED,
        OPT_START,
        OPT_DONE,
        OPT_FAILED,
        OPT_FAIL_DETAIL,
        OPT_DEQUEUED,
        OPT_DEOPT,
        OPT_INVALIDATED,
        OPT_UNKNOWN,
        OPT_UNPARSED,
    }
)

# Verbs are matched exactly. The invalidation aliases were not observed in the retained logs; they
# are accepted because their meaning is unambiguous. Any other verb becomes OPT_UNKNOWN.
VERB_KINDS = {
    "queued": OPT_QUEUED,
    "start": OPT_START,
    "done": OPT_DONE,
    "failed": OPT_FAILED,
    "fail": OPT_FAIL_DETAIL,
    "unque.": OPT_DEQUEUED,
    "deopt": OPT_DEOPT,
    "inv.": OPT_INVALIDATED,
    "inv": OPT_INVALIDATED,
    "invalid": OPT_INVALIDATED,
    "invalidated": OPT_INVALIDATED,
}

OPT_RE = re.compile(
    r"^\[engine\] opt (?P<verb>[A-Za-z.]+)\s+"
    r"(?:engine=(?P<engine>\d+)\s+id=(?P<id>\d+)\s+)?"
    r"(?P<label>[^\s|]+)(?P<rest>\s*\|.*|\s*)$"
)
INLINE_RE = re.compile(
    r"^\[engine\] (?P<verb>Inline start|Inline done|Inlined|Cutoff|Removed|Expanded|Indirect|BailedOut)"
    r"\s+(?P<label>\S+)\s*\|(?P<rest>.*)$"
)
PERF_WARN_RE = re.compile(r"^\[engine\] perf warn\s+(?P<label>\S+)\s*\|(?P<message>.*)$")
ENGINE_WARNING_RE = re.compile(r"^\[engine\] WARNING: (?P<text>.*)$")
DEPRECATED_OPTION_RE = re.compile(r"Option '(?P<option>[^']+)' is deprecated")
DUMP_FILE_RE = re.compile(r"^Dumping debug output to '(?P<path>[^']*)'\s*$")
DUMP_DIR_RE = re.compile(r"^Dumping IGV graphs in (?P<path>.+?)\s*$")
DUMP_NAME_RE = re.compile(r"TruffleHotSpotCompilation-(?P<comp_id>\d+)\[(?P<label>[^\]]*)\]")
MARK_RE = re.compile(r"^" + re.escape(MARKER_PREFIX) + r"phase=(?P<phase>[A-Za-z0-9_.-]+)(?P<extra>.*)$")
TIER_RE = re.compile(r"\|Tier\s+(?P<tier>\d+)")
COMP_ID_RE = re.compile(r"\|CompId\s+(?P<comp_id>\d+)")
INVALIDATED_RE = re.compile(r"\|Invalidated\s+(?P<value>true|false)")
REASON_RE = re.compile(r"\|Reason:?\s*(?P<reason>.*)$", re.DOTALL)
SRC_RE = re.compile(r"\|Src\s+(?P<src>[^|]*)")
UTC_RE = re.compile(r"\|UTC\s+(?P<utc>[^|]*)")
TOKEN_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z /]*?)\s+(?P<value>\S+)$")
TARGET_RE = re.compile(r"HotSpotMethod<(?P<target>.*?)>\s+\((?P<node>\d+\|\w+)\)")
FRAME_RE = re.compile(r"^\s+at\s+(?P<frame>\S.*)$")
OPTION_REJECTION_RE = re.compile(
    r"(?i)could not find option|is experimental and must be enabled|unrecognized (?:vm )?option"
    r"|invalid (?:boolean )?option value|unknown option|error parsing (?:graal )?options"
)
PERMANENT_BAILOUT_RE = re.compile(r"PermanentBailoutException")
BAILOUT_RE = re.compile(r"BailoutException")


class TraceRecord:
    """One ordered record: `seq` is its 0-based ordinal, `line` its 1-based first raw line.

    A plain class (not a dataclass): runner modules are loaded by file path in tests, where a
    dataclass with postponed annotations would need the module registered in `sys.modules`."""

    __slots__ = ("seq", "line", "kind", "lines", "fields")

    def __init__(self, seq: int, line: int, kind: str, lines: list[str]) -> None:
        self.seq = seq
        self.line = line
        self.kind = kind
        self.lines = lines
        self.fields: dict[str, Any] = {}

    @property
    def end_line(self) -> int:
        return self.line + len(self.lines) - 1

    @property
    def raw(self) -> str:
        return "\n".join(self.lines)

    @property
    def header(self) -> str:
        return self.lines[0] if self.lines else ""


def _tokens(rest: str) -> dict[str, str]:
    """Generic `|Key value|Key value` tokens of a header, for records without free text."""
    out: dict[str, str] = {}
    for token in rest.split("|"):
        match = TOKEN_RE.match(token.strip())
        if match:
            out.setdefault(match.group("key").strip(), match.group("value"))
    return out


def _start_kind(line: str) -> str | None:
    """The record kind that `line` opens, or None if it is a continuation line."""
    if line.startswith(MARKER_PREFIX):
        return MARK
    if line.startswith("[engine] opt "):
        return OPT_UNPARSED  # refined by parse_header
    if line.startswith("[engine] perf warn"):
        return PERF_WARN
    if line.startswith("[engine] WARNING: "):
        return ENGINE_WARNING
    if INLINE_RE.match(line):
        return INLINE_DECISION
    if line.startswith("[engine] "):
        return ENGINE_OTHER
    if DUMP_FILE_RE.match(line):
        return DUMP_FILE
    if DUMP_DIR_RE.match(line):
        return DUMP_DIR
    if line.startswith("WARNING: "):
        return JVM_WARNING
    if line.startswith("[To redirect Truffle log output"):
        return OTHER
    return None


def _parse_header(record: TraceRecord) -> None:
    header = record.header
    kind = record.kind
    fields = record.fields
    if kind == MARK:
        match = MARK_RE.match(header)
        if match is None:
            record.kind = OTHER
            return
        fields["phase"] = match.group("phase")
        fields["extra"] = match.group("extra").strip()
    elif kind == OPT_UNPARSED:
        match = OPT_RE.match(header)
        if match is None:
            return
        record.kind = VERB_KINDS.get(match.group("verb"), OPT_UNKNOWN)
        fields["verb"] = match.group("verb")
        fields["label"] = match.group("label")
        fields["engine"] = int(match.group("engine")) if match.group("engine") else None
        fields["id"] = int(match.group("id")) if match.group("id") else None
        rest = match.group("rest")
        tier = TIER_RE.search(rest)
        fields["tier"] = int(tier.group("tier")) if tier else None
        comp = COMP_ID_RE.search(rest)
        fields["comp_id"] = int(comp.group("comp_id")) if comp else None
        invalidated = INVALIDATED_RE.search(rest)
        fields["invalidated"] = (invalidated.group("value") == "true") if invalidated else None
        reason = REASON_RE.search(rest)
        fields["reason"] = reason.group("reason").strip() if reason else None
        for name, regex in (("src", SRC_RE), ("utc", UTC_RE)):
            found = regex.search(rest if reason is None else rest[: reason.start()])
            fields[name] = found.group(name).strip() if found else None
    elif kind == PERF_WARN:
        match = PERF_WARN_RE.match(header)
        if match is None:
            record.kind = ENGINE_OTHER
            return
        fields["label"] = match.group("label")
        message = match.group("message").strip()
        fields["message"] = message
        target = TARGET_RE.search(message)
        fields["target"] = target.group("target") if target else None
        fields["node"] = target.group("node") if target else None
        fields["frames"] = [
            frame.group("frame").strip()
            for frame in (FRAME_RE.match(text) for text in record.lines[1:])
            if frame
        ]
    elif kind == INLINE_DECISION:
        match = INLINE_RE.match(header)
        verb = match.group("verb")
        record.kind = {"Inline start": INLINE_START, "Inline done": INLINE_DONE}.get(
            verb, INLINE_DECISION
        )
        fields["verb"] = verb
        fields["label"] = match.group("label")
        fields["values"] = _tokens(match.group("rest"))
    elif kind == ENGINE_WARNING:
        text = ENGINE_WARNING_RE.match(header).group("text")
        fields["text"] = text
        option = DEPRECATED_OPTION_RE.search(text)
        fields["deprecated_option"] = option.group("option") if option else None
    elif kind == DUMP_FILE:
        path = DUMP_FILE_RE.match(header).group("path")
        fields["path"] = path
        name = DUMP_NAME_RE.search(path)
        fields["comp_id"] = int(name.group("comp_id")) if name else None
        fields["label"] = name.group("label") if name else None
    elif kind == DUMP_DIR:
        fields["path"] = DUMP_DIR_RE.match(header).group("path")


def split_records(text: str) -> list[TraceRecord]:
    """Ordered records of a raw diagnostic log. Lossless: `"\\n".join(r.raw for r in records)`
    reproduces the input (modulo a final newline)."""
    records: list[TraceRecord] = []
    current: TraceRecord | None = None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for number, line in enumerate(lines, start=1):
        line = line.rstrip("\r")
        kind = _start_kind(line)
        if kind is None and current is None:
            kind = OTHER
        if kind is not None:
            if current is not None:
                _parse_header(current)
            current = TraceRecord(seq=len(records), line=number, kind=kind, lines=[line])
            records.append(current)
        else:
            current.lines.append(line)
    if current is not None:
        _parse_header(current)
    return records


def classify_failure(text: str) -> str:
    """PERMANENT, TEMPORARY or ERROR from the raw failure text (header plus continuation)."""
    if PERMANENT_BAILOUT_RE.search(text):
        return "PERMANENT"
    if BAILOUT_RE.search(text):
        return "TEMPORARY"
    return "ERROR"


def find_option_rejections(text: str) -> list[str]:
    """Lines of a raw log that show a diagnostic option was rejected by the runtime."""
    return [line.strip() for line in text.splitlines() if OPTION_REJECTION_RE.search(line)]


def deprecated_options(records: list[TraceRecord]) -> list[str]:
    return sorted(
        {
            record.fields["deprecated_option"]
            for record in records
            if record.kind == ENGINE_WARNING and record.fields.get("deprecated_option")
        }
    )
