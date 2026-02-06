import logging
import os
from dataclasses import dataclass

import requests


LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "ddns_updater.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE_PATH),
    ],
)

REQUEST_TIMEOUT_SECONDS = 10
IPIFY_URL = "https://api.ipify.org?format=json"
CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"


@dataclass(frozen=True)
class Config:
    api_token: str
    zone_id: str
    record_name: str


def load_config_from_env():
    api_token = (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()
    zone_id = (os.environ.get("CLOUDFLARE_ZONE_ID") or "").strip()
    record_name = (os.environ.get("CLOUDFLARE_RECORD_NAME") or "").strip()

    missing = []
    if not api_token:
        missing.append("CLOUDFLARE_API_TOKEN")
    if not zone_id:
        missing.append("CLOUDFLARE_ZONE_ID")
    if not record_name:
        missing.append("CLOUDFLARE_RECORD_NAME")
    if missing:
        logging.error("Missing required environment variable(s): %s", ", ".join(missing))
        return None

    # Catch obvious placeholders while avoiding brittle one-off exact-value rules.
    token_upper = api_token.upper()
    if "TOKEN" in token_upper and ("YOUR" in token_upper or "CLOUDFLARE" in token_upper):
        logging.error(
            "CLOUDFLARE_API_TOKEN looks like a placeholder value. Set a real API token in .env."
        )
        return None

    return Config(api_token=api_token, zone_id=zone_id, record_name=record_name)


def build_headers(api_token):
    return {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }


def _extract_cloudflare_errors(response):
    try:
        payload = response.json()
    except ValueError:
        return ""

    errors = payload.get("errors", [])
    messages = payload.get("messages", [])
    details = []

    for item in errors:
        code = item.get("code", "unknown")
        message = item.get("message", "unknown error")
        details.append(f"code={code} message={message}")

    for message in messages:
        if isinstance(message, dict):
            details.append(message.get("message", str(message)))
        else:
            details.append(str(message))

    return "; ".join(details)


def get_current_ip(session=requests, timeout=REQUEST_TIMEOUT_SECONDS):
    try:
        response = session.get(IPIFY_URL, timeout=timeout)
        response.raise_for_status()
        return response.json()["ip"]
    except requests.exceptions.RequestException as error:
        logging.error("Error getting current IP: %s", error)
        return None


def get_dns_record(zone_id, record_name, headers, session=requests, timeout=REQUEST_TIMEOUT_SECONDS):
    url = f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records"
    params = {"type": "A", "name": record_name}

    try:
        response = session.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        records = response.json().get("result", [])
        if records:
            return records[0]
        return None
    except requests.exceptions.RequestException as error:
        error_details = ""
        if getattr(error, "response", None) is not None:
            error_details = _extract_cloudflare_errors(error.response)
        if error_details:
            logging.error("Error getting DNS record: %s (%s)", error, error_details)
        else:
            logging.error("Error getting DNS record: %s", error)
        return None


def update_dns_record(zone_id, record, new_ip, headers, session=requests, timeout=REQUEST_TIMEOUT_SECONDS):
    record_id = record["id"]
    record_name = record["name"]
    ttl = record.get("ttl", 1)
    proxied = record.get("proxied", False)

    url = f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records/{record_id}"
    data = {
        "type": "A",
        "name": record_name,
        "content": new_ip,
        "ttl": ttl,
        "proxied": proxied,
    }

    try:
        response = session.put(url, headers=headers, json=data, timeout=timeout)
        response.raise_for_status()
        logging.info("DNS record for %s updated to %s", record_name, new_ip)
        return True
    except requests.exceptions.RequestException as error:
        error_details = ""
        if getattr(error, "response", None) is not None:
            error_details = _extract_cloudflare_errors(error.response)
        if error_details:
            logging.error("Error updating DNS record: %s (%s)", error, error_details)
        else:
            logging.error("Error updating DNS record: %s", error)
        return False


def main():
    config = load_config_from_env()
    if config is None:
        return 1

    headers = build_headers(config.api_token)
    logging.info("Starting Cloudflare DDNS update process...")
    current_ip = get_current_ip()
    if not current_ip:
        logging.error("Could not determine current public IP. Exiting.")
        return 1

    logging.info("Current public IP: %s", current_ip)
    dns_record = get_dns_record(config.zone_id, config.record_name, headers)
    if not dns_record:
        logging.error(
            "DNS record for %s not found. Please create it manually in Cloudflare first. Exiting.",
            config.record_name,
        )
        return 1

    existing_ip = dns_record["content"]
    logging.info("Existing Cloudflare DNS IP for %s: %s", config.record_name, existing_ip)

    if current_ip == existing_ip:
        logging.info("Current IP matches existing DNS record. No update needed.")
    else:
        logging.info(
            "IP mismatch detected. Updating %s from %s to %s...",
            config.record_name,
            existing_ip,
            current_ip,
        )
        if update_dns_record(config.zone_id, dns_record, current_ip, headers):
            logging.info("DDNS update successful.")
        else:
            logging.error("DDNS update failed.")
            return 1

    logging.info("Cloudflare DDNS update process finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
