package com.travel.intelligence.api.platform.application;

import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;

public interface AgentConversationUseCase {

    AgentQueryResult ask(AgentQueryCommand command);
}
