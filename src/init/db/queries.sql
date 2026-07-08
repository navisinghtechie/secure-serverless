-- Run once while connected to the default "postgres" database:
--   CREATE DATABASE unicorn_customization;
-- Then reconnect to unicorn_customization and run the rest of this file.

CREATE TABLE IF NOT EXISTS "Companies" (
    "ID" SERIAL PRIMARY KEY,
    "NAME" VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS "Socks" (
    "ID" SERIAL PRIMARY KEY,
    "NAME" VARCHAR(255) NOT NULL,
    "PRICE" DECIMAL(5,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS "Horns" (
    "ID" SERIAL PRIMARY KEY,
    "NAME" VARCHAR(255) NOT NULL,
    "PRICE" DECIMAL(5,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS "Glasses" (
    "ID" SERIAL PRIMARY KEY,
    "NAME" VARCHAR(255) NOT NULL,
    "PRICE" DECIMAL(5,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS "Capes" (
    "ID" SERIAL PRIMARY KEY,
    "NAME" VARCHAR(255) NOT NULL,
    "PRICE" DECIMAL(5,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS "Custom_Unicorns" (
    "ID" SERIAL PRIMARY KEY,
    "NAME" VARCHAR(255) NOT NULL,
    "COMPANY" INT NOT NULL REFERENCES "Companies"("ID"),
    "IMAGEURL" VARCHAR(255) NOT NULL,
    "SOCK" INT NOT NULL REFERENCES "Socks"("ID"),
    "HORN" INT NOT NULL REFERENCES "Horns"("ID"),
    "GLASSES" INT NOT NULL REFERENCES "Glasses"("ID"),
    "CAPE" INT NOT NULL REFERENCES "Capes"("ID")
);

INSERT INTO "Socks" ("NAME", "PRICE") VALUES
    ('Basic', 0.00),
    ('Branded', 1.00);

INSERT INTO "Horns" ("NAME", "PRICE") VALUES
    ('White', 0.00),
    ('Red', 1.00),
    ('Blue', 1.00),
    ('Purple', 1.00),
    ('Green', 1.00),
    ('Yellow', 1.00),
    ('Silver', 2.00),
    ('Gold', 3.00);

INSERT INTO "Glasses" ("NAME", "PRICE") VALUES
    ('Basic', 1.00),
    ('Elvis Presley style', 2.50),
    ('John Lennon style', 2.50),
    ('Kanye West style', 2.50),
    ('Hearts', 2.00),
    ('Stars', 2.00),
    ('Butterfly', 2.00);

INSERT INTO "Capes" ("NAME", "PRICE") VALUES
    ('White', 0.00),
    ('Rainbow', 2.00),
    ('Branded on White', 3.00),
    ('Branded on Rainbow', 4.00);

INSERT INTO "Companies" ("NAME") VALUES ('Placeholder company');

/*
INSERT INTO "Custom_Unicorns" ("NAME", "COMPANY", "IMAGEURL", "SOCK", "HORN", "GLASSES", "CAPE")
VALUES ('Cool new phone', 1, 'https://mybucket.s3.amazonaws.com/myimage', 2, 1, 2, 4);

SELECT * FROM "Custom_Unicorns";
*/
