-- Row-Level Security template, applied once per patient table by scripts/setup_databases.py.
-- {table}  = table name,  {patient_col} = column holding the patient's id.
-- Rule: clinicians see every row; a patient sees only rows whose patient column equals their id;
-- AND the "who is asking" notes must carry a valid signature (aether_private.identity_ok(), see
-- postgres_identity.sql). It is called per row (not wrapped in a sub-select) so a query that changes
-- the notes part-way through stops matching immediately.
-- If no context was set, current_setting(..., true) returns NULL/'' and NO rows are visible (safe default).
-- RLS never applies to the table owner (the admin), only to chatbot_ro.
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS chatbot_access ON {table};
CREATE POLICY chatbot_access ON {table} FOR SELECT TO chatbot_ro
    USING (
        (current_setting('app.role', true) = 'clinician'
         OR {patient_col} = current_setting('app.patient_id', true))
        AND aether_private.identity_ok()
    );
