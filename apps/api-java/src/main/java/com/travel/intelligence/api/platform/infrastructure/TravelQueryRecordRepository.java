package com.travel.intelligence.api.platform.infrastructure;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TravelQueryRecordRepository extends JpaRepository<TravelQueryRecordEntity, Long> {

    List<TravelQueryRecordEntity> findByConversationIdOrderByCreatedAtAsc(Long conversationId);

    List<TravelQueryRecordEntity> findByConversationUserIdAndFavoriteTrueOrderByCreatedAtDesc(Long userId);

    Optional<TravelQueryRecordEntity> findByIdAndConversationUserId(Long id, Long userId);
}
