import os
import tempfile
import unittest

from src.env import env_bool, env_float, env_int, env_list, env_value, load_dotenv


class DotenvTests(unittest.TestCase):
    def test_load_dotenv_reads_values_without_overriding_environment(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as env_file:
            env_file.write("INFLUX_URL=http://localhost:8086\n")
            env_file.write('INFLUX_ORG="airframes org"\n')
            env_file.write("export INFLUX_BUCKET='airframes'\n")
            env_file.write("INFLUX_TOKEN=from-file\n")
            path = env_file.name

        old_values = {
            key: os.environ.get(key)
            for key in ("INFLUX_URL", "INFLUX_ORG", "INFLUX_BUCKET", "INFLUX_TOKEN")
        }
        try:
            for key in old_values:
                os.environ.pop(key, None)
            os.environ["INFLUX_TOKEN"] = "from-shell"

            load_dotenv(path)

            self.assertEqual(os.environ["INFLUX_URL"], "http://localhost:8086")
            self.assertEqual(os.environ["INFLUX_ORG"], "airframes org")
            self.assertEqual(os.environ["INFLUX_BUCKET"], "airframes")
            self.assertEqual(os.environ["INFLUX_TOKEN"], "from-shell")
        finally:
            os.unlink(path)
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_env_helpers_cast_common_values(self):
        old_values = {
            key: os.environ.get(key)
            for key in ("TEST_BOOL", "TEST_INT", "TEST_FLOAT", "TEST_LIST", "TEST_EMPTY")
        }
        try:
            os.environ["TEST_BOOL"] = "yes"
            os.environ["TEST_INT"] = "42"
            os.environ["TEST_FLOAT"] = "4.5"
            os.environ["TEST_LIST"] = "a=b,c=d"
            os.environ["TEST_EMPTY"] = ""

            self.assertTrue(env_bool("TEST_BOOL"))
            self.assertEqual(env_int("TEST_INT"), 42)
            self.assertEqual(env_float("TEST_FLOAT"), 4.5)
            self.assertEqual(env_list("TEST_LIST"), ["a=b", "c=d"])
            self.assertEqual(env_value("TEST_EMPTY", "fallback"), "fallback")
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
