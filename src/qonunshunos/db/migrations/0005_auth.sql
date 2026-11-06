-- Users, OAuth 2.1 authorization server state and per-user limits (stage 4).
-- Codes and tokens are stored as SHA-256 hex digests only. DCR client secrets stay in `info`:
-- the SDK compares them in plain text, and PKCE protects the flow anyway.

CREATE TABLE users (
    id              bigserial PRIMARY KEY,
    display_name    text,
    email           text,
    plan            text NOT NULL DEFAULT 'free',
    limits_override jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_seen_at    timestamptz,
    blocked_at      timestamptz,
    blocked_reason  text
);

CREATE TABLE user_identities (
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider   text NOT NULL,          -- 'google' (later: 'telegram'), 'dev' for local testing
    subject    text NOT NULL,          -- stable id at the provider (Google `sub`)
    email      text,
    username   text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject)
);
CREATE INDEX user_identities_user ON user_identities (user_id);

CREATE TABLE oauth_clients (
    client_id    text PRIMARY KEY,
    info         jsonb NOT NULL,  -- RFC 7591 client information, incl. the DCR client secret
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz
);

-- A pending /authorize request while the user signs in (10 minutes).
CREATE TABLE auth_requests (
    id         text PRIMARY KEY,
    client_id  text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    params     jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE TABLE oauth_codes (
    code_hash  text PRIMARY KEY,
    client_id  text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    params     jsonb NOT NULL,          -- redirect_uri, code_challenge, scopes, resource
    expires_at timestamptz NOT NULL
);

CREATE TABLE oauth_tokens (
    token_hash text PRIMARY KEY,
    kind       text NOT NULL CHECK (kind IN ('access', 'refresh')),
    client_id  text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    scopes     text[] NOT NULL,
    resource   text,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX oauth_tokens_user ON oauth_tokens (user_id);
CREATE INDEX oauth_tokens_expires ON oauth_tokens (expires_at);

CREATE TABLE oauth_consents (
    user_id    bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    client_id  text NOT NULL REFERENCES oauth_clients (client_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, client_id)
);

-- Calls refused by a limit are logged with counted = false and do not use up the quota.
ALTER TABLE usage_events ADD COLUMN counted boolean NOT NULL DEFAULT true;
ALTER TABLE usage_events
    ADD CONSTRAINT usage_events_user_fk FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL;
