package com.travel.intelligence.api.platform.application;

import com.travel.intelligence.api.platform.domain.ConversationStatus;
import com.travel.intelligence.api.platform.domain.TravelConversation;
import java.util.List;
import java.util.Optional;

public interface ConversationStore {

    List<TravelConversation> findByUserIdAndStatus(Long userId, ConversationStatus status);

    Optional<TravelConversation> findByIdAndUserId(Long id, Long userId);

    TravelConversation save(TravelConversation conversation);
}
