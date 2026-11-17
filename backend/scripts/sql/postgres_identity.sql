-- Signed identity for row-level security (run by scripts/setup_databases.py before the policies).
-- A private schema holds the signing key; chatbot_ro may CALL the checking function but never READ the key.
-- identity_ok() runs as its owner (SECURITY DEFINER), recomputes sha256(key|role|patient_id) and compares
-- it with the app.sig note. Any changed note -> mismatch -> false -> the row is hidden.
CREATE SCHEMA IF NOT EXISTS aether_private;
REVOKE ALL ON SCHEMA aether_private FROM PUBLIC;
CREATE TABLE IF NOT EXISTS aether_private.rls_key (k text NOT NULL);
REVOKE ALL ON aether_private.rls_key FROM PUBLIC;
DELETE FROM aether_private.rls_key;
INSERT INTO aether_private.rls_key (k) VALUES (:key);
CREATE OR REPLACE FUNCTION aether_private.identity_ok() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
    AS $$
        SELECT coalesce(
            current_setting('app.sig', true) = encode(sha256(convert_to(
                k || '|' || coalesce(current_setting('app.role', true), '')
                  || '|' || coalesce(current_setting('app.patient_id', true), ''), 'UTF8')), 'hex'),
            false)
        FROM aether_private.rls_key
    $$;
REVOKE ALL ON FUNCTION aether_private.identity_ok() FROM PUBLIC;
GRANT USAGE ON SCHEMA aether_private TO chatbot_ro;
GRANT EXECUTE ON FUNCTION aether_private.identity_ok() TO chatbot_ro;
