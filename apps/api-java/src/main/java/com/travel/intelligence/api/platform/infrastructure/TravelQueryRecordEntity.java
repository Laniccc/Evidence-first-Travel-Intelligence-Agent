package com.travel.intelligence.api.platform.infrastructure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "travel_query_records")
public class TravelQueryRecordEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "conversation_id", nullable = false)
    private TravelConversationEntity conversation;

    @Column(nullable = false, length = 1000)
    private String queryText;

    @Column(length = 4000)
    private String answerPreview;

    @Column
    private Double confidence;

    @Column(nullable = false)
    private boolean favorite;

    @Lob
    @Column(nullable = false)
    private String responseJson;

    @Column(nullable = false)
    private Instant createdAt = Instant.now();

    protected TravelQueryRecordEntity() {
    }

    public TravelQueryRecordEntity(
            Long id,
            TravelConversationEntity conversation,
            String queryText,
            String answerPreview,
            Double confidence,
            boolean favorite,
            String responseJson,
            Instant createdAt) {
        this.id = id;
        this.conversation = conversation;
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

    public TravelConversationEntity getConversation() {
        return conversation;
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
}
