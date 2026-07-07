package com.deepresearch.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;

@ConfigurationProperties(prefix = "agent")
public record AgentProperties(
    String baseUrl,
    Duration connectTimeout,
    Duration readTimeout
) {}
