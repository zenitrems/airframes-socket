import os
import unittest

from main import build_parser


class MainParserEnvironmentTests(unittest.TestCase):
    def test_parser_defaults_can_come_from_environment(self):
        values = {
            "STREAM": "feed",
            "SOCKET_URL": "https://example.test",
            "AIRFRAMES_API_KEY": "airframes-key",
            "AIRFRAMES_TOKEN": "jwt-token",
            "STATION_ID": "123",
            "FILTERS": "station.country_code=US,airframe.military=true",
            "SUMMARY": "true",
            "INLINE_SUMMARY": "yes",
            "INLINE_WIDTH": "140",
            "NODE_RED_URL": "https://node-red.test/airframes",
            "NODE_RED_TIMEOUT": "11.5",
            "NODE_RED_QUEUE_SIZE": "1234",
            "NODE_RED_RETRIES": "3",
            "NODE_RED_RETRY_DELAY": "2.5",
            "NODE_RED_ONLY": "1",
            "NODE_RED_INSECURE_TLS": "on",
            "NODE_RED_CA_FILE": "/tmp/ca.pem",
            "INFLUX_URL": "http://influx.test:8086",
            "INFLUX_TOKEN": "influx-token",
            "INFLUX_ORG": "airframes",
            "INFLUX_BUCKET": "messages",
            "INFLUX_TIMEOUT": "12.5",
            "INFLUX_QUEUE_SIZE": "5678",
            "INFLUX_RETRIES": "4",
            "INFLUX_RETRY_DELAY": "3.5",
            "LIBACARS": "true",
            "LIBACARS_DECODER": "/opt/decode_acars_apps",
            "LIBACARS_TIMEOUT": "6.5",
        }
        old_values = {key: os.environ.get(key) for key in values}
        try:
            os.environ.update(values)
            args = build_parser().parse_args([])

            self.assertEqual(args.stream, "feed")
            self.assertEqual(args.socket_url, "https://example.test")
            self.assertEqual(args.api_key, "airframes-key")
            self.assertEqual(args.token, "jwt-token")
            self.assertEqual(args.station_id, 123)
            self.assertEqual(
                args.filter,
                ["station.country_code=US", "airframe.military=true"],
            )
            self.assertTrue(args.summary)
            self.assertTrue(args.inline_summary)
            self.assertEqual(args.inline_width, 140)
            self.assertEqual(args.node_red_url, "https://node-red.test/airframes")
            self.assertEqual(args.node_red_timeout, 11.5)
            self.assertEqual(args.node_red_queue_size, 1234)
            self.assertEqual(args.node_red_retries, 3)
            self.assertEqual(args.node_red_retry_delay, 2.5)
            self.assertTrue(args.node_red_only)
            self.assertTrue(args.node_red_insecure_tls)
            self.assertEqual(args.node_red_ca_file, "/tmp/ca.pem")
            self.assertEqual(args.influx_url, "http://influx.test:8086")
            self.assertEqual(args.influx_token, "influx-token")
            self.assertEqual(args.influx_org, "airframes")
            self.assertEqual(args.influx_bucket, "messages")
            self.assertEqual(args.influx_timeout, 12.5)
            self.assertEqual(args.influx_queue_size, 5678)
            self.assertEqual(args.influx_retries, 4)
            self.assertEqual(args.influx_retry_delay, 3.5)
            self.assertTrue(args.libacars)
            self.assertEqual(args.libacars_decoder, "/opt/decode_acars_apps")
            self.assertEqual(args.libacars_timeout, 6.5)
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
