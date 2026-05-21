package com.jsh.aidesk.serverapi.agents.mapper;

import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.jsh.aidesk.serverapi.agents.vo.AgentVo;

@Mapper
public interface AgentMapper {

    /** 본인 user 의 에이전트만. */
    List<AgentVo> selectList(@Param("ownerAccountSn") Long ownerAccountSn,
                             @Param("status") String status);

    /** 대시보드 통계 — 본인 user 의 model<>'human' 에이전트만. */
    List<Map<String, Object>> selectStatusCounts(@Param("ownerAccountSn") Long ownerAccountSn);

    /** 본인 소유의 에이전트 단건 조회. 다른 user 의 row 면 null. */
    AgentVo selectById(@Param("agentId") String agentId,
                       @Param("ownerAccountSn") Long ownerAccountSn);

    /**
     * 시스템 콜용 — owner 격리 없이 단건 조회. 스케줄러(MessageRetryScheduler) /
     * helper / 메시지 라우팅이 sender/receiver 정체를 확인할 때 사용. caller 가 적절한
     * 경계 검증을 책임진다.
     */
    AgentVo selectByIdAnyOwner(@Param("agentId") String agentId);

    /** 시스템 콜용 — owner 격리 없이 전체 활성 에이전트. watcher 와 helper reporter 가 사용. */
    List<AgentVo> selectAllForSystem();

    /**
     * 사내 동료 조회 — 본인 외 user 들의 (me) AI 만.
     * (me) 식별 : tmux_session LIKE 'aidesk-self-%' AND deleted_at IS NULL.
     * 각 user 당 0~1 row (가입했지만 (me) 미지정이면 0 row).
     * <p>CollaboratorService 가 t_user.account_sn 기준 left join 으로 보강.
     */
    List<AgentVo> selectMeAgents(@Param("excludeAccountSn") Long excludeAccountSn);

    /** vo.ownerAccountSn 가 채워져 있어야 한다. */
    int insert(AgentVo agent);

    /** 본인 소유 에이전트만 삭제 가능. */
    int hardDelete(@Param("agentId") String agentId,
                   @Param("ownerAccountSn") Long ownerAccountSn);

    /**
     * 세션 파일 감지 스케줄러용 — 상태와 컨텍스트 사용률을 함께 갱신.
     * watcher 는 시스템 콜이라 owner 검증 없음 (모든 user 의 에이전트가 대상).
     */
    int updateStatusFromWatcher(@Param("agentId") String agentId,
                                 @Param("status") String status,
                                 @Param("contextPct") Integer contextPct);

    /**
     * tmux_session 으로 에이전트를 찾는 데 사용. helper / last-mile 시스템 콜이라
     * owner 격리 없음. caller 가 필요하면 결과의 ownerAccountSn 비교.
     */
    AgentVo selectByTmuxSession(@Param("tmuxSession") String tmuxSession);

    /**
     * workspace_dir 로 에이전트 매핑 — 액션 로그가 어느 에이전트 cwd 인지 식별.
     * helper 의 호출이라 owner 격리 없음.
     */
    AgentVo selectByWorkspaceDir(@Param("workspaceDir") String workspaceDir);

    /** (me) 워크스페이스 변경 — 본인 소유 row 만 수정. */
    int updateWorkspaceDir(@Param("agentId") String agentId,
                           @Param("workspaceDir") String workspaceDir,
                           @Param("ownerAccountSn") Long ownerAccountSn);
}
