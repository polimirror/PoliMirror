-- PoliMirror データベーススキーマ v1.0.0

-- 議員マスタ
CREATE TABLE IF NOT EXISTS politicians (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    name_kana VARCHAR(100),
    name_en VARCHAR(100),
    birth_year INTEGER,
    prefecture VARCHAR(50),
    constituency VARCHAR(100),
    party VARCHAR(100),
    role VARCHAR(200),
    status VARCHAR(20) DEFAULT '現職',
    first_elected_year INTEGER,
    house VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 発言記録
CREATE TABLE IF NOT EXISTS statements (
    id SERIAL PRIMARY KEY,
    speech_id VARCHAR(100) UNIQUE,
    issue_id VARCHAR(50),
    politician_name VARCHAR(100) NOT NULL,
    politician_name_yomi VARCHAR(100),
    party VARCHAR(100),
    position VARCHAR(200),
    role VARCHAR(100),
    house VARCHAR(20),
    meeting_name VARCHAR(200),
    issue_number VARCHAR(20),
    session_number INTEGER,
    date DATE,
    speech_order INTEGER,
    speech_text TEXT,
    speech_url TEXT,
    meeting_url TEXT,
    pdf_url TEXT,
    web_archive_url TEXT,
    source_reliability INTEGER DEFAULT 5,
    collected_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

-- 汎用属性
CREATE TABLE IF NOT EXISTS politician_attributes (
    id SERIAL PRIMARY KEY,
    politician_id INTEGER REFERENCES politicians(id),
    category VARCHAR(100),
    key VARCHAR(200),
    value TEXT,
    value_type VARCHAR(50),
    source_url TEXT,
    web_archive_url TEXT,
    screenshot_s3_url TEXT,
    source_reliability INTEGER,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- 収集ログ
CREATE TABLE IF NOT EXISTS collection_logs (
    id SERIAL PRIMARY KEY,
    script_name VARCHAR(100),
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    total_count INTEGER,
    success_count INTEGER,
    error_count INTEGER,
    error_details TEXT,
    model_used VARCHAR(100)
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_statements_politician ON statements(politician_name);
CREATE INDEX IF NOT EXISTS idx_statements_date ON statements(date);
CREATE INDEX IF NOT EXISTS idx_statements_session ON statements(session_number);
CREATE INDEX IF NOT EXISTS idx_statements_house ON statements(house);
CREATE INDEX IF NOT EXISTS idx_statements_speech_id ON statements(speech_id);
CREATE INDEX IF NOT EXISTS idx_politicians_name ON politicians(name);
CREATE INDEX IF NOT EXISTS idx_politician_attributes_politician ON politician_attributes(politician_id);
CREATE INDEX IF NOT EXISTS idx_politician_attributes_category ON politician_attributes(category);
