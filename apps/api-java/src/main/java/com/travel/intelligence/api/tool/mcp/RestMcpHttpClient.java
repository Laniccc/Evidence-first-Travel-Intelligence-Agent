package com.travel.intelligence.api.tool.mcp;

import java.util.Map;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class RestMcpHttpClient implements McpHttpClient {

    @Override
    public McpInvokeResult invoke(
            String serverUrl, String toolName, Map<String, Object> arguments, int timeoutSeconds) {
        long started = System.nanoTime();
        if (serverUrl == null || serverUrl.isBlank()) {
            return McpInvokeResult.failure("MCP server URL missing", elapsedMs(started));
        }

        String url = serverUrl.replaceAll("/+$", "") + "/invoke";
        Map<String, Object> body = Map.of(
                "tool", toolName,
                "arguments", arguments != null ? arguments : Map.of());

        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        int timeoutMs = Math.max(1000, timeoutSeconds * 1000);
        requestFactory.setConnectTimeout(timeoutMs);
        requestFactory.setReadTimeout(timeoutMs);

        RestClient client = RestClient.builder().requestFactory(requestFactory).build();

        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> response = client.post()
                    .uri(url)
                    .body(body)
                    .retrieve()
                    .body(Map.class);

            Object data = response;
            if (response != null && response.containsKey("result")) {
                data = response.get("result");
            }
            return McpInvokeResult.success(data, elapsedMs(started));
        } catch (RestClientException ex) {
            return McpInvokeResult.failure(ex.getMessage(), elapsedMs(started));
        }
    }

    private static long elapsedMs(long startedNanos) {
        return Math.max(1L, (System.nanoTime() - startedNanos) / 1_000_000L);
    }
}
