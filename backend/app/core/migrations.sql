-- ReceiptLedger PostgreSQL/Supabase DDL Migration
-- Version: 1.0.0
-- Run this against your Supabase project SQL editor or psql.
-- Reference: docs/specifications/05_ERD.md

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Categories ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    color_hex   VARCHAR(7)  NOT NULL,
    description TEXT
);

-- Seed baseline categories (idempotent)
INSERT INTO categories (name, color_hex, description) VALUES
    ('Groceries & Food',     '#10B981', 'Staples, dairy, flour, produce, and fresh meat'),
    ('Household & Cleaning', '#3B82F6', 'Detergents, cleaning supplies, and paper goods'),
    ('Personal Care',        '#8B5CF6', 'Toiletries, skincare, and hygiene essentials'),
    ('Utilities & Bills',    '#F59E0B', 'Electricity, gas, water, and top-up bills'),
    ('Snacks & Beverages',   '#EC4899', 'Confectionery, soft drinks, tea, and bakeries'),
    ('Miscellaneous',        '#6B7280', 'Unclassified or irregular expenses')
ON CONFLICT (name) DO NOTHING;

-- ── Users (managed by Supabase Auth; mirror table for FK references) ──────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       VARCHAR(255),
    full_name   VARCHAR(255),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Receipts ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS receipts (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID,                               -- nullable for anonymous in dev
    merchant_name   VARCHAR(255),
    receipt_date    DATE        NOT NULL DEFAULT CURRENT_DATE,
    total_amount    DECIMAL(10,2) NOT NULL,
    receipt_type    VARCHAR(32) NOT NULL CHECK (receipt_type IN ('PRINTED', 'HANDWRITTEN')),
    status          VARCHAR(32) NOT NULL DEFAULT 'PROCESSED'
                    CHECK (status IN ('PROCESSED', 'PENDING_REVIEW', 'DUPLICATE')),
    ocr_confidence  DECIMAL(4,3) NOT NULL CHECK (ocr_confidence BETWEEN 0 AND 1),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_receipts_user_date ON receipts(user_id, receipt_date);
CREATE INDEX IF NOT EXISTS idx_receipts_status    ON receipts(status);

-- ── Line Items ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS line_items (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id      UUID        NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    category_id     UUID        NOT NULL REFERENCES categories(id),
    raw_text        TEXT        NOT NULL,
    item_name       VARCHAR(255) NOT NULL,
    quantity        DECIMAL(8,3) NOT NULL DEFAULT 1.000,
    unit            VARCHAR(32) NOT NULL DEFAULT 'pcs',
    unit_price      DECIMAL(10,2) NOT NULL,
    total_price     DECIMAL(10,2) NOT NULL,
    confidence_score DECIMAL(4,3) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    is_verified     BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_line_items_receipt  ON line_items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_line_items_category ON line_items(category_id);

-- ── Receipt Hashes (deduplication) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS receipt_hashes (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id               UUID        NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    phash_64                 VARCHAR(64) NOT NULL,
    text_fingerprint_sha256  VARCHAR(64) NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_receipt_hashes_phash ON receipt_hashes(phash_64);
CREATE INDEX IF NOT EXISTS idx_receipt_hashes_text  ON receipt_hashes(text_fingerprint_sha256);

-- ── Review Queue ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS review_queue (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    line_item_id      UUID        NOT NULL REFERENCES line_items(id) ON DELETE CASCADE,
    candidate_text    TEXT        NOT NULL,
    model_confidence  DECIMAL(4,3) NOT NULL CHECK (model_confidence BETWEEN 0 AND 1),
    review_status     VARCHAR(32) NOT NULL DEFAULT 'UNRESOLVED'
                      CHECK (review_status IN ('UNRESOLVED', 'ACCEPTED', 'EDITED')),
    flagged_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(review_status);

-- ── Analytics View ────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW view_monthly_category_spend AS
SELECT
    r.user_id,
    TO_CHAR(r.receipt_date, 'YYYY-MM')  AS spend_period,
    c.name                               AS category_name,
    c.color_hex                          AS category_color,
    SUM(li.total_price)                  AS category_total,
    COUNT(li.id)                         AS item_count
FROM line_items li
JOIN receipts   r  ON li.receipt_id   = r.id
JOIN categories c  ON li.category_id  = c.id
WHERE r.status = 'PROCESSED'
GROUP BY r.user_id, spend_period, c.name, c.color_hex;

-- ── Migration 1.1: Normalized Bounding Box for Line Items ──────────────────────
-- Persists normalized bounding boxes (ymin, xmin, ymax, xmax) for pixel-perfect crops
ALTER TABLE line_items ADD COLUMN IF NOT EXISTS bbox JSONB;
