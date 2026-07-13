package com.travel.intelligence.api.platform.infrastructure;

import com.travel.intelligence.api.platform.application.ConversationStore;
import com.travel.intelligence.api.platform.domain.ConversationStatus;
import com.travel.intelligence.api.platform.domain.TravelConversation;
import com.travel.intelligence.api.user.infrastructure.UserAccountEntity;
import com.travel.intelligence.api.user.infrastructure.UserAccountRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class JpaConversationStore implements ConversationStore {

    private final TravelConversationRepository conversations;
    private final UserAccountRepository users;

    public JpaConversationStore(TravelConversationRepository conversations, UserAccountRepository users) {
        this.conversations = conversations;
        this.users = users;
    }

    @Override
    public List<TravelConversation> findByUserIdAndStatus(Long userId, ConversationStatus status) {
        return conversations.findByUserIdAndStatusOrderByUpdatedAtDesc(userId, status)
                .stream()
                .map(TravelPlatformMapper::toDomain)
                .toList();
    }

    @Override
    public Optional<TravelConversation> findByIdAndUserId(Long id, Long userId) {
        return conversations.findByIdAndUserId(id, userId).map(TravelPlatformMapper::toDomain);
    }

    @Override
    public TravelConversation save(TravelConversation conversation) {
        UserAccountEntity user = users.getReferenceById(conversation.getUserId());
        TravelConversationEntity entity = TravelPlatformMapper.toEntity(conversation, user);
        return TravelPlatformMapper.toDomain(conversations.save(entity));
    }
}
