package com.travel.intelligence.api.platform.application;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.travel.intelligence.api.agent.application.AgentQueryCommand;
import com.travel.intelligence.api.agent.application.AgentQueryResult;
import com.travel.intelligence.api.common.ApiException;
import com.travel.intelligence.api.common.ApplicationErrorCode;
import com.travel.intelligence.api.platform.domain.ConversationStatus;
import com.travel.intelligence.api.platform.domain.TravelConversation;
import com.travel.intelligence.api.platform.domain.TravelQueryRecord;
import com.travel.intelligence.api.platform.web.dto.AskTravelAgentRequest;
import com.travel.intelligence.api.platform.web.dto.AskTravelAgentResponse;
import com.travel.intelligence.api.platform.web.dto.ConversationDetail;
import com.travel.intelligence.api.platform.web.dto.ConversationSummary;
import com.travel.intelligence.api.platform.web.dto.CreateConversationRequest;
import com.travel.intelligence.api.platform.web.dto.QueryRecordSummary;
import com.travel.intelligence.api.platform.web.dto.RenameConversationRequest;
import com.travel.intelligence.api.user.application.UserAccountStore;
import com.travel.intelligence.api.user.domain.UserPrincipal;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TravelPlatformService {

    private final UserAccountStore users;
    private final ConversationStore conversations;
    private final QueryRecordStore records;
    private final AgentConversationUseCase agentConversation;
    private final ObjectMapper objectMapper;

    public TravelPlatformService(
            UserAccountStore users,
            ConversationStore conversations,
            QueryRecordStore records,
            AgentConversationUseCase agentConversation,
            ObjectMapper objectMapper) {
        this.users = users;
        this.conversations = conversations;
        this.records = records;
        this.agentConversation = agentConversation;
        this.objectMapper = objectMapper;
    }

    public List<ConversationSummary> listConversations(UserPrincipal principal) {
        return conversations.findByUserIdAndStatus(principal.id(), ConversationStatus.ACTIVE)
                .stream()
                .map(ConversationSummary::from)
                .toList();
    }

    @Transactional
    public ConversationSummary createConversation(UserPrincipal principal, CreateConversationRequest request) {
        users.findById(principal.id()).orElseThrow(this::userNotFound);
        TravelConversation conversation = conversations.save(new TravelConversation(principal.id(), request != null ? request.title() : null));
        return ConversationSummary.from(conversation);
    }

    public ConversationDetail getConversation(UserPrincipal principal, Long conversationId) {
        TravelConversation conversation = requireConversation(principal, conversationId);
        List<QueryRecordSummary> queryRecords = records.findByConversationId(conversation.getId())
                .stream()
                .map(QueryRecordSummary::from)
                .toList();
        return new ConversationDetail(ConversationSummary.from(conversation), queryRecords);
    }

    @Transactional
    public ConversationSummary renameConversation(UserPrincipal principal, Long conversationId, RenameConversationRequest request) {
        TravelConversation conversation = requireConversation(principal, conversationId);
        conversation.rename(request.title());
        return ConversationSummary.from(conversations.save(conversation));
    }

    @Transactional
    public ConversationSummary archiveConversation(UserPrincipal principal, Long conversationId) {
        TravelConversation conversation = requireConversation(principal, conversationId);
        conversation.archive();
        return ConversationSummary.from(conversations.save(conversation));
    }

    @Transactional
    public AskTravelAgentResponse ask(UserPrincipal principal, Long conversationId, AskTravelAgentRequest request) {
        TravelConversation conversation = requireConversation(principal, conversationId);
        AgentQueryCommand command = new AgentQueryCommand(
                request.query(),
                conversation.getAgentSessionId(),
                request.debug() != null && request.debug(),
                userContext(request.userContext()));
        AgentQueryResult agentResponse = agentConversation.ask(command);
        TravelQueryRecord record = records.save(new TravelQueryRecord(
                conversation.getId(),
                request.query(),
                preview(agentResponse.answer()),
                agentResponse.confidence(),
                writeJson(agentResponse.rawResponse())));
        conversation.touch();
        conversations.save(conversation);
        return new AskTravelAgentResponse(QueryRecordSummary.from(record), agentResponse.rawResponse());
    }

    public JsonNode getRecordResponse(UserPrincipal principal, Long recordId) {
        TravelQueryRecord record = requireRecord(principal, recordId);
        try {
            return objectMapper.readTree(record.getResponseJson());
        } catch (JsonProcessingException ex) {
            throw new ApiException(ApplicationErrorCode.RECORD_CORRUPT, "Stored response cannot be parsed");
        }
    }

    @Transactional
    public QueryRecordSummary setFavorite(UserPrincipal principal, Long recordId, boolean favorite) {
        TravelQueryRecord record = requireRecord(principal, recordId);
        record.setFavorite(favorite);
        return QueryRecordSummary.from(records.save(record));
    }

    public List<QueryRecordSummary> listFavorites(UserPrincipal principal) {
        return records.findFavoritesByUserId(principal.id())
                .stream()
                .map(QueryRecordSummary::from)
                .toList();
    }

    private TravelConversation requireConversation(UserPrincipal principal, Long conversationId) {
        return conversations.findByIdAndUserId(conversationId, principal.id())
                .orElseThrow(() -> new ApiException(ApplicationErrorCode.CONVERSATION_NOT_FOUND, "Conversation not found"));
    }

    private TravelQueryRecord requireRecord(UserPrincipal principal, Long recordId) {
        return records.findByIdAndConversationUserId(recordId, principal.id())
                .orElseThrow(() -> new ApiException(ApplicationErrorCode.RECORD_NOT_FOUND, "Query record not found"));
    }

    private Map<String, Object> userContext(JsonNode userContext) {
        if (userContext == null || !userContext.isObject()) {
            return Map.of();
        }
        return objectMapper.convertValue(userContext, new TypeReference<>() {
        });
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new ApiException(ApplicationErrorCode.RECORD_WRITE_FAILED, "Could not persist agent response");
        }
    }

    private String preview(String text) {
        if (text == null || text.isBlank()) {
            return "";
        }
        String normalized = text.replaceAll("\\s+", " ").trim();
        return normalized.length() > 500 ? normalized.substring(0, 500) : normalized;
    }

    private ApiException userNotFound() {
        return new ApiException(ApplicationErrorCode.USER_NOT_FOUND, "User not found");
    }
}
