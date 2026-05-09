-- AI Desk PostgreSQL 스키마
-- 적용: docker exec -i postgres-db psql -U postgres -d aidesk < backend/src/main/resources/db/schema.sql

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
