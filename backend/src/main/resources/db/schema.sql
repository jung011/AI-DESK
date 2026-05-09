-- AI Desk PostgreSQL 스키마
-- 적용: docker exec -i postgres-db psql -U postgres -d aidesk < backend/src/main/resources/db/schema.sql

-- =====================================================================
-- t_ai_agent — AI 에이전트
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_agent (
    agent_id        VARCHAR(36)  PRIMARY KEY,
    agent_name      VARCHAR(50)  NOT NULL,
    workspace_dir   VARCHAR(500) NOT NULL,
    tmux_session    VARCHAR(80)  NOT NULL,
    status          VARCHAR(10)  NOT NULL,
    task_desc       VARCHAR(200),
    model           VARCHAR(50)  NOT NULL,
    context_pct     INTEGER,
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

COMMENT ON TABLE  t_ai_agent IS 'AI 에이전트 인스턴스';
COMMENT ON COLUMN t_ai_agent.agent_id      IS '에이전트 UUID (PK)';
COMMENT ON COLUMN t_ai_agent.agent_name    IS 'AI 이름';
COMMENT ON COLUMN t_ai_agent.workspace_dir IS '워크스페이스 절대 경로';
COMMENT ON COLUMN t_ai_agent.tmux_session  IS 'last mile 주입용 tmux 세션명';
COMMENT ON COLUMN t_ai_agent.status        IS '상태 active / idle / done';
COMMENT ON COLUMN t_ai_agent.task_desc     IS '현재 수행 작업 설명';
COMMENT ON COLUMN t_ai_agent.model         IS '사용 모델 풀네임';
COMMENT ON COLUMN t_ai_agent.context_pct   IS '컨텍스트 사용률 0~100';
COMMENT ON COLUMN t_ai_agent.deleted_at    IS '소프트 딜리트 시각, NULL = 미삭제';

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
    created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    delivered_at         TIMESTAMPTZ,
    read_at              TIMESTAMPTZ,
    replied_at           TIMESTAMPTZ
);

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

-- =====================================================================
-- t_ai_room — 그룹 대화방 (Phase 6 그룹 대화)
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_room (
    room_id      VARCHAR(36)  PRIMARY KEY,
    room_name    VARCHAR(50)  NOT NULL,
    created_by   VARCHAR(36)  NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    archived_at  TIMESTAMPTZ
);

COMMENT ON TABLE  t_ai_room IS 'AI 그룹 대화방';
COMMENT ON COLUMN t_ai_room.created_by  IS '방을 만든 AI agent_id';
COMMENT ON COLUMN t_ai_room.archived_at IS '아카이브 시각, NULL = 활성';

CREATE INDEX IF NOT EXISTS idx_ai_room_archived
    ON t_ai_room (archived_at);

-- =====================================================================
-- t_ai_room_member — 방 멤버 (다대다)
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_room_member (
    room_id    VARCHAR(36) NOT NULL,
    agent_id   VARCHAR(36) NOT NULL,
    role       VARCHAR(20) NOT NULL DEFAULT 'member',
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (room_id, agent_id)
);

COMMENT ON COLUMN t_ai_room_member.role IS 'coordinator / member';

CREATE INDEX IF NOT EXISTS idx_ai_room_member_agent
    ON t_ai_room_member (agent_id);

-- =====================================================================
-- t_ai_room_message — 방 안에서 오간 메시지
-- =====================================================================
CREATE TABLE IF NOT EXISTS t_ai_room_message (
    message_id     VARCHAR(36)   PRIMARY KEY,
    room_id        VARCHAR(36)   NOT NULL,
    from_agent_id  VARCHAR(36)   NOT NULL,
    content        VARCHAR(1000) NOT NULL,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_room_message_room
    ON t_ai_room_message (room_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_room_message_from
    ON t_ai_room_message (from_agent_id, created_at DESC);
