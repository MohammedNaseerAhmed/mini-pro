CREATE DATABASE IF NOT EXISTS legal_ai;
USE legal_ai;

CREATE TABLE IF NOT EXISTS cases (
    case_id INT AUTO_INCREMENT PRIMARY KEY,
    case_number VARCHAR(255) UNIQUE,
    title TEXT,
    court_name VARCHAR(255),
    court_level VARCHAR(50),
    bench VARCHAR(100),
    case_type VARCHAR(100),
    filing_date DATE,
    registration_date DATE,
    decision_date DATE,
    petitioner TEXT,
    respondent TEXT,
    judge_names TEXT,
    advocates TEXT,
    disposition VARCHAR(100),
    citation VARCHAR(255),
    source VARCHAR(50),
    pdf_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_acts (
    act_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    act_name VARCHAR(255),
    section VARCHAR(100),
    description TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_facts (
    fact_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    fact_type VARCHAR(100),
    fact_text TEXT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_summaries (
    summary_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    summary_type VARCHAR(50),
    summary_text TEXT,
    model_used VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_translations (
    translation_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    language_code VARCHAR(10),
    translated_summary TEXT,
    model_used VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS case_predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    predicted_outcome VARCHAR(100),
    win_probability FLOAT,
    confidence_score FLOAT,
    key_factors TEXT,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS similar_cases (
    similar_id INT AUTO_INCREMENT PRIMARY KEY,
    case_id INT,
    similar_case_id INT,
    similarity_score FLOAT,
    FOREIGN KEY (case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS judge_analytics (
    judge_id INT AUTO_INCREMENT PRIMARY KEY,
    judge_name VARCHAR(255) UNIQUE,
    court_name VARCHAR(255),
    total_cases INT,
    disposed_cases INT,
    allowed_cases INT,
    dismissed_cases INT,
    avg_disposal_days FLOAT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_history (
    chat_id INT AUTO_INCREMENT PRIMARY KEY,
    user_query TEXT,
    ai_response TEXT,
    case_context_ids TEXT,
    response_time_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    module VARCHAR(100),
    action VARCHAR(100),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
