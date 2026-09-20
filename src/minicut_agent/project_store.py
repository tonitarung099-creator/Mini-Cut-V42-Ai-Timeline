from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .timeline_history import TimelineHistory
from .timeline_model import TimelineClip, TimelineDocument, TimelineTrack
from .timeline_tools import TimelineToolRegistry

SCHEMA_VERSION = 1
APP_ID = "MiniCut V42 AI Timeline"


@dataclass(slots=True)
class ProjectSnapshot:
    revision: int
    playhead_ms: int
    tracks: list[TimelineTrack]
    clips: list[TimelineClip]
    media: list[dict[str, Any]]
    workflow: dict[str, Any]
    missing_sources: list[str]


def build_project_data(
    document: TimelineDocument,
    *,
    revision: int,
    playhead_ms: int,
    media: list[dict[str, Any]] | None = None,
    workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if revision < 0:
        raise ValueError("revision tidak boleh negatif.")
    if playhead_ms < 0:
        raise ValueError("playhead_ms tidak boleh negatif.")

    return {
        "schema_version": SCHEMA_VERSION,
        "app": APP_ID,
        "timeline_revision": int(revision),
        "playhead_ms": int(playhead_ms),
        "tracks": [asdict(track) for track in document.tracks],
        "clips": [asdict(clip) for clip in document.clips],
        "media": _normalize_media(media or []),
        "workflow": dict(workflow or {}),
    }


def save_project(
    path: str | Path,
    document: TimelineDocument,
    *,
    revision: int,
    playhead_ms: int,
    media: list[dict[str, Any]] | None = None,
    workflow: dict[str, Any] | None = None,
) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = build_project_data(
        document,
        revision=revision,
        playhead_ms=playhead_ms,
        media=media,
        workflow=workflow,
    )

    temp = target.with_name(target.name + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp.replace(target)
    return target


def load_project(path: str | Path) -> ProjectSnapshot:
    source = Path(path).expanduser()
    raw = json.loads(source.read_text(encoding="utf-8"))
    return parse_project_data(raw)


def parse_project_data(raw: Any) -> ProjectSnapshot:
    if not isinstance(raw, dict):
        raise ValueError("Project harus berupa object JSON.")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Schema project tidak didukung: {raw.get('schema_version')!r}."
        )

    revision = _nonnegative_int(raw.get("timeline_revision", 0), "timeline_revision")
    playhead_ms = _nonnegative_int(raw.get("playhead_ms", 0), "playhead_ms")

    tracks_raw = raw.get("tracks")
    clips_raw = raw.get("clips")
    if not isinstance(tracks_raw, list) or not tracks_raw:
        raise ValueError("tracks harus berupa array yang tidak kosong.")
    if not isinstance(clips_raw, list):
        raise ValueError("clips harus berupa array.")

    tracks: list[TimelineTrack] = []
    track_ids: set[str] = set()
    valid_kinds = {"video", "audio", "subtitle"}
    for index, item in enumerate(tracks_raw):
        if not isinstance(item, dict):
            raise ValueError(f"Track #{index} harus berupa object.")
        track_id = str(item.get("id", ""))
        kind = str(item.get("kind", ""))
        if not track_id:
            raise ValueError(f"Track #{index} tidak memiliki id.")
        if track_id in track_ids:
            raise ValueError(f"Track id duplikat: {track_id}")
        if kind not in valid_kinds:
            raise ValueError(f"Jenis track tidak valid: {kind}")
        track_ids.add(track_id)
        tracks.append(
            TimelineTrack(
                id=track_id,
                name=str(item.get("name", track_id)),
                kind=kind,  # type: ignore[arg-type]
                locked=bool(item.get("locked", False)),
                visible=bool(item.get("visible", True)),
                muted=bool(item.get("muted", False)),
            )
        )

    clips: list[TimelineClip] = []
    clip_ids: set[str] = set()
    for index, item in enumerate(clips_raw):
        if not isinstance(item, dict):
            raise ValueError(f"Clip #{index} harus berupa object.")
        clip_id = str(item.get("id", ""))
        track_id = str(item.get("track_id", ""))
        if not clip_id:
            raise ValueError(f"Clip #{index} tidak memiliki id.")
        if clip_id in clip_ids:
            raise ValueError(f"Clip id duplikat: {clip_id}")
        if track_id not in track_ids:
            raise ValueError(f"Clip {clip_id} menunjuk track yang tidak ada: {track_id}")

        source_in_ms = _nonnegative_int(item.get("source_in_ms"), "source_in_ms")
        source_out_ms = _nonnegative_int(item.get("source_out_ms"), "source_out_ms")
        timeline_start_ms = _nonnegative_int(
            item.get("timeline_start_ms"), "timeline_start_ms"
        )
        try:
            speed = float(item.get("speed", 1.0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"speed clip {clip_id} tidak valid.") from exc

        if source_out_ms <= source_in_ms:
            raise ValueError(f"Rentang source clip {clip_id} tidak valid.")
        if speed <= 0:
            raise ValueError(f"speed clip {clip_id} harus lebih besar dari 0.")

        clip_ids.add(clip_id)
        clips.append(
            TimelineClip(
                id=clip_id,
                source=str(item.get("source", "")),
                track_id=track_id,
                source_in_ms=source_in_ms,
                source_out_ms=source_out_ms,
                timeline_start_ms=timeline_start_ms,
                speed=speed,
                muted=bool(item.get("muted", False)),
                locked=bool(item.get("locked", False)),
                group_id=(
                    None
                    if item.get("group_id") in (None, "")
                    else str(item.get("group_id"))
                ),
                label=str(item.get("label", "")),
            )
        )

    media = _normalize_media(raw.get("media", []))
    workflow_raw = raw.get("workflow", {})
    if not isinstance(workflow_raw, dict):
        raise ValueError("workflow harus berupa object.")

    known_sources = {
        str(entry["source"])
        for entry in media
        if str(entry.get("source", ""))
    }
    known_sources.update(clip.source for clip in clips if clip.source)
    missing_sources = sorted(
        source for source in known_sources if not Path(source).expanduser().exists()
    )

    return ProjectSnapshot(
        revision=revision,
        playhead_ms=playhead_ms,
        tracks=tracks,
        clips=clips,
        media=media,
        workflow=dict(workflow_raw),
        missing_sources=missing_sources,
    )


def apply_project(
    snapshot: ProjectSnapshot,
    *,
    document: TimelineDocument,
    history: TimelineHistory,
    registry: TimelineToolRegistry,
) -> None:
    if history.document is not document or registry.document is not document:
        raise ValueError("Document, history, dan registry harus menggunakan timeline yang sama.")

    document.tracks[:] = snapshot.tracks
    document.clips[:] = snapshot.clips
    history.reset()
    registry.restore_revision(snapshot.revision)


def _normalize_media(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("media harus berupa array.")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if isinstance(item, str):
            item = {"source": item}
        if not isinstance(item, dict):
            raise ValueError(f"Media #{index} harus berupa object atau string.")
        source = str(item.get("source", ""))
        if not source:
            raise ValueError(f"Media #{index} tidak memiliki source.")
        if source in seen:
            continue
        seen.add(source)
        duration = item.get("duration_ms")
        if duration is None:
            duration_ms = 0
        else:
            duration_ms = _nonnegative_int(duration, "duration_ms")
        normalized.append({"source": source, "duration_ms": duration_ms})
    return normalized


def _nonnegative_int(value: Any, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} harus berupa integer.") from exc
    if number < 0:
        raise ValueError(f"{name} tidak boleh negatif.")
    return number
