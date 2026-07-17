import unittest

from src.flight_init import parse_flight_init_message, parse_flight_init_text


class FlightInitParserTests(unittest.TestCase):
    def test_parses_hash_mdini_space_separated_text(self):
        text = "- #MDINI/ID44129A RCH268 PAM306410163/MR0 0/AFPHNL PGWT/TD132140 00509B35"

        parsed = parse_flight_init_text(text)

        self.assertEqual(
            parsed,
            {
                "flight_init_id": "44129A",
                "callsign": "RCH268",
                "dataref": "PAM306410163",
                "mr": "0",
                "departure": "PHNL",
                "arrival": "PGWT",
                "date_day": "13",
                "time": "2140",
                "trailer": "00509B35",
            },
        )

    def test_parses_ini_comma_separated_text(self):
        text = "INI/ID15734T,RCH403,GJZF710QJ198/MR0,1/AFKLRF,KHRT/TD171245,1245011F"

        parsed = parse_flight_init_text(text)

        self.assertEqual(
            parsed,
            {
                "flight_init_id": "15734T",
                "callsign": "RCH403",
                "dataref": "GJZF710QJ198",
                "mr": "0",
                "departure": "KLRF",
                "arrival": "KHRT",
                "date_day": "17",
                "time": "1245",
                "trailer": "1245011F",
            },
        )

    def test_non_matching_text_returns_none(self):
        text = "73/N11356,1356,4332,0815,0859,0323,09071/N21356,1356,4114"

        self.assertIsNone(parse_flight_init_text(text))

    def test_empty_text_returns_none(self):
        self.assertIsNone(parse_flight_init_text(""))
        self.assertIsNone(parse_flight_init_text(None))

    def test_parse_flight_init_message_requires_h1_label(self):
        text = "- #MDINI/ID44129A RCH268 PAM306410163/MR0 0/AFPHNL PGWT/TD132140 00509B35"

        self.assertIsNone(
            parse_flight_init_message({"label": "SA", "text": text})
        )
        self.assertIsNotNone(
            parse_flight_init_message({"label": "H1", "text": text})
        )
        self.assertIsNotNone(
            parse_flight_init_message({"label": "h1", "text": text})
        )

    def test_parse_flight_init_message_rejects_non_dict(self):
        self.assertIsNone(parse_flight_init_message("not a dict"))
        self.assertIsNone(parse_flight_init_message(None))


if __name__ == "__main__":
    unittest.main()
