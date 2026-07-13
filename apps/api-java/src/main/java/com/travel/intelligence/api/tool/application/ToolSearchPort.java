package com.travel.intelligence.api.tool.application;

import com.travel.intelligence.api.tool.dto.ToolCallRequest;
import com.travel.intelligence.api.tool.dto.ToolCallResult;

public interface ToolSearchPort {

    String toolName();

    boolean isConfigured();

    ToolCallResult call(ToolCallRequest request);
}
