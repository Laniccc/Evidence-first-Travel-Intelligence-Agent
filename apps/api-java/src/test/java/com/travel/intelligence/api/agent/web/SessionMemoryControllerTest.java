package com.travel.intelligence.api.agent.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.travel.intelligence.api.agent.domain.SessionMemory;
import com.travel.intelligence.api.agent.infrastructure.InMemorySessionMemoryStore;
import com.travel.intelligence.api.infrastructure.security.JwtService;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = SessionMemoryController.class)
@AutoConfigureMockMvc(addFilters = false)
@Import(SessionMemoryControllerTest.TestConfig.class)
class SessionMemoryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private InMemorySessionMemoryStore store;

    @MockitoBean
    private com.travel.intelligence.api.agent.application.TravelQueryService unused;

    @MockitoBean
    private JwtService jwtService;

    @Test
    void getMemoryReturnsStoredSession() throws Exception {
        store.save(new SessionMemory(
                "debug-1",
                "When should I visit Kanas Lake?",
                List.of("Kanas Lake"),
                null,
                "China",
                "Q: When should I visit Kanas Lake?",
                Instant.parse("2026-06-21T00:00:00Z")));

        mockMvc.perform(get("/api/session/debug-1/memory"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.last_query").value("When should I visit Kanas Lake?"))
                .andExpect(jsonPath("$.last_places[0]").value("Kanas Lake"));
    }

    @Test
    void deleteMemoryClearsSession() throws Exception {
        store.save(new SessionMemory("debug-2", "q", List.of(), null, null, "", Instant.now()));

        mockMvc.perform(delete("/api/session/debug-2/memory"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.deleted").value(true));
    }

    static class TestConfig {
        @Bean
        InMemorySessionMemoryStore sessionMemoryStore() {
            return new InMemorySessionMemoryStore();
        }
    }
}
