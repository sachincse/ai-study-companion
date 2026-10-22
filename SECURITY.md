# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Email the maintainer
(see the GitHub profile of `sachincse`) with a description and reproduction
steps. You will get an acknowledgement within a few days and a fix or
mitigation as soon as practical.

## What the app does to protect students' data

- Every record (documents, passages, vectors, chats, quizzes, cards, artifacts, progress) is scoped to the owning account; the test-suite includes cross-account access checks.
- Passwords are hashed with bcrypt; sessions use signed JWTs (`SECRET_KEY`).
- API keys entered in Settings are encrypted at rest (Fernet, key derived from `SECRET_KEY`) and are only ever returned masked.
- Uploads are validated by extension and size, file names are sanitised, and files are stored outside the web root.
- Text extracted from uploads is treated as untrusted data in prompts (prompt-injection guard).
- AI endpoints are rate-limited per account.

## Deployment checklist

- Set a strong `SECRET_KEY` and `APP_ENV=production`.
- Put the app behind HTTPS (reverse proxy) and restrict `CORS_ORIGINS` to your domain.
- Set `ALLOW_REGISTRATION=false` once your users have accounts if the instance is public.
- Keep `storage/` on a persistent, backed-up volume; it holds the database, uploads and the vector index.
