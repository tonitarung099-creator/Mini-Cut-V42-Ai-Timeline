import json
import tempfile
import unittest
from pathlib import Path

from minicut_agent.evidence_packets import (
    FrameEvidence,
    ShotEvidence,
    SubtitleCue,
    UnitEvidencePacket,
)
from minicut_agent.gemini_client import (
    EvidenceBatch,
    GeminiEvidenceClient,
    GeminiRequestError,
    GeminiResponseError,
    build_evidence_batches,
    build_interaction_body,
    extract_output_text,
    parse_batch_response,
)
from minicut_agent.gemini_keys import GeminiKeyPool


def fake_key(number: int) -> str:
    return "AIza" + f"{number:036d}"


def model_response(unit_id, batch_index, decisions, notes="ok"):
    payload = {
        "unit_id": unit_id,
        "batch_index": batch_index,
        "decisions": decisions,
        "notes": notes,
    }
    return {
        "id": "int_test",
        "steps": [
            {
                "type": "model_output",
                "status": "done",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(payload),
                    }
                ],
            }
        ],
    }


class GeminiClientTests(unittest.TestCase):
    def packet(self, root: Path, shots=2):
        evidence = []
        for index in range(shots):
            frames = []
            for sample in range(3):
                path = root / f"s{index}-{sample}.jpg"
                path.write_bytes(bytes([index + sample + 1]) * 10)
                frames.append(
                    FrameEvidence(
                        timestamp_ms=index * 5000 + sample * 500,
                        path=str(path),
                        size_bytes=10,
                    )
                )
            evidence.append(
                ShotEvidence(
                    start_ms=index * 5000,
                    end_ms=(index + 1) * 5000,
                    candidate_start_ms=0,
                    candidate_end_ms=shots * 5000,
                    location="lokasi",
                    frames=frames,
                    subtitles=[
                        SubtitleCue(
                            start_ms=index * 5000,
                            end_ms=index * 5000 + 1000,
                            text=f"dialog {index + 1}",
                        )
                    ],
                )
            )
        return UnitEvidencePacket(
            unit_id="N-001",
            source="film.mp4",
            source_fingerprint="fp",
            one_b2_source_sha256="1b2",
            shots=evidence,
        )

    def test_batches_respect_image_count(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=5)
            batches = build_evidence_batches(
                packet,
                max_images=6,
                max_inline_bytes=100000,
            )
            self.assertEqual(
                [batch.shot_indexes for batch in batches],
                [[1, 2], [3, 4], [5]],
            )
            self.assertTrue(all(batch.image_count <= 6 for batch in batches))

    def test_interaction_body_uses_interactions_multimodal_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=1)
            batch = build_evidence_batches(packet)[0]
            body = build_interaction_body(
                packet,
                batch,
                model="gemini-test",
                unit_context={"Narasi": "teks target"},
            )
            self.assertEqual(body["model"], "gemini-test")
            self.assertFalse(body["store"])
            self.assertEqual(body["response_format"]["mime_type"], "application/json")
            images = [item for item in body["input"] if item["type"] == "image"]
            self.assertEqual(len(images), 3)
            self.assertTrue(all(item["mime_type"] == "image/jpeg" for item in images))
            encoded = json.dumps(body)
            self.assertNotIn(str(Path(temp)), encoded)

    def test_parse_response_rejects_missing_shot(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=2)
            batch = build_evidence_batches(packet)[0]
            response = model_response(
                "N-001",
                1,
                [
                    {
                        "shot_index": 1,
                        "decision": "keep",
                        "confidence": 0.8,
                        "reason": "relevan",
                    }
                ],
            )
            with self.assertRaises(GeminiResponseError):
                parse_batch_response(
                    response,
                    packet=packet,
                    batch=batch,
                    model="m",
                    key_id="k",
                )

    def test_trim_must_stay_inside_shot(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=1)
            batch = build_evidence_batches(packet)[0]
            response = model_response(
                "N-001",
                1,
                [
                    {
                        "shot_index": 1,
                        "decision": "trim",
                        "confidence": 0.8,
                        "reason": "bagian tengah",
                        "trim_start_ms": -10,
                        "trim_end_ms": 3000,
                    }
                ],
            )
            with self.assertRaises(GeminiResponseError):
                parse_batch_response(
                    response,
                    packet=packet,
                    batch=batch,
                    model="m",
                    key_id="k",
                )

    def test_429_fails_over_to_second_key(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=1)
            calls = []
            keys = [fake_key(1), fake_key(2)]
            pool = GeminiKeyPool(keys)

            def transport(url, headers, body, timeout):
                calls.append(headers["x-goog-api-key"])
                if len(calls) == 1:
                    return (
                        429,
                        {"Retry-After": "30"},
                        json.dumps({"error": {"message": "quota"}}).encode(),
                    )
                return (
                    200,
                    {},
                    json.dumps(
                        model_response(
                            "N-001",
                            1,
                            [
                                {
                                    "shot_index": 1,
                                    "decision": "keep",
                                    "confidence": 0.9,
                                    "reason": "sesuai",
                                }
                            ],
                        )
                    ).encode(),
                )

            client = GeminiEvidenceClient(
                pool,
                model="gemini-test",
                transport=transport,
                key_state_saver=None,
            )
            result = client.verify_unit(packet)
            self.assertEqual(calls, keys)
            self.assertEqual(result.summary()["keep"], 1)
            self.assertEqual(result.batches[0].key_id, pool.records[1].key_id)

    def test_400_does_not_cycle_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=1)
            calls = []
            pool = GeminiKeyPool([fake_key(1), fake_key(2)])

            def transport(url, headers, body, timeout):
                calls.append(headers["x-goog-api-key"])
                return (
                    400,
                    {},
                    json.dumps({"error": {"message": "bad schema"}}).encode(),
                )

            client = GeminiEvidenceClient(
                pool,
                transport=transport,
                key_state_saver=None,
            )
            with self.assertRaises(GeminiRequestError):
                client.verify_unit(packet)
            self.assertEqual(len(calls), 1)
            self.assertEqual(pool.summary()["disabled"], 0)

    def test_401_disables_and_fails_over(self):
        with tempfile.TemporaryDirectory() as temp:
            packet = self.packet(Path(temp), shots=1)
            pool = GeminiKeyPool([fake_key(1), fake_key(2)])
            calls = []

            def transport(url, headers, body, timeout):
                calls.append(headers["x-goog-api-key"])
                if len(calls) == 1:
                    return (
                        401,
                        {},
                        b'{"error":{"message":"invalid key"}}',
                    )
                return (
                    200,
                    {},
                    json.dumps(
                        model_response(
                            "N-001",
                            1,
                            [
                                {
                                    "shot_index": 1,
                                    "decision": "reject",
                                    "confidence": 0.7,
                                    "reason": "tidak relevan",
                                }
                            ],
                        )
                    ).encode(),
                )

            client = GeminiEvidenceClient(
                pool,
                transport=transport,
                key_state_saver=None,
            )
            result = client.verify_unit(packet)
            self.assertEqual(result.summary()["reject"], 1)
            self.assertEqual(pool.summary()["disabled"], 1)

    def test_extract_output_text_from_steps(self):
        interaction = {
            "steps": [
                {"type": "user_input", "content": [{"type": "text", "text": "x"}]},
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": '{"ok":true}'}],
                },
            ]
        }
        self.assertEqual(extract_output_text(interaction), '{"ok":true}')


if __name__ == "__main__":
    unittest.main()
