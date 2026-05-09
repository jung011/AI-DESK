package com.jsh.aidesk.serverapi;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class AiDeskApplication {

	public static void main(String[] args) {
		SpringApplication.run(AiDeskApplication.class, args);
	}

}
