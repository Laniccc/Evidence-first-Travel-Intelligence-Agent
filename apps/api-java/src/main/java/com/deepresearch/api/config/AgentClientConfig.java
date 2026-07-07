package com.deepresearch.api.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
@EnableConfigurationProperties(AgentProperties.class)
public class AgentClientConfig {

    @Bean
    public RestClient agentRestClient(AgentProperties props) {
        return RestClient.builder()
            .baseUrl(props.baseUrl())
            .build();
    }
}
