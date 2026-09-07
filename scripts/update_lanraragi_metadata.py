"""Repair LANraragi title and tags from the current EH Archive database.

The script is intentionally independent from the normal upload pipeline.  It
only updates metadata of archives that can be mapped unambiguously to a
database row and whose title or source manga ID is inconsistent.

Preview is the default.  Pass ``--apply`` to send PUT requests to LANraragi.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from eh_archive.config import load_config
from eh_archive.db import Database
from eh_archive.db.models import MangaRecord
from eh_archive.domain.models import MangaInfo
from eh_archive.services.uploader.lanraragi import LANraragiApiGateway

if __package__:
    from .collect_all_archives import fetch_archives, output_path, write_json
else:
    from collect_all_archives import fetch_archives, output_path, write_json


GALLERY_ID_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:exhentai|e-hentai)\.org/g/([0-9]+/[A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
ARCHIVE_ID_RE = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class DatabaseEntry:
    manga_id: str
    lrr_archive_id: str | None
    artifact_filename: str | None
    info: MangaInfo | None


class ProgressBar:
    """Small dependency-free terminal progress bar for long metadata repairs."""

    def __init__(self, total: int) -> None:
        self.total = max(0, total)
        self.current = 0
        self.started_at = time.monotonic()

    def update(self, *, candidates: int, updated: int, failed: int, skipped: int) -> None:
        self.current += 1
        width = 32
        done = min(self.current, self.total)
        ratio = done / self.total if self.total else 1.0
        filled = int(width * ratio)
        bar = "#" * filled + "." * (width - filled)
        elapsed = max(0.001, time.monotonic() - self.started_at)
        rate = done / elapsed
        line = (
            f"\r[{bar}] {done}/{self.total} {ratio:6.2%} "
            f"candidate={candidates} updated={updated} failed={failed} "
            f"skipped={skipped} {rate:.1f}/s"
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


def _manga_info(row: MangaRecord) -> MangaInfo | None:
    value = row.info
    if value is None:
        return None
    return MangaInfo(
        manga_id=value.manga_id,
        name=value.name,
        roman_name=value.roman_name,
        real_name=value.real_name,
        link=value.link,
        category=value.category,
        uploader=value.uploader,
        posted_at=value.posted_at,
        language=value.language,
        estimated_size_raw=value.estimated_size_raw,
        pages=value.pages,
        favorited=value.favorited,
        rating_count=value.rating_count,
        rating=value.rating,
        fetched_at=value.fetched_at,
        tags_raw=value.tags_raw,
        tags_translated_raw=value.tags_translated_raw,
        archive_url=None,
        parent_id=None,
    )


def load_database_entries(database: Database) -> list[DatabaseEntry]:
    with database.session() as session:
        rows = list(
            session.scalars(
                select(MangaRecord).options(joinedload(MangaRecord.info))
            )
        )
    return [
        DatabaseEntry(
            manga_id=row.manga_id,
            lrr_archive_id=row.lrr_archive_id,
            artifact_filename=row.artifact_filename,
            info=_manga_info(row),
        )
        for row in rows
    ]


def _normalise_tag_text(tags: str) -> str:
    return tags.replace("\\", "")


def gallery_ids_from_tags(tags: str) -> set[str]:
    return {
        match.group(1).rstrip("/").casefold()
        for match in GALLERY_ID_RE.finditer(_normalise_tag_text(tags))
    }


def _numeric_id(manga_id: str) -> str:
    return manga_id.split("/", 1)[0]


def filename_keys(filename: str, extension: str = "") -> set[str]:
    value = filename.strip().casefold()
    if not value:
        return set()
    keys = {value}
    clean_extension = extension.strip().lstrip(".").casefold()
    if clean_extension:
        suffix = f".{clean_extension}"
        if value.endswith(suffix):
            keys.add(value[: -len(suffix)])
        else:
            keys.add(value + suffix)
    return keys


def gallery_ids_from_filename(filename: str) -> set[str]:
    match = re.match(r"^\[([0-9]+(?:/[A-Za-z0-9_-]+)?)\]", filename.strip())
    return {match.group(1).casefold()} if match else set()


def build_indexes(
    entries: list[DatabaseEntry],
) -> tuple[
    dict[str, list[DatabaseEntry]],
    dict[str, list[DatabaseEntry]],
    dict[str, list[DatabaseEntry]],
    dict[str, list[DatabaseEntry]],
    dict[str, list[DatabaseEntry]],
]:
    by_archive_id: dict[str, list[DatabaseEntry]] = defaultdict(list)
    by_manga_id: dict[str, list[DatabaseEntry]] = defaultdict(list)
    by_numeric_id: dict[str, list[DatabaseEntry]] = defaultdict(list)
    by_filename: dict[str, list[DatabaseEntry]] = defaultdict(list)
    by_title: dict[str, list[DatabaseEntry]] = defaultdict(list)
    for entry in entries:
        if entry.lrr_archive_id:
            by_archive_id[entry.lrr_archive_id.casefold()].append(entry)
        by_manga_id[entry.manga_id.casefold()].append(entry)
        by_numeric_id[_numeric_id(entry.manga_id)].append(entry)
        if entry.artifact_filename:
            for key in filename_keys(entry.artifact_filename):
                by_filename[key].append(entry)
        if entry.info and entry.info.name.strip():
            by_title[entry.info.name.casefold()].append(entry)
    return by_archive_id, by_manga_id, by_numeric_id, by_filename, by_title


def resolve_entry(
    archive: dict[str, Any],
    *,
    by_archive_id: dict[str, list[DatabaseEntry]],
    by_manga_id: dict[str, list[DatabaseEntry]],
    by_numeric_id: dict[str, list[DatabaseEntry]],
    by_filename: dict[str, list[DatabaseEntry]],
    by_title: dict[str, list[DatabaseEntry]],
) -> tuple[DatabaseEntry | None, str | None, str | None]:
    archive_id = str(archive.get("arcid") or archive.get("id") or "").strip()
    direct = by_archive_id.get(archive_id.casefold(), [])
    if len(direct) == 1:
        return direct[0], None, "lrr_archive_id"

    ambiguous_reason: str | None = None

    tagged_ids = gallery_ids_from_tags(str(archive.get("tags") or ""))
    exact = {
        entry.manga_id.casefold(): entry
        for tagged_id in tagged_ids
        for entry in by_manga_id.get(tagged_id, [])
    }
    if len(exact) == 1:
        return next(iter(exact.values())), None, "tag_manga_id"
    if len(exact) > 1:
        ambiguous_reason = "ambiguous_manga_id"

    numeric_candidates = {
        entry.manga_id.casefold(): entry
        for tagged_id in tagged_ids
        for entry in by_numeric_id.get(tagged_id.split("/", 1)[0], [])
    }
    if len(numeric_candidates) == 1:
        return next(iter(numeric_candidates.values())), None, "tag_numeric_manga_id"
    if len(numeric_candidates) > 1:
        ambiguous_reason = ambiguous_reason or "ambiguous_numeric_manga_id"

    filename = str(archive.get("filename") or "")
    extension = str(archive.get("extension") or "")
    filename_candidates = {
        entry.manga_id.casefold(): entry
        for key in filename_keys(filename, extension)
        for entry in by_filename.get(key, [])
    }
    if len(filename_candidates) == 1:
        return next(iter(filename_candidates.values())), None, "filename"
    if len(filename_candidates) > 1:
        ambiguous_reason = ambiguous_reason or "ambiguous_filename"

    filename_numeric_candidates = {
        entry.manga_id.casefold(): entry
        for tagged_id in gallery_ids_from_filename(filename)
        for entry in by_numeric_id.get(tagged_id.split("/", 1)[0], [])
    }
    if len(filename_numeric_candidates) == 1:
        return next(iter(filename_numeric_candidates.values())), None, "filename_numeric_manga_id"
    if len(filename_numeric_candidates) > 1:
        ambiguous_reason = ambiguous_reason or "ambiguous_filename_numeric_manga_id"

    title = expected_title(archive).strip().casefold()
    title_candidates = {
        entry.manga_id.casefold(): entry for entry in by_title.get(title, [])
    }
    if title and len(title_candidates) == 1:
        return next(iter(title_candidates.values())), None, "title"
    if len(title_candidates) > 1:
        ambiguous_reason = ambiguous_reason or "ambiguous_title"

    return None, ambiguous_reason or "no_database_mapping", None


def expected_title(archive: dict[str, Any]) -> str:
    # LANraragi's documented field is title.  name is accepted for old export
    # files, but is never sent back to the API.
    return str(archive.get("title") or archive.get("name") or "")


def metadata_matches(payload: dict[str, Any] | None, expected: dict[str, str]) -> bool:
    return payload is not None and all(payload.get(key) == value for key, value in expected.items())


def report_path(app: Any, requested: str | None) -> Path:
    if requested:
        path = Path(requested).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return output_path(app.log_dir, "lanraragi_metadata_repair", app.timezone)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair LANraragi title/tags from EH Archive MangaInfo."
    )
    parser.add_argument("--config-dir", default="config")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="send metadata updates; without this flag the script only previews",
    )
    parser.add_argument("--limit", type=int, help="process at most this many LANraragi archives")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--report", help="write the JSON report to this path")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    app, _, _, secrets = load_config(args.config_dir)
    database = Database(app.database_url)
    api = LANraragiApiGateway(
        app.lanraragi_url,
        headers=secrets.lanraragi,
        timeout=args.timeout,
    )

    try:
        archives = fetch_archives(
            app.lanraragi_url,
            headers=secrets.lanraragi,
            timeout=args.timeout,
        )
        if args.limit is not None:
            archives = archives[: args.limit]
        entries = load_database_entries(database)
    finally:
        database.dispose()

    (
        by_archive_id,
        by_manga_id,
        by_numeric_id,
        by_filename,
        by_title,
    ) = build_indexes(entries)
    mode = "apply" if args.apply else "dry-run"
    print(f"LANraragi archives: {len(archives)}")
    print(f"Database rows with lrr_archive_id: {len(entries)}")
    print(f"Mode: {mode}")

    counters = {
        "scanned": 0,
        "unchanged": 0,
        "candidates": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }
    issues: list[dict[str, Any]] = []
    progress = ProgressBar(len(archives))

    def advance() -> None:
        progress.update(
            candidates=counters["candidates"],
            updated=counters["updated"],
            failed=counters["failed"],
            skipped=counters["skipped"],
        )

    for archive in archives:
        counters["scanned"] += 1
        archive_id = str(archive.get("arcid") or archive.get("id") or "").strip()
        item: dict[str, Any] = {
            "arcid": archive_id,
            "title": expected_title(archive),
            "filename": str(archive.get("filename") or ""),
        }

        if not ARCHIVE_ID_RE.fullmatch(archive_id):
            item["result"] = "skipped"
            item["reason"] = "unsupported_archive_id"
            counters["skipped"] += 1
            issues.append(item)
            advance()
            continue

        entry, mapping_error, mapping_method = resolve_entry(
            archive,
            by_archive_id=by_archive_id,
            by_manga_id=by_manga_id,
            by_numeric_id=by_numeric_id,
            by_filename=by_filename,
            by_title=by_title,
        )
        if entry is None:
            item["result"] = "skipped"
            item["reason"] = mapping_error or "no_database_mapping"
            counters["skipped"] += 1
            issues.append(item)
            advance()
            continue

        item["manga_id"] = entry.manga_id
        item["mapping_method"] = mapping_method
        if entry.info is None or not entry.info.is_complete():
            item["result"] = "skipped"
            item["reason"] = "missing_or_incomplete_mangainfo"
            counters["skipped"] += 1
            issues.append(item)
            advance()
            continue

        expected = api.metadata_values(entry.info)
        reasons: list[str] = []
        if expected_title(archive) != expected["title"]:
            reasons.append("title_mismatch")
        tagged_ids = gallery_ids_from_tags(str(archive.get("tags") or ""))
        if entry.manga_id.casefold() not in tagged_ids:
            reasons.append("manga_id_missing_from_tags")

        if not reasons:
            counters["unchanged"] += 1
            advance()
            continue

        counters["candidates"] += 1
        item["reasons"] = reasons
        item["expected_title"] = expected["title"]

        if not args.apply:
            item["result"] = "would_update"
            issues.append(item)
            advance()
            continue

        try:
            # Use the ID returned by the current LANraragi listing.  The
            # database ID is the preferred mapping key, but tag-based fallback
            # mapping may recover from a stale database archive ID.
            outcome = api.update_metadata(archive_id, entry.info, metadata=expected)
        except Exception as exc:  # noqa: BLE001 - one bad archive must not stop the batch
            counters["failed"] += 1
            item["result"] = "failed"
            item["error_code"] = type(exc).__name__
            item["error"] = str(exc)[:1000]
            issues.append(item)
            advance()
            continue

        if outcome.kind != "success":
            counters["failed"] += 1
            item["result"] = "failed"
            item["error_code"] = outcome.error_code
            item["status_code"] = outcome.status_code
            item["error"] = (outcome.response or "")[:1000]
            issues.append(item)
            advance()
            continue

        try:
            verify_status, payload = api.metadata(archive_id)
            verified = verify_status == 200 and metadata_matches(payload, expected)
        except Exception as exc:  # noqa: BLE001 - report verification failure and continue
            verified = False
            verify_status = None
            item["error"] = str(exc)[:1000]
        if not verified:
            counters["failed"] += 1
            item["result"] = "failed_verification"
            item["status_code"] = verify_status
            item.setdefault(
                "error",
                "LANraragi metadata did not match the generated metadata after update",
            )
            issues.append(item)
            advance()
            continue

        counters["updated"] += 1
        item["result"] = "updated"
        issues.append(item)
        advance()

    progress.finish()

    finished = datetime.now(ZoneInfo(app.timezone))
    report = {
        "generated_at": finished.isoformat(),
        "mode": mode,
        "lanraragi_source": f"{app.lanraragi_url.rstrip('/')}/api/archives",
        "summary": counters,
        "items": issues,
    }
    path = report_path(app, args.report)
    write_json(path, report)

    print(
        "Summary: "
        f"scanned={counters['scanned']}, unchanged={counters['unchanged']}, "
        f"candidates={counters['candidates']}, updated={counters['updated']}, "
        f"failed={counters['failed']}, skipped={counters['skipped']}"
    )
    print(f"JSON written: {path}")
    return 1 if counters["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
