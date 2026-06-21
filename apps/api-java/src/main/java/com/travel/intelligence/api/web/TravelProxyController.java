package com.travel.intelligence.api.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.travel.intelligence.api.session.TravelQueryService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api/travel")
public class TravelProxyController {

    private final TravelQueryService travelQueryService;

    public TravelProxyController(TravelQueryService travelQueryService) {
        this.travelQueryService = travelQueryService;
    }

    @PostMapping("/query")
    public ResponseEntity<JsonNode> travelQuery(@RequestBody JsonNode requestBody) {
        try {
            return ResponseEntity.ok(travelQueryService.travelQuery(requestBody));
        } catch (ResourceAccessException ex) {
            if (isTimeout(ex)) {
                return gatewayError(HttpStatus.GATEWAY_TIMEOUT, "agent_timeout", ex);
            }
            return gatewayError(HttpStatus.BAD_GATEWAY, "agent_unavailable", ex);
        } catch (RestClientResponseException ex) {
            return ResponseEntity.status(ex.getStatusCode()).body(ex.getResponseBodyAs(JsonNode.class));
        } catch (RestClientException ex) {
            return gatewayError(HttpStatus.BAD_GATEWAY, "agent_unavailable", ex);
        }
    }

    private static boolean isTimeout(ResourceAccessException ex) {
        String message = ex.getMessage() != null ? ex.getMessage().toLowerCase() : "";
        return message.contains("timed out") || message.contains("timeout");
    }

    private static ResponseEntity<JsonNode> gatewayError(HttpStatus status, String code, Exception ex) {
        JsonNode body = JsonNodeFactory.instance.objectNode()
                .put("error", code)
                .put("message", ex.getMessage() != null ? ex.getMessage() : status.getReasonPhrase());
        return ResponseEntity.status(status).body(body);
    }
}
