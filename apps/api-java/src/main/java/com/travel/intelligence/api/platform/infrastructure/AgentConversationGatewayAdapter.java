package com.travel.intelligence.api.platform.infrastructure;

import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.agent.application.TravelQueryService;
import com.travel.intelligence.api.platform.application.AgentConversationUseCase;
import org.springframework.stereotype.Component;

@Component
public class AgentConversationGatewayAdapter implements AgentConversationUseCase {

    private final TravelQueryService travelQueryService;

    public AgentConversationGatewayAdapter(TravelQueryService travelQueryService) {
        this.travelQueryService = travelQueryService;
    }

    @Override
    public AgentQueryResult ask(AgentQueryCommand command) {
        return travelQueryService.travelQuery(command);
    }
}
