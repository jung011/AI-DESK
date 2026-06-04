package com.jsh.aidesk.serverapi.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * ObjectMapper bean 명시 등록.
 *
 * spring-boot-starter-webmvc (lightweight) 사용 시 JacksonAutoConfiguration 이
 * 어떤 조건으로 동작 안 하는 경우가 확인됨 (1.34-rc1 / rc2 부팅 실패). 의존성을
 * 늘려도 (starter-json 명시) 같은 증상이라 *명시 @Bean 으로 보장*.
 *
 * findAndAddModules() — classpath 의 모든 Jackson module (예: jackson-datatype-jsr310)
 * 자동 등록. LocalDateTime 등 java.time 직렬화도 같은 ObjectMapper 가 처리.
 */
@Configuration
public class JsonConfig {

    @Bean
    public ObjectMapper objectMapper() {
        return JsonMapper.builder()
                .findAndAddModules()
                .build();
    }
}
