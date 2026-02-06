# Cloudflare DDNS Updater

Updates a Cloudflare `A` record to your current public IP.

## Requirements

- Python 3.9+
- `requests` package
- Cloudflare API token with:
  - `Zone:Read`
  - `DNS:Edit`

## Setup

1. Create/update `.env` in `/Users/yan/Dev/my-ddns`:

```env
CLOUDFLARE_RECORD_NAME='your_record'
CLOUDFLARE_ZONE_ID='your_zone_id'
CLOUDFLARE_API_TOKEN='your_real_api_token'
```

2. Install dependency:

```bash
python3 -m pip install requests
```

## Run

Use the wrapper script:

```bash
/Users/yan/Dev/my-ddns/run_ddns.sh
```

What it does:
- Loads environment variables from `.env`
- Gets your public IP from `api.ipify.org`
- Reads the Cloudflare DNS `A` record
- Updates the record only if the IP changed
- Writes logs to console and `/Users/yan/Dev/my-ddns/ddns_updater.log`

## Test

Run unit tests:

```bash
python3 -m unittest discover -s /Users/yan/Dev/my-ddns/tests -v
```

Current tests cover:
- Public IP fetch success/failure handling
- DNS record lookup success and error logging
- DNS update payload behavior
- Main flow when no update is needed

Run optional live Cloudflare integration test (reads `.env`):

```bash
RUN_CLOUDFLARE_INTEGRATION_TESTS=1 python3 -m unittest discover -s /Users/yan/Dev/my-ddns/tests -v
```

This integration test performs a real DNS-record lookup only (no update/write).
It asserts Cloudflare response fields like `success`, `errors`, `messages`, `result_info`, and validates the first `A` record for your configured name.

Optional strict assertions in `.env`:

```env
CLOUDFLARE_EXPECTED_RECORD_ID='your_dns_record_id'
CLOUDFLARE_EXPECTED_CONTENT_IP='x.x.x.x'
```

## Git Safety

`.env` is ignored by `/Users/yan/Dev/my-ddns/.gitignore` so secrets are not committed.
