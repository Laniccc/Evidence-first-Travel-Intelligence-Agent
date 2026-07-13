package com.travel.intelligence.api.user.domain;

public record UserPrincipal(
        Long id,
        String username,
        String displayName,
        UserRole role
) {
}
