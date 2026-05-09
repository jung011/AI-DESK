// AI Desk CLI — entry point.
//
// 환경변수:
//   AIDESK_AGENT_ID  필수. 이 tmux 세션이 어떤 t_ai_agent 행에 해당하는지.
//   AIDESK_API_URL   선택. 백엔드 베이스 URL (기본 http://localhost:8081).
//   AIDESK_API_TOKEN 선택. 향후 인증 도입 시 사용 (현재는 무시).
//
// 종료 코드:
//   0 성공
//   1 일반 오류 (네트워크, 백엔드 4xx 등)
//   2 정책 위반 (백엔드 envelope.result != 0)
//   3 환경변수 미설정

import { Command } from 'commander';
import { whoamiCommand } from './commands/whoami.js';
import { replyCommand } from './commands/reply.js';

export async function run(argv) {
  const program = new Command();
  program
    .name('adesk')
    .description('AI Desk CLI — tmux 안에서 받은 메시지에 답변')
    .version('0.1.0');

  whoamiCommand(program);
  replyCommand(program);

  await program.parseAsync(argv);
}

/** 공통 환경 헬퍼. */
export function loadEnv() {
  const agentId = process.env.AIDESK_AGENT_ID;
  const apiUrl = process.env.AIDESK_API_URL || 'http://localhost:8081';
  const token = process.env.AIDESK_API_TOKEN || null;
  return { agentId, apiUrl, token };
}
