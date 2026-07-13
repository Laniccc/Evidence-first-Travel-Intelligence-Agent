package com.travel.intelligence.api.platform.infrastructure;

import com.travel.intelligence.api.platform.domain.ConversationStatus;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TravelConversationRepository extends JpaRepository<TravelConversationEntity, Long> {

    List<TravelConversationEntity> findByUserIdAndStatusOrderByUpdatedAtDesc(Long userId, ConversationStatus status);

    Optional<TravelConversationEntity> findByIdAndUserId(Long id, Long userId);
}
