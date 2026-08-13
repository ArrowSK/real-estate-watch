# Security and data minimisation

Do not post credentials, deployment tokens, database passwords or exploitable private details in a public issue.

For ordinary non-sensitive bugs, use GitHub issues. For a security problem that would be unsafe to disclose publicly, contact the repository owner privately through their GitHub profile until GitHub private vulnerability reporting is enabled for this repository.

## Deployment notes

- Keep `.env` private. It is ignored by Git.
- Set a strong database password outside local development.
- If `/ops/refresh` is needed, configure a strong `ADMIN_KEY` and send it only in the `X-Admin-Key` header.
- If `ADMIN_KEY` is absent, the web refresh endpoint is disabled by design.
- Treat `NOTIFY_WEBHOOK_URL` as a secret if the receiving system embeds credentials in the URL.
- Treat `TELEGRAM_BOT_TOKEN` and `SMTP_PASSWORD` as secrets. Store them only in deployment environment variables or a secret manager.
- Delivery errors deliberately record only the exception type for webhook, Telegram and email failures so credential-bearing URLs or tokens are not written to notification history.

## Experimental listing observer

The Duna House observer is designed for market aggregation, not republication of advertisements.

It intentionally does not persist:

- listing descriptions;
- photographs or floor plans;
- seller or agent names;
- telephone numbers;
- email addresses;
- other contact details.

Stored listing records contain only the minimum factual fields required to identify an observation, calculate asking HUF/m² and build aggregate market history. There is no public individual-listing browsing endpoint.

A provider-policy guard runs before collection and can pause the source after a reviewed policy/robots change or expired manual review. Do not weaken, remove or bypass that guard merely to keep a collector working after the source changes its access conditions.

If an upstream site begins returning a challenge, access-denied response or other restriction, treat that as a source failure. Do not add proxy rotation, CAPTCHA bypass, user-agent impersonation or another circumvention mechanism to this repository.

The detailed provider boundary is documented in `docs/DUNA_HOUSE_PROVIDER.md`.
