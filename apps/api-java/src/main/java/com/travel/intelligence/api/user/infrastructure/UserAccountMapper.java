package com.travel.intelligence.api.user.infrastructure;

import com.travel.intelligence.api.user.domain.UserAccount;

public final class UserAccountMapper {

    private UserAccountMapper() {
    }

    public static UserAccount toDomain(UserAccountEntity entity) {
        if (entity == null) {
            return null;
        }
        return new UserAccount(
                entity.getId(),
                entity.getUsername(),
                entity.getEmail(),
                entity.getPasswordHash(),
                entity.getDisplayName(),
                entity.getRole(),
                entity.getCreatedAt());
    }

    public static UserAccountEntity toEntity(UserAccount account) {
        return new UserAccountEntity(
                account.getId(),
                account.getUsername(),
                account.getEmail(),
                account.getPasswordHash(),
                account.getDisplayName(),
                account.getRole(),
                account.getCreatedAt());
    }
}
