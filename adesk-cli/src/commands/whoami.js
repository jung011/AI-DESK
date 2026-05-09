import { loadEnv } from '../index.js';

export function whoamiCommand(program) {
  program
    .command('whoami')
    .description('현재 환경변수 + 백엔드 연결 검증')
    .action(async () => {
      const { agentId, apiUrl, token } = loadEnv();

      console.log(`API URL:      ${apiUrl}`);
      console.log(`Agent ID:     ${agentId || '(unset)'}`);
      console.log(`Token:        ${token ? '****** (loaded)' : '(unset — ok for dev)'}`);

      if (!agentId) {
        console.error('Error: AIDESK_AGENT_ID is not set.');
        process.exit(3);
      }

      try {
        const res = await fetch(`${apiUrl}/api/agents/${encodeURIComponent(agentId)}`);
        if (!res.ok) {
          console.error(`Backend returned HTTP ${res.status}`);
          process.exit(1);
        }
        const env = await res.json();
        if (env.result !== 0 || !env.data) {
          console.error(`Agent not found: ${env.message ?? '(no message)'}`);
          process.exit(1);
        }
        const d = env.data;
        console.log(`Agent Name:   ${d.agentName}`);
        console.log(`Tmux Session: ${d.tmuxSession}`);
        console.log(`Status:       ${d.status}`);
        console.log(`Workspace:    ${d.workspaceDir}`);
        console.log(`Model:        ${d.model}`);
        console.log(`Context:      ${d.contextPct ?? 0}%`);
        console.log(`Connectivity: ✓ OK`);
      } catch (err) {
        console.error(`Connection failed: ${err.message}`);
        process.exit(1);
      }
    });
}
