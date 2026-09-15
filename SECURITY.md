# Security Policy

## Untrusted input

Avatar ZIP files are treated as untrusted. The extractor rejects absolute paths, `..` traversal, drive-prefixed paths, symlinks, unsupported file types, oversized individual files, excessive file counts, and excessive expanded archive size.

The converter does **not** execute scripts from the archive and does **not** automatically retrieve `meshId`, `textureId`, or other URLs embedded in manifests. This avoids turning a conversion operation into an arbitrary network request or credential-bearing fetch.

## Secrets

Do not commit Roblox cookies, API keys, session tokens, private asset URLs containing credentials, or other secrets. The converter does not require Roblox credentials for local exported packages.

## Reporting

Please open a GitHub security report/private advisory when available instead of publishing exploitable details in a public issue.
