package com.travel.intelligence.api.agent.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServerError;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.agent.config.AgentProperties;
import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

class PythonAgentClientTest {

    private MockRestServiceServer server;
    private PythonAgentClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://agent.test");
        server = MockRestServiceServer.bindTo(builder).build();
        AgentProperties properties = new AgentProperties();
        properties.setServiceKey("service-secret");
        client = new PythonAgentClient(builder.build(), new ObjectMapper(), properties);
    }

    @Test
    void sendsTypedRequestHeadersAndMapsRagResponse() {
        server.expect(requestTo("http://agent.test/agent/query"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Trace-Id", "trace-1"))
                .andExpect(header("X-Agent-Service-Key", "service-secret"))
                .andExpect(jsonPath("$.session_id").value("session-1"))
                .andExpect(jsonPath("$.debug").value(true))
                .andExpect(jsonPath("$.user_context.party[0]").value("elderly"))
                .andRespond(withSuccess("""
                        {
                          "answer":"八点半开放",
                          "session_id":"session-1",
                          "query_id":"query-1",
                          "confidence":1.0,
                          "retrieval_reports":[{
                            "subtask_id":"sub-1",
                            "corpus_version":"corpus-1",
                            "degradation":"lexical_only",
                            "final_hits":[{"chunk_id":"e-1"}]
                          }],
                          "citation_report":{
                            "passed":true,
                            "safe_failure":false,
                            "unsupported_hard_fact_count":0,
                            "citation_precision":1.0,
                            "decisions":[{"claim_id":"c-1","status":"supported","reason":"valid"}]
                          },
                          "metrics":{"citation_precision":1.0},
                          "orchestration_summary":{"run_id":"run-1","terminal_state":"deliver","trace_id":"trace-1"}
                        }
                        """, MediaType.APPLICATION_JSON));

        AgentQueryResult result = client.query(new AgentQueryCommand(
                "故宫几点开放", "session-1", true,
                Map.<String, Object>of("party", java.util.List.of("elderly")), "trace-1"));

        server.verify();
        assertThat(result.retrievalReports()).hasSize(1);
        assertThat(result.retrievalReports().getFirst().degradation()).isEqualTo("lexical_only");
        assertThat(result.citationReport().citationPrecision()).isEqualTo(1.0);
        assertThat(result.metrics()).containsEntry("citation_precision", 1.0);
        assertThat(result.orchestrationSummary()).containsEntry("trace_id", "trace-1");
    }

    @Test
    void mapsTimeoutUnauthorizedAndServerFailuresToStableCodes() {
        server.expect(requestTo("http://agent.test/agent/query"))
                .andRespond(request -> { throw new ResourceAccessException("read timed out"); });
        assertThatThrownBy(() -> client.query(command()))
                .isInstanceOfSatisfying(ApiException.class,
                        ex -> assertThat(ex.errorCode()).isEqualTo(ApplicationErrorCode.AGENT_TIMEOUT));
        server.verify();

        setUp();
        server.expect(requestTo("http://agent.test/agent/query"))
                .andRespond(withStatus(HttpStatus.UNAUTHORIZED));
        assertThatThrownBy(() -> client.query(command()))
                .isInstanceOfSatisfying(ApiException.class,
                        ex -> assertThat(ex.errorCode()).isEqualTo(ApplicationErrorCode.AGENT_UNAUTHORIZED));
        server.verify();

        setUp();
        server.expect(requestTo("http://agent.test/agent/query"))
                .andRespond(withServerError());
        assertThatThrownBy(() -> client.query(command()))
                .isInstanceOfSatisfying(ApiException.class,
                        ex -> assertThat(ex.errorCode()).isEqualTo(ApplicationErrorCode.AGENT_ERROR));
        server.verify();
    }

    private static AgentQueryCommand command() {
        return new AgentQueryCommand("故宫", "session-1", false, Map.of(), "trace-1");
    }
}
