package com.travel.intelligence.api.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.travel.intelligence.api.session.InMemorySessionMemoryStore;
import com.travel.intelligence.api.session.SessionMemory;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers = SessionMemoryController.class)
@Import(SessionMemoryControllerTest.TestConfig.class)
class SessionMemoryControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private InMemorySessionMemoryStore store;

    @MockitoBean
    private com.travel.intelligence.api.session.TravelQueryService unused;

    @Test
    void getMemoryReturnsStoredSession() throws Exception {
        store.save(new SessionMemory(
                "debug-1",
                "喀纳斯湖适合几月份去",
                List.of("喀纳斯湖"),
                null,
                "China",
                "Q: 喀纳斯湖适合几月份去",
                Instant.parse("2026-06-21T00:00:00Z")));

        mockMvc.perform(get("/api/session/debug-1/memory"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.last_query").value("喀纳斯湖适合几月份去"))
                .andExpect(jsonPath("$.last_places[0]").value("喀纳斯湖"));
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
