package com.travel.intelligence.api.platform.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.travel.intelligence.api.infrastructure.security.CurrentUser;
import com.travel.intelligence.api.platform.application.TravelPlatformService;
import com.travel.intelligence.api.platform.web.dto.AskTravelAgentRequest;
import com.travel.intelligence.api.platform.web.dto.AskTravelAgentResponse;
import com.travel.intelligence.api.platform.web.dto.ConversationDetail;
import com.travel.intelligence.api.platform.web.dto.ConversationSummary;
import com.travel.intelligence.api.platform.web.dto.CreateConversationRequest;
import com.travel.intelligence.api.platform.web.dto.FavoriteRequest;
import com.travel.intelligence.api.platform.web.dto.QueryRecordSummary;
import com.travel.intelligence.api.platform.web.dto.RenameConversationRequest;
import com.travel.intelligence.api.user.domain.UserPrincipal;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/platform")
public class TravelPlatformController {

    private final TravelPlatformService platformService;
    private final CurrentUser currentUser;

    public TravelPlatformController(TravelPlatformService platformService, CurrentUser currentUser) {
        this.platformService = platformService;
        this.currentUser = currentUser;
    }

    @GetMapping("/conversations")
    public List<ConversationSummary> listConversations(Authentication authentication) {
        return platformService.listConversations(user(authentication));
    }

    @PostMapping("/conversations")
    public ConversationSummary createConversation(
            Authentication authentication,
            @Valid @RequestBody(required = false) CreateConversationRequest request) {
        return platformService.createConversation(user(authentication), request);
    }

    @GetMapping("/conversations/{conversationId}")
    public ConversationDetail getConversation(Authentication authentication, @PathVariable Long conversationId) {
        return platformService.getConversation(user(authentication), conversationId);
    }

    @PatchMapping("/conversations/{conversationId}")
    public ConversationSummary renameConversation(
            Authentication authentication,
            @PathVariable Long conversationId,
            @Valid @RequestBody RenameConversationRequest request) {
        return platformService.renameConversation(user(authentication), conversationId, request);
    }

    @DeleteMapping("/conversations/{conversationId}")
    public ConversationSummary archiveConversation(Authentication authentication, @PathVariable Long conversationId) {
        return platformService.archiveConversation(user(authentication), conversationId);
    }

    @PostMapping("/conversations/{conversationId}/query")
    public AskTravelAgentResponse ask(
            Authentication authentication,
            @PathVariable Long conversationId,
            @Valid @RequestBody AskTravelAgentRequest request) {
        return platformService.ask(user(authentication), conversationId, request);
    }

    @GetMapping("/records/{recordId}/response")
    public JsonNode getRecordResponse(Authentication authentication, @PathVariable Long recordId) {
        return platformService.getRecordResponse(user(authentication), recordId);
    }

    @PutMapping("/records/{recordId}/favorite")
    public QueryRecordSummary setFavorite(
            Authentication authentication,
            @PathVariable Long recordId,
            @RequestBody FavoriteRequest request) {
        return platformService.setFavorite(user(authentication), recordId, request.favorite());
    }

    @GetMapping("/favorites")
    public List<QueryRecordSummary> listFavorites(Authentication authentication) {
        return platformService.listFavorites(user(authentication));
    }

    private UserPrincipal user(Authentication authentication) {
        return currentUser.require(authentication);
    }
}
