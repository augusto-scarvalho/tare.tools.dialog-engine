"""External-memory indexing and compact graph sharding for Watson Dialog exports.

This module deliberately separates three concerns:

* the JSON export remains the source payload;
* :class:`DialogSourceIndex` keeps only compact structural metadata in memory;
* :class:`CompactGraph` represents graph topology with integer arrays and can
  produce semantic work shards without materializing node payloads.

The scanner is stdlib-only and works from an mmap.  It does not call
``json.load``.  Individual scalar fields are decoded independently and full
records are materialized only on explicit request.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path when invoked directly
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


import hashlib
import json
import mmap
import os
import tempfile
from array import array
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tare_dialog.resources import resolve_max_input_bytes

_WS = b" \t\r\n"
_DEFAULT_IGNORED_FIELDS = frozenset({"dataCriacao", "dataModificacao"})


class JsonStructureError(ValueError):
    pass


class _MappedJson:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = path.open("rb")
        try:
            self.mm = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception:
            self._file.close()
            raise

    def close(self) -> None:
        try:
            self.mm.close()
        finally:
            self._file.close()

    def __enter__(self) -> _MappedJson:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def skip_ws(self, pos: int, limit: int | None = None) -> int:
        end = len(self.mm) if limit is None else limit
        while pos < end and self.mm[pos] in _WS:
            pos += 1
        return pos

    def string_end(self, pos: int, limit: int | None = None) -> int:
        end = len(self.mm) if limit is None else limit
        if pos >= end or self.mm[pos] != 34:  # '"'
            raise JsonStructureError(f"String JSON esperada em byte {pos}")
        pos += 1
        escaped = False
        while pos < end:
            byte = self.mm[pos]
            if escaped:
                escaped = False
            elif byte == 92:  # '\\'
                escaped = True
            elif byte == 34:
                return pos + 1
            pos += 1
        raise JsonStructureError("String JSON não terminada")

    def value_end(self, pos: int, limit: int | None = None) -> int:
        end = len(self.mm) if limit is None else limit
        pos = self.skip_ws(pos, end)
        if pos >= end:
            raise JsonStructureError("Valor JSON ausente")
        first = self.mm[pos]
        if first == 34:
            return self.string_end(pos, end)
        if first in (123, 91):  # { [
            opening = first
            expected = 125 if opening == 123 else 93
            stack = [expected]
            i = pos + 1
            in_string = False
            escaped = False
            while i < end:
                byte = self.mm[i]
                if in_string:
                    if escaped:
                        escaped = False
                    elif byte == 92:
                        escaped = True
                    elif byte == 34:
                        in_string = False
                else:
                    if byte == 34:
                        in_string = True
                    elif byte == 123:
                        if len(stack) > 500:
                            raise JsonStructureError("Profundidade máxima de aninhamento JSON excedida")
                        stack.append(125)
                    elif byte == 91:
                        if len(stack) > 500:
                            raise JsonStructureError("Profundidade máxima de aninhamento JSON excedida")
                        stack.append(93)
                    elif byte in (125, 93):
                        if not stack or byte != stack[-1]:
                            raise JsonStructureError(f"Fechamento JSON inesperado em byte {i}")
                        stack.pop()
                        if not stack:
                            return i + 1
                i += 1
            raise JsonStructureError("Objeto/array JSON não terminado")
        if first in b",]}:":
            raise JsonStructureError(f"Valor JSON inesperado em byte {pos}")
        i = pos
        while i < end and self.mm[i] not in b",]} \t\r\n":
            i += 1
        if i == pos:
            raise JsonStructureError(f"Valor JSON ausente em byte {pos}")
        return i

    def decode(self, start: int, end: int) -> Any:
        return json.loads(self.mm[start:end])

    def object_fields(self, start: int, end: int) -> Iterator[tuple[str, int, int]]:
        pos = self.skip_ws(start, end)
        if pos >= end or self.mm[pos] != 123:
            raise JsonStructureError(f"Objeto JSON esperado em byte {pos}")
        pos += 1
        while True:
            pos = self.skip_ws(pos, end)
            if pos >= end:
                raise JsonStructureError("Objeto JSON não terminado")
            if self.mm[pos] == 125:
                return
            key_start = pos
            key_end = self.string_end(key_start, end)
            key = str(self.decode(key_start, key_end))
            pos = self.skip_ws(key_end, end)
            if pos >= end or self.mm[pos] != 58:
                raise JsonStructureError(f"':' esperado após chave {key!r}")
            value_start = self.skip_ws(pos + 1, end)
            value_end = self.value_end(value_start, end)
            yield key, value_start, value_end
            pos = self.skip_ws(value_end, end)
            if pos < end and self.mm[pos] == 44:
                pos += 1
                continue
            if pos < end and self.mm[pos] == 125:
                return
            raise JsonStructureError(f"Separador inválido após chave {key!r}")

    def array_items(self, start: int, end: int) -> Iterator[tuple[int, int]]:
        pos = self.skip_ws(start, end)
        if pos >= end or self.mm[pos] != 91:
            raise JsonStructureError(f"Array JSON esperado em byte {pos}")
        pos += 1
        while True:
            pos = self.skip_ws(pos, end)
            if pos >= end:
                raise JsonStructureError("Array JSON não terminado")
            if self.mm[pos] == 93:
                return
            item_start = pos
            item_end = self.value_end(item_start, end)
            if item_start == item_end:
                raise JsonStructureError("Item vazio em array JSON")
            yield item_start, item_end
            pos = self.skip_ws(item_end, end)
            if pos < end and self.mm[pos] == 44:
                pos += 1
                continue
            if pos < end and self.mm[pos] == 93:
                return
            raise JsonStructureError("Separador inválido em array JSON")


@dataclass(frozen=True, slots=True)
class RecordRef:
    record_id: str
    source_id: str
    kind: str
    start: int
    end: int
    local_bytes: int
    parent_id: str | None
    sequence: int | None
    previous_sibling: str | None
    name: str | None
    condition: str | None
    folder: bool
    jump_target: str | None
    jump_selector: str | None
    semantic_digest: str | None

    @property
    def byte_length(self) -> int:
        return self.end - self.start

    @property
    def work_weight(self) -> int:
        # Payload size matters for diff/validation work, but cap the influence
        # so a single verbose node cannot monopolize a shard indefinitely.
        return max(1, min(64, 1 + self.local_bytes // 4096))


@dataclass(frozen=True, slots=True)
class CollectionItemRef:
    item_id: str
    start: int
    end: int
    semantic_digest: str

    @property
    def byte_length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class OrderedItemRef:
    """One item in an order-sensitive root JSON array.

    ``stable_digest`` is computed from the same canonical serialization used
    by :func:`watson_dialog_diff.stable_item`, including fields that may later
    be ignored by the semantic diff.  This matters for exact parity with the
    incumbent ``SequenceMatcher`` alignment semantics.

    The digest is only a compact candidate token.  The diff layer performs an
    exact canonical-byte collision check whenever a digest occurs more than
    once across the two sequences before feeding tokens to ``SequenceMatcher``.
    """

    ordinal: int
    start: int
    end: int
    stable_digest: str

    @property
    def byte_length(self) -> int:
        return self.end - self.start


class DialogSourceIndex:
    """Source-backed structural index that never materializes the full export."""

    def __init__(
        self,
        path: Path,
        mapped: _MappedJson,
        format_type: str,
        capture_details: bool = False,
        ignored_fields: Iterable[str] | None = None,
    ) -> None:
        self.path = path
        self._mapped = mapped
        self.format_type = format_type
        self.capture_details = capture_details
        self.ignored_fields = frozenset(_DEFAULT_IGNORED_FIELDS if ignored_fields is None else ignored_fields)
        self.records: dict[str, RecordRef] = {}
        self.children_by_parent: dict[str | None, list[str]] = {}
        self.roots: list[str] = []
        self.top_level_counts: dict[str, int] = {}
        self.root_fields: dict[str, tuple[int, int]] = {}
        self._collection_cache: dict[tuple[str, str], dict[str, CollectionItemRef] | None] = {}
        self._ordered_array_cache: dict[str, list[OrderedItemRef] | None] = {}
        self._local_spool = tempfile.TemporaryFile(mode="w+b") if capture_details else None
        self._local_spool_ranges: dict[str, tuple[int, int]] = {}
        self._local_spool_bytes = 0
        self.file_size_bytes = path.stat().st_size

    @classmethod
    def open(
        cls,
        path: Path,
        max_bytes: int | None = None,
        *,
        capture_details: bool = False,
        ignored_fields: Iterable[str] | None = None,
    ) -> DialogSourceIndex:
        if not path.exists():
            raise ValueError(f"File not found: {path}")
        max_bytes = resolve_max_input_bytes(max_bytes)
        size = path.stat().st_size
        if max_bytes and max_bytes > 0 and size > max_bytes:
            raise ValueError(
                f"File {path} ({size} bytes) exceeds configured limit of {max_bytes} bytes. "
                "Use --max-input-bytes to increase limit if necessary."
            )
        mapped = _MappedJson(path)
        try:
            index = cls(
                path,
                mapped,
                "unknown",
                capture_details=capture_details,
                ignored_fields=ignored_fields,
            )
            index._build()
            return index
        except Exception:
            mapped.close()
            raise

    def close(self) -> None:
        try:
            if self._local_spool is not None:
                self._local_spool.close()
        finally:
            self._mapped.close()

    def __enter__(self) -> DialogSourceIndex:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _local_payload_bytes(self, fields: dict[str, tuple[int, int]], excluded: set[str]) -> bytes:
        parts: list[bytes] = []
        for key, (start, end) in fields.items():
            if key in excluded:
                continue
            parts.append(json.dumps(key, ensure_ascii=False).encode("utf-8") + b":" + bytes(self._mapped.mm[start:end]))
        return b"{" + b",".join(parts) + b"}"

    def _spool_local_record(self, record_id: str, fields: dict[str, tuple[int, int]], excluded: set[str]) -> None:
        if self._local_spool is None:
            return
        payload = self._local_payload_bytes(fields, excluded)
        self._local_spool.seek(0, os.SEEK_END)
        start = self._local_spool.tell()
        self._local_spool.write(payload)
        end = start + len(payload)
        self._local_spool_ranges[str(record_id)] = (start, end)
        self._local_spool_bytes = end

    def _read_local_spool(self, record_id: str) -> bytes | None:
        bounds = self._local_spool_ranges.get(str(record_id))
        if bounds is None or self._local_spool is None:
            return None
        start, end = bounds
        self._local_spool.seek(start)
        return self._local_spool.read(end - start)

    def _decoded_field(self, fields: dict[str, tuple[int, int]], name: str, default: Any = None) -> Any:
        value = fields.get(name)
        if value is None:
            return default
        return self._mapped.decode(*value)

    @staticmethod
    def _local_bytes(fields: dict[str, tuple[int, int]], excluded: set[str]) -> int:
        return sum(end - start for key, (start, end) in fields.items() if key not in excluded)

    def _semantic_digest(self, fields: dict[str, tuple[int, int]], excluded: set[str]) -> str:
        """Return a conservative local-record rejection digest.

        This digest is deliberately computed from the original JSON bytes, not
        from a decoded/canonicalized Python object.  Digest *equality* therefore
        proves that every non-ignored local field has identical source bytes and
        can safely skip a detailed semantic comparison.  Digest *inequality* is
        only a candidate-change signal: whitespace, numeric spelling, escape
        style or nested object-key ordering may cause a false positive, after
        which the normal semantic diff decides whether a real change exists.

        That asymmetry is intentional.  A rejection filter must never create a
        false negative, while false positives cost only bounded extra work.  It
        also avoids json.loads/json.dumps for every field in a large mmap-backed
        export, which is the dominant CPU cost on constrained runtimes.
        """
        digest = hashlib.blake2b(digest_size=16)
        for key in sorted(fields):
            if key in excluded or key in self.ignored_fields:
                continue
            start, end = fields[key]
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
            digest.update(self._mapped.mm[start:end])
            digest.update(b"\0")
        return digest.hexdigest()

    def _canonical_digest(self, fields: dict[str, tuple[int, int]], excluded: set[str]) -> str:
        """Canonical digest for comparatively small root UUID collections.

        Root collections such as ``entidades`` can have equivalent objects
        serialized with different whitespace/key ordering.  A raw-byte digest
        would safely reject fewer items and then force expensive semantic
        comparisons for most of the collection.  These collections are much
        smaller than ``nos``, so canonicalization is an evidence-backed trade:
        spend bounded CPU here to avoid hundreds of false-positive work items.
        """
        digest = hashlib.blake2b(digest_size=16)
        for key in sorted(fields):
            if key in excluded or key in self.ignored_fields:
                continue
            start, end = fields[key]
            try:
                value = self._mapped.decode(start, end)
                rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                rendered = bytes(self._mapped.mm[start:end])
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
            digest.update(rendered)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _stable_value_bytes(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _stable_item_digest(self, start: int, end: int) -> str:
        value = self._mapped.decode(start, end)
        rendered = self._stable_value_bytes(value)
        return hashlib.sha256(rendered).hexdigest()

    def _build(self) -> None:
        """Build the structural index with a single-pass legacy fast path.

        The original mmap implementation first discovered the byte range of a
        complete ``nos`` subtree and then recursively rescanned the same nested
        ``filhos``/``slots`` containers while indexing descendants.  On deep
        dialogs that makes the strict low-memory backend spend substantially
        more CPU than the encoded file size suggests.

        Legacy exports now parse the root object incrementally and descend into
        ``nos`` exactly when that field is encountered.  Nested dialog arrays
        are consumed by the same cursor and return their end offset to the
        parent.  Local scalar/object values still use :meth:`value_end`, but a
        dialog subtree is not scanned once per ancestor anymore.

        V1 keeps the incumbent byte-range scanner for now; this slice changes
        no V1 semantic contract.
        """
        mm = self._mapped
        pos = mm.skip_ws(0)
        if pos >= len(mm.mm) or mm.mm[pos] != 123:
            raise ValueError(f"{self.path} deve conter um objeto JSON na raiz.")
        pos += 1
        root_fields: dict[str, tuple[int, int]] = {}
        legacy_seen = False
        v1_range: tuple[int, int] | None = None

        while True:
            pos = mm.skip_ws(pos)
            if pos >= len(mm.mm):
                raise JsonStructureError("Objeto JSON raiz não terminado")
            if mm.mm[pos] == 125:  # '}'
                pos += 1
                break

            key_start = pos
            key_end = mm.string_end(key_start)
            key = str(mm.decode(key_start, key_end))
            pos = mm.skip_ws(key_end)
            if pos >= len(mm.mm) or mm.mm[pos] != 58:  # ':'
                raise JsonStructureError(f"':' esperado após chave raiz {key!r}")
            value_start = mm.skip_ws(pos + 1)

            if key == "nos":
                value_end = self._index_legacy_array_stream(value_start, parent_id=None)
                legacy_seen = True
            else:
                value_end = mm.value_end(value_start)
                if key == "dialog_nodes":
                    v1_range = (value_start, value_end)
            root_fields[key] = (value_start, value_end)

            pos = mm.skip_ws(value_end)
            if pos < len(mm.mm) and mm.mm[pos] == 44:  # ','
                pos += 1
                continue
            if pos < len(mm.mm) and mm.mm[pos] == 125:
                pos += 1
                break
            raise JsonStructureError(f"Separador inválido após chave raiz {key!r}")

        self.root_fields = root_fields
        if legacy_seen:
            self.format_type = "legacy"
            for name in ("intencoes", "entidades", "variaveisContexto"):
                if name in root_fields:
                    self.top_level_counts[name] = sum(1 for _ in mm.array_items(*root_fields[name]))
        elif v1_range is not None:
            self.format_type = "v1"
            self._index_v1_array(*v1_range)
            for name in ("intents", "entities"):
                if name in root_fields:
                    self.top_level_counts[name] = sum(1 for _ in mm.array_items(*root_fields[name]))
        else:
            raise ValueError("Dialog must contain 'nos' (legacy) or 'dialog_nodes' (V1 API).")

    def _index_legacy_array_stream(self, start: int, parent_id: str | None) -> int:
        """Index a legacy node array while consuming each subtree once.

        Returns the byte offset immediately after the closing ``]`` so the
        caller can continue parsing its containing object without a separate
        structural scan.
        """
        mm = self._mapped
        pos = mm.skip_ws(start)
        if pos >= len(mm.mm) or mm.mm[pos] != 91:  # '['
            raise JsonStructureError(f"Expected JSON array at byte {pos}")
        pos += 1
        while True:
            pos = mm.skip_ws(pos)
            if pos >= len(mm.mm):
                raise JsonStructureError("Unterminated legacy JSON array")
            if mm.mm[pos] == 93:  # ']'
                return pos + 1
            if mm.mm[pos] == 123:  # '{'
                item_end = self._index_legacy_node_stream(pos, parent_id)
            else:
                # Preserve the incumbent tolerance for non-object items: skip
                # them rather than inventing a dialog node.
                item_end = mm.value_end(pos)
            pos = mm.skip_ws(item_end)
            if pos < len(mm.mm) and mm.mm[pos] == 44:
                pos += 1
                continue
            if pos < len(mm.mm) and mm.mm[pos] == 93:
                return pos + 1
            raise JsonStructureError("Invalid separator in legacy array")

    def _index_legacy_slots_stream(self, start: int, owner_id: str) -> int:
        mm = self._mapped
        pos = mm.skip_ws(start)
        if pos >= len(mm.mm) or mm.mm[pos] != 91:
            raise JsonStructureError(f"Expected JSON array at byte {pos}")
        pos += 1
        while True:
            pos = mm.skip_ws(pos)
            if pos >= len(mm.mm):
                raise JsonStructureError("Unterminated slots array")
            if mm.mm[pos] == 93:
                return pos + 1
            if mm.mm[pos] == 123:
                item_end = self._index_legacy_slot_stream(pos, owner_id)
            else:
                item_end = mm.value_end(pos)
            pos = mm.skip_ws(item_end)
            if pos < len(mm.mm) and mm.mm[pos] == 44:
                pos += 1
                continue
            if pos < len(mm.mm) and mm.mm[pos] == 93:
                return pos + 1
            raise JsonStructureError("Invalid separator in slots array")

    def _index_legacy_node_stream(self, start: int, parent_id: str | None) -> int:
        mm = self._mapped
        pos = mm.skip_ws(start)
        if pos >= len(mm.mm) or mm.mm[pos] != 123:
            raise JsonStructureError(f"Expected legacy node object at byte {pos}")
        pos += 1
        fields: dict[str, tuple[int, int]] = {}
        node_id: str | None = None
        pending_nested: list[tuple[str, int, int]] = []

        while True:
            pos = mm.skip_ws(pos)
            if pos >= len(mm.mm):
                raise JsonStructureError("Unterminated legacy node")
            if mm.mm[pos] == 125:
                object_end = pos + 1
                break

            key_start = pos
            key_end = mm.string_end(key_start)
            key = str(mm.decode(key_start, key_end))
            pos = mm.skip_ws(key_end)
            if pos >= len(mm.mm) or mm.mm[pos] != 58:
                raise JsonStructureError(f"Expected ':' after key {key!r}")
            value_start = mm.skip_ws(pos + 1)

            if key in {"filhos", "slots"} and node_id is not None:
                if key == "filhos":
                    value_end = self._index_legacy_array_stream(value_start, parent_id=node_id)
                else:
                    value_end = self._index_legacy_slots_stream(value_start, owner_id=node_id)
            else:
                value_end = mm.value_end(value_start)
                if key in {"filhos", "slots"}:
                    pending_nested.append((key, value_start, value_end))
                else:
                    fields[key] = (value_start, value_end)
                    if key == "uuid":
                        raw_uuid = mm.decode(value_start, value_end)
                        if raw_uuid not in (None, ""):
                            node_id = str(raw_uuid)

            pos = mm.skip_ws(value_end)
            if pos < len(mm.mm) and mm.mm[pos] == 44:
                pos += 1
                continue
            if pos < len(mm.mm) and mm.mm[pos] == 125:
                object_end = pos + 1
                break
            raise JsonStructureError(f"Invalid separator after key {key!r}")

        if node_id is None:
            raise ValueError(f"Legacy node missing uuid at bytes {start}:{object_end}")

        # JSON object order is not normative.  If a nested container appeared
        # before uuid we had to skip it once to discover the later identifier;
        # replay only that exceptional range now.  Normal Watson exports place
        # uuid before filhos/slots and stay strictly single-pass.
        for key, nested_start, _nested_end in pending_nested:
            if key == "filhos":
                self._index_legacy_array_stream(nested_start, parent_id=node_id)
            else:
                self._index_legacy_slots_stream(nested_start, owner_id=node_id)

        self._spool_local_record(node_id, fields, set())
        ref = RecordRef(
            record_id=node_id,
            source_id=node_id,
            kind="slot_child" if self._decoded_field(fields, "uuidSlot") not in (None, "") else "dialog_node",
            start=start,
            end=object_end,
            local_bytes=self._local_bytes(fields, set()),
            parent_id=parent_id,
            sequence=self._coerce_int(self._decoded_field(fields, "sequencia")),
            previous_sibling=None,
            name=self._coerce_text(self._decoded_field(fields, "nome")) if self.capture_details else None,
            condition=self._coerce_text(self._decoded_field(fields, "condicao")) if self.capture_details else None,
            folder=bool(self._decoded_field(fields, "folder", False)),
            jump_target=self._coerce_text(self._decoded_field(fields, "uuidEnviarPara")),
            jump_selector=self._coerce_text(self._decoded_field(fields, "jumpSelector")),
            semantic_digest=self._semantic_digest(fields, set()) if self.capture_details else None,
        )
        self._add_record(ref)
        return object_end

    def _index_legacy_slot_stream(self, start: int, owner_id: str) -> int:
        mm = self._mapped
        pos = mm.skip_ws(start)
        if pos >= len(mm.mm) or mm.mm[pos] != 123:
            raise JsonStructureError(f"Objeto de slot esperado em byte {pos}")
        pos += 1
        fields: dict[str, tuple[int, int]] = {}
        source_id: str | None = None
        pending_children: list[tuple[int, int]] = []

        while True:
            pos = mm.skip_ws(pos)
            if pos >= len(mm.mm):
                raise JsonStructureError("Slot legado não terminado")
            if mm.mm[pos] == 125:
                object_end = pos + 1
                break

            key_start = pos
            key_end = mm.string_end(key_start)
            key = str(mm.decode(key_start, key_end))
            pos = mm.skip_ws(key_end)
            if pos >= len(mm.mm) or mm.mm[pos] != 58:
                raise JsonStructureError(f"':' esperado após chave de slot {key!r}")
            value_start = mm.skip_ws(pos + 1)

            if key == "filhos" and source_id is not None:
                value_end = self._index_legacy_array_stream(value_start, parent_id=f"slot:{source_id}")
            else:
                value_end = mm.value_end(value_start)
                if key == "filhos":
                    pending_children.append((value_start, value_end))
                else:
                    fields[key] = (value_start, value_end)
                    if key == "uuid":
                        raw_uuid = mm.decode(value_start, value_end)
                        if raw_uuid not in (None, ""):
                            source_id = str(raw_uuid)

            pos = mm.skip_ws(value_end)
            if pos < len(mm.mm) and mm.mm[pos] == 44:
                pos += 1
                continue
            if pos < len(mm.mm) and mm.mm[pos] == 125:
                object_end = pos + 1
                break
            raise JsonStructureError(f"Separador inválido após chave de slot {key!r}")

        if source_id is None:
            raise ValueError(f"Slot legado sem uuid em bytes {start}:{object_end}")
        slot_id = f"slot:{source_id}"
        for nested_start, _nested_end in pending_children:
            self._index_legacy_array_stream(nested_start, parent_id=slot_id)

        self._spool_local_record(slot_id, fields, set())
        ref = RecordRef(
            record_id=slot_id,
            source_id=source_id,
            kind="slot",
            start=start,
            end=object_end,
            local_bytes=self._local_bytes(fields, set()),
            parent_id=owner_id,
            sequence=self._coerce_int(self._decoded_field(fields, "sequencia")),
            previous_sibling=None,
            name=self._coerce_text(self._decoded_field(fields, "identificador")) if self.capture_details else None,
            condition=self._coerce_text(self._decoded_field(fields, "condicao")) if self.capture_details else None,
            folder=False,
            jump_target=None,
            jump_selector=None,
            semantic_digest=self._semantic_digest(fields, set()) if self.capture_details else None,
        )
        self._add_record(ref)
        return object_end

    def _add_record(self, ref: RecordRef) -> None:
        if ref.record_id in self.records:
            raise ValueError(f"Identificador duplicado no export: {ref.record_id}")
        self.records[ref.record_id] = ref
        self.children_by_parent.setdefault(ref.parent_id, []).append(ref.record_id)
        if ref.parent_id is None and ref.kind not in {"slot", "response_condition", "event_handler"}:
            self.roots.append(ref.record_id)

    def _index_legacy_array(self, start: int, end: int, parent_id: str | None) -> None:
        for item_start, item_end in self._mapped.array_items(start, end):
            if self._mapped.mm[self._mapped.skip_ws(item_start, item_end)] != 123:
                continue
            self._index_legacy_node(item_start, item_end, parent_id)

    def _index_legacy_node(self, start: int, end: int, parent_id: str | None) -> None:
        fields = {key: (vstart, vend) for key, vstart, vend in self._mapped.object_fields(start, end)}
        uuid = self._decoded_field(fields, "uuid")
        if uuid in (None, ""):
            raise ValueError(f"Legacy node missing uuid at bytes {start}:{end}")
        node_id = str(uuid)
        ref = RecordRef(
            record_id=node_id,
            source_id=node_id,
            kind="slot_child" if self._decoded_field(fields, "uuidSlot") not in (None, "") else "dialog_node",
            start=start,
            end=end,
            local_bytes=self._local_bytes(fields, {"filhos", "slots"}),
            parent_id=parent_id,
            sequence=self._coerce_int(self._decoded_field(fields, "sequencia")),
            previous_sibling=None,
            name=self._coerce_text(self._decoded_field(fields, "nome")) if self.capture_details else None,
            condition=self._coerce_text(self._decoded_field(fields, "condicao")) if self.capture_details else None,
            folder=bool(self._decoded_field(fields, "folder", False)),
            jump_target=self._coerce_text(self._decoded_field(fields, "uuidEnviarPara")),
            jump_selector=self._coerce_text(self._decoded_field(fields, "jumpSelector")),
            semantic_digest=self._semantic_digest(fields, {"filhos", "slots"}) if self.capture_details else None,
        )
        self._add_record(ref)

        slots_range = fields.get("slots")
        if slots_range:
            for slot_start, slot_end in self._mapped.array_items(*slots_range):
                self._index_legacy_slot(slot_start, slot_end, node_id)
        children_range = fields.get("filhos")
        if children_range:
            self._index_legacy_array(*children_range, parent_id=node_id)

    def _index_legacy_slot(self, start: int, end: int, owner_id: str) -> None:
        fields = {key: (vstart, vend) for key, vstart, vend in self._mapped.object_fields(start, end)}
        uuid = self._decoded_field(fields, "uuid")
        if uuid in (None, ""):
            raise ValueError(f"Slot legado sem uuid em bytes {start}:{end}")
        source_id = str(uuid)
        slot_id = f"slot:{source_id}"
        ref = RecordRef(
            record_id=slot_id,
            source_id=source_id,
            kind="slot",
            start=start,
            end=end,
            local_bytes=self._local_bytes(fields, {"filhos"}),
            parent_id=owner_id,
            sequence=self._coerce_int(self._decoded_field(fields, "sequencia")),
            previous_sibling=None,
            name=self._coerce_text(self._decoded_field(fields, "identificador")) if self.capture_details else None,
            condition=self._coerce_text(self._decoded_field(fields, "condicao")) if self.capture_details else None,
            folder=False,
            jump_target=None,
            jump_selector=None,
            semantic_digest=self._semantic_digest(fields, {"filhos"}) if self.capture_details else None,
        )
        self._add_record(ref)
        children_range = fields.get("filhos")
        if children_range:
            self._index_legacy_array(*children_range, parent_id=slot_id)

    def _index_v1_array(self, start: int, end: int) -> None:
        staged: list[tuple[int, int, dict[str, tuple[int, int]]]] = []
        by_source_id: dict[str, str] = {}
        kind_by_source_id: dict[str, str] = {}
        for item_start, item_end in self._mapped.array_items(start, end):
            fields = {key: (vstart, vend) for key, vstart, vend in self._mapped.object_fields(item_start, item_end)}
            source_id = self._decoded_field(fields, "dialog_node")
            if source_id in (None, ""):
                continue
            source_id = str(source_id)
            node_type = str(self._decoded_field(fields, "type", "standard") or "standard")
            record_id = f"slot:{source_id}" if node_type == "slot" else source_id
            by_source_id[source_id] = record_id
            kind_by_source_id[source_id] = node_type
            staged.append((item_start, item_end, fields))

        for item_start, item_end, fields in staged:
            source_id = str(self._decoded_field(fields, "dialog_node"))
            node_type = kind_by_source_id[source_id]
            raw_parent = self._coerce_text(self._decoded_field(fields, "parent"))
            parent_id = by_source_id.get(raw_parent, raw_parent) if raw_parent else None
            graph_kind = {
                "slot": "slot",
                "event_handler": "event_handler",
                "response_condition": "response_condition",
            }.get(node_type, "dialog_node")
            next_step = self._decoded_field(fields, "next_step", {})
            jump_target = None
            jump_selector = None
            if isinstance(next_step, dict) and str(next_step.get("behavior") or "") in {"jump_to", "jump"}:
                target = next_step.get("dialog_node") or next_step.get("target")
                jump_target = str(target) if target not in (None, "") else None
                selector = str(next_step.get("selector") or "condition")
                jump_selector = {"response": "body", "client": "user_input"}.get(selector, selector)
            ref = RecordRef(
                record_id=by_source_id[source_id],
                source_id=source_id,
                kind=graph_kind,
                start=item_start,
                end=item_end,
                local_bytes=self._local_bytes(fields, set()),
                parent_id=parent_id,
                sequence=None,
                previous_sibling=self._coerce_text(self._decoded_field(fields, "previous_sibling")),
                name=self._coerce_text(self._decoded_field(fields, "title")) if self.capture_details else None,
                condition=(self._coerce_text(self._decoded_field(fields, "conditions")) or "true") if self.capture_details else None,
                folder=node_type == "folder",
                jump_target=jump_target,
                jump_selector=jump_selector,
                semantic_digest=self._semantic_digest(fields, set()) if self.capture_details else None,
            )
            self._add_record(ref)

        # Reproduce V1 sibling ordering without materializing normalized nodes.
        for parent_id, children in list(self.children_by_parent.items()):
            source_to_record = {self.records[child].source_id: child for child in children}
            previous_to_child = {
                self.records[child].previous_sibling: child
                for child in children
                if self.records[child].previous_sibling not in (None, "")
            }
            first = [child for child in children if self.records[child].previous_sibling in (None, "")]
            ordered: list[str] = []
            if len(first) == 1:
                current = first[0]
                seen: set[str] = set()
                while current not in seen:
                    ordered.append(current); seen.add(current)
                    source_id = self.records[current].source_id
                    next_child = previous_to_child.get(source_id)
                    if next_child is None:
                        break
                    current = next_child
            if len(ordered) == len(children):
                self.children_by_parent[parent_id] = ordered
            else:
                self.children_by_parent[parent_id] = sorted(children)

    @staticmethod
    def _coerce_text(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def load_record(self, record_id: str) -> dict[str, Any]:
        ref = self.records[str(record_id)]
        value = self._mapped.decode(ref.start, ref.end)
        if not isinstance(value, dict):
            raise ValueError(f"Registro {record_id} não é um objeto JSON")
        return value

    def record_bytes(self, record_id: str) -> bytes:
        ref = self.records[str(record_id)]
        return bytes(self._mapped.mm[ref.start:ref.end])

    def load_local_record(self, record_id: str) -> dict[str, Any]:
        """Materialize only the record's own fields.

        Diff-oriented indexes spool these local bytes during the initial
        structural pass, so loading a changed high-level node never rescans its
        complete descendant subtree.
        """
        spooled = self._read_local_spool(record_id)
        if spooled is not None:
            value = json.loads(spooled)
            if not isinstance(value, dict):
                raise ValueError(f"Registro local {record_id} não é objeto JSON")
            return value
        ref = self.records[str(record_id)]
        excluded: set[str] = set()
        if self.format_type == "legacy":
            excluded = {"filhos", "slots"} if ref.kind != "slot" else {"filhos"}
        result: dict[str, Any] = {}
        for key, start, end in self._mapped.object_fields(ref.start, ref.end):
            if key not in excluded:
                result[key] = self._mapped.decode(start, end)
        return result

    def local_record_bytes(self, record_id: str) -> bytes:
        """Return bounded record-local JSON bytes without descendant rescans."""
        spooled = self._read_local_spool(record_id)
        if spooled is not None:
            return spooled
        ref = self.records[str(record_id)]
        excluded: set[str] = set()
        if self.format_type == "legacy":
            excluded = {"filhos", "slots"} if ref.kind != "slot" else {"filhos"}
        fields = {key: (start, end) for key, start, end in self._mapped.object_fields(ref.start, ref.end)}
        return self._local_payload_bytes(fields, excluded)

    def root_value(self, name: str) -> Any:
        bounds = self.root_fields[name]
        return self._mapped.decode(*bounds)

    def root_value_bytes(self, name: str) -> bytes:
        start, end = self.root_fields[name]
        return bytes(self._mapped.mm[start:end])

    def collection_item_bytes(self, ref: CollectionItemRef) -> bytes:
        return bytes(self._mapped.mm[ref.start:ref.end])

    def ordered_object_array(self, name: str) -> list[OrderedItemRef] | None:
        """Return compact refs for an order-sensitive array of JSON objects.

        No complete array is materialized.  Each item is decoded independently
        only to compute the incumbent-compatible canonical matching digest.
        ``None`` means the root is not an array containing only objects.
        """
        if name in self._ordered_array_cache:
            return self._ordered_array_cache[name]
        bounds = self.root_fields.get(name)
        if bounds is None:
            self._ordered_array_cache[name] = None
            return None
        start, end = bounds
        start = self._mapped.skip_ws(start, end)
        if start >= end or self._mapped.mm[start] != 91:
            self._ordered_array_cache[name] = None
            return None
        refs: list[OrderedItemRef] = []
        for ordinal, (item_start, item_end) in enumerate(self._mapped.array_items(start, end)):
            if self._mapped.mm[self._mapped.skip_ws(item_start, item_end)] != 123:
                self._ordered_array_cache[name] = None
                return None
            refs.append(
                OrderedItemRef(
                    ordinal=ordinal,
                    start=item_start,
                    end=item_end,
                    stable_digest=self._stable_item_digest(item_start, item_end),
                )
            )
        self._ordered_array_cache[name] = refs
        return refs

    def ordered_item_bytes(self, ref: OrderedItemRef) -> bytes:
        return bytes(self._mapped.mm[ref.start:ref.end])

    def ordered_item_stable_bytes(self, ref: OrderedItemRef) -> bytes:
        return self._stable_value_bytes(self._mapped.decode(ref.start, ref.end))

    def uuid_collection(self, name: str, id_field: str = "uuid") -> dict[str, CollectionItemRef] | None:
        """Index a root array of objects by *id_field* without materializing it.

        ``None`` means the root value is not an array whose every item is an
        object containing the requested identifier.  Results are cached so a
        diff may make multiple passes without rescanning the array.
        """
        cache_key = (name, id_field)
        if cache_key in self._collection_cache:
            return self._collection_cache[cache_key]
        bounds = self.root_fields.get(name)
        if bounds is None:
            self._collection_cache[cache_key] = None
            return None
        start, end = bounds
        start = self._mapped.skip_ws(start, end)
        if start >= end or self._mapped.mm[start] != 91:  # '['
            self._collection_cache[cache_key] = None
            return None
        indexed: dict[str, CollectionItemRef] = {}
        for item_start, item_end in self._mapped.array_items(start, end):
            if self._mapped.mm[self._mapped.skip_ws(item_start, item_end)] != 123:
                self._collection_cache[cache_key] = None
                return None
            fields = {key: (vstart, vend) for key, vstart, vend in self._mapped.object_fields(item_start, item_end)}
            raw_id = self._decoded_field(fields, id_field)
            if raw_id in (None, ""):
                self._collection_cache[cache_key] = None
                return None
            item_id = str(raw_id)
            if item_id in indexed:
                raise ValueError(f"Identificador duplicado em {name}: {item_id}")
            indexed[item_id] = CollectionItemRef(
                item_id=item_id,
                start=item_start,
                end=item_end,
                semantic_digest=self._canonical_digest(fields, set()),
            )
        self._collection_cache[cache_key] = indexed
        return indexed

    def legacy_root_and_path(self, record_id: str) -> tuple[str, str]:
        """Return ``(top_root_uuid, relative_path)`` for a legacy record."""
        if self.format_type != "legacy":
            raise ValueError("legacy_root_and_path só é válido para exports legados")
        current = str(record_id)
        segments: list[str] = []
        seen: set[str] = set()
        while True:
            if current in seen:
                raise ValueError(f"Ciclo estrutural inesperado no índice: {record_id}")
            seen.add(current)
            ref = self.records[current]
            parent_id = ref.parent_id
            if parent_id is None:
                return current, ".".join(reversed(segments))
            if ref.kind == "slot":
                segment = f"slots[uuid={ref.source_id}]"
            else:
                segment = f"filhos[uuid={ref.source_id}]"
            segments.append(segment)
            current = parent_id

    def ancestors(self, record_id: str) -> Iterator[str]:
        current = self.records[str(record_id)].parent_id
        seen: set[str] = set()
        while current is not None and current not in seen:
            yield current
            seen.add(current)
            parent = self.records.get(current)
            current = parent.parent_id if parent else None

    def ordered_children(self, parent_id: str | None) -> list[str]:
        children = list(self.children_by_parent.get(parent_id, []))
        if self.format_type == "v1":
            return children
        return sorted(
            children,
            key=lambda child: (
                self.records[child].sequence is None,
                self.records[child].sequence or 0,
                child,
            ),
        )

    def graph_vertex_ids(self) -> list[str]:
        result: list[str] = []
        for record_id, ref in self.records.items():
            if self.format_type == "v1":
                if ref.kind == "response_condition":
                    continue
                if ref.kind == "event_handler":
                    parent = self.records.get(ref.parent_id or "")
                    if not parent or parent.kind != "slot":
                        continue
            result.append(record_id)
        return sorted(result)

    def summary(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for ref in self.records.values():
            kinds[ref.kind] = kinds.get(ref.kind, 0) + 1
        return {
            "format_type": self.format_type,
            "file_size_bytes": self.file_size_bytes,
            "records": len(self.records),
            "graph_vertices": len(self.graph_vertex_ids()),
            "roots": len(self.roots),
            "kinds": dict(sorted(kinds.items())),
            "top_level_counts": dict(sorted(self.top_level_counts.items())),
            "local_spool_bytes": self._local_spool_bytes,
        }


class DialogTransientIndex:
    """Fast one-document-at-a-time index backed by an ephemeral record spool.

    This backend intentionally accepts a bounded transient DOM peak to avoid
    the much larger *two-document* DOM peak of the incumbent diff.  It is
    selected only when :class:`ResourceBudget` says current free memory can
    absorb the source safely.  The parsed document is flattened immediately
    into local record bytes + compact metadata, then released before the next
    export is parsed.

    No pickle/database is used: the spool contains ordinary JSON records in an
    anonymous temporary file and disappears on close.
    """

    def __init__(self, path: Path, *, capture_details: bool, ignored_fields: Iterable[str] | None) -> None:
        self.path = path
        self.capture_details = capture_details
        self.ignored_fields = frozenset(_DEFAULT_IGNORED_FIELDS if ignored_fields is None else ignored_fields)
        self.records: dict[str, RecordRef] = {}
        self.children_by_parent: dict[str | None, list[str]] = {}
        self.roots: list[str] = []
        self.top_level_counts: dict[str, int] = {}
        self.root_fields: dict[str, tuple[int, int]] = {}
        self.file_size_bytes = path.stat().st_size
        self.format_type = "unknown"
        self._spool = tempfile.TemporaryFile(mode="w+b")
        self._collection_cache: dict[tuple[str, str], dict[str, CollectionItemRef] | None] = {}
        self._ordered_array_cache: dict[str, list[OrderedItemRef] | None] = {}
        self._root_ranges: dict[str, tuple[int, int]] = {}
        self._nested_presence: dict[str, tuple[bool, bool]] = {}

    @classmethod
    def open(
        cls,
        path: Path,
        max_bytes: int | None = None,
        *,
        capture_details: bool = False,
        ignored_fields: Iterable[str] | None = None,
    ) -> DialogTransientIndex:
        if not path.exists():
            raise ValueError(f"File not found: {path}")
        max_bytes = resolve_max_input_bytes(max_bytes)
        size = path.stat().st_size
        if max_bytes and max_bytes > 0 and size > max_bytes:
            raise ValueError(
                f"File {path} ({size} bytes) exceeds configured limit of {max_bytes} bytes. "
                "Use --max-input-bytes to increase limit if necessary."
            )
        index = cls(path, capture_details=capture_details, ignored_fields=ignored_fields)
        try:
            index._build_from_document(index._load_document())
            return index
        except Exception:
            index.close()
            raise

    def close(self) -> None:
        self._spool.close()

    def __enter__(self) -> DialogTransientIndex:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _load_document(self) -> dict[str, Any]:
        try:
            parser = os.environ.get("WATSON_DIALOG_JSON_PARSER", "auto").strip().lower() or "auto"
            if parser not in {"auto", "stdlib", "orjson"}:
                raise ValueError("WATSON_DIALOG_JSON_PARSER deve ser auto, stdlib ou orjson")
            use_orjson = parser == "orjson"
            if parser == "auto":
                from tare_dialog.resources import ResourceBudget

                available = ResourceBudget.detect().available_memory_bytes
                # orjson is measurably faster but its bytes-oriented decode
                # carries a higher transient RSS on large Watson exports.  On
                # constrained hosts prefer stdlib; high-memory workstations
                # can spend that headroom for throughput.
                use_orjson = bool(available and available >= 8 * 1024**3)
            if use_orjson:
                try:
                    import orjson  # type: ignore
                except ImportError:
                    if parser == "orjson":
                        raise ValueError("WATSON_DIALOG_JSON_PARSER=orjson solicitado, mas orjson não está instalado")
                    use_orjson = False
            if use_orjson:
                document = orjson.loads(self.path.read_bytes())  # type: ignore[name-defined]
            else:
                with self.path.open(encoding="utf-8") as source:
                    document = json.load(source)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(f"Não foi possível ler {self.path}: {error}") from error
        if not isinstance(document, dict):
            raise ValueError(f"{self.path} deve conter um objeto JSON na raiz.")
        return document

    @staticmethod
    def _encode(value: Any) -> bytes:
        try:
            import orjson  # type: ignore

            return orjson.dumps(value)
        except ImportError:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _write(self, payload: bytes) -> tuple[int, int]:
        self._spool.seek(0, os.SEEK_END)
        start = self._spool.tell()
        self._spool.write(payload)
        return start, start + len(payload)

    def _read(self, start: int, end: int) -> bytes:
        self._spool.seek(start)
        return self._spool.read(end - start)

    def _semantic_digest_value(self, value: dict[str, Any], excluded: set[str]) -> str:
        digest = hashlib.blake2b(digest_size=16)
        for key in sorted(value):
            if key in excluded or key in self.ignored_fields:
                continue
            rendered = json.dumps(value[key], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest.update(key.encode("utf-8")); digest.update(b"\0"); digest.update(rendered); digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _stable_value_bytes(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _ordered_refs_from_values(self, name: str, value: Any) -> list[OrderedItemRef] | None:
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            return None
        refs: list[OrderedItemRef] = []
        for ordinal, item in enumerate(value):
            payload = self._encode(item)
            start, end = self._write(payload)
            refs.append(
                OrderedItemRef(
                    ordinal=ordinal,
                    start=start,
                    end=end,
                    stable_digest=hashlib.sha256(self._stable_value_bytes(item)).hexdigest(),
                )
            )
        self._ordered_array_cache[name] = refs
        self.top_level_counts[name] = len(value)
        return refs

    def _add_record(self, ref: RecordRef) -> None:
        if ref.record_id in self.records:
            raise ValueError(f"Identificador duplicado no export: {ref.record_id}")
        self.records[ref.record_id] = ref
        self.children_by_parent.setdefault(ref.parent_id, []).append(ref.record_id)
        if ref.parent_id is None and ref.kind not in {"slot", "response_condition", "event_handler"}:
            self.roots.append(ref.record_id)

    def _build_from_document(self, document: dict[str, Any]) -> None:
        self.root_fields = {str(key): (0, 0) for key in document}
        if "nos" in document:
            self.format_type = "legacy"
            nodes = document.get("nos")
            if not isinstance(nodes, list):
                raise ValueError("nos must be an array")
            self._index_legacy_array_value(nodes, parent_id=None)
        elif "dialog_nodes" in document:
            self.format_type = "v1"
        else:
            raise ValueError("Dialog must contain 'nos' (legacy) or 'dialog_nodes' (V1 API).")

        for name, value in document.items():
            if name == "nos" and self.format_type == "legacy":
                self.top_level_counts[name] = len(value) if isinstance(value, list) else 0
                continue
            if name == "dialog_nodes" and self.format_type == "v1":
                if self._ordered_refs_from_values(name, value) is None:
                    payload = self._encode(value)
                    self._root_ranges[name] = self._write(payload)
                    if isinstance(value, list):
                        self.top_level_counts[name] = len(value)
                continue
            if isinstance(value, list) and all(isinstance(item, dict) and item.get("uuid") not in (None, "") for item in value):
                indexed: dict[str, CollectionItemRef] = {}
                for item in value:
                    item_id = str(item["uuid"])
                    if item_id in indexed:
                        raise ValueError(f"Duplicate identifier in {name}: {item_id}")
                    payload = self._encode(item)
                    start, end = self._write(payload)
                    indexed[item_id] = CollectionItemRef(
                        item_id=item_id,
                        start=start,
                        end=end,
                        semantic_digest=self._semantic_digest_value(item, set()),
                    )
                self._collection_cache[(name, "uuid")] = indexed
                self.top_level_counts[name] = len(value)
            else:
                payload = self._encode(value)
                self._root_ranges[name] = self._write(payload)
                if isinstance(value, list):
                    self.top_level_counts[name] = len(value)

        # Make the large DOM collectible before the second index is opened.
        document.clear()

    def _index_legacy_array_value(self, nodes: list[Any], parent_id: str | None) -> None:
        for node in nodes:
            if isinstance(node, dict):
                self._index_legacy_node_value(node, parent_id)

    def _index_legacy_node_value(self, node: dict[str, Any], parent_id: str | None) -> None:
        raw_uuid = node.get("uuid")
        if raw_uuid in (None, ""):
            raise ValueError("Legacy node missing uuid")
        node_id = str(raw_uuid)
        local = {key: value for key, value in node.items() if key not in {"filhos", "slots"}}
        payload = self._encode(local)
        start, end = self._write(payload)
        ref = RecordRef(
            record_id=node_id,
            source_id=node_id,
            kind="slot_child" if node.get("uuidSlot") not in (None, "") else "dialog_node",
            start=start,
            end=end,
            local_bytes=len(payload),
            parent_id=parent_id,
            sequence=self._coerce_int(node.get("sequencia")),
            previous_sibling=None,
            name=self._coerce_text(node.get("nome")) if self.capture_details else None,
            condition=self._coerce_text(node.get("condicao")) if self.capture_details else None,
            folder=bool(node.get("folder", False)),
            jump_target=self._coerce_text(node.get("uuidEnviarPara")),
            jump_selector=self._coerce_text(node.get("jumpSelector")),
            semantic_digest=self._semantic_digest_value(local, set()) if self.capture_details else None,
        )
        self._nested_presence[node_id] = ("filhos" in node, "slots" in node)
        self._add_record(ref)
        slots = node.get("slots")
        if isinstance(slots, list):
            for slot in slots:
                if isinstance(slot, dict):
                    self._index_legacy_slot_value(slot, node_id)
        children = node.get("filhos")
        if isinstance(children, list):
            self._index_legacy_array_value(children, node_id)

    def _index_legacy_slot_value(self, slot: dict[str, Any], owner_id: str) -> None:
        raw_uuid = slot.get("uuid")
        if raw_uuid in (None, ""):
            raise ValueError("Slot legado sem uuid")
        source_id = str(raw_uuid)
        slot_id = f"slot:{source_id}"
        local = {key: value for key, value in slot.items() if key != "filhos"}
        payload = self._encode(local)
        start, end = self._write(payload)
        ref = RecordRef(
            record_id=slot_id,
            source_id=source_id,
            kind="slot",
            start=start,
            end=end,
            local_bytes=len(payload),
            parent_id=owner_id,
            sequence=self._coerce_int(slot.get("sequencia")),
            previous_sibling=None,
            name=self._coerce_text(slot.get("identificador")) if self.capture_details else None,
            condition=self._coerce_text(slot.get("condicao")) if self.capture_details else None,
            folder=False,
            jump_target=None,
            jump_selector=None,
            semantic_digest=self._semantic_digest_value(local, set()) if self.capture_details else None,
        )
        self._nested_presence[slot_id] = ("filhos" in slot, False)
        self._add_record(ref)
        children = slot.get("filhos")
        if isinstance(children, list):
            self._index_legacy_array_value(children, slot_id)

    @staticmethod
    def _coerce_text(value: Any) -> str | None:
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def load_local_record(self, record_id: str) -> dict[str, Any]:
        ref = self.records[str(record_id)]
        value = json.loads(self._read(ref.start, ref.end))
        if not isinstance(value, dict):
            raise ValueError(f"Registro {record_id} não é um objeto JSON")
        return value

    def local_record_bytes(self, record_id: str) -> bytes:
        ref = self.records[str(record_id)]
        return self._read(ref.start, ref.end)

    def load_record(self, record_id: str) -> dict[str, Any]:
        record_id = str(record_id)
        ref = self.records[record_id]
        value = self.load_local_record(record_id)
        has_children, has_slots = self._nested_presence.get(record_id, (False, False))
        direct = self.children_by_parent.get(record_id, [])
        if ref.kind == "slot":
            if has_children:
                value["filhos"] = [self.load_record(child) for child in direct if self.records[child].kind != "slot"]
            return value
        if has_slots:
            value["slots"] = [self.load_record(child) for child in direct if self.records[child].kind == "slot"]
        if has_children:
            value["filhos"] = [self.load_record(child) for child in direct if self.records[child].kind != "slot"]
        return value

    def record_bytes(self, record_id: str) -> bytes:
        return self._encode(self.load_record(record_id))

    def root_value(self, name: str) -> Any:
        if name == "nos" and self.format_type == "legacy":
            return [self.load_record(root) for root in self.roots]
        ordered = self._ordered_array_cache.get(name)
        if ordered is not None:
            return [json.loads(self.ordered_item_bytes(ref)) for ref in ordered]
        bounds = self._root_ranges.get(name)
        if bounds is None:
            collection = self._collection_cache.get((name, "uuid"))
            if collection is not None:
                return [json.loads(self.collection_item_bytes(ref)) for ref in collection.values()]
            raise KeyError(name)
        return json.loads(self._read(*bounds))

    def root_value_bytes(self, name: str) -> bytes:
        return self._encode(self.root_value(name))

    def collection_item_bytes(self, ref: CollectionItemRef) -> bytes:
        return self._read(ref.start, ref.end)

    def ordered_object_array(self, name: str) -> list[OrderedItemRef] | None:
        if name in self._ordered_array_cache:
            return self._ordered_array_cache[name]
        bounds = self._root_ranges.get(name)
        if bounds is None:
            self._ordered_array_cache[name] = None
            return None
        value = json.loads(self._read(*bounds))
        refs = self._ordered_refs_from_values(name, value)
        return refs

    def ordered_item_bytes(self, ref: OrderedItemRef) -> bytes:
        return self._read(ref.start, ref.end)

    def ordered_item_stable_bytes(self, ref: OrderedItemRef) -> bytes:
        return self._stable_value_bytes(json.loads(self._read(ref.start, ref.end)))

    def uuid_collection(self, name: str, id_field: str = "uuid") -> dict[str, CollectionItemRef] | None:
        return self._collection_cache.get((name, id_field))

    def ordered_children(self, parent_id: str | None) -> list[str]:
        children = list(self.children_by_parent.get(parent_id, []))
        return sorted(
            children,
            key=lambda child: (
                self.records[child].sequence is None,
                self.records[child].sequence or 0,
                child,
            ),
        )

    def graph_vertex_ids(self) -> list[str]:
        return sorted(self.records)

    def legacy_root_and_path(self, record_id: str) -> tuple[str, str]:
        current = str(record_id)
        segments: list[str] = []
        seen: set[str] = set()
        while True:
            if current in seen:
                raise ValueError(f"Ciclo estrutural inesperado no índice: {record_id}")
            seen.add(current)
            ref = self.records[current]
            if ref.parent_id is None:
                return current, ".".join(reversed(segments))
            segment = f"slots[uuid={ref.source_id}]" if ref.kind == "slot" else f"filhos[uuid={ref.source_id}]"
            segments.append(segment)
            current = ref.parent_id

    def ancestors(self, record_id: str) -> Iterator[str]:
        current = self.records[str(record_id)].parent_id
        seen: set[str] = set()
        while current is not None and current not in seen:
            yield current
            seen.add(current)
            parent = self.records.get(current)
            current = parent.parent_id if parent else None

    def summary(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for ref in self.records.values():
            kinds[ref.kind] = kinds.get(ref.kind, 0) + 1
        return {
            "format_type": self.format_type,
            "file_size_bytes": self.file_size_bytes,
            "records": len(self.records),
            "graph_vertices": len(self.graph_vertex_ids()),
            "roots": len(self.roots),
            "kinds": dict(sorted(kinds.items())),
            "top_level_counts": dict(sorted(self.top_level_counts.items())),
        }


def choose_index_backend(path: Path, requested: str = "auto") -> str:
    """Choose ``transient`` when one-at-a-time DOM parsing fits comfortably."""
    if requested in {"mmap", "transient"}:
        return requested
    if requested != "auto":
        raise ValueError("index backend deve ser auto, mmap ou transient")
    override = os.environ.get("WATSON_DIALOG_INDEX_BACKEND", "").strip().lower()
    if override in {"mmap", "transient"}:
        return override
    from tare_dialog.resources import ResourceBudget

    budget = ResourceBudget.detect()
    if not budget.available_memory_bytes:
        return "mmap"
    # Empirical safety envelope: Python DOM expansion can be several times the
    # encoded JSON size.  Reserve 65% of currently available memory for the OS,
    # workers and unexpected object expansion; require an 8x source allowance.
    estimated_peak = path.stat().st_size * 8
    return "transient" if estimated_peak <= int(budget.available_memory_bytes * 0.35) else "mmap"


def open_dialog_index(
    path: Path,
    max_bytes: int | None = None,
    *,
    capture_details: bool = False,
    ignored_fields: Iterable[str] | None = None,
    backend: str = "auto",
) -> DialogSourceIndex | DialogTransientIndex:
    selected = choose_index_backend(path, backend)
    cls = DialogTransientIndex if selected == "transient" else DialogSourceIndex
    return cls.open(
        path,
        max_bytes=max_bytes,
        capture_details=capture_details,
        ignored_fields=ignored_fields,
    )


EDGE_TYPES = ("contains", "contains_slot", "slot_branch", "folder_entry", "next_evaluation", "jump")
_EDGE_CODE = {name: index for index, name in enumerate(EDGE_TYPES)}
_EDGE_AFFINITY = {
    "contains": 4,
    "contains_slot": 5,
    "slot_branch": 5,
    "folder_entry": 4,
    "next_evaluation": 3,
    "jump": 1,
}


@dataclass
class CompactGraph:
    vertex_ids: tuple[str, ...]
    src: array
    dst: array
    edge_types: bytearray
    weights: array

    @classmethod
    def from_index(cls, index: DialogSourceIndex) -> CompactGraph:
        vertex_ids = tuple(index.graph_vertex_ids())
        id_to_int = {vertex_id: pos for pos, vertex_id in enumerate(vertex_ids)}
        edges: set[tuple[str, str, str]] = set()

        def graph_parent(ref: RecordRef) -> str | None:
            parent = ref.parent_id
            if parent is None:
                return None
            if parent in id_to_int:
                return parent
            return None

        # Structural containment.
        for vertex_id in vertex_ids:
            ref = index.records[vertex_id]
            parent = graph_parent(ref)
            if parent is None:
                continue
            parent_ref = index.records[parent]
            if ref.kind == "slot":
                edge_type = "contains_slot"
            elif parent_ref.kind == "slot":
                edge_type = "slot_branch"
            else:
                edge_type = "contains"
            edges.add((parent, vertex_id, edge_type))

        # Sibling evaluation + folder entry.
        parents = {index.records[v].parent_id for v in vertex_ids}
        parents.add(None)
        for parent_id in parents:
            ordered = [child for child in index.ordered_children(parent_id) if child in id_to_int]
            parent_ref = index.records.get(parent_id or "")
            if parent_ref and parent_ref.kind == "slot":
                siblings = ordered
            else:
                # Slots are evaluated by the frame/slot runtime, not as dialog
                # siblings.  Preserve only dialog-node/handler ordering here.
                siblings = [child for child in ordered if index.records[child].kind != "slot"]
            for left, right in zip(siblings, siblings[1:]):
                edges.add((left, right, "next_evaluation"))
            if parent_id in id_to_int and index.records[parent_id].folder and siblings:
                edges.add((parent_id, siblings[0], "folder_entry"))

        # Jumps only when both endpoints are graph vertices. root/tree restart is
        # deliberately excluded from partition affinity because it is global.
        source_id_to_vertex = {index.records[v].source_id: v for v in vertex_ids}
        for vertex_id in vertex_ids:
            target = index.records[vertex_id].jump_target
            if not target or target == "root":
                continue
            target_vertex = source_id_to_vertex.get(target) or (target if target in id_to_int else None)
            if target_vertex in id_to_int:
                edges.add((vertex_id, str(target_vertex), "jump"))

        ordered = sorted(edges, key=lambda item: (item[0], item[1], item[2]))
        src = array("I", (id_to_int[s] for s, _, _ in ordered))
        dst = array("I", (id_to_int[d] for _, d, _ in ordered))
        types = bytearray(_EDGE_CODE[t] for _, _, t in ordered)
        weights = array("I", (index.records[v].work_weight for v in vertex_ids))
        return cls(vertex_ids=vertex_ids, src=src, dst=dst, edge_types=types, weights=weights)

    def iter_edges(self) -> Iterator[tuple[str, str, str]]:
        for source, target, edge_code in zip(self.src, self.dst, self.edge_types):
            yield self.vertex_ids[source], self.vertex_ids[target], EDGE_TYPES[edge_code]

    def memory_bytes(self) -> int:
        return len(self.src) * self.src.itemsize + len(self.dst) * self.dst.itemsize + len(self.edge_types) + len(self.weights) * self.weights.itemsize

    def summary(self) -> dict[str, Any]:
        by_type = {name: 0 for name in EDGE_TYPES}
        for code in self.edge_types:
            by_type[EDGE_TYPES[code]] += 1
        return {
            "vertices": len(self.vertex_ids),
            "edges": len(self.src),
            "edges_by_type": {key: value for key, value in by_type.items() if value},
            "compact_array_bytes": self.memory_bytes(),
        }

    def semantic_shards(self, shard_count: int, tolerance: float = 1.15) -> dict[str, Any]:
        if shard_count < 1:
            raise ValueError("shard_count deve ser pelo menos 1")
        if not self.vertex_ids:
            return {"shards": [], "metrics": {"edge_cut": 0, "edge_cut_ratio": 0.0, "max_load_ratio": 0.0}}
        shard_count = min(shard_count, len(self.vertex_ids))
        id_to_int = {vertex_id: i for i, vertex_id in enumerate(self.vertex_ids)}

        # Structural forest ignores sibling/jump edges.  This lets us preserve
        # semantic subtrees while still splitting oversized roots recursively.
        children: dict[int, list[int]] = {i: [] for i in range(len(self.vertex_ids))}
        parent: dict[int, int] = {}
        for s, d, code in zip(self.src, self.dst, self.edge_types):
            edge_type = EDGE_TYPES[code]
            if edge_type in {"contains", "contains_slot", "slot_branch"}:
                if d not in parent:
                    parent[d] = s
                    children[s].append(d)
        for values in children.values():
            values.sort(key=lambda i: self.vertex_ids[i])
        roots = sorted((i for i in range(len(self.vertex_ids)) if i not in parent), key=lambda i: self.vertex_ids[i])

        subtree_weight: dict[int, int] = {}
        for root in roots:
            stack: list[tuple[int, bool]] = [(root, False)]
            while stack:
                node, visited = stack.pop()
                if visited:
                    subtree_weight[node] = int(self.weights[node]) + sum(subtree_weight[c] for c in children[node])
                else:
                    stack.append((node, True))
                    stack.extend((child, False) for child in reversed(children[node]))

        total_weight = sum(int(value) for value in self.weights)
        target = max(1.0, total_weight / shard_count)
        chunk_limit = max(1.0, target * tolerance)
        chunks: list[list[int]] = []

        def collect_subtree(root: int) -> list[int]:
            result: list[int] = []
            stack = [root]
            while stack:
                node = stack.pop(); result.append(node)
                stack.extend(reversed(children[node]))
            return result

        def split(node: int) -> None:
            if subtree_weight[node] <= chunk_limit:
                chunks.append(collect_subtree(node))
                return
            # Keep the owner itself atomic; recursively split its semantic children.
            chunks.append([node])
            for child in children[node]:
                split(child)

        for root in roots:
            split(root)
        chunks.sort(key=lambda chunk: (-sum(int(self.weights[i]) for i in chunk), self.vertex_ids[chunk[0]]))

        incident: dict[int, list[tuple[int, int]]] = {i: [] for i in range(len(self.vertex_ids))}
        for s, d, code in zip(self.src, self.dst, self.edge_types):
            affinity = _EDGE_AFFINITY[EDGE_TYPES[code]]
            incident[s].append((d, affinity)); incident[d].append((s, affinity))

        assignments: list[list[int]] = [[] for _ in range(shard_count)]
        loads = [0 for _ in range(shard_count)]
        assigned_to: dict[int, int] = {}
        hard_cap = target * tolerance

        # Seed every shard when enough chunks exist. Without this guard a long
        # next_evaluation chain can attract nearly all chunks into N-1 shards
        # while still respecting the hard cap, wasting available workers.
        seeded = min(shard_count, len(chunks))
        for shard_index in range(seeded):
            chunk = chunks[shard_index]
            chunk_weight = sum(int(self.weights[i]) for i in chunk)
            assignments[shard_index].extend(chunk)
            loads[shard_index] += chunk_weight
            for node in chunk:
                assigned_to[node] = shard_index

        for chunk in chunks[seeded:]:
            chunk_weight = sum(int(self.weights[i]) for i in chunk)
            affinity_scores = [0 for _ in range(shard_count)]
            chunk_set = set(chunk)
            for node in chunk:
                for other, affinity in incident[node]:
                    if other in chunk_set:
                        continue
                    shard = assigned_to.get(other)
                    if shard is not None:
                        affinity_scores[shard] += affinity
            # Keep load balance as a hard scheduling concern and affinity as
            # the locality tiebreaker. This prevents a strong sibling chain
            # from starving otherwise available shards.
            underfilled = [
                i for i in range(shard_count)
                if loads[i] < target * 0.90 and loads[i] + chunk_weight <= hard_cap
            ]
            candidates = underfilled or [i for i in range(shard_count) if loads[i] + chunk_weight <= hard_cap]
            if not candidates:
                candidates = list(range(shard_count))
            chosen = max(candidates, key=lambda i: (affinity_scores[i], -loads[i], -i))
            assignments[chosen].extend(chunk)
            loads[chosen] += chunk_weight
            for node in chunk:
                assigned_to[node] = chosen

        edge_cut = 0
        for s, d in zip(self.src, self.dst):
            if assigned_to.get(s) != assigned_to.get(d):
                edge_cut += 1
        max_load = max(loads) if loads else 0
        mean_load = total_weight / shard_count if shard_count else 0
        return {
            "shards": [
                {
                    "shard": index,
                    "weight": loads[index],
                    "vertices": [self.vertex_ids[node] for node in sorted(assignments[index], key=lambda n: self.vertex_ids[n])],
                }
                for index in range(shard_count)
            ],
            "metrics": {
                "total_weight": total_weight,
                "target_weight": round(target, 3),
                "max_load": max_load,
                "max_load_ratio": round(max_load / mean_load, 4) if mean_load else 0.0,
                "edge_cut": edge_cut,
                "edge_cut_ratio": round(edge_cut / len(self.src), 6) if self.src else 0.0,
                "chunk_count": len(chunks),
            },
        }
