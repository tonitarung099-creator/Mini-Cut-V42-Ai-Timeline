import json
import tempfile
import unittest
from pathlib import Path

from minicut_agent.gemini_keys import (
    GeminiKeyPool,
    NoGeminiKeyAvailable,
    import_key_file,
    key_fingerprint,
    load_key_store,
    parse_key_text,
    save_key_store,
)


def fake_key(number: int) -> str:
    return "AIza" + f"{number:036d}"


class GeminiKeyPoolTests(unittest.TestCase):
    def test_parse_deduplicates_keys(self):
        a = fake_key(1)
        b = fake_key(2)
        self.assertEqual(parse_key_text(f"{a}\n{b}\n{a}\n"), [a, b])

    def test_maximum_100_keys(self):
        pool = GeminiKeyPool(fake_key(i) for i in range(100))
        self.assertEqual(pool.summary()["total"], 100)
        with self.assertRaises(ValueError):
            GeminiKeyPool(fake_key(i) for i in range(101))

    def test_round_robin_acquire(self):
        keys = [fake_key(1), fake_key(2), fake_key(3)]
        pool = GeminiKeyPool(keys)
        order = [pool.acquire().secret for _ in range(4)]
        self.assertEqual(order, [keys[0], keys[1], keys[2], keys[0]])

    def test_429_cools_key_and_fails_over(self):
        clock = [1000.0]
        pool = GeminiKeyPool(
            [fake_key(1), fake_key(2)],
            now=lambda: clock[0],
        )
        first = pool.acquire()
        pool.report_failure(first.key_id, status_code=429, error="quota")
        second = pool.acquire()
        self.assertNotEqual(first.key_id, second.key_id)
        states = {item["key_id"]: item for item in pool.summary()["keys"]}
        self.assertEqual(states[first.key_id]["status"], "cooldown")

    def test_bad_request_does_not_disable_key(self):
        pool = GeminiKeyPool([fake_key(1)])
        record = pool.acquire()
        pool.report_failure(record.key_id, status_code=400, error="bad request")
        state = pool.summary()["keys"][0]
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["failure_count"], 1)

    def test_auth_error_disables_key(self):
        pool = GeminiKeyPool([fake_key(1), fake_key(2)])
        first = pool.acquire()
        pool.report_failure(first.key_id, status_code=401, error="bad key")
        states = {item["key_id"]: item for item in pool.summary()["keys"]}
        self.assertEqual(states[first.key_id]["status"], "disabled")
        self.assertNotEqual(pool.acquire().key_id, first.key_id)

    def test_all_cooldown_reports_retry_time(self):
        clock = [50.0]
        pool = GeminiKeyPool([fake_key(1)], now=lambda: clock[0])
        record = pool.acquire()
        pool.report_failure(
            record.key_id,
            status_code=429,
            retry_after_seconds=12,
        )
        with self.assertRaises(NoGeminiKeyAvailable) as ctx:
            pool.acquire()
        self.assertAlmostEqual(ctx.exception.retry_after_seconds, 12.0)

    def test_success_resets_health(self):
        clock = [10.0]
        pool = GeminiKeyPool([fake_key(1)], now=lambda: clock[0])
        record = pool.acquire()
        pool.report_failure(record.key_id, status_code=500)
        clock[0] = 100.0
        record = pool.acquire()
        pool.report_success(record.key_id)
        state = pool.summary()["keys"][0]
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["failure_count"], 0)

    def test_store_round_trip_and_import_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "keys.json"
            import_file = Path(temp) / "keys.txt"
            import_file.write_text(
                f"{fake_key(1)}\n{fake_key(2)}\n",
                encoding="utf-8",
            )
            pool = import_key_file(import_file)
            save_key_store(pool, path)
            loaded = load_key_store(path)
            self.assertEqual(loaded.summary()["total"], 2)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("secret", raw["keys"][0])

    def test_public_summary_never_exposes_secret(self):
        key = fake_key(123)
        pool = GeminiKeyPool([key])
        summary_text = json.dumps(pool.summary())
        self.assertNotIn(key, summary_text)
        self.assertIn(key_fingerprint(key), summary_text)

    def test_error_redacts_api_key(self):
        key = fake_key(9)
        pool = GeminiKeyPool([key])
        record = pool.acquire()
        pool.report_failure(
            record.key_id,
            status_code=500,
            error=f"provider echoed {key}",
        )
        self.assertNotIn(key, pool.summary()["keys"][0]["last_error"])


if __name__ == "__main__":
    unittest.main()
