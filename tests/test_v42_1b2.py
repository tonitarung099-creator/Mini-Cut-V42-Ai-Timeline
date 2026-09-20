import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from minicut_agent.v42_1b2 import (
    V42OneB2Plan,
    extract_candidate_ranges,
    load_1b2,
    parse_1b2_text,
    parse_registration_json,
    parse_timestamp,
)


class OneB2ParserTests(unittest.TestCase):
    def test_timestamp_parser_supports_v42_common_formats(self):
        self.assertEqual(parse_timestamp("00:01:02.500"), 62500)
        self.assertEqual(parse_timestamp("01:02,250"), 62250)

    def test_extract_candidate_ranges_preserves_order(self):
        ranges = extract_candidate_ranges(
            "00:01:00.000–00:01:05.000 lalu 00:01:07,500 --> 00:01:10,000"
        )
        self.assertEqual(
            [(item.start_ms, item.end_ms) for item in ranges],
            [(60000, 65000), (67500, 70000)],
        )

    def test_parse_v42_block_text_and_work_order(self):
        text = """
## B-001 — PENGANTAR
**Unit:** N-001, N-002, J-001
**Urutan tayang:** N-001 → N-002 → J-001
**Urutan pengerjaan:** J-001 → N-001 → N-002 → Audit B-001
**Wilayah kandidat tambahan yang belum eksklusif:** 00:10:00.000 - 00:10:08.000
**Kepemilikan visual:**
- N-001 → kandidat 00:09:40.000–00:09:48.500
- J-001: inti 00:10:02.000–00:10:05.000

1. J-001
2. N-001
3. N-002
4. Audit B-001
"""
        plan = parse_1b2_text(text)
        self.assertIn("B-001", plan.blocks)
        self.assertEqual(
            plan.blocks["B-001"].display_order,
            ["N-001", "N-002", "J-001"],
        )
        self.assertEqual(
            plan.work_queue,
            ["J-001", "N-001", "N-002", "Audit B-001"],
        )
        self.assertEqual(plan.units["N-001"].kind, "narration")
        self.assertEqual(plan.units["J-001"].kind, "anchor")
        self.assertEqual(len(plan.units["N-001"].candidate_ranges), 1)

    def test_parse_registration_json(self):
        raw = {
            "Registrasi Pusat": [
                {
                    "Part": 1,
                    "Blok": "B-001",
                    "Unit": "J-001",
                    "Jenis unit": "Jangkar",
                    "Urutan pengerjaan": 1,
                    "Wilayah kandidat visual": [
                        "00:00:10.000 - 00:00:14.000",
                        "00:00:15.000 - 00:00:18.000",
                    ],
                },
                {
                    "Part": 1,
                    "Blok": "B-001",
                    "Unit": "N-001",
                    "Jenis unit": "Narasi",
                    "Urutan pengerjaan": 2,
                    "Kolam visual per lokasi narasi": {
                        "Kantor": ["00:00:20.000 - 00:00:28.000"]
                    },
                    "Wilayah kandidat visual": "00:00:20.000 - 00:00:28.000",
                },
            ]
        }
        plan = parse_registration_json(raw)
        self.assertEqual(plan.work_queue, ["J-001", "N-001"])
        self.assertEqual(len(plan.units["J-001"].candidate_ranges), 2)
        self.assertEqual(len(plan.units["N-001"].candidate_ranges), 1)
        self.assertEqual(plan.units["N-001"].block_id, "B-001")
        self.assertEqual(plan.blocks["B-001"].work_order, ["J-001", "N-001"])
        self.assertEqual(
            plan.units["N-001"].fields["Kolam visual per lokasi narasi"]["Kantor"][0],
            "00:00:20.000 - 00:00:28.000",
        )

    def test_load_json_sets_digest_and_round_trips(self):
        raw = [
            {
                "Blok": "B-001",
                "Unit": "N-001",
                "Urutan pengerjaan": 1,
                "Wilayah kandidat visual": "00:00:01 - 00:00:04",
            }
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Registrasi-Pusat.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            plan = load_1b2(path)
            self.assertTrue(plan.source_sha256)
            restored = V42OneB2Plan.from_dict(plan.to_dict())
            self.assertEqual(restored.units["N-001"].candidate_ranges[0].start_ms, 1000)

    def test_load_minimal_docx_without_python_docx_dependency(self):
        document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>B-001 — TEST</w:t></w:r></w:p>
<w:p><w:r><w:t>Unit: N-001, J-001</w:t></w:r></w:p>
<w:p><w:r><w:t>Urutan pengerjaan: J-001 → N-001 → Audit B-001</w:t></w:r></w:p>
<w:p><w:r><w:t>N-001: 00:00:05.000 - 00:00:09.000</w:t></w:r></w:p>
</w:body></w:document>"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "Rencana-Induk.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
            plan = load_1b2(path)
            self.assertIn("B-001", plan.blocks)
            self.assertEqual(plan.work_queue[0], "J-001")
            self.assertEqual(len(plan.units["N-001"].candidate_ranges), 1)


if __name__ == "__main__":
    unittest.main()
