import logging
import os
import unittest
from unittest.mock import Mock, patch

import requests

import cloudflare_ddns_updater as updater


def configure_test_logging():
    formatter = logging.Formatter("%(asctime)s - [TEST] - %(levelname)s - %(message)s")
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


def load_env_file(env_file_path):
    if not os.path.exists(env_file_path):
        return

    with open(env_file_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ[key] = value


configure_test_logging()


class CloudflareDdnsUpdaterTests(unittest.TestCase):
    def test_get_current_ip_success(self):
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"ip": "1.2.3.4"}
        mock_session.get.return_value = mock_response

        result = updater.get_current_ip(session=mock_session, timeout=5)

        self.assertEqual(result, "1.2.3.4")
        mock_session.get.assert_called_once_with(updater.IPIFY_URL, timeout=5)

    def test_get_current_ip_handles_request_exception(self):
        mock_session = Mock()
        mock_session.get.side_effect = requests.exceptions.RequestException("network error")

        result = updater.get_current_ip(session=mock_session, timeout=5)

        self.assertIsNone(result)

    def test_get_dns_record_success(self):
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"result": [{"id": "record-id", "content": "1.2.3.4"}]}
        mock_session.get.return_value = mock_response
        headers = {"Authorization": "Bearer test"}

        result = updater.get_dns_record(
            zone_id="zone-id",
            record_name="example.com",
            headers=headers,
            session=mock_session,
            timeout=7,
        )

        self.assertEqual(result["id"], "record-id")
        mock_session.get.assert_called_once_with(
            "https://api.cloudflare.com/client/v4/zones/zone-id/dns_records",
            headers=headers,
            params={"type": "A", "name": "example.com"},
            timeout=7,
        )

    def test_get_dns_record_logs_cloudflare_error_details(self):
        mock_session = Mock()
        error_response = Mock()
        error_response.json.return_value = {"errors": [{"code": 6003, "message": "Invalid request headers"}]}
        http_error = requests.exceptions.HTTPError("400 Client Error")
        http_error.response = error_response

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = http_error
        mock_session.get.return_value = mock_response

        with self.assertLogs(level="ERROR") as logs:
            result = updater.get_dns_record(
                zone_id="zone-id",
                record_name="example.com",
                headers={},
                session=mock_session,
            )

        self.assertIsNone(result)
        joined_logs = "\n".join(logs.output)
        self.assertIn("Invalid request headers", joined_logs)
        self.assertIn("code=6003", joined_logs)

    def test_update_dns_record_preserves_ttl_and_proxied(self):
        mock_session = Mock()
        mock_response = Mock()
        mock_session.put.return_value = mock_response

        record = {
            "id": "record-id",
            "name": "example.com",
            "ttl": 300,
            "proxied": True,
        }
        headers = {"Authorization": "Bearer test"}
        result = updater.update_dns_record(
            zone_id="zone-id",
            record=record,
            new_ip="8.8.8.8",
            headers=headers,
            session=mock_session,
            timeout=11,
        )

        self.assertTrue(result)
        mock_session.put.assert_called_once_with(
            "https://api.cloudflare.com/client/v4/zones/zone-id/dns_records/record-id",
            headers=headers,
            json={
                "type": "A",
                "name": "example.com",
                "content": "8.8.8.8",
                "ttl": 300,
                "proxied": True,
            },
            timeout=11,
        )

    @patch("cloudflare_ddns_updater.update_dns_record")
    @patch("cloudflare_ddns_updater.get_dns_record")
    @patch("cloudflare_ddns_updater.get_current_ip")
    @patch("cloudflare_ddns_updater.load_config_from_env")
    def test_main_skips_update_when_ip_matches(
        self,
        mock_load_config,
        mock_get_current_ip,
        mock_get_dns_record,
        mock_update_dns_record,
    ):
        mock_load_config.return_value = updater.Config(
            api_token="token",
            zone_id="zone-id",
            record_name="example.com",
        )
        mock_get_current_ip.return_value = "1.2.3.4"
        mock_get_dns_record.return_value = {"id": "record-id", "content": "1.2.3.4", "name": "example.com"}

        exit_code = updater.main()

        self.assertEqual(exit_code, 0)
        mock_update_dns_record.assert_not_called()


@unittest.skipUnless(
    os.environ.get("RUN_CLOUDFLARE_INTEGRATION_TESTS") == "1",
    "Set RUN_CLOUDFLARE_INTEGRATION_TESTS=1 to run live Cloudflare integration test",
)
class CloudflareIntegrationTests(unittest.TestCase):
    def test_live_dns_lookup_with_env(self):
        repo_root = os.path.dirname(os.path.dirname(__file__))
        env_file = os.path.join(repo_root, ".env")
        load_env_file(env_file)

        config = updater.load_config_from_env()
        self.assertIsNotNone(
            config,
            "Missing valid CLOUDFLARE_API_TOKEN/CLOUDFLARE_ZONE_ID/CLOUDFLARE_RECORD_NAME in .env",
        )

        headers = updater.build_headers(config.api_token)
        response = requests.get(
            f"{updater.CLOUDFLARE_API_BASE}/zones/{config.zone_id}/dns_records",
            headers=headers,
            params={"type": "A", "name": config.record_name},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        self.assertTrue(payload.get("success"), f"Cloudflare API returned failure: {payload}")
        self.assertEqual(payload.get("errors"), [])
        self.assertIsInstance(payload.get("messages"), list)
        self.assertIsInstance(payload.get("result_info"), dict)
        self.assertIn("count", payload["result_info"])

        records = payload.get("result", [])
        self.assertGreater(len(records), 0, "No A records returned for configured name.")
        record = records[0]
        self.assertEqual(record.get("type"), "A")
        self.assertEqual(record.get("name"), config.record_name)
        self.assertIsInstance(record.get("id"), str)
        self.assertGreater(len(record["id"]), 0)
        self.assertIsInstance(record.get("content"), str)
        self.assertGreater(len(record["content"]), 0)

        expected_record_id = os.environ.get("CLOUDFLARE_EXPECTED_RECORD_ID")
        expected_content_ip = os.environ.get("CLOUDFLARE_EXPECTED_CONTENT_IP")
        if expected_record_id:
            self.assertEqual(record.get("id"), expected_record_id)
        if expected_content_ip:
            self.assertEqual(record.get("content"), expected_content_ip)


if __name__ == "__main__":
    unittest.main()
