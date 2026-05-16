package com.jsh.aidesk.serverapi.logs.service;

import java.util.regex.Pattern;

/**
 * 메시지 본문 패턴 매칭으로 카테고리 추론 (A 접근). 정확도 100% 는 아니고 휴리스틱.
 *
 * 우선순위: schema > code > file > discussion
 *   - schema 가 가장 구체적 (SQL DDL 키워드, 테이블명 패턴) 이라 먼저 매칭
 *   - code 는 코드블록 / 파일 확장자 / 키워드
 *   - file 은 변경 동사 + 파일경로 패턴
 *   - 위에 안 잡히면 discussion (일반 잡담)
 */
public final class MessageClassifier {

    private MessageClassifier() {}

    private static final Pattern SCHEMA = Pattern.compile(
            "(?i)\\b(CREATE\\s+TABLE|ALTER\\s+TABLE|DROP\\s+TABLE|ALTER\\s+COLUMN|"
            + "CREATE\\s+INDEX|DROP\\s+INDEX|INSERT\\s+INTO|UPDATE\\s+\\w+\\s+SET|"
            + "DELETE\\s+FROM|CREATE\\s+SCHEMA)\\b"
            + "|\\b[Tt]_[A-Za-z_]{2,}\\b"  // t_xxx / T_XXX 테이블 명명
    );

    private static final Pattern CODE = Pattern.compile(
            "```"  // 코드블록 펜스
            + "|\\.(java|kt|py|vue|ts|tsx|js|jsx|html|css|scss|go|rs|swift|cpp|c|h|rb|php|sql|sh|cjs|mjs)\\b"
            + "|\\b(function|class|method|컴포넌트|모듈|interface|public\\s+\\w+\\s*\\(|def\\s+\\w+|async\\s+function)\\b"
    );

    private static final Pattern FILE_OP = Pattern.compile(
            "(?i)(수정|생성|삭제|만들었|추가했|제거했|"
            + "added|removed|deleted|modified|created|wrote|saved)"
            + ".*?[/\\\\][A-Za-z0-9._-]+"  // 변경 동사 근처에 path-like 가 있어야
    );

    public static String classify(String content) {
        if (content == null || content.isBlank()) return "discussion";
        if (SCHEMA.matcher(content).find()) return "schema";
        if (CODE.matcher(content).find()) return "code";
        if (FILE_OP.matcher(content).find()) return "file";
        return "discussion";
    }
}
