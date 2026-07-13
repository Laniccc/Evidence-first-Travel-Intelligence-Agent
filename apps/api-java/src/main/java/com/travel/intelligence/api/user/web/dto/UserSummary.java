package com.travel.intelligence.api.user.web.dto;

import com.travel.intelligence.api.user.domain.UserAccount;
import com.travel.intelligence.api.user.domain.UserRole;
import java.time.Instant;

public record UserSummary(
        Long id,
        String username,
        String email,
        String displayName,
        UserRole role,
        Instant createdAt
) {
    public static UserSummary from(UserAccount account) {
        return new UserSummary(
                account.getId(),
                account.getUsername(),
                account.getEmail(),
                account.getDisplayName(),
                account.getRole(),
                account.getCreatedAt());
    }
}
