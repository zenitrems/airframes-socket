import unittest

from src.helpers import parse_station_ids


class ParseStationIdsTests(unittest.TestCase):
    def test_parses_repeated_arguments(self):
        self.assertEqual(parse_station_ids(["123", "456"]), [123, 456])

    def test_parses_comma_separated_values(self):
        self.assertEqual(parse_station_ids(["123,456"]), [123, 456])

    def test_deduplicates_while_preserving_order(self):
        self.assertEqual(parse_station_ids(["456", "123,456"]), [456, 123])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(parse_station_ids(None), [])
        self.assertEqual(parse_station_ids([]), [])

    def test_invalid_value_raises(self):
        with self.assertRaises(ValueError):
            parse_station_ids(["abc"])


if __name__ == "__main__":
    unittest.main()
