package com.jsh.aidesk.serverapi.helper.controller;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
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

/**
 * 동료가 본인 mac 에 .pkg 설치 직전 단계에서 brower 로 helper 패키지 다운로드.
 * image 안의 /app/helper/AIDeskHelper-*.pkg 를 반환한다.
 * <p>SecurityConfig 의 anyRequest().authenticated() 가 적용 — 로그인한 사용자만 다운로드.</p>
 */
@RestController
@RequestMapping("/api/helper")
public class HelperDownloadController {

    @Value("${aidesk.helper-pkg-dir:/app/helper}")
    private String helperPkgDir;

    @GetMapping("/download")
    public ResponseEntity<Resource> download() throws IOException {
        Path dir = Path.of(helperPkgDir);
        if (!Files.isDirectory(dir)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        Optional<Path> pkgOpt;
        try (Stream<Path> stream = Files.list(dir)) {
            pkgOpt = stream.filter(p -> p.getFileName().toString().endsWith(".pkg")).findFirst();
        }
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
