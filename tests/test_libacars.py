import unittest
from unittest.mock import patch

from src.helpers import get_libacars_summary, inline_summary
from src.libacars import decode_airframes_message


class LibacarsDecodeTests(unittest.TestCase):
    @patch("src.libacars.subprocess.run")
    def test_decode_airframes_message_accepts_ads_c_label(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"decoded": true}'

        message = {"label": "S6", "text": "POSITIVE", "link_direction": "d"}
        decoded = decode_airframes_message(message, decoder="/usr/bin/fake")

        self.assertEqual(decoded["label"], "S6")
        self.assertEqual(decoded["direction"], "d")
        self.assertEqual(decoded["decoded"], {"decoded": True})

    @patch("src.libacars.subprocess.run")
    def test_decode_airframes_message_accepts_generic_label(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"decoded": true}'

        message = {"label": "OH", "text": "DIAGNOSTIC", "link_direction": "u"}
        decoded = decode_airframes_message(message, decoder="/usr/bin/fake")

        self.assertEqual(decoded["label"], "OH")
        self.assertEqual(decoded["direction"], "u")
        self.assertEqual(decoded["decoded"], {"decoded": True})


class HelpersExampleTests(unittest.TestCase):
    def test_get_libacars_summary_formats_cpdcl_position(self):
        message = {
            "libacars": {
                "ok": True,
                "label": "SA",
                "decoded": {
                    "position": "40°38'N 73°47'W",
                    "flight_id": "AAL234",
                    "altitude": 25000,
                },
            }
        }

        summary = get_libacars_summary(message)

        self.assertIn("[SA]", summary)
        self.assertIn("position=40°38'N 73°47'W", summary)
        self.assertIn("flight_id=AAL234", summary)

    def test_inline_summary_prefers_libacars_decoded_text(self):
        message = {
            "timestamp": "2026-04-17T22:04:45Z",
            "station": {"ident": "KJFK", "country_code": "US"},
            "flight": {"flight_iata": "AA234"},
            "airframe": {"icao": "AE1453", "tail": "N12345", "military": False},
            "label": "H1",
            "text": "unused raw text",
            "libacars": {
                "ok": True,
                "label": "H1",
                "decoded": {
                    "message_type": "POS_REPORT",
                    "altitude": 3875,
                },
            },
        }

        summary = inline_summary(message, max_width=200)

        self.assertIn("[H1] message_type=POS_REPORT", summary)
        self.assertIn("altitude=3875", summary)


if __name__ == "__main__":
    unittest.main()
