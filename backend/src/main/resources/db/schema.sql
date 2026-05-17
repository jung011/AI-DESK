-- AI Desk PostgreSQL 스키마
-- 적용: docker exec -i postgres-db psql -U postgres -d aidesk < backend/src/main/resources/db/schema.sql

-- =====================================================================
-- t_ai_agent — AI 에이전트
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_agent (
    agent_id          VARCHAR(36)  PRIMARY KEY,
    agent_name        VARCHAR(50)  NOT NULL,
    workspace_dir     VARCHAR(500) NOT NULL,
    tmux_session      VARCHAR(80)  NOT NULL,
    status            VARCHAR(10)  NOT NULL,
    task_desc         VARCHAR(200),
    model             VARCHAR(50)  NOT NULL,
    context_pct       INTEGER,
    bootstrap_applied BOOLEAN      NOT NULL DEFAULT FALSE,
    started_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ,
    deleted_at        TIMESTAMPTZ
);

COMMENT ON TABLE  t_ai_agent IS 'AI 에이전트 인스턴스';
COMMENT ON COLUMN t_ai_agent.agent_id          IS '에이전트 UUID (PK)';
COMMENT ON COLUMN t_ai_agent.agent_name        IS 'AI 이름';
COMMENT ON COLUMN t_ai_agent.workspace_dir     IS '워크스페이스 절대 경로';
COMMENT ON COLUMN t_ai_agent.tmux_session      IS 'last mile 주입용 tmux 세션명';
COMMENT ON COLUMN t_ai_agent.status            IS '상태 active / idle / done';
COMMENT ON COLUMN t_ai_agent.task_desc         IS '현재 수행 작업 설명';
COMMENT ON COLUMN t_ai_agent.model             IS '사용 모델 풀네임';
COMMENT ON COLUMN t_ai_agent.context_pct       IS '컨텍스트 사용률 0~100';
COMMENT ON COLUMN t_ai_agent.bootstrap_applied IS '부트스트랩 프롬프트(workrole 학습)를 이 에이전트에 한 번이라도 주입했는지. 첫 [터미널 열기] 시 주입 후 true';
COMMENT ON COLUMN t_ai_agent.deleted_at        IS '소프트 딜리트 시각, NULL = 미삭제';

CREATE INDEX IF NOT EXISTS idx_ai_agent_status
    ON t_ai_agent (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_agent_deleted
    ON t_ai_agent (deleted_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_agent_tmux_session
    ON t_ai_agent (tmux_session) WHERE deleted_at IS NULL;

-- =====================================================================
-- t_ai_message — AI 협업 메시지
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_message (
    message_id           VARCHAR(36)   PRIMARY KEY,
    from_agent_id        VARCHAR(36)   NOT NULL,
    to_agent_id          VARCHAR(36)   NOT NULL,
    content              VARCHAR(1000) NOT NULL,
    reply_to_message_id  VARCHAR(36),
    root_message_id      VARCHAR(36),
    hop_count            INTEGER       NOT NULL DEFAULT 0,
    status               VARCHAR(15)   NOT NULL,
    error_reason         VARCHAR(200),
    retry_count          INTEGER       NOT NULL DEFAULT 0,
    last_attempt_at      TIMESTAMPTZ,
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    delivered_at         TIMESTAMPTZ,
    read_at              TIMESTAMPTZ,
    replied_at           TIMESTAMPTZ
);
-- 기존 DB 호환 (이미 만들어진 테이블에 column 추가)
ALTER TABLE t_ai_message ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE t_ai_message ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;

COMMENT ON TABLE  t_ai_message IS 'AI 에이전트 간 메시지';
COMMENT ON COLUMN t_ai_message.message_id           IS '메시지 UUID (PK)';
COMMENT ON COLUMN t_ai_message.from_agent_id        IS '보낸 AI (FK → t_ai_agent)';
COMMENT ON COLUMN t_ai_message.to_agent_id          IS '받는 AI (FK → t_ai_agent)';
COMMENT ON COLUMN t_ai_message.content              IS '본문 (최대 1000자)';
COMMENT ON COLUMN t_ai_message.reply_to_message_id  IS '답장 체인 — 원본 메시지 ID';
COMMENT ON COLUMN t_ai_message.root_message_id      IS '체인 루트 메시지 (자기 자신이면 NULL)';
COMMENT ON COLUMN t_ai_message.hop_count            IS '위임 깊이 (기본 0, 답장이면 부모+1)';
COMMENT ON COLUMN t_ai_message.status               IS 'sent / delivered / replied / failed';
COMMENT ON COLUMN t_ai_message.error_reason         IS 'failed 사유';
COMMENT ON COLUMN t_ai_message.retry_count          IS 'last-mile 재시도 횟수 (0 = 초회)';
COMMENT ON COLUMN t_ai_message.last_attempt_at      IS '마지막 last-mile publish 시각 — retry scheduler 가 timeout 판정에 사용';

CREATE INDEX IF NOT EXISTS idx_ai_message_from
    ON t_ai_message (from_agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_message_to
    ON t_ai_message (to_agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_message_reply
    ON t_ai_message (reply_to_message_id);
CREATE INDEX IF NOT EXISTS idx_ai_message_status
    ON t_ai_message (status, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_message_root
    ON t_ai_message (root_message_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_message_retry
    ON t_ai_message (status, last_attempt_at) WHERE status = 'sent';

-- =====================================================================
-- t_aidesk_setting — 런타임 변경 가능한 앱 단일 설정 (key-value)
-- 첫 항목: 'a2a_workspace' — 사내 동료 AI 와의 소통(kaflix-a2a/kaflix-channel MCP)
-- 권한이 활성화되는 워크스페이스 절대 경로. NULL 이면 (me) 터미널 열기 비활성.
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_aidesk_setting (
    setting_key   VARCHAR(80)  PRIMARY KEY,
    setting_value TEXT,
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  t_aidesk_setting IS 'AI Desk 런타임 단일값 설정';
COMMENT ON COLUMN t_aidesk_setting.setting_key   IS '설정 키';
COMMENT ON COLUMN t_aidesk_setting.setting_value IS '설정값 (NULL 가능)';

-- =====================================================================
-- t_ai_action_log — AI 가 수행한 실제 mutation 액션 (Write/Edit/Bash/DB MCP 등)
-- 메시지(t_ai_message)와 결합해 "어떤 대화가 어떤 변경을 만들었나" 추적용.
-- Helper 가 PostToolUse 훅에서 POST /api/action-logs 로 기록.
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_action_log (
    log_id       VARCHAR(36)  PRIMARY KEY,
    agent_id     VARCHAR(36),
    agent_name   VARCHAR(50),
    session_id   VARCHAR(80),
    tool         VARCHAR(50)  NOT NULL,
    category     VARCHAR(20)  NOT NULL,
    target       VARCHAR(500),
    summary      VARCHAR(500),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  t_ai_action_log IS 'AI 가 수행한 mutation 액션 감사 로그';
COMMENT ON COLUMN t_ai_action_log.log_id      IS '액션 UUID (PK)';
COMMENT ON COLUMN t_ai_action_log.agent_id    IS '수행 에이전트 ID (식별 안되면 NULL)';
COMMENT ON COLUMN t_ai_action_log.agent_name  IS '비정규화 이름 (조회 성능)';
COMMENT ON COLUMN t_ai_action_log.session_id  IS 'Claude 세션 UUID';
COMMENT ON COLUMN t_ai_action_log.tool        IS 'Write / Edit / Bash / mcp__postgres__query 등';
COMMENT ON COLUMN t_ai_action_log.category    IS 'code | schema | file | command';
COMMENT ON COLUMN t_ai_action_log.target      IS '파일 경로 / 테이블 / 명령 요약';
COMMENT ON COLUMN t_ai_action_log.summary     IS '액션 요약 (사람 가독)';

CREATE INDEX IF NOT EXISTS idx_action_log_created_at
    ON t_ai_action_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_category
    ON t_ai_action_log (category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_agent
    ON t_ai_action_log (agent_id, created_at DESC);
