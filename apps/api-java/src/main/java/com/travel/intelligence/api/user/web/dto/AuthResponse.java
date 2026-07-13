package com.travel.intelligence.api.user.web.dto;

import com.travel.intelligence.api.user.web.dto.UserSummary;

public record AuthResponse(
        String token,
        UserSummary user
) {
}
