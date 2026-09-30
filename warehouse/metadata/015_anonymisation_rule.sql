-- Seed: reusable anonymisation rules. salt_secret_name is a Key Vault secret
-- NAME resolved at runtime via notebookutils.credentials.getSecret -- the
-- salt value itself is never stored in metadata, code or audit.
BEGIN TRANSACTION;

DELETE FROM [control].[anonymisation_rule] WHERE anonymisation_rule_id IN (1, 2, 3, 4, 5);

INSERT INTO [control].[anonymisation_rule]
    (anonymisation_rule_id, rule_name, rule_type, algorithm, parameters, salt_secret_name,
     active_flag, created_datetime, created_by)
VALUES
    (1, 'HASH_EMAIL', 'HASH',     'EMAIL',    '{"domain": "example.invalid", "length": 16}', 'bronze-anonymisation-salt', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (2, 'MASK_PHONE', 'MASK',     'PARTIAL',  '{"keep_last": 4, "mask_char": "*"}',          NULL,                        1, SYSUTCDATETIME(), 'metadata_deploy'),
    (3, 'HASH_SHA256','HASH',     'SHA2_256', '{}',                                          'bronze-anonymisation-salt', 1, SYSUTCDATETIME(), 'metadata_deploy'),
    (4, 'REDACT_TEXT','REDACT',   NULL,       '{"replacement": "REDACTED"}',                 NULL,                        1, SYSUTCDATETIME(), 'metadata_deploy'),
    (5, 'TOKEN_NAME', 'TOKENIZE', 'SHA2_256', '{"prefix": "TKN_", "length": 12}',            'bronze-anonymisation-salt', 1, SYSUTCDATETIME(), 'metadata_deploy');

COMMIT TRANSACTION;
