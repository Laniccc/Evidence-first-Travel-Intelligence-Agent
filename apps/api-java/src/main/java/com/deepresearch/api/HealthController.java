package com.deepresearch.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    @GetMapping("/api/health")
    public java.util.Map<String, Object> health() {
        return java.util.Map.of(
            "status", "ok",
            "service", "deep-research-api",
            "version", "0.1.0"
        );
    }
}
