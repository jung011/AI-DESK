-- AI Desk 1단계 시드 데이터
-- 적용: docker exec -i postgres-db psql -U postgres -d aidesk < backend/src/main/resources/db/data.sql

INSERT INTO t_ai_agent (agent_id, agent_name, workspace_dir, tmux_session, status, task_desc, model, context_pct, started_at)
VALUES
  ('a1b2c3d4-0000-0000-0000-000000000001', '코드 리뷰 AI', '/workspace/project-alpha', 'aidesk-a1b2c3d4', 'active', '현재 project-alpha 저장소의 PR #42를 분석하고 있습니다.', 'claude-opus-4-7', 68, NOW()),
  ('b2c3d4e5-0000-0000-0000-000000000002', '문서화 AI',    '/workspace/docs-repo',     'aidesk-b2c3d4e5', 'idle',   '대기 상태입니다. 새 작업이 할당되면 즉시 시작합니다.',     'codex',           12, NOW()),
  ('c3d4e5f6-0000-0000-0000-000000000003', '테스트 AI',    '/workspace/test-suite',    'aidesk-c3d4e5f6', 'done',   '유닛 테스트 전체 통과 확인 완료. 총 142개 테스트 성공.', 'hermes',          95, NOW())
ON CONFLICT (agent_id) DO NOTHING;
