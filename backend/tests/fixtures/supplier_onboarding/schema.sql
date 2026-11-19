-- Supplier onboarding: a sample Postgres schema for the mfgen demo.
-- Copied from Engram's app/samples/supplier-onboarding.sql (the same schema
-- the modeler's DDL import was built against). It mixes what real exports
-- hold: keys, cascades, checks, an enum, comments and audit columns.

CREATE TYPE equipment_category AS ENUM ('forklift', 'conveyor', 'compressor', 'packaging_line');

CREATE TABLE vendors (
    vendor_id        SERIAL PRIMARY KEY,
    legal_name       VARCHAR(200) NOT NULL,
    dba_name         VARCHAR(200),
    tax_id           CHAR(10) NOT NULL UNIQUE,
    payment_terms    VARCHAR(10) NOT NULL CHECK (payment_terms IN ('net_15', 'net_30', 'net_45', 'net_60')),
    annual_spend_est NUMERIC(14, 2) CHECK (annual_spend_est >= 0),
    discount_pct     NUMERIC(5, 2) CHECK (discount_pct BETWEEN 0 AND 100),
    website          VARCHAR(255),
    remit_to         VARCHAR(400),
    is_minority_owned BOOLEAN NOT NULL DEFAULT FALSE,
    first_order_on   DATE,
    insurance_expires DATE NOT NULL,
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by       VARCHAR(50)
);
COMMENT ON TABLE vendors IS 'A supplier we buy from';
COMMENT ON COLUMN vendors.tax_id IS 'EIN as shown on the W-9, like 12-3456789';
COMMENT ON COLUMN vendors.remit_to IS 'Where payments are mailed';

CREATE TABLE vendor_contacts (
    contact_id   SERIAL PRIMARY KEY,
    vendor_id    INT NOT NULL REFERENCES vendors (vendor_id) ON DELETE CASCADE,
    first_name   VARCHAR(80) NOT NULL,
    last_name    VARCHAR(80) NOT NULL,
    contact_role VARCHAR(20) NOT NULL CHECK (contact_role IN ('primary', 'billing', 'technical')),
    email        VARCHAR(255),
    direct_line  VARCHAR(30),
    title        VARCHAR(100)
);

CREATE TABLE manufacturers (
    manufacturer_id SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    country         CHAR(2),
    support_line    VARCHAR(30)
);

CREATE TABLE locations (
    location_id   SERIAL PRIMARY KEY,
    vendor_id     INT NOT NULL REFERENCES vendors (vendor_id) ON DELETE CASCADE,
    site_name     VARCHAR(120) NOT NULL,
    street        VARCHAR(200) NOT NULL,
    city          VARCHAR(100) NOT NULL,
    postal_code   VARCHAR(12),
    is_primary    BOOLEAN NOT NULL DEFAULT FALSE,
    square_feet   INT CHECK (square_feet > 0)
);

CREATE TABLE equipment (
    equipment_id    SERIAL PRIMARY KEY,
    location_id     INT NOT NULL REFERENCES locations (location_id) ON DELETE CASCADE,
    manufacturer_id INT REFERENCES manufacturers (manufacturer_id),
    serial_number   VARCHAR(40) NOT NULL,
    category        equipment_category NOT NULL,
    purchased_on    DATE,
    purchase_price  NUMERIC(12, 2),
    utilization     NUMERIC(4, 3),
    last_serviced   TIMESTAMP,
    row_version     INT NOT NULL DEFAULT 1
);
COMMENT ON COLUMN equipment.utilization IS 'Share of the shift the machine runs, from 0 to 1';

CREATE INDEX ix_equipment_location ON equipment (location_id);
