import { loadEnv } from '../index.js';

export function replyCommand(program) {
  program
    .command('reply <messageId> [content...]')
    .description('받은 메시지에 답변 (POST /api/messages with replyToMessageId)')
    .option('--stdin', '본문을 STDIN 으로 입력 (multi-line 가능)')
    .option('--json',  '응답 envelope 을 JSON 으로 출력')
    .action(async (messageId, contentArgs, opts) => {
      const { agentId, apiUrl } = loadEnv();
      if (!agentId) {
        console.error('Error: AIDESK_AGENT_ID is not set.');
        process.exit(3);
      }

      const content = opts.stdin
        ? await readStdin()
        : (contentArgs ?? []).join(' ').trim();
      if (!content) {
        console.error('Error: 답변 본문이 비어있습니다.');
        process.exit(1);
      }

      // 1. 원본 메시지 단건 조회 → fromAgentId 가져오기
      let original;
      try {
        const res = await fetch(`${apiUrl}/api/messages/${encodeURIComponent(messageId)}`);
        if (!res.ok) {
          console.error(`원본 메시지 조회 실패: HTTP ${res.status}`);
          process.exit(1);
        }
        const env = await res.json();
        if (env.result !== 0 || !env.data) {
          console.error(`원본 메시지를 찾을 수 없음: ${env.message}`);
          process.exit(1);
        }
        original = env.data;
      } catch (err) {
        console.error(`원본 메시지 조회 실패: ${err.message}`);
        process.exit(1);
      }

      // 2. 받는 사람: 원본의 sender. 자기 자신에게 답하면 안 됨.
      if (original.toAgentId !== agentId) {
        console.error(`Error: 이 메시지는 본인(${agentId}) 수신이 아닙니다.`);
        console.error(`  원본 to_agent_id: ${original.toAgentId}`);
        process.exit(1);
      }
      const toAgentId = original.fromAgentId;

      // 3. 답장 POST
      try {
        const res = await fetch(`${apiUrl}/api/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            fromAgentId: agentId,
            toAgentId,
            content,
            replyToMessageId: messageId
          })
        });
        const env = await res.json();
        if (opts.json) {
          console.log(JSON.stringify(env, null, 2));
        }
        if (env.result === 0 && env.data) {
          if (!opts.json) {
            console.log(`✓ Replied. status=${env.data.status}  id=${env.data.messageId}`);
            if (env.data.status === 'failed') {
              console.error(`  사유: ${env.data.errorReason ?? '(unknown)'}`);
            }
          }
          process.exit(env.data.status === 'failed' ? 2 : 0);
        }
        console.error(`Reply failed: ${env.message ?? '(no message)'}`);
        process.exit(2);
      } catch (err) {
        console.error(`POST 실패: ${err.message}`);
        process.exit(1);
      }
    });
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf-8').trim();
}
