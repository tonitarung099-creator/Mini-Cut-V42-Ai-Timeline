from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

TrackKind = Literal["video", "audio", "subtitle"]


@dataclass(slots=True)
class TimelineTrack:
    id: str
    name: str
    kind: TrackKind
    locked: bool = False
    visible: bool = True
    muted: bool = False


@dataclass(slots=True)
class TimelineClip:
    id: str
    source: str
    track_id: str
    source_in_ms: int
    source_out_ms: int
    timeline_start_ms: int
    speed: float = 1.0
    muted: bool = False
    locked: bool = False
    group_id: str | None = None
    label: str = ""

    @property
    def source_duration_ms(self) -> int:
        return max(0, self.source_out_ms - self.source_in_ms)

    @property
    def timeline_duration_ms(self) -> int:
        if self.speed <= 0:
            return 0
        return int(round(self.source_duration_ms / self.speed))

    @property
    def timeline_end_ms(self) -> int:
        return self.timeline_start_ms + self.timeline_duration_ms

    def contains_timeline_time(self, milliseconds: int) -> bool:
        return self.timeline_start_ms < milliseconds < self.timeline_end_ms


@dataclass
class TimelineDocument:
    tracks: list[TimelineTrack] = field(default_factory=list)
    clips: list[TimelineClip] = field(default_factory=list)

    @classmethod
    def default(cls) -> "TimelineDocument":
        return cls(
            tracks=[
                TimelineTrack("V2", "V2", "video"),
                TimelineTrack("V1", "V1", "video"),
                TimelineTrack("A2", "A2", "audio"),
                TimelineTrack("A1", "A1", "audio"),
                TimelineTrack("SUB", "SUB", "subtitle"),
            ]
        )

    def track(self, track_id: str) -> TimelineTrack:
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise KeyError(f"Track tidak ditemukan: {track_id}")

    def clip(self, clip_id: str) -> TimelineClip:
        for clip in self.clips:
            if clip.id == clip_id:
                return clip
        raise KeyError(f"Clip tidak ditemukan: {clip_id}")

    def linked_clips(self, clip_id: str) -> list[TimelineClip]:
        selected = self.clip(clip_id)
        if not selected.group_id:
            return [selected]
        return [clip for clip in self.clips if clip.group_id == selected.group_id]

    def insert_clip(
        self,
        *,
        source: str | Path,
        track_id: str,
        source_in_ms: int,
        source_out_ms: int,
        timeline_start_ms: int,
        speed: float = 1.0,
        muted: bool = False,
        group_id: str | None = None,
        label: str = "",
        clip_id: str | None = None,
    ) -> TimelineClip:
        track = self.track(track_id)
        if track.locked:
            raise ValueError(f"Track {track_id} sedang dikunci.")
        if source_out_ms <= source_in_ms:
            raise ValueError("source_out_ms harus lebih besar dari source_in_ms.")
        if timeline_start_ms < 0:
            raise ValueError("timeline_start_ms tidak boleh negatif.")
        if speed <= 0:
            raise ValueError("speed harus lebih besar dari 0.")

        clip = TimelineClip(
            id=clip_id or uuid4().hex,
            source=str(source),
            track_id=track_id,
            source_in_ms=int(source_in_ms),
            source_out_ms=int(source_out_ms),
            timeline_start_ms=int(timeline_start_ms),
            speed=float(speed),
            muted=bool(muted),
            group_id=group_id,
            label=label or Path(source).name,
        )
        self.clips.append(clip)
        self._sort_clips()
        return clip

    def remove_clip(self, clip_id: str) -> TimelineClip:
        clip = self.clip(clip_id)
        if clip.locked:
            raise ValueError("Clip sedang dikunci.")
        self.clips.remove(clip)
        return clip

    def remove_linked(self, clip_id: str) -> list[TimelineClip]:
        targets = list(self.linked_clips(clip_id))
        if any(clip.locked or self.track(clip.track_id).locked for clip in targets):
            raise ValueError("Clip atau track terkait sedang dikunci.")
        for clip in targets:
            self.clips.remove(clip)
        return targets

    def move_clip(self, clip_id: str, *, track_id: str | None = None, timeline_start_ms: int | None = None) -> TimelineClip:
        clip = self.clip(clip_id)
        if clip.locked:
            raise ValueError("Clip sedang dikunci.")
        if track_id is not None:
            current_track = self.track(clip.track_id)
            target_track = self.track(track_id)
            if target_track.locked:
                raise ValueError(f"Track {track_id} sedang dikunci.")
            if target_track.kind != current_track.kind:
                raise ValueError("Clip hanya boleh dipindahkan ke track dengan jenis yang sama.")
            clip.track_id = track_id
        if timeline_start_ms is not None:
            if timeline_start_ms < 0:
                raise ValueError("timeline_start_ms tidak boleh negatif.")
            clip.timeline_start_ms = int(timeline_start_ms)
        self._sort_clips()
        return clip

    def move_linked(
        self,
        clip_id: str,
        *,
        timeline_start_ms: int,
        track_id: str | None = None,
    ) -> list[TimelineClip]:
        selected = self.clip(clip_id)
        if selected.locked:
            raise ValueError("Clip sedang dikunci.")
        targets = list(self.linked_clips(clip_id))
        delta = int(timeline_start_ms) - selected.timeline_start_ms
        if any(clip.timeline_start_ms + delta < 0 for clip in targets):
            raise ValueError("Linked clip tidak boleh bergerak sebelum awal timeline.")
        if any(clip.locked or self.track(clip.track_id).locked for clip in targets):
            raise ValueError("Clip atau track terkait sedang dikunci.")

        if track_id is not None and track_id != selected.track_id:
            current_track = self.track(selected.track_id)
            target_track = self.track(track_id)
            if target_track.locked:
                raise ValueError(f"Track {track_id} sedang dikunci.")
            if target_track.kind != current_track.kind:
                raise ValueError("Clip hanya boleh dipindahkan ke track dengan jenis yang sama.")
            selected.track_id = track_id

        for clip in targets:
            clip.timeline_start_ms += delta
        self._sort_clips()
        return targets

    def split_linked_at(self, clip_id: str, timeline_ms: int) -> list[TimelineClip]:
        selected = self.clip(clip_id)
        if not selected.contains_timeline_time(timeline_ms):
            raise ValueError("Playhead harus berada di dalam clip yang dipilih.")

        targets = [
            clip
            for clip in self.linked_clips(clip_id)
            if clip.contains_timeline_time(timeline_ms)
        ]
        if any(clip.locked or self.track(clip.track_id).locked for clip in targets):
            raise ValueError("Clip atau track terkait sedang dikunci.")

        right_group = uuid4().hex if selected.group_id else None
        created: list[TimelineClip] = []
        for clip in targets:
            original_out = clip.source_out_ms
            source_split = clip.source_in_ms + int(round((timeline_ms - clip.timeline_start_ms) * clip.speed))
            source_split = min(max(source_split, clip.source_in_ms + 1), original_out - 1)

            clip.source_out_ms = source_split
            right = TimelineClip(
                id=uuid4().hex,
                source=clip.source,
                track_id=clip.track_id,
                source_in_ms=source_split,
                source_out_ms=original_out,
                timeline_start_ms=int(timeline_ms),
                speed=clip.speed,
                muted=clip.muted,
                locked=False,
                group_id=right_group,
                label=clip.label,
            )
            self.clips.append(right)
            created.append(right)

        self._sort_clips()
        return created

    def clips_on_track(self, track_id: str) -> list[TimelineClip]:
        self.track(track_id)
        return [clip for clip in self.clips if clip.track_id == track_id]

    def next_free_time(self, track_id: str) -> int:
        clips = self.clips_on_track(track_id)
        return max((clip.timeline_end_ms for clip in clips), default=0)

    @property
    def duration_ms(self) -> int:
        return max((clip.timeline_end_ms for clip in self.clips), default=0)

    def _sort_clips(self) -> None:
        self.clips.sort(key=lambda item: (self._track_index(item.track_id), item.timeline_start_ms, item.id))

    def _track_index(self, track_id: str) -> int:
        for index, track in enumerate(self.tracks):
            if track.id == track_id:
                return index
        return len(self.tracks)
