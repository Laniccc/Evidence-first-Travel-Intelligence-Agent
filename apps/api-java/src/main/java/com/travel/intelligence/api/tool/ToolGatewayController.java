package com.travel.intelligence.api.tool;

import com.travel.intelligence.api.tool.dto.ToolCallRequest;
import com.travel.intelligence.api.tool.dto.ToolCallResult;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/tools")
public class ToolGatewayController {

    private final ToolGatewayService toolGatewayService;

    public ToolGatewayController(ToolGatewayService toolGatewayService) {
        this.toolGatewayService = toolGatewayService;
    }

    @PostMapping("/call")
    public ResponseEntity<?> call(@RequestBody ToolCallRequest request) {
        if (!toolGatewayService.isGatewayEnabled()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of("error", "tool_gateway_disabled"));
        }
        if (request.toolName() == null || request.toolName().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "tool_name_required"));
        }
        ToolCallResult result = toolGatewayService.call(request);
        if (!result.ok()) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(result);
        }
        return ResponseEntity.ok(result);
    }
}
