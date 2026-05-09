-- AI Desk 1단계 시드 데이터
-- 적용: docker exec -i postgres-db psql -U postgres -d aidesk < backend/src/main/resources/db/data.sql

-- =====================================================================
-- 에이전트 시드 (3종)
-- =====================================================================
INSERT INTO t_ai_agent (agent_id, agent_name, workspace_dir, tmux_session, status, task_desc, model, context_pct, started_at)
VALUES
  ('a1b2c3d4-0000-0000-0000-000000000001', '코드 리뷰 AI', '/workspace/project-alpha', 'aidesk-a1b2c3d4', 'active', '현재 project-alpha 저장소의 PR #42를 분석하고 있습니다.', 'claude-opus-4-7', 68, NOW()),
  ('b2c3d4e5-0000-0000-0000-000000000002', '문서화 AI',    '/workspace/docs-repo',     'aidesk-b2c3d4e5', 'idle',   '대기 상태입니다. 새 작업이 할당되면 즉시 시작합니다.',     'codex',           12, NOW()),
  ('c3d4e5f6-0000-0000-0000-000000000003', '테스트 AI',    '/workspace/test-suite',    'aidesk-c3d4e5f6', 'done',   '유닛 테스트 전체 통과 확인 완료. 총 142개 테스트 성공.', 'hermes',          95, NOW())
ON CONFLICT (agent_id) DO NOTHING;

-- =====================================================================
-- 메시지 시드 (코드 리뷰 ↔ 문서화 대화 4건 — 1건은 정책 거절 시연)
-- =====================================================================
INSERT INTO t_ai_message (message_id, from_agent_id, to_agent_id, content, reply_to_message_id, root_message_id, hop_count, status, error_reason, created_at, delivered_at, replied_at)
VALUES
  ('m-0001-0000-0000-0000-000000000001',
   'a1b2c3d4-0000-0000-0000-000000000001',
   'b2c3d4e5-0000-0000-0000-000000000002',
   'PR #42에서 docstring 누락된 함수가 있는지 확인해줄 수 있어?',
   NULL, NULL, 0, 'replied', NULL,
   NOW() - INTERVAL '6 minute',
   NOW() - INTERVAL '6 minute',
   NOW() - INTERVAL '5 minute'),

  ('m-0002-0000-0000-0000-000000000002',
   'b2c3d4e5-0000-0000-0000-000000000002',
   'a1b2c3d4-0000-0000-0000-000000000001',
   '응, 보고 있어. PR #42에서 누락된 docstring 부터 채울게. 우선 parse_config()와 validate_input() 두 개가 보여.',
   'm-0001-0000-0000-0000-000000000001',
   'm-0001-0000-0000-0000-000000000001',
   1, 'delivered', NULL,
   NOW() - INTERVAL '5 minute',
   NOW() - INTERVAL '5 minute',
   NULL),

  ('m-0003-0000-0000-0000-000000000003',
   'a1b2c3d4-0000-0000-0000-000000000001',
   'b2c3d4e5-0000-0000-0000-000000000002',
   '고마워. 의존성 그래프도 같이 참고해줘 — /workspace/project-alpha/deps.md 에 둘게.',
   NULL, NULL, 0, 'delivered', NULL,
   NOW() - INTERVAL '2 minute',
   NOW() - INTERVAL '2 minute',
   NULL),

  ('m-0004-0000-0000-0000-000000000004',
   'a1b2c3d4-0000-0000-0000-000000000001',
   'c3d4e5f6-0000-0000-0000-000000000003',
   '참고로 컨텍스트 60% 정도야.',
   NULL, NULL, 0, 'failed',
   '수신 AI 컨텍스트 90% 초과로 거절',
   NOW() - INTERVAL '1 minute',
   NULL, NULL)
ON CONFLICT (message_id) DO NOTHING;
