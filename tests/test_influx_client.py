import unittest

from src.influx_client import InfluxClient


def sample_message(**overrides):
    message = {
        "timestamp": "2026-06-30T12:00:00Z",
        "station": {"ident": "ACARS-1", "country_code": "US"},
        "airframe": {"icao": "A1B2C3", "tail": "N123AB", "military": False},
        "flight": {"flight_iata": "AA123"},
        "source": "acarsdec",
        "source_type": "acars",
        "label": "H1",
        "mode": "2",
        "text": "hello",
        "libacars": {"ok": False},
    }
    message.update(overrides)
    return message


def build_client():
    return InfluxClient(
        "http://localhost:8086",
        token="token",
        org="org",
        bucket="bucket",
    )


class InfluxClientTests(unittest.TestCase):
    def test_event_line_uses_icao_as_tag_and_event_count_field(self):
        line = build_client().build_event_line(sample_message())

        self.assertIn("airframes_event,", line)
        self.assertIn("airframe_icao=A1B2C3", line)
        self.assertIn('tail="N123AB"', line)
        self.assertIn('flight="AA123"', line)
        self.assertIn("libacars_ok=0i", line)
        self.assertIn("text_present=1i", line)
        self.assertIn("text_length=5i", line)
        self.assertIn("event_count=1i", line)

    def test_event_line_includes_pretty_printed_libacars_decoded_text(self):
        message = sample_message(
            label="SA",
            libacars={
                "ok": True,
                "label": "SA",
                "decoded": {"position": "40N", "flight_id": "AAL234"},
            },
        )

        line = build_client().build_event_line(message)

        self.assertIn('libacars_text="{\\n', line)
        self.assertIn('flight_id\\": \\"AAL234\\"', line)

    def test_event_line_libacars_text_empty_when_decode_missing(self):
        line = build_client().build_event_line(sample_message())

        self.assertIn('libacars_text="",', line)

    def test_catalog_line_keeps_one_entity_per_icao(self):
        client = build_client()

        first = client.build_catalog_line(sample_message())
        second = client.build_catalog_line(
            sample_message(
                timestamp="2026-06-30T12:05:00Z",
                airframe={"icao": "A1B2C3", "tail": "N456CD", "military": True},
                flight={"flight_iata": "AA456"},
                label="SA",
                libacars={"ok": True, "label": "SA", "decoded": {"position": "40N"}},
            )
        )

        self.assertIn("airframes_catalog,airframe_icao=A1B2C3", first)
        self.assertTrue(first.endswith(" 0"))
        self.assertIn('first_seen="2026-06-30T12:00:00Z"', second)
        self.assertIn('last_seen="2026-06-30T12:05:00Z"', second)
        self.assertIn('tail="N456CD"', second)
        self.assertIn('flight="AA456"', second)
        self.assertIn("military=true", second)
        self.assertIn("message_count=2i", second)
        self.assertIn('last_decoded_text="{\\n  \\"position\\": \\"40N\\"\\n}"', second)

    def test_catalog_skips_messages_without_icao(self):
        client = build_client()

        line = client.build_catalog_line(sample_message(airframe={}))

        self.assertIsNone(line)


if __name__ == "__main__":
    unittest.main()
