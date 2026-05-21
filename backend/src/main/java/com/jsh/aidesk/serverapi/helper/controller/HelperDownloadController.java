package com.jsh.aidesk.serverapi.helper.controller;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.jsh.aidesk.serverapi.common.response.ResponseJson;

/**
 * 동료가 본인 mac 에 .pkg 설치 직전 단계에서 brower 로 helper 패키지 다운로드.
 * image 안의 /app/helper/AIDeskHelper-*.pkg 를 반환한다.
 * <p>SecurityConfig 의 anyRequest().authenticated() 가 적용 — 로그인한 사용자만 다운로드.</p>
 */
@RestController
@RequestMapping("/api/helper")
public class HelperDownloadController {

    /** AIDeskHelper-X.Y.Z-arm64.pkg 또는 AIDeskHelper-X.Y.Z.pkg 에서 X.Y.Z 추출. */
    private static final Pattern VERSION_RE = Pattern.compile("AIDeskHelper-([0-9]+(?:\\.[0-9]+)+)");

    @Value("${aidesk.helper-pkg-dir:/app/helper}")
    private String helperPkgDir;

    /**
     * image 안 baked .pkg 의 최신 버전 + 파일명 반환.
     * frontend 가 helper /api/health 의 version 과 비교해 업데이트 권유.
     */
    @GetMapping("/version")
    public ResponseJson<Map<String, String>> version() throws IOException {
        Optional<Path> pkgOpt = locatePkg();
        Map<String, String> data = new LinkedHashMap<>();
        if (pkgOpt.isEmpty()) {
            data.put("latest", "");
            data.put("filename", "");
            return ResponseJson.ok(data);
        }
        String filename = pkgOpt.get().getFileName().toString();
        Matcher m = VERSION_RE.matcher(filename);
        data.put("latest", m.find() ? m.group(1) : "");
        data.put("filename", filename);
        return ResponseJson.ok(data);
    }

    private Optional<Path> locatePkg() throws IOException {
        Path dir = Path.of(helperPkgDir);
        if (!Files.isDirectory(dir)) return Optional.empty();
        try (Stream<Path> stream = Files.list(dir)) {
            return stream.filter(p -> p.getFileName().toString().endsWith(".pkg")).findFirst();
        }
    }

    @GetMapping("/download")
    public ResponseEntity<Resource> download() throws IOException {
        Optional<Path> pkgOpt = locatePkg();
        if (pkgOpt.isEmpty()) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        Path pkg = pkgOpt.get();
        Resource res = new FileSystemResource(pkg);
        String filename = pkg.getFileName().toString();
        // 한글/공백 안전 — RFC 5987.
        String dispositionFilename = URLEncoder.encode(filename, StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"" + filename + "\"; filename*=UTF-8''" + dispositionFilename)
                .contentLength(Files.size(pkg))
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(res);
    }
}
