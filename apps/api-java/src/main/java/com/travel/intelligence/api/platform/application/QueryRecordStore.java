package com.travel.intelligence.api.platform.application;

import com.travel.intelligence.api.platform.domain.TravelQueryRecord;
import java.util.List;
import java.util.Optional;

public interface QueryRecordStore {

    List<TravelQueryRecord> findByConversationId(Long conversationId);

    List<TravelQueryRecord> findFavoritesByUserId(Long userId);

    Optional<TravelQueryRecord> findByIdAndConversationUserId(Long id, Long userId);

    TravelQueryRecord save(TravelQueryRecord record);
}
