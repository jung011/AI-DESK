package com.jsh.aidesk.serverapi.agents.mapper;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;

@Mapper
public interface AgentMapper {

    List<AgentVo> selectList(@Param("status") String status);

    List<Map<String, Object>> selectStatusCounts();

    AgentVo selectById(@Param("agentId") String agentId);

    int insert(AgentVo agent);

    int hardDelete(@Param("agentId") String agentId);

    /**
     * 세션 파일 감지 스케줄러용 — 상태와 컨텍스트 사용률을 함께 갱신.
     * contextPct 가 null 이면 컬럼은 변경하지 않는다 (status 만 변경).
     */
    int updateStatusFromWatcher(@Param("agentId") String agentId,
                                 @Param("status") String status,
                                 @Param("contextPct") Integer contextPct);

    /**
     * 부트스트랩 프롬프트 주입 완료 마킹 — 첫 [터미널 열기] 시 워크로드 학습 직후 호출.
     * 이후 호출에서는 부트스트랩 재주입을 건너뛴다.
     */
    int markBootstrapApplied(@Param("agentId") String agentId);

    /** tmux_session 으로 (me) 에이전트를 찾는 데 사용. 소프트 삭제는 제외. */
    AgentVo selectByTmuxSession(@Param("tmuxSession") String tmuxSession);

    /** (me) 워크스페이스 변경 시 같은 에이전트 행의 workspace_dir 만 갈아끼우기 위한 단일 업데이트. */
    int updateWorkspaceDir(@Param("agentId") String agentId,
                           @Param("workspaceDir") String workspaceDir);
}
