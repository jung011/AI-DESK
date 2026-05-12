package com.jsh.aidesk.serverapi.setting.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import org.springframework.stereotype.Service;

import com.jsh.aidesk.serverapi.setting.mapper.SettingMapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

/**
 * 런타임 변경 가능한 단일값 앱 설정.
 *
 * 현재 다루는 키:
 *   - `a2a_workspace` : 사내 동료 AI 와의 소통(kaflix-a2a/kaflix-channel) 권한이 활성화될
 *     워크스페이스 절대 경로. 미설정 시 (me) 터미널 열기는 비활성.
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class SettingService {

    public static final String KEY_A2A_WORKSPACE = "a2a_workspace";

    private final SettingMapper mapper;
    private final ClaudeJsonScopeService claudeJsonScope;

    /** A2A 워크스페이스 경로 — 없으면 빈 문자열 반환. */
    public String getA2aWorkspace() {
        String v = mapper.selectValue(KEY_A2A_WORKSPACE);
        return v == null ? "" : v;
    }

    /**
     * A2A 워크스페이스 변경. DB 저장 후 `~/.claude.json` 의 kaflix-* MCP 스코프를
     * 이동시킨다. 두 작업 모두 성공해야 커밋(트랜잭션은 아님 — claude.json 은 외부 파일).
     *
     * @return rc 0=성공, 1=빈 경로, 2=경로 미존재/파일, 3=claude.json 갱신 실패
     */
    public int setA2aWorkspace(String path) {
        if (path == null || path.isBlank()) return 1;
        Path p = Paths.get(path);
        if (!Files.isDirectory(p)) {
            log.warn("setA2aWorkspace: 디렉토리 아님 path={}", path);
            return 2;
        }
        String absolute = p.toAbsolutePath().normalize().toString();

        String old = mapper.selectValue(KEY_A2A_WORKSPACE);
        try {
            claudeJsonScope.scopeKaflixToWorkspace(old, absolute);
        } catch (IOException | RuntimeException e) {
            log.warn("setA2aWorkspace: claude.json 갱신 실패 {}", e.getMessage());
            return 3;
        }
        mapper.upsertValue(KEY_A2A_WORKSPACE, absolute);
        return 0;
    }
}
