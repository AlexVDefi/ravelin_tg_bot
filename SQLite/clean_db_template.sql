--
-- File generated with SQLiteStudio v3.3.3 on Thu Apr 14 15:31:35 2022
--
-- Text encoding used: UTF-8
--
PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

-- Table: admin_table
CREATE TABLE admin_table (welcome_message BOOLEAN PRIMARY KEY);

-- Table: channel_table
CREATE TABLE channel_table (msg_id BIGINT PRIMARY KEY, msg_type TEXT, user_id BIGINT);

-- Table: tg_users
CREATE TABLE tg_users (peer_id BIGINT PRIMARY KEY, warnings INT DEFAULT (0), verified BOOLEAN DEFAULT (False));

COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
