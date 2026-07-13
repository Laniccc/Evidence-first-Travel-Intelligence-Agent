package com.travel.intelligence.api.platform.domain;

import java.time.Instant;

public class TravelQueryRecord {

    private Long id;
    private Long conversationId;
    private String queryText;
    private String answerPreview;
    private Double confidence;
    private boolean favorite;
    private String responseJson;
    private Instant createdAt = Instant.now();

    public TravelQueryRecord(
            Long conversationId,
            String queryText,
            String answerPreview,
            Double confidence,
            String responseJson) {
        this(null, conversationId, queryText, answerPreview, confidence, false, responseJson, Instant.now());
    }

    public TravelQueryRecord(
            Long id,
            Long conversationId,
            String queryText,
            String answerPreview,
            Double confidence,
            boolean favorite,
            String responseJson,
            Instant createdAt) {
        this.id = id;
        this.conversationId = conversationId;
        this.queryText = queryText;
        this.answerPreview = answerPreview;
        this.confidence = confidence;
        this.favorite = favorite;
        this.responseJson = responseJson;
        this.createdAt = createdAt != null ? createdAt : Instant.now();
    }

    public Long getId() {
        return id;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public String getQueryText() {
        return queryText;
    }

    public String getAnswerPreview() {
        return answerPreview;
    }

    public Double getConfidence() {
        return confidence;
    }

    public boolean isFavorite() {
        return favorite;
    }

    public String getResponseJson() {
        return responseJson;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setFavorite(boolean favorite) {
        this.favorite = favorite;
    }
}
