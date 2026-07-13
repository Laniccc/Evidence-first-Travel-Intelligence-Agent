package com.travel.intelligence.api.platform.infrastructure;

import com.travel.intelligence.api.platform.application.QueryRecordStore;
import com.travel.intelligence.api.platform.domain.TravelQueryRecord;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class JpaQueryRecordStore implements QueryRecordStore {

    private final TravelQueryRecordRepository records;
    private final TravelConversationRepository conversations;

    public JpaQueryRecordStore(TravelQueryRecordRepository records, TravelConversationRepository conversations) {
        this.records = records;
        this.conversations = conversations;
    }

    @Override
    public List<TravelQueryRecord> findByConversationId(Long conversationId) {
        return records.findByConversationIdOrderByCreatedAtAsc(conversationId)
                .stream()
                .map(TravelPlatformMapper::toDomain)
                .toList();
    }

    @Override
    public List<TravelQueryRecord> findFavoritesByUserId(Long userId) {
        return records.findByConversationUserIdAndFavoriteTrueOrderByCreatedAtDesc(userId)
                .stream()
                .map(TravelPlatformMapper::toDomain)
                .toList();
    }

    @Override
    public Optional<TravelQueryRecord> findByIdAndConversationUserId(Long id, Long userId) {
        return records.findByIdAndConversationUserId(id, userId).map(TravelPlatformMapper::toDomain);
    }

    @Override
    public TravelQueryRecord save(TravelQueryRecord record) {
        TravelConversationEntity conversation = conversations.getReferenceById(record.getConversationId());
        TravelQueryRecordEntity entity = TravelPlatformMapper.toEntity(record, conversation);
        return TravelPlatformMapper.toDomain(records.save(entity));
    }
}
