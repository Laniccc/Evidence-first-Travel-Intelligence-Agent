package com.travel.intelligence.api.agent.application;

public interface PythonAgentGateway {

    AgentQueryResult query(AgentQueryCommand command);
}
