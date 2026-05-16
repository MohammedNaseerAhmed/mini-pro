-- ============================================================
-- Legal AI Platform — New Feature Schema (Additive Migration)
-- Run: mysql -u root -p legal_ai < backend/scripts/add_new_features_schema.sql
-- SAFE: All tables use IF NOT EXISTS. No existing tables modified.
-- ============================================================

USE legal_ai;

-- ============================================================
-- FEATURE 1: eCourts / NJDG API Integration
-- ============================================================

CREATE TABLE IF NOT EXISTS ecourts_case_status (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    case_id         INT,
    case_number     VARCHAR(255) NOT NULL,
    cnr_number      VARCHAR(30),
    court_complex   VARCHAR(255),
    state_code      VARCHAR(10),
    district_code   VARCHAR(10),
    next_hearing_date DATE,
    last_hearing_date DATE,
    case_stage      VARCHAR(150),
    judge_assigned  VARCHAR(255),
    pending_since   DATE,
    disposal_nature VARCHAR(100),
    petitioner_name TEXT,
    respondent_name TEXT,
    act_section     TEXT,
    raw_response    JSON,
    source          ENUM('ecourts_api','njdg_dataset','manual') DEFAULT 'njdg_dataset',
    last_synced_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ecourts_case_number (case_number),
    INDEX idx_ecourts_cnr (cnr_number),
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS ecourts_sync_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    case_number     VARCHAR(255),
    cnr_number      VARCHAR(30),
    sync_type       ENUM('manual','auto','startup') DEFAULT 'auto',
    status          ENUM('success','failed','partial','skipped') DEFAULT 'skipped',
    http_status     INT,
    error_message   TEXT,
    synced_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sync_case (case_number),
    INDEX idx_sync_status (status)
);

-- ============================================================
-- FEATURE 2: ADR Suitability Checker & Lok Adalat Predictor
-- ============================================================

CREATE TABLE IF NOT EXISTS adr_suitability (
    id                          INT AUTO_INCREMENT PRIMARY KEY,
    case_id                     INT,
    case_number                 VARCHAR(255) NOT NULL,
    case_type                   VARCHAR(100),
    dispute_amount              BIGINT,
    dispute_years               FLOAT DEFAULT 0,
    case_complexity             ENUM('Simple','Moderate','Complex') DEFAULT 'Moderate',
    number_of_parties           INT DEFAULT 2,
    party_consent_level         ENUM('Both Willing','One Willing','Neutral','Unwilling') DEFAULT 'Neutral',
    lok_adalat_score            INT DEFAULT 0,
    mediation_score             INT DEFAULT 0,
    arbitration_score           INT DEFAULT 0,
    negotiation_score           INT DEFAULT 0,
    recommended_adr             ENUM('lok_adalat','mediation','arbitration','negotiation','court') DEFAULT 'court',
    is_lok_adalat_eligible      BOOLEAN DEFAULT FALSE,
    confidence_level            FLOAT DEFAULT 0.0,
    reasoning                   TEXT,
    predicted_settlement_amount BIGINT,
    predicted_settlement_pct    FLOAT,
    predicted_days_to_settle    INT,
    algorithm_version           VARCHAR(20) DEFAULT 'v1.0',
    assessed_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_adr_case_number (case_number),
    INDEX idx_adr_eligible (is_lok_adalat_eligible),
    INDEX idx_adr_recommended (recommended_adr),
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS lok_adalat_awards (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    case_type           VARCHAR(100) NOT NULL,
    court_level         VARCHAR(50),
    state               VARCHAR(100),
    avg_claim_amount    BIGINT,
    avg_award_amount    BIGINT,
    settlement_rate_pct FLOAT,
    avg_days_to_settle  INT,
    sample_size         INT DEFAULT 0,
    data_year           INT,
    source              VARCHAR(100) DEFAULT 'NALSA',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_la_case_type (case_type),
    INDEX idx_la_year (data_year)
);

INSERT IGNORE INTO lok_adalat_awards
    (case_type, court_level, state, avg_claim_amount, avg_award_amount, settlement_rate_pct, avg_days_to_settle, sample_size, data_year, source)
VALUES
    ('motor_accident','District','National',800000,560000,78.5,90,50000,2023,'NALSA Annual Report 2023'),
    ('consumer','District','National',50000,35000,71.2,45,30000,2023,'NALSA Annual Report 2023'),
    ('labour','District','National',200000,140000,65.0,120,15000,2023,'NALSA Annual Report 2023'),
    ('cheque_bounce','District','National',150000,130000,82.0,30,80000,2023,'NALSA Annual Report 2023'),
    ('matrimonial','District','National',300000,250000,55.0,180,20000,2023,'NALSA Annual Report 2023'),
    ('property','District','National',1500000,900000,40.0,240,12000,2023,'NALSA Annual Report 2023'),
    ('commercial','High Court','National',5000000,3200000,50.0,180,8000,2023,'NALSA Annual Report 2023'),
    ('civil','District','National',200000,140000,60.0,90,40000,2023,'NALSA Annual Report 2023'),
    ('municipal','District','National',10000,8000,85.0,20,25000,2023,'NALSA Annual Report 2023'),
    ('revenue','District','National',500000,350000,45.0,150,18000,2023,'NALSA Annual Report 2023');

-- ============================================================
-- FEATURE 3: IPC to BNS Section Mapper
-- ============================================================

CREATE TABLE IF NOT EXISTS section_mappings (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    old_act             ENUM('IPC','CrPC','IEA') NOT NULL,
    old_section         VARCHAR(30) NOT NULL,
    old_title           VARCHAR(255),
    old_description     TEXT,
    new_act             ENUM('BNS','BNSS','BSA') NOT NULL,
    new_section         VARCHAR(30),
    new_title           VARCHAR(255),
    new_description     TEXT,
    change_type         ENUM('retained','modified','merged','split','replaced','omitted') NOT NULL,
    change_notes        TEXT,
    legal_implications  TEXT,
    keywords            TEXT,
    effective_date      DATE DEFAULT '2024-07-01',
    is_critical         BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sm_old (old_act, old_section),
    INDEX idx_sm_new (new_act, new_section),
    UNIQUE KEY uk_sm_old (old_act, old_section)
);

CREATE TABLE IF NOT EXISTS case_section_citations (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    case_id             INT,
    case_number         VARCHAR(255) NOT NULL,
    cited_act           VARCHAR(10) NOT NULL,
    cited_section       VARCHAR(30) NOT NULL,
    mapped_act          VARCHAR(10),
    mapped_section      VARCHAR(30),
    is_deprecated       BOOLEAN DEFAULT FALSE,
    change_type         VARCHAR(30),
    occurrence_count    INT DEFAULT 1,
    context_snippet     VARCHAR(500),
    extracted_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_csc_case (case_number),
    INDEX idx_csc_deprecated (is_deprecated),
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS case_section_reports (
    id                          INT AUTO_INCREMENT PRIMARY KEY,
    case_number                 VARCHAR(255) NOT NULL UNIQUE,
    case_id                     INT,
    total_citations             INT DEFAULT 0,
    unique_sections             INT DEFAULT 0,
    deprecated_count            INT DEFAULT 0,
    unmapped_count              INT DEFAULT 0,
    document_era                ENUM('pre_2024','transitional','post_2024','unknown') DEFAULT 'unknown',
    has_deprecated_citations    BOOLEAN DEFAULT FALSE,
    citation_quality_score      INT DEFAULT 100,
    created_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_csr_case (case_number),
    INDEX idx_csr_deprecated (has_deprecated_citations),
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS section_mapping_feedback (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    old_act         VARCHAR(10),
    old_section     VARCHAR(30),
    reported_issue  TEXT,
    suggested_fix   TEXT,
    submitted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
