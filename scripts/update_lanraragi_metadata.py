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
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from eh_archive.config import load_config
from eh_archive.db import Database
from eh_archive.db.models import MangaRecord
from eh_archive.domain.models import MangaInfo
from eh_archive.services.uploader.lanraragi import (
    RETRYABLE_HTTP_STATUSES,
    LANraragiApiGateway,
)

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


@dataclass(frozen=True)
class MetadataUpdateJob:
    archive_id: str
    info: MangaInfo
    expected: dict[str, str]
    item: dict[str, Any]


@dataclass(frozen=True)
class MetadataVerificationJob:
    ready_at: float
    archive_id: str
    expected: dict[str, str]
    item: dict[str, Any]


class ProgressBar:
    """Small dependency-free terminal progress bar for long metadata repairs."""

    def __init__(self, total: int, timezone: str) -> None:
        self.total = max(0, total)
        self.timezone = timezone
        self.current = 0
        self.started_at = time.monotonic()

    def update(self, *, candidates: int, updated: int, failed: int, skipped: int) -> None:
        self.current += 1
        self.render(candidates=candidates, updated=updated, failed=failed, skipped=skipped)

    def refresh(self, *, candidates: int, updated: int, failed: int, skipped: int) -> None:
        self.render(candidates=candidates, updated=updated, failed=failed, skipped=skipped)

    def render(self, *, candidates: int, updated: int, failed: int, skipped: int) -> None:
        width = 32
        done = min(self.current, self.total)
        ratio = done / self.total if self.total else 1.0
        filled = int(width * ratio)
        bar = "#" * filled + "." * (width - filled)
        elapsed = max(0.001, time.monotonic() - self.started_at)
        rate = done / elapsed
        current_time = datetime.now(ZoneInfo(self.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"\r[{current_time}] [{bar}] {done}/{self.total} {ratio:6.2%} "
            f"candidate={candidates} updated={updated} failed={failed} "
            f"skipped={skipped} {rate:.1f}/s"
        )
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self) -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()


class RequestPacer:
    def __init__(self, interval: float) -> None:
        self.interval = max(0.0, interval)
        self.next_allowed_at = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next_allowed_at - now
            if delay > 0:
                time.sleep(delay)
            self.next_allowed_at = time.monotonic() + self.interval


def _retry_delay(backoff: float, attempt: int) -> float:
    return min(30.0, backoff * (2 ** max(0, attempt - 1)))


def _timestamp(timezone: str) -> str:
    return datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S")


def _metadata_update_with_retry(
    api: LANraragiApiGateway,
    archive_id: str,
    info: MangaInfo,
    expected: dict[str, str],
    *,
    pacer: RequestPacer,
    attempts: int,
    backoff: float,
    timezone: str,
) -> Any:
    for attempt in range(1, attempts + 1):
        pacer.wait()
        try:
            outcome = api.update_metadata(archive_id, info, metadata=expected)
        except Exception:
            if attempt >= attempts:
                raise
            delay = _retry_delay(backoff, attempt)
            print(
                f"\n[{_timestamp(timezone)}] metadata update exception for "
                f"{archive_id}; retry {attempt}/{attempts - 1} in {delay:.1f}s"
            )
            time.sleep(delay)
            continue
        if outcome.kind != "retry" or attempt >= attempts:
            return outcome
        delay = _retry_delay(backoff, attempt)
        print(
            f"\n[{_timestamp(timezone)}] LANraragi returned "
            f"HTTP {outcome.status_code}; retry {attempt}/{attempts - 1} "
            f"for {archive_id} in {delay:.1f}s"
        )
        time.sleep(delay)
    raise RuntimeError("metadata update retry loop ended unexpectedly")


def _metadata_with_retry(
    api: LANraragiApiGateway,
    archive_id: str,
    *,
    pacer: RequestPacer,
    attempts: int,
    backoff: float,
    timezone: str,
) -> tuple[int | None, dict[str, Any] | None]:
    for attempt in range(1, attempts + 1):
        pacer.wait()
        try:
            status, payload = api.metadata(archive_id)
        except Exception:
            if attempt >= attempts:
                raise
            delay = _retry_delay(backoff, attempt)
            print(
                f"\n[{_timestamp(timezone)}] metadata verification exception for "
                f"{archive_id}; retry {attempt}/{attempts - 1} in {delay:.1f}s"
            )
            time.sleep(delay)
            continue
        if status not in RETRYABLE_HTTP_STATUSES and status not in {400, 404}:
            return status, payload
        if attempt >= attempts:
            return status, payload
        delay = _retry_delay(backoff, attempt)
        print(
            f"\n[{_timestamp(timezone)}] metadata verification returned "
            f"HTTP {status}; retry {attempt}/{attempts - 1} for "
            f"{archive_id} in {delay:.1f}s"
        )
        time.sleep(delay)
    raise RuntimeError("metadata verification retry loop ended unexpectedly")


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
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="HTTP timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--request-interval",
        type=float,
        default=0.2,
        help="minimum seconds between LANraragi requests (default: 0.2)",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=5,
        help="total attempts for retryable update/verification failures (default: 5)",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=1.0,
        help="initial retry backoff in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--verify-delay",
        type=float,
        default=5.0,
        help="seconds to wait after a successful PUT before GET verification (default: 5)",
    )
    parser.add_argument("--report", help="write the JSON report to this path")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if args.request_interval < 0:
        parser.error("--request-interval must be non-negative")
    if args.retry_attempts <= 0:
        parser.error("--retry-attempts must be positive")
    if args.retry_backoff < 0:
        parser.error("--retry-backoff must be non-negative")
    if args.verify_delay < 0:
        parser.error("--verify-delay must be non-negative")

    app, _, _, secrets = load_config(args.config_dir)
    database = Database(app.database_url)
    api = LANraragiApiGateway(
        app.lanraragi_url,
        headers=secrets.lanraragi,
        timeout=args.timeout,
    )
    verify_api = LANraragiApiGateway(
        app.lanraragi_url,
        headers=secrets.lanraragi,
        timeout=args.timeout,
    )

    fetch_started_at = time.monotonic()
    fetch_started_text = datetime.now(ZoneInfo(app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"[{fetch_started_text}] Fetching LANraragi archives "
        f"(timeout={args.timeout:.0f}s)..."
    )
    try:
        archives = fetch_archives(
            app.lanraragi_url,
            headers=secrets.lanraragi,
            timeout=args.timeout,
        )
        if args.limit is not None:
            archives = archives[: args.limit]
        fetch_elapsed = time.monotonic() - fetch_started_at
        fetch_finished_text = datetime.now(ZoneInfo(app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"[{fetch_finished_text}] LANraragi archives received: "
            f"{len(archives)} (elapsed={fetch_elapsed:.1f}s)"
        )
    except Exception:
        fetch_elapsed = time.monotonic() - fetch_started_at
        fetch_failed_text = datetime.now(ZoneInfo(app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"[{fetch_failed_text}] LANraragi archive request failed "
            f"(elapsed={fetch_elapsed:.1f}s)",
            file=sys.stderr,
        )
        raise

    db_started_at = time.monotonic()
    db_started_text = datetime.now(ZoneInfo(app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{db_started_text}] Loading database metadata...")
    try:
        entries = load_database_entries(database)
        db_elapsed = time.monotonic() - db_started_at
        db_finished_text = datetime.now(ZoneInfo(app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"[{db_finished_text}] Database metadata loaded: "
            f"{len(entries)} (elapsed={db_elapsed:.1f}s)"
        )
    except Exception:
        db_elapsed = time.monotonic() - db_started_at
        db_failed_text = datetime.now(ZoneInfo(app.timezone)).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"[{db_failed_text}] Database metadata load failed "
            f"(elapsed={db_elapsed:.1f}s)",
            file=sys.stderr,
        )
        raise
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
    print(f"Database rows loaded: {len(entries)}")
    print(f"Mode: {mode}")
    if args.apply:
        print(
            f"Request interval: {args.request_interval:.2f}s; "
            f"retry attempts: {args.retry_attempts}; "
            f"PUT-to-GET verification delay: {args.verify_delay:.1f}s; "
            "pipeline: 1 PUT worker + 1 GET worker"
        )

    counters = {
        "scanned": 0,
        "unchanged": 0,
        "candidates": 0,
        "updated": 0,
        "failed": 0,
        "skipped": 0,
    }
    failure_reasons: defaultdict[str, int] = defaultdict(int)
    issues: list[dict[str, Any]] = []
    progress = ProgressBar(len(archives), app.timezone)
    pacer = RequestPacer(args.request_interval)
    state_lock = threading.Lock()
    progress_lock = threading.Lock()
    put_queue: Queue[MetadataUpdateJob | None] = Queue()
    verify_queue: Queue[MetadataVerificationJob | None] = Queue()

    def advance() -> None:
        with progress_lock:
            progress.update(
                candidates=counters["candidates"],
                updated=counters["updated"],
                failed=counters["failed"],
                skipped=counters["skipped"],
            )

    def refresh_progress() -> None:
        with progress_lock:
            progress.refresh(
                candidates=counters["candidates"],
                updated=counters["updated"],
                failed=counters["failed"],
                skipped=counters["skipped"],
            )

    def record_failure(
        item: dict[str, Any],
        *,
        result: str,
        error_code: str | None,
        status_code: int | None = None,
        error: str = "",
    ) -> None:
        with state_lock:
            counters["failed"] += 1
            item["result"] = result
            item["error_code"] = error_code
            if status_code is not None:
                item["status_code"] = status_code
            if error:
                item["error"] = error[:1000]
            reason = error_code or f"http_{status_code}"
            failure_reasons[reason] += 1
            issues.append(item)
        refresh_progress()

    def record_updated(item: dict[str, Any]) -> None:
        with state_lock:
            counters["updated"] += 1
            item["result"] = "updated"
            issues.append(item)
        refresh_progress()

    def put_worker() -> None:
        while True:
            job = put_queue.get()
            try:
                if job is None:
                    return
                try:
                    outcome = _metadata_update_with_retry(
                        api,
                        job.archive_id,
                        job.info,
                        job.expected,
                        pacer=pacer,
                        attempts=args.retry_attempts,
                        backoff=args.retry_backoff,
                        timezone=app.timezone,
                    )
                except Exception as exc:  # noqa: BLE001 - one bad archive must not stop the batch
                    record_failure(
                        job.item,
                        result="failed",
                        error_code=type(exc).__name__,
                        error=str(exc),
                    )
                    continue

                if outcome.kind != "success":
                    record_failure(
                        job.item,
                        result="failed",
                        error_code=outcome.error_code,
                        status_code=outcome.status_code,
                        error=outcome.response or "",
                    )
                    continue

                verify_queue.put(
                    MetadataVerificationJob(
                        ready_at=time.monotonic() + args.verify_delay,
                        archive_id=job.archive_id,
                        expected=job.expected,
                        item=job.item,
                    )
                )
            finally:
                put_queue.task_done()

    def verify_worker() -> None:
        while True:
            job = verify_queue.get()
            try:
                if job is None:
                    return
                delay = job.ready_at - time.monotonic()
                if delay > 0:
                    time.sleep(delay)

                try:
                    verify_status, payload = _metadata_with_retry(
                        verify_api,
                        job.archive_id,
                        pacer=pacer,
                        attempts=args.retry_attempts,
                        backoff=args.retry_backoff,
                        timezone=app.timezone,
                    )
                    verified = verify_status == 200 and metadata_matches(
                        payload, job.expected
                    )
                except Exception as exc:  # noqa: BLE001 - report verification failure and continue
                    verified = False
                    verify_status = None
                    job.item["error"] = str(exc)[:1000]

                if verified:
                    record_updated(job.item)
                    continue

                job.item.setdefault(
                    "error",
                    "LANraragi metadata did not match the generated metadata after update",
                )
                if verify_status is None:
                    failure_reason = "verification_exception"
                elif verify_status != 200:
                    failure_reason = f"verification_http_{verify_status}"
                else:
                    failure_reason = "verification_mismatch"
                record_failure(
                    job.item,
                    result="failed_verification",
                    error_code=failure_reason,
                    status_code=verify_status,
                    error=str(job.item["error"]),
                )
            finally:
                verify_queue.task_done()

    put_thread: threading.Thread | None = None
    verify_thread: threading.Thread | None = None
    if args.apply:
        verify_thread = threading.Thread(
            target=verify_worker,
            name="lanraragi-metadata-verify",
            daemon=True,
        )
        put_thread = threading.Thread(
            target=put_worker,
            name="lanraragi-metadata-put",
            daemon=True,
        )
        verify_thread.start()
        put_thread.start()

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

        # The PUT worker can continue with the next archive while the GET
        # worker waits for this archive's delayed verification window.
        put_queue.put(
            MetadataUpdateJob(
                archive_id=archive_id,
                info=entry.info,
                expected=expected,
                item=item,
            )
        )
        advance()

    if args.apply:
        put_queue.put(None)
        put_queue.join()
        assert put_thread is not None
        assert verify_thread is not None
        put_thread.join()
        verify_queue.put(None)
        verify_queue.join()
        verify_thread.join()

    progress.finish()

    finished = datetime.now(ZoneInfo(app.timezone))
    report = {
        "generated_at": finished.isoformat(),
        "mode": mode,
        "lanraragi_source": f"{app.lanraragi_url.rstrip('/')}/api/archives",
        "summary": counters,
        "failure_reasons": dict(sorted(failure_reasons.items())),
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
