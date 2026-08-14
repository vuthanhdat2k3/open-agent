# Customer Intelligence meeting datetime normalization

## Problem

Calendar providers return timezone-aware datetimes while the application
persists `TIMESTAMP WITHOUT TIME ZONE` values as naive UTC. Passing provider
values directly to SQLAlchemy causes PostgreSQL flush failures and leaves the
research case retrying.

## Design

- Normalize meeting `start_at` and `end_at` immediately before constructing the
  persistence model.
- Convert aware values to UTC, then remove `tzinfo` for the existing naive-UTC
  schema.
- Treat legacy naive provider values as UTC and preserve `None` values.
- Keep API rendering responsible for attaching/displaying the user timezone;
  persistence remains canonical UTC.

## Verification

- Unit tests cover UTC offset conversion, naive compatibility, and null values.
- Full backend suite must pass.
- Live Gmail → research case processing must reach approval instead of failing
  at `ci_meetings` insertion.
