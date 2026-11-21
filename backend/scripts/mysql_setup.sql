-- One-time MySQL 8 setup. Run as a MySQL admin, e.g.:
--   mysql -u root -p < backend/scripts/mysql_setup.sql
-- 1) Change the password below, 2) put the same password in backend/.env (see .env.example).

CREATE DATABASE IF NOT EXISTS tms       CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE DATABASE IF NOT EXISTS tms_test  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;  -- tests only (truncated!)

CREATE USER IF NOT EXISTS 'tms_user'@'localhost' IDENTIFIED BY 'CHANGE_ME_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON tms.*      TO 'tms_user'@'localhost';   -- migrations need DDL rights
GRANT ALL PRIVILEGES ON tms_test.* TO 'tms_user'@'localhost';
FLUSH PRIVILEGES;

-- Later hardening (Phase 9): run the API as a second user WITHOUT DDL rights and with INSERT/SELECT
-- only on activity_logs and the other append-only history tables.
