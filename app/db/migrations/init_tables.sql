CREATE TABLE IF NOT EXISTS users (
    uid             VARCHAR(33) PRIMARY KEY,
    name            TEXT,
    language_code   VARCHAR(10),
    currency_code   VARCHAR(3) DEFAULT 'JPY',
    timezone        VARCHAR(50) DEFAULT 'Asia/Tokyo',
    blocked_at      TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL,
    icon    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_methods (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL,
    icon    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  SERIAL PRIMARY KEY,
    uid                 VARCHAR(33) NOT NULL REFERENCES users(uid),
    amount              INTEGER NOT NULL,
    category_id         INTEGER REFERENCES categories(id),
    payment_method_id   INTEGER REFERENCES payment_methods(id),
    receipt_image_url   TEXT,
    note                TEXT,
    transacted_at       TIMESTAMP NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW()
);