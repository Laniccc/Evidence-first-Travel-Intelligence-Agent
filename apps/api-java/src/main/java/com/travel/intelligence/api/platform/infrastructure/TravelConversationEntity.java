package com.travel.intelligence.api.platform.infrastructure;

import com.travel.intelligence.api.platform.domain.ConversationStatus;
import com.travel.intelligence.api.user.infrastructure.UserAccountEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "travel_conversations")
public class TravelConversationEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private UserAccountEntity user;

    @Column(nullable = false, length = 120)
    private String title;

    @Column(nullable = false, unique = true, length = 80)
    private String agentSessionId = UUID.randomUUID().toString();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ConversationStatus status = ConversationStatus.ACTIVE;

    @Column(nullable = false)
    private Instant createdAt = Instant.now();

    @Column(nullable = false)
    private Instant updatedAt = Instant.now();

    protected TravelConversationEntity() {
    }

    public TravelConversationEntity(
            Long id,
            UserAccountEntity user,
            String title,
            String agentSessionId,
            ConversationStatus status,
            Instant createdAt,
            Instant updatedAt) {
        this.id = id;
        this.user = user;
        this.title = title;
        this.agentSessionId = agentSessionId != null ? agentSessionId : UUID.randomUUID().toString();
        this.status = status != null ? status : ConversationStatus.ACTIVE;
        this.createdAt = createdAt != null ? createdAt : Instant.now();
        this.updatedAt = updatedAt != null ? updatedAt : this.createdAt;
    }

    public Long getId() {
        return id;
    }

    public UserAccountEntity getUser() {
        return user;
    }

    public String getTitle() {
        return title;
    }

    public String getAgentSessionId() {
        return agentSessionId;
    }

    public ConversationStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
