# Security

Do not post credentials, deployment tokens, database passwords or exploitable private details in a public issue.

For ordinary non-sensitive bugs, use GitHub issues. For a security problem that would be unsafe to disclose publicly, contact the repository owner privately through their GitHub profile until GitHub private vulnerability reporting is enabled for this repository.

## Deployment notes

- Keep `.env` private. It is ignored by Git.
- Set a strong database password outside local development.
- If `/ops/refresh` is needed, configure a strong `ADMIN_KEY` and send it only in the `X-Admin-Key` header.
- If `ADMIN_KEY` is absent, the web refresh endpoint is disabled by design.
- Treat `NOTIFY_WEBHOOK_URL` as a secret if the receiving system embeds credentials in the URL.
